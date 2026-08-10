"""Publicador Ekipon — crea un producto en la tienda de PRUEBAS como borrador.

Uso:  python publicador.py <ruta_ficha.json> [--simular] [--actualizar]
                                             [--refrescar-galeria]

Pipeline:
1. Valida la ficha contra el contrato v1.4 (mismo inspector que validar_ficha).
2. Extrae el codigo de proveedor y arma el slug <codigo>-<nombre>.
3. Verifica que el producto no exista ya (libreta local + tienda) — nunca duplica.
4. Resuelve la categoria contra el arbol EN VIVO de la tienda.
5. Sube las imagenes de la galeria con su texto alt.
6. Crea el producto SIEMPRE como borrador (el cliente lo fuerza ademas).

Con --simular no se toca la red en absoluto: solo valida, arma el payload
completo y lo muestra para revision humana.

Con --actualizar, si el producto ya existe COMO BORRADOR se actualiza su
texto (nombre, precio, categoria, etiquetas, descripciones y metadatos).
Las imagenes NO se tocan en una actualizacion: solo se suben al crear.
Un producto publicado nunca se modifica (lo verifica el cliente).

Con --refrescar-galeria (junto a --actualizar) SI se vuelve a subir la
galeria y se manda en la actualizacion, REEMPLAZANDO la que hay en la tienda.
Es opt-in y ruidoso a proposito: sin la bandera, una actualizacion jamas puede
borrar una galeria viva. Y si la ficha no trae NINGUNA imagen preparada, la
corrida se detiene: "no hay nada que subir" no puede significar "borra todo".

Codigos de salida: 0 = creado o ya existia (o simulacro OK); 1 = error de
ficha, categoria o tienda, o refresco de galeria sin imagenes; 2 = problema
con el archivo (via cargar_json).
"""

import argparse
import difflib
import html
import json
import sys
import tempfile
import unicodedata
from pathlib import Path

from pydantic import ValidationError

import generador_banner
import registro
from cliente_tienda import ClienteTienda, ErrorTienda
from esquema_ficha import FichaEkipon
from texto_publico import limpiar_valor_publico
from validar_ficha import cargar_json, describir_error, imprimir_lista

# Plantillas Elementor guardadas en la tienda de pruebas. La plantilla del
# producto ya arma la descripcion completa (tabla de ficha tecnica + banner +
# caracteristicas + video) de forma dinamica, leyendo los meta_data ekipon_*.
# Por eso el publicador deja el campo 'description' vacio: los meta_data ekipon_*
# viajan intactos y son la unica fuente que la plantilla renderiza.
PLANTILLA_FICHA_TECNICA = 50198
PLANTILLA_CARACTERISTICAS_VIDEO = 50201

# WordPress guarda el slug en post_name (VARCHAR 200); 180 deja margen para
# el sufijo -N que WordPress agrega si el slug ya existe.
LONGITUD_MAX_SLUG = 180


# ----------------------------------------------------------------------
# Funciones puras (sin red, sin disco): faciles de probar.
# ----------------------------------------------------------------------

def generar_slug(codigo: str, nombre: str) -> str:
    """Arma el slug <codigo>-<nombre> en minusculas, sin acentos ni simbolos.

    Lanza ValueError si el resultado queda vacio (codigo y nombre sin ninguna
    letra ni numero): un slug vacio produciria una URL invalida en la tienda.
    """
    crudo = f"{codigo} {nombre}".lower()
    # NFKD separa letra y acento; al codificar a ASCII el acento se descarta
    # (á→a, ñ→n, – y — desaparecen).
    plano = unicodedata.normalize("NFKD", crudo).encode("ascii", "ignore").decode()
    partes = "".join(c if c.isalnum() else " " for c in plano).split()
    slug = "-".join(partes)[:LONGITUD_MAX_SLUG].rstrip("-")
    if not slug:
        raise ValueError(
            f"no se pudo generar un slug a partir de codigo='{codigo}' y "
            f"nombre='{nombre}': no contienen letras ni numeros."
        )
    return slug


def ruta_relativa_segura(url: str) -> bool:
    """Indica si una url de imagen es una ruta relativa segura, dentro de la
    carpeta del caso. Rechaza URLs, rutas absolutas y saltos hacia arriba (..)
    que permitirian leer y subir archivos fuera de la ficha."""
    if not isinstance(url, str) or not url:
        return False
    if url.startswith(("http://", "https://", "/", "\\")) or ":" in url[:3]:
        return False
    return ".." not in url.replace("\\", "/").split("/")


def precio_a_texto(precio) -> str:
    """Precio de la ficha como texto para WooCommerce. Un precio pendiente
    (null) va como cadena vacia, NUNCA como el texto literal 'None'."""
    return "" if precio is None else str(precio)


