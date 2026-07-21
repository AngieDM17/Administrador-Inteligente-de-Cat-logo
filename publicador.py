"""Publicador Ekipon — crea un producto en la tienda de PRUEBAS como borrador.

Uso:  python publicador.py <ruta_ficha.json> [--simular] [--actualizar]

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

Codigos de salida: 0 = creado o ya existia (o simulacro OK); 1 = error de
ficha, categoria o tienda; 2 = problema con el archivo (via cargar_json).
"""

import argparse
import difflib
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
        # La plantilla Elementor arma la descripcion (ficha tecnica + banner +
        # caracteristicas + video) leyendo los meta_data ekipon_*. El campo queda
        # vacio para no duplicar ese contenido en la pestaña Descripcion.
        "description": "",
        "images": [{"id": img["id"], "alt": img["alt"]} for img in imagenes],
        "meta_data": meta_data,
    }


def construir_payload_actualizacion(datos: dict, codigo: str,
                                    categoria_id, banner: dict | None = None) -> dict:
    """Arma el payload de ACTUALIZACION: solo los campos textuales.

    Regla fija: las imagenes solo se suben al crear; una actualizacion nunca
    las toca (el payload NI SIQUIERA lleva la clave 'images', para que la
    tienda no borre la galeria existente). Tampoco lleva slug ni type: eso
    quedo fijado al crear el producto. El banner (si se pasa) si viaja: es
    texto/meta, no toca la galeria.
    """
    completo = construir_payload(datos, codigo, slug="", categoria_id=categoria_id,
                                 imagenes=[], banner=banner)
    campos_textuales = (
        "name", "regular_price", "categories", "tags",
        "short_description", "description", "meta_data",
    )
    return {campo: completo[campo] for campo in campos_textuales}


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
            "titulo": ruta.stem,
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
                        carpeta_ficha: Path) -> int:
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
    print("\nSIMULACRO terminado. Nada se creo ni se subio.")
    return 0


def resolver_categoria_en_vivo(cliente, datos: dict) -> dict | None:
    """Lee el arbol de categorias de la tienda y resuelve la propuesta.

    Devuelve la categoria, o None (con el error ya impreso) si no existe.
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
            imprimir_lista("Nombres mas parecidos en la tienda:", sugerencias)
        return None
    print(f"Categoria resuelta: {categoria['name']} (id {categoria['id']})")
    return categoria


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
                         cliente, carpeta_ficha: Path, ruta_db=None) -> int:
    """Actualiza el TEXTO de un borrador existente (--actualizar).

    Las imagenes de la galeria no se tocan: solo se suben al crear. El banner
    si se regenera (es texto/meta, no toca la galeria). El cliente verifica
    ademas que el producto siga en borrador antes de enviar nada.
    """
    print(f"Actualizando el borrador existente (id {existente['id']})...")
    print("Solo texto: las imagenes de la galeria no se tocan.")
    categoria = resolver_categoria_en_vivo(cliente, datos)
    if categoria is None:
        return 1

    banner = generar_y_subir_banner(datos, codigo, slug, carpeta_ficha, cliente)
    payload = construir_payload_actualizacion(datos, codigo, categoria["id"], banner)
    producto = cliente.actualizar_borrador(existente["id"], payload)

    registro.registrar_publicacion(
        codigo, existente["id"], existente.get("slug") or slug,
        "borrador_actualizado", ruta_db,
    )

    print("\n" + "=" * 62)
    print("BORRADOR ACTUALIZADO — pendiente de revision humana en la tienda")
    print("=" * 62)
    print(f"Producto id: {existente['id']}")
    print(f"Nombre: {producto.get('name', payload['name'])}")
    print(f"Revisar en: {cliente.base}/wp-admin/post.php?post={existente['id']}&action=edit")
    return 0


def publicar(datos: dict, codigo: str, slug: str, carpeta_ficha: Path,
             cliente, ruta_db=None, actualizar: bool = False) -> int:
    """Ejecuta la publicacion real (siempre como borrador)."""
    print("Verificando que el producto no exista ya...")
    existente = buscar_existente(cliente, codigo, slug, ruta_db)
    if existente:
        if actualizar:
            return actualizar_existente(
                datos, codigo, slug, existente, cliente, carpeta_ficha, ruta_db
            )
        print(f"El producto ya existe (id {existente['id']}), no se duplica.")
        registro.registrar_publicacion(
            codigo, existente["id"], existente.get("slug") or slug,
            existente.get("status") or "existente", ruta_db,
        )
        return 0

    categoria = resolver_categoria_en_vivo(cliente, datos)
    if categoria is None:
        return 1

    imagenes = preparar_imagenes(datos, carpeta_ficha)
    subidas = []
    for numero, imagen in enumerate(imagenes, start=1):
        print(f"Subiendo imagen {numero}/{len(imagenes)}: {imagen['ruta'].name}...")
        medio = cliente.subir_imagen(
            imagen["ruta"], imagen["alt"], imagen["titulo"], imagen["slug_medio"]
        )
        subidas.append({"id": medio["id"], "alt": imagen["alt"]})

    banner = generar_y_subir_banner(datos, codigo, slug, carpeta_ficha, cliente)
    payload = construir_payload(datos, codigo, slug, categoria["id"], subidas, banner)
    print("Creando el producto como BORRADOR...")
    producto = cliente.crear_producto(payload)

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
             actualizar: bool = False) -> int:
    """Punto de entrada del pipeline; separa el simulacro de la ejecucion real."""
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
        return simular_publicacion(datos, codigo, slug, ruta_ficha.parent)

    cliente = fabrica_cliente()
    print(f"Tienda: {cliente.base}  [candado OK: es la tienda de pruebas]")
    return publicar(
        datos, codigo, slug, ruta_ficha.parent, cliente, ruta_db,
        actualizar=actualizar,
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
    argumentos = parser.parse_args()

    try:
        codigo_salida = ejecutar(
            Path(argumentos.ruta_ficha).resolve(), argumentos.simular,
            actualizar=argumentos.actualizar,
        )
    except (ErrorTienda, registro.ErrorRegistro) as error:
        sys.exit(str(error))
    sys.exit(codigo_salida)


if __name__ == "__main__":
    main()