def extraer_codigo_proveedor(datos: dict) -> str | None:
    """Codigo del proveedor tal como lo entrego Angie (entrada_original)."""
    entrada = datos.get("entrada_original")
    if not isinstance(entrada, dict):
        return None
    codigo = entrada.get("codigo_proveedor")
    if isinstance(codigo, str) and codigo.strip():
        return codigo.strip()
    return None


def texto_alt_imagen(alt_base: str | None, nota: str | None) -> str:
    """Texto alt de una imagen: base SEO + nota propia de la toma."""
    partes = [p.strip() for p in (alt_base, nota) if p and p.strip()]
    return " — ".join(partes)


def resolver_categoria(categorias: list, nombre_buscado: str):
    """Busca la categoria por nombre exacto (sin distinguir mayusculas).

    Devuelve (categoria, sugerencias): si hay coincidencia, sugerencias queda
    vacia; si no, trae los nombres mas parecidos para orientar la correccion.
    """
    objetivo = nombre_buscado.strip().casefold()
    for categoria in categorias:
        if str(categoria.get("name", "")).strip().casefold() == objetivo:
            return categoria, []
    nombres = [str(c.get("name", "")) for c in categorias]
    sugerencias = difflib.get_close_matches(nombre_buscado, nombres, n=5, cutoff=0.4)
    return None, sugerencias


def _es_clave_publica(clave: str) -> bool:
    """Filtra claves de la ficha tecnica que NO deben mostrarse al publico.

    Quedan fuera los metadatos internos (empiezan con '_') y las claves que
    la propia ficha marca como no publicas (ej. "MARCA FISICA (no publica)"
    — regla fija del negocio: sin marcas).
    """
    if clave.startswith("_"):
        return False
    plano = unicodedata.normalize("NFKD", clave).encode("ascii", "ignore").decode()
    return "no publica" not in plano.casefold()


def ficha_tecnica_publica(datos: dict) -> dict:
    """Version apta para publico de la ficha tecnica: sin claves internas ni
    no publicas, y con los valores limpios de marcas de origen. Alimenta los
    meta_data ekipon_* que la plantilla Elementor renderiza — asi ningun
    consumidor puede filtrar cocina interna."""
    ficha_tecnica = datos.get("ficha_tecnica") or {}
    return {
        str(clave): limpiar_valor_publico(str(valor))
        for clave, valor in ficha_tecnica.items()
        if _es_clave_publica(str(clave))
    }


def generar_descripcion_html(datos: dict, banner: dict | None = None) -> str:
    """Arma el HTML de la descripcion: ficha tecnica + banner (2 columnas) +
    caracteristicas, con estilos EN LINEA.

    Va en el campo 'description' de WooCommerce, que el tema renderiza en la
    pestana Descripcion SIN depender de Elementor, ningun shortcode ni snippet.
    Asi cada producto sale completo solo: la duenia solo revisa y publica. Los
    estilos son inline a proposito: no dependen de que ningun CSS externo cargue.
    """
    producto = datos.get("producto") or {}
    titulo = str(producto.get("nombre_propuesto") or "").strip()
    filas = ficha_tecnica_publica(datos)
    caracteristicas = [c.strip() for c in (datos.get("caracteristicas") or [])
                       if isinstance(c, str) and c.strip()]
    video_url = (datos.get("multimedia") or {}).get("video_youtube") or ""

    # Ficha tecnica (columna izquierda, arriba).
    tabla = ""
    if filas:
        cuerpo = ""
        for clave, valor in filas.items():
            cuerpo += (
                '<tr><th style="text-align:left;padding:8px 12px;border-bottom:'
                '1px solid rgba(0,0,0,.08);width:40%;white-space:nowrap;'
                'vertical-align:top">' + html.escape(str(clave)) + '</th>'
                '<td style="padding:8px 12px;border-bottom:1px solid '
                'rgba(0,0,0,.08);vertical-align:top">'
                + html.escape(str(valor)) + '</td></tr>'
            )
        tabla = ('<table style="width:100%;border-collapse:collapse">'
                 '<tbody>' + cuerpo + '</tbody></table>')

    # Video (columna izquierda, debajo de la ficha).
    video = ""
    if isinstance(video_url, str) and video_url.strip():
        video = ('<p style="margin-top:16px"><a href="'
                 + html.escape(video_url.strip(), quote=True)
                 + '" target="_blank" rel="noopener noreferrer">'
                 'Ver video del producto</a></p>')

    # Banner (columna derecha, arriba).
    img = ""
    if banner and banner.get("url"):
        img = ('<img src="' + html.escape(str(banner["url"]), quote=True)
               + '" alt="' + html.escape(titulo, quote=True)
               + '" style="max-width:100%;height:auto;display:block" />')

    # Caracteristicas (columna derecha, debajo del banner).
    lista = ""
    if caracteristicas:
        items = "".join('<li style="margin:.25em 0">' + html.escape(c) + '</li>'
                        for c in caracteristicas)
        encabezado = ""
        if titulo:
            encabezado = ('<h3 style="color:#ff4e03;font-weight:700;'
                          'margin:0 0 .5em;font-size:1.2em;line-height:1.25">'
                          + html.escape(titulo) + '</h3>')
        lista = ('<div style="margin-top:16px">' + encabezado
                 + '<ul style="margin:0;padding-left:1.2em">' + items
                 + '</ul></div>')

    # Layout 2x2: izquierda = ficha + video; derecha = banner + caracteristicas.
    izquierda = tabla + video
    derecha = img + lista
    if not (izquierda or derecha):
        return ""
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start">'
        '<div style="flex:1 1 320px;min-width:280px">' + izquierda + '</div>'
        '<div style="flex:1 1 320px;min-width:280px">' + derecha + '</div>'
        '</div>'
    )


def construir_payload(datos: dict, codigo: str, slug: str, categoria_id,
                      imagenes: list, banner: dict | None = None) -> dict:
    """Arma el payload de creacion del producto WooCommerce.

    Es una funcion pura: recibe la ficha (dict crudo), el id de categoria ya
    resuelto, la lista de imagenes [{"id", "alt"}] ya subidas (o marcadores en
    un simulacro) y el banner opcional ({"id", "url", "alt"}). No define sku:
    lo asigna WooCommerce (regla fija). Los metadatos van con prefijo ekipon_
    para alimentar las plantillas dinamicas de Elementor.
    """
    producto = datos["producto"]
    meta_data = [
        {"key": "ekipon_codigo_proveedor", "value": codigo},
        {"key": "ekipon_ficha_version", "value": datos.get("_version_ficha") or ""},
        {"key": "ekipon_ficha_tecnica",
         "value": json.dumps(ficha_tecnica_publica(datos), ensure_ascii=False)},
        {"key": "ekipon_caracteristicas",
         "value": json.dumps(datos.get("caracteristicas") or [], ensure_ascii=False)},
        {"key": "ekipon_garantia", "value": producto["garantia"]},
    ]
    video = (datos.get("multimedia") or {}).get("video_youtube")
    if isinstance(video, str) and video.strip():
        meta_data.append({"key": "ekipon_video_url", "value": video.strip()})
    # El banner viaja tambien como meta: es el dato que la plantilla Elementor
    # va a leer (widget Imagen dinamico) para mostrarlo por producto.
    if banner and banner.get("url"):
        meta_data.append({"key": "ekipon_banner_id", "value": banner.get("id") or ""})
        meta_data.append({"key": "ekipon_banner_url", "value": banner["url"]})

    return {
        "name": producto["nombre_propuesto"],
        "slug": slug,
        "type": "simple",
        # El cliente fuerza 'draft' de todos modos; aqui queda explicito.
        "status": "draft",
        "regular_price": precio_a_texto(datos["precios"]["precio"]),
        "categories": [{"id": categoria_id}],
        "tags": [{"name": e} for e in (producto.get("etiquetas_propuestas") or [])],
        "short_description": limpiar_valor_publico(
            datos.get("descripcion_principal") or ""
        ),
        # La descripcion lleva la ficha tecnica + banner + caracteristicas como
        # HTML nativo (estilos inline): WooCommerce la renderiza en la pestaña
        # Descripcion sin depender de Elementor. Asi el producto sale completo
        # solo, sin armar nada a mano.
        "description": generar_descripcion_html(datos, banner),
        "images": [{"id": img["id"], "alt": img["alt"]} for img in imagenes],
        "meta_data": meta_data,
    }


def construir_payload_actualizacion(datos: dict, codigo: str,
                                    categoria_id, banner: dict | None = None,
                                    imagenes: list | None = None) -> dict:
    """Arma el payload de ACTUALIZACION: solo los campos textuales.

    Regla fija por defecto: las imagenes solo se suben al crear; una
    actualizacion nunca las toca (el payload NI SIQUIERA lleva la clave
    'images', para que la tienda no borre la galeria existente). Tampoco lleva
    slug ni type: eso quedo fijado al crear el producto. El banner (si se pasa)
    si viaja: es texto/meta, no toca la galeria.

    'imagenes' es la unica excepcion, y hay que pedirla a mano
    (--refrescar-galeria): si llega una lista, el payload lleva 'images' y la
    galeria de la tienda queda REEMPLAZADA por ella. None (el defecto) es
    exactamente el comportamiento de siempre.

    OJO: una lista VACIA no es None. Mandaria 'images': [] y la tienda borraria
    la galeria. Quien llame con --refrescar-galeria corta antes con
    `sin_galeria_para_refrescar`; aqui no se adivina la intencion.
    """
    completo = construir_payload(datos, codigo, slug="", categoria_id=categoria_id,
                                 imagenes=imagenes or [], banner=banner)
    campos_textuales = (
        "name", "regular_price", "categories", "tags",
        "short_description", "description", "meta_data",
    )
    payload = {campo: completo[campo] for campo in campos_textuales}
    if imagenes is not None:
        payload["images"] = completo["images"]
    return payload


def imagenes_de_la_ficha(datos: dict) -> list[dict]:
    """Lista de imagenes confirmadas de la galeria, en el orden de la ficha."""
    multimedia = datos.get("multimedia") or {}
    return list(multimedia.get("imagenes_galeria_confirmadas") or [])


# ----------------------------------------------------------------------
# Pasos del pipeline.
# ----------------------------------------------------------------------

def cargar_ficha_validada(ruta: Path) -> dict:
    """Carga y valida la ficha; con errores imprime el reporte y termina (1)."""
    datos = cargar_json(ruta)  # termina con codigo 2 si el archivo falla
    try:
        FichaEkipon.model_validate(datos)
    except ValidationError as fallo:
        errores = [describir_error(error) for error in fallo.errors()]
        imprimir_lista(f"FICHA INVALIDA — {len(errores)} error(es):", errores)
        print("\nNo se publica una ficha invalida. Corregir y reintentar.")
        sys.exit(1)
    print("Ficha valida — cumple el contrato y las reglas fijas del negocio.")
    return datos


def preparar_imagenes(datos: dict, carpeta_ficha: Path) -> list[dict]:
    """Resuelve rutas y textos alt de la galeria; exige que existan en disco.

    Devuelve [{"ruta": Path, "alt": str, "titulo": str, "slug_medio": str}]
    en orden de ficha. El slug_medio hace idempotente la subida: si una imagen
    ya se subio (por un reintento tras un fallo), se reutiliza en vez de crear
    un duplicado en la mediateca.
    """
    alt_base = (datos.get("seo") or {}).get("texto_alt_base")
    codigo = extraer_codigo_proveedor(datos) or "sin-codigo"
    preparadas = []
    faltantes = []
    inseguras = []
    for imagen in imagenes_de_la_ficha(datos):
        url = imagen["url"]
        if not ruta_relativa_segura(url):
            # Barrera de seguridad: una url con '..' o absoluta podria leer y
            # subir archivos fuera de la carpeta del caso (p. ej. el .env).
            inseguras.append(url)
            continue
        ruta = carpeta_ficha / url
        if not ruta.is_file():
            faltantes.append(url)
            continue
        preparadas.append({
            "ruta": ruta,
            "alt": texto_alt_imagen(alt_base, imagen.get("nota")),
            # El titulo lleva el CODIGO adelante: subir_imagen deduplica por
            # titulo, y el motor nombra las piezas generadas igual para todos
            # (01-producto_limpio.webp). Sin el prefijo, la portada de un
            # producto reutilizaba la de otro ya subido (bug del taladro 50268:
            # tomo la portada de la picadora). Con el codigo el titulo es unico
            # por producto, como ya lo era el slug_medio.
            "titulo": f"{codigo}-{ruta.stem}",
            "slug_medio": generar_slug(codigo, ruta.stem),
        })
    if inseguras:
        imprimir_lista(
            f"IMAGENES CON RUTA NO PERMITIDA — {len(inseguras)} (solo se aceptan "
            "rutas relativas dentro de la carpeta del caso):",
            inseguras,
        )
        sys.exit(1)
    if faltantes:
        imprimir_lista(
            f"IMAGENES FALTANTES — {len(faltantes)} archivo(s) no encontrados "
            f"(relativos a {carpeta_ficha}):",
            faltantes,
        )
        sys.exit(1)
    return preparadas


def subir_galeria(preparadas: list[dict], cliente) -> list[dict]:
    """Sube las imagenes ya preparadas y devuelve [{"id", "alt"}] en su orden.

    La subida es idempotente por slug_medio: reintentar tras un fallo reutiliza
    la imagen ya subida en vez de duplicarla en la mediateca.
    """
    subidas = []
    for numero, imagen in enumerate(preparadas, start=1):
        print(f"Subiendo imagen {numero}/{len(preparadas)}: {imagen['ruta'].name}...")
        medio = cliente.subir_imagen(
            imagen["ruta"], imagen["alt"], imagen["titulo"], imagen["slug_medio"]
        )
        subidas.append({"id": medio["id"], "alt": imagen["alt"]})
    return subidas


def anunciar_reemplazo_de_galeria(preparadas: list[dict]) -> None:
    """Aviso a viva voz antes de pisar una galeria que ya esta en la tienda.

    Se imprime siempre que se pide --refrescar-galeria, tambien en simulacro:
    reemplazar la galeria de un producto vivo no puede pasar en silencio.
    """
    print("\n" + "!" * 62)
    print("REFRESCAR GALERIA — la galeria que hay en la tienda sera REEMPLAZADA")
    print(f"por estas {len(preparadas)} imagenes, en este orden:")
    for numero, imagen in enumerate(preparadas, start=1):
        print(f"  {numero:>2}. {imagen['ruta'].name}  (alt: {imagen['alt']})")
    print("Las imagenes que hoy tenga el producto y no esten en esta lista")
    print("dejan de estar asociadas a el.")
    print("!" * 62)


def sin_galeria_para_refrescar(preparadas: list[dict]) -> bool:
    """True (con el motivo ya impreso) si se pidio refrescar la galeria y no
    hay ni una sola imagen preparada.

    "No hay nada que subir" y "borra todo" no pueden ser la misma orden. Un PUT
    con `images: []` deja al producto SIN galeria en la tienda, y esa lista
    vacia se produce sola: una ficha valida puede tener todos sus slots sin
    archivo, o con origen sin firmar, y `imagenes_confirmadas_del_plan` devuelve
    []. Por eso el corte va aqui: antes de subir nada y antes de armar payload.
    """
    if preparadas:
        return False
    print("\n" + "!" * 62)
    print("REFRESCAR GALERIA CANCELADO — no hay ninguna imagen preparada")
    print("La ficha no trae imagenes en multimedia.imagenes_galeria_confirmadas,")
    print("asi que NO HAY NADA QUE SUBIR. Por eso la galeria que el producto ya")
    print("tiene en la tienda NO se toca: mandar una galeria vacia la borraria.")
    print("Que hacer: producir la galeria (motor_galeria.py) y reintentar, o")
    print("actualizar solo el texto quitando --refrescar-galeria.")
    print("!" * 62)
    return True


def buscar_existente(cliente, codigo: str, slug: str, ruta_db) -> dict | None:
    """Idempotencia: devuelve el producto si ya existe, o None.

    Revisa primero la libreta local (y confirma contra la tienda que el
    producto siga existiendo) y luego busca el slug en la tienda.
    """
    anotado = registro.obtener_publicacion(codigo, ruta_db)
    if anotado and anotado.get("product_id"):
        try:
            producto = cliente.obtener(
                f"/wp-json/wc/v3/products/{anotado['product_id']}"
            )
            if producto and producto.get("id"):
                return producto
        except ErrorTienda as error:
            if error.codigo_http != 404:
                raise
            print(
                f"Aviso: la libreta anotaba el producto {anotado['product_id']}, "
                "pero ya no existe en la tienda. Se continua."
            )
    encontrados = cliente.obtener(f"/wp-json/wc/v3/products?slug={slug}&status=any")
    if isinstance(encontrados, list) and encontrados:
        return encontrados[0]
    return None


def simular_publicacion(datos: dict, codigo: str, slug: str,
                        carpeta_ficha: Path,
                        refrescar_galeria: bool = False) -> int:
    """Muestra todo lo que SE HARIA, sin tocar la red en absoluto."""
    print("\n" + "=" * 62)
    print("SIMULACRO — no se envio nada (cero conexiones de red)")
    print("=" * 62)
    print(f"Codigo proveedor: {codigo}")
    print(f"Slug: {slug}")
    categoria = (datos.get("producto") or {}).get("categoria_propuesta")
    print(f"Categoria propuesta: {categoria} (se resolveria en vivo contra la tienda)")

    imagenes = preparar_imagenes(datos, carpeta_ficha)
    print(f"\nImagenes de la galeria ({len(imagenes)}):")
    for imagen in imagenes:
        print(f"  se subiria: {imagen['ruta'].name} (alt: {imagen['alt']})")

    marcadores = [
        {"id": f"(pendiente {n}: se asigna al subir)", "alt": imagen["alt"]}
        for n, imagen in enumerate(imagenes, start=1)
    ]
    # Banner: en simulacro no se genera ni sube; solo se marca si hay recorte.
    hay_recorte = (carpeta_ficha / f"{codigo}_recorte.png").is_file()
    banner = {"id": "(pendiente)", "url": "(banner: se generaria y subiria)",
              "alt": ""} if hay_recorte else None
    print(f"\nBanner: {'se generaria desde ' + codigo + '_recorte.png' if hay_recorte else 'sin recorte, no se genera'}")
    payload = construir_payload(
        datos, codigo, slug,
        categoria_id=f"(pendiente: id en vivo de '{categoria}')",
        imagenes=marcadores, banner=banner,
    )

    # Resumen en palabras simples (para revision humana, no tecnica).
    precio = payload["regular_price"] or "PENDIENTE (Angie lo define)"
    print("\nResumen del producto que se crearia (como BORRADOR):")
    print(f"  Nombre:     {payload['name']}")
    print(f"  Precio:     {precio} COP")
    print(f"  Categoria:  {categoria}")
    print(f"  Etiquetas:  {len(payload['tags'])}")
    print(f"  Imagenes:   {len(marcadores)}")
    print(f"  Banner:     {'si' if hay_recorte else 'no (falta recorte)'}")

    # Detalle tecnico completo, por si se quiere revisar a fondo.
    print("\nDetalle tecnico (payload que se enviaria a WooCommerce):")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if refrescar_galeria:
        # Ensayo del camino que pisa una galeria viva: se muestra el aviso y el
        # payload de actualizacion completo, para poder mirarlo antes de correrlo
        # de verdad. Sin imagenes el ensayo tambien se detiene: el simulacro
        # tiene que mostrar el mismo corte que haria la corrida real.
        if sin_galeria_para_refrescar(imagenes):
            return 1
        anunciar_reemplazo_de_galeria(imagenes)
        payload_actualizacion = construir_payload_actualizacion(
            datos, codigo,
            categoria_id=f"(pendiente: id en vivo de '{categoria}')",
            banner=banner, imagenes=marcadores,
        )
        print("\nDetalle tecnico (payload de ACTUALIZACION con galeria refrescada):")
        print(json.dumps(payload_actualizacion, indent=2, ensure_ascii=False))

    print("\nSIMULACRO terminado. Nada se creo ni se subio.")
    return 0


def resolver_categoria_en_vivo(cliente, datos: dict,
                               resultado: dict | None = None) -> dict | None:
    """Lee el arbol de categorias de la tienda y resuelve la propuesta.

    Devuelve la categoria, o None (con el error ya impreso) si no existe.

    `resultado`, si se pasa, es un dict de salida (mutado in-place) donde se
    anota 'categoria_buscada' y 'categoria_sugerencias' cuando NO hay match.
    Es aditivo a proposito (parametro opcional, default None, nada cambia
    para quien no lo pasa — CLI y tests existentes intactos): lo usa
    orquestador.py para distinguir el CHECKPOINT 2 (categoria sin match) de
    cualquier otro motivo por el que publicar() devuelva 1, algo que el
    codigo original no exponia de forma programatica (solo imprimia a
    stdout). Ver mismatch documentado en el reporte final del orquestador.
    """
    print("Leyendo el arbol de categorias en vivo...")
    categorias = cliente.obtener_paginado(
        "/wp-json/wc/v3/products/categories?orderby=name"
    )
    nombre_categoria = (datos.get("producto") or {}).get("categoria_propuesta") or ""
    categoria, sugerencias = resolver_categoria(categorias, nombre_categoria)
    if categoria is None:
        print(
            f"\nERROR: la categoria propuesta '{nombre_categoria}' no existe "
            "en la tienda."
        )
        if sugerencias:
            imprimir_lista("Nombres mas parecidas en la tienda:", sugerencias)
        if resultado is not None:
            resultado["categoria_buscada"] = nombre_categoria
            resultado["categoria_sugerencias"] = sugerencias
        return None
    print(f"Categoria resuelta: {categoria['name']} (id {categoria['id']})")
    return categoria


def _adjuntar_video(cliente, product_id: int, ruta_video: Path, codigo: str) -> dict:
    """Sube el video del producto y lo asocia via meta_data
    (ekipon_video_id/ekipon_video_url), mismo patron que el banner
    (generar_y_subir_banner). A diferencia del banner, un fallo de la tienda
    ACA se propaga (no se degrada en silencio): si el orquestador llego hasta
    ofrecer un video, es porque ya se genero con exito; perderlo en silencio
    seria peor que fallar en voz alta."""
    print("Subiendo el video del producto...")
    medio = cliente.subir_video(ruta_video, product_id, titulo=f"{codigo}-video")
    meta_video = [
        {"key": "ekipon_video_id", "value": medio.get("id") or ""},
        {"key": "ekipon_video_url", "value": medio.get("source_url") or ""},
    ]
    cliente.actualizar_borrador(product_id, {"meta_data": meta_video})
    return medio


def generar_y_subir_banner(datos: dict, codigo: str, slug: str,
                           carpeta_ficha: Path, cliente) -> dict | None:
    """Si existe <codigo>_recorte.png en la carpeta del caso, genera el banner,
    lo sube a la mediateca (idempotente por titulo) y devuelve {id, url, alt}.
    Si no hay recorte, devuelve None: el producto se publica sin banner."""
    ruta_recorte = carpeta_ficha / f"{codigo}_recorte.png"
    if not ruta_recorte.is_file():
        print(f"Sin recorte ({ruta_recorte.name}): se publica sin banner.")
        return None
    alt = generador_banner.titulo_banner(datos)
    print("Generando el banner y subiendolo...")
    with tempfile.TemporaryDirectory() as tmp:
        ruta_banner = Path(tmp) / f"{codigo}_banner.png"
        # Solo la GENERACION se degrada con gracia: si el recorte o la plantilla
        # son ilegibles, o el disco se llena al guardar, se publica sin banner.
        try:
            generador_banner.generar_a_archivo(datos, ruta_recorte, ruta_banner)
        except (generador_banner.ErrorRecurso, OSError) as error:
            print(f"Aviso: no se pudo generar el banner ({error}). Se publica sin banner.")
            return None
        # La SUBIDA queda fuera del try: un fallo de la tienda es critico y se
        # propaga (igual que las imagenes de la galeria), no se traga en silencio.
        medio = cliente.subir_imagen(ruta_banner, alt, f"{codigo}-banner",
                                     f"{slug}-banner")
    return {"id": medio.get("id"), "url": medio.get("source_url"), "alt": alt}


def actualizar_existente(datos: dict, codigo: str, slug: str, existente: dict,
                         cliente, carpeta_ficha: Path, ruta_db=None,
                         refrescar_galeria: bool = False,
                         ruta_video: Path | None = None,
                         resultado: dict | None = None) -> int:
    """Actualiza el TEXTO de un borrador existente (--actualizar).

    Las imagenes de la galeria no se tocan: solo se suben al crear. El banner
    si se regenera (es texto/meta, no toca la galeria). El cliente verifica
    ademas que el producto siga en borrador antes de enviar nada.

    Con refrescar_galeria=True (--refrescar-galeria) se vuelve a subir la
    galeria y viaja en el payload, REEMPLAZANDO la de la tienda. Es la unica
    forma de que una actualizacion toque imagenes, y hay que pedirla a mano.

    `ruta_video`/`resultado`: ver publicar() — mismos parametros aditivos,
    mismo comportamiento (video opcional, resultado opcional de solo
    lectura para quien orquesta).
    """
    print(f"Actualizando el borrador existente (id {existente['id']})...")
    subidas = None
    if refrescar_galeria:
        preparadas = preparar_imagenes(datos, carpeta_ficha)
        # Corte antes de subir nada y antes de armar el payload: por este
        # camino jamas puede salir un 'images': [] que borre la galeria viva.
        if sin_galeria_para_refrescar(preparadas):
            return 1
        anunciar_reemplazo_de_galeria(preparadas)
    else:
        print("Solo texto: las imagenes de la galeria no se tocan.")
    categoria = resolver_categoria_en_vivo(cliente, datos, resultado=resultado)
    if categoria is None:
        return 1

    if refrescar_galeria:
        subidas = subir_galeria(preparadas, cliente)
    banner = generar_y_subir_banner(datos, codigo, slug, carpeta_ficha, cliente)
    payload = construir_payload_actualizacion(
        datos, codigo, categoria["id"], banner, imagenes=subidas)
    producto = cliente.actualizar_borrador(existente["id"], payload)

    if resultado is not None:
        resultado["producto_id"] = existente["id"]
    if ruta_video is not None:
        _adjuntar_video(cliente, existente["id"], ruta_video, codigo)

    registro.registrar_publicacion(
        codigo, existente["id"], existente.get("slug") or slug,
        "borrador_actualizado", ruta_db,
    )

    print("\n" + "=" * 62)
    print("BORRADOR ACTUALIZADO — pendiente de revision humana en la tienda")
    print("=" * 62)
    print(f"Producto id: {existente['id']}")
    print(f"Nombre: {producto.get('name', payload['name'])}")
    if subidas is None:
        print("Galeria: intacta (no se envio 'images')")
    else:
        print(f"Galeria: REEMPLAZADA por {len(subidas)} imagenes")
    print(f"Revisar en: {cliente.base}/wp-admin/post.php?post={existente['id']}&action=edit")
    return 0


def publicar(datos: dict, codigo: str, slug: str, carpeta_ficha: Path,
             cliente, ruta_db=None, actualizar: bool = False,
             refrescar_galeria: bool = False,
             ruta_video: Path | None = None,
             resultado: dict | None = None) -> int:
    """Ejecuta la publicacion real (siempre como borrador).

    `ruta_video` (opcional): si se pasa, DESPUES de crear/actualizar el
    producto se sube el video y se asocia via meta_data (ekipon_video_id/
    ekipon_video_url) — ver _adjuntar_video. Parametro aditivo: None (el
    default) no cambia nada del comportamiento existente.

    `resultado` (opcional): dict de salida que orquestador.py usa para leer
    el producto_id creado/actualizado y, si el checkpoint de categoria
    dispara, sus sugerencias — ver resolver_categoria_en_vivo(). Tambien
    aditivo: nada cambia para quien no lo pasa (todos los tests existentes).
    """
    print("Verificando que el producto no exista ya...")
    existente = buscar_existente(cliente, codigo, slug, ruta_db)
    if existente:
        if actualizar:
            return actualizar_existente(
                datos, codigo, slug, existente, cliente, carpeta_ficha, ruta_db,
                refrescar_galeria=refrescar_galeria,
                ruta_video=ruta_video, resultado=resultado,
            )
        print(f"El producto ya existe (id {existente['id']}), no se duplica.")
        if resultado is not None:
            resultado["producto_id"] = existente["id"]
        registro.registrar_publicacion(
            codigo, existente["id"], existente.get("slug") or slug,
            existente.get("status") or "existente", ruta_db,
        )
        return 0

    categoria = resolver_categoria_en_vivo(cliente, datos, resultado=resultado)
    if categoria is None:
        return 1

    subidas = subir_galeria(preparar_imagenes(datos, carpeta_ficha), cliente)

    banner = generar_y_subir_banner(datos, codigo, slug, carpeta_ficha, cliente)
    payload = construir_payload(datos, codigo, slug, categoria["id"], subidas, banner)
    print("Creando el producto como BORRADOR...")
    producto = cliente.crear_producto(payload)

    if resultado is not None:
        resultado["producto_id"] = producto["id"]
    if ruta_video is not None:
        _adjuntar_video(cliente, producto["id"], ruta_video, codigo)

    registro.registrar_publicacion(
        codigo, producto["id"], slug, "borrador_creado", ruta_db
    )

    print("\n" + "=" * 62)
    print("BORRADOR CREADO — pendiente de revision humana en la tienda")
    print("=" * 62)
    print(f"Producto id: {producto['id']}")
    print(f"Nombre: {producto.get('name', payload['name'])}")
    print(f"Categoria: {categoria['name']} (id {categoria['id']})")
    print(f"Imagenes subidas: {len(subidas)}")
    print(f"Revisar en: {cliente.base}/wp-admin/post.php?post={producto['id']}&action=edit")
    return 0


def ejecutar(ruta_ficha: Path, simular: bool,
             fabrica_cliente=ClienteTienda.desde_env, ruta_db=None,
             actualizar: bool = False, refrescar_galeria: bool = False,
             ruta_video: Path | None = None,
             resultado: dict | None = None) -> int:
    """Punto de entrada del pipeline; separa el simulacro de la ejecucion real.

    `ruta_video`/`resultado`: parametros aditivos (ambos None por defecto,
    igual que antes de que existieran) pensados para orquestador.py — ver
    publicar(). El CLI (main(), abajo) no los usa y su comportamiento no
    cambia.
    """
    # La consola de Windows no siempre esta en UTF-8; sin esto, imprimir la
    # ficha tecnica (simbolos como ≤) rompe con UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"Publicador Ekipon — ficha: {ruta_ficha}")
    datos = cargar_ficha_validada(ruta_ficha)

    codigo = extraer_codigo_proveedor(datos)
    if not codigo:
        print(
            "\nERROR: la ficha no trae entrada_original.codigo_proveedor. "
            "El publicador lo necesita como identificador unico del producto."
        )
        return 1
    try:
        slug = generar_slug(codigo, datos["producto"]["nombre_propuesto"])
    except ValueError as error:
        print(f"\nERROR: {error}")
        return 1
    print(f"Codigo proveedor: {codigo}")
    print(f"Slug: {slug}")

    if simular:
        # Cero red por diseño: ni siquiera se construye el cliente.
        return simular_publicacion(datos, codigo, slug, ruta_ficha.parent,
                                   refrescar_galeria=refrescar_galeria)

    cliente = fabrica_cliente()
    print(f"Tienda: {cliente.base}  [candado OK: es la tienda de pruebas]")
    return publicar(
        datos, codigo, slug, ruta_ficha.parent, cliente, ruta_db,
        actualizar=actualizar, refrescar_galeria=refrescar_galeria,
        ruta_video=ruta_video, resultado=resultado,
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Crea un producto en la tienda de PRUEBAS como borrador, "
        "a partir de una ficha Ekipon validada."
    )
    parser.add_argument("ruta_ficha", help="ruta al archivo .json de la ficha")
    parser.add_argument(
        "--simular",
        action="store_true",
        help="no envia nada: muestra el payload completo para revision",
    )
    parser.add_argument(
        "--actualizar",
        action="store_true",
        help="si el producto ya existe COMO BORRADOR, actualiza su texto "
        "(nombre, precio, categoria, etiquetas, descripciones y metadatos). "
        "Las imagenes NO se tocan: solo se suben al crear. Un producto "
        "publicado nunca se modifica.",
    )
    parser.add_argument(
        "--refrescar-galeria",
        action="store_true",
        help="junto con --actualizar, vuelve a subir la galeria de la ficha y "
        "la manda en la actualizacion, REEMPLAZANDO la que hay en la tienda. "
        "Sin esta bandera una actualizacion nunca toca las imagenes. "
        "Se puede ensayar con --simular.",
    )
    argumentos = parser.parse_args()

    if argumentos.refrescar_galeria and not argumentos.actualizar:
        # No se corta la corrida: sin producto existente el camino normal ya
        # sube la galeria. Pero la bandera no hace nada aqui, y una bandera que
        # no hace nada en silencio es una trampa.
        print("Aviso: --refrescar-galeria solo tiene efecto junto con "
              "--actualizar (al crear, la galeria se sube igual).")

    try:
        codigo_salida = ejecutar(
            Path(argumentos.ruta_ficha).resolve(), argumentos.simular,
            actualizar=argumentos.actualizar,
            refrescar_galeria=argumentos.refrescar_galeria,
        )
    except (ErrorTienda, registro.ErrorRegistro) as error:
        sys.exit(str(error))
    sys.exit(codigo_salida)


if __name__ == "__main__":
    main()
