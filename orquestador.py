"""Orquestador del pipeline de producto (Fase 1: video + publicacion).

Encadena, EN ORDEN y sin pausas manuales, los modulos ya existentes y
probados del repo para llevar una ficha YA INVESTIGADA (JSON en disco,
investigacion = Fase 2, fuera de alcance) hasta un borrador publicado en la
tienda de pruebas CON el video de producto adjunto:

  colador de calidad -> recorte -> galeria -> banner/portada -> guion+musica
  (IA) -> video normalizado -> voz -> musica -> subtitulos -> marca de agua
  -> ensamblado final -> publicacion (borrador) -> subida del video.

Hay DOS puntos de control que SIEMPRE detienen la corrida y la devuelven para
revision humana en vez de seguir de largo:

  1. El colador de calidad (revisor_publicacion.revisar_listo_para_publicar):
     si la ficha marca REVISAR, se detiene ahi con los motivos. Nunca se
     genera video ni se publica una ficha con datos reales por confirmar.
  2. La categoria de la ficha no matchea el arbol real de la tienda
     (publicador.resolver_categoria_en_vivo): se detiene con las categorias
     mas parecidas, para que Angie corrija el nombre en la ficha.

Cualquier OTRO fallo (imagen corrupta, ffmpeg ausente, ElevenLabs caido,
WooCommerce con error de red, etc.) se PROPAGA tal cual como estado "error":
nunca se oculta ni se sigue de largo. Ver el reporte final de la sesion que
implemento este modulo para los desvios documentados respecto del plan
original (convenciones inventadas, mismatches de firma reales, etc.).

Uso (via app.py, no CLI propio):

    from orquestador import ejecutar_pipeline
    resultado = ejecutar_pipeline(Path("ficha.json"), print)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

import generador_portada
import motor_galeria
import musica
import redactor_ia
import subtitulos
import voz_en_off
import youtube_uploader
from cliente_tienda import ErrorTienda, cargar_env
from ensamblar_video_producto import generar_a_archivo as ensamblar_video
from marca_agua import generar_a_archivo as aplicar_marca_agua
from preparar_video_producto import generar_a_archivo as normalizar_video
from recortar_producto import generar_recorte
from revisor_publicacion import revisar_listo_para_publicar

Notificador = Callable[[str], None]


class ErrorPipeline(Exception):
    """Fallo real de un paso del pipeline (no un checkpoint esperado). El
    mensaje ya viene en español, listo para mostrar a Angie via
    publicar_notificacion."""


# --- Convenciones de nombres de archivo ------------------------------------
#
# '<codigo>_recorte.png' es una convencion REAL y ya vigente en el repo:
# publicador.generar_y_subir_banner() busca EXACTAMENTE ese nombre en la
# carpeta de la ficha para generar y subir el banner solo -- por eso este
# orquestador guarda el recorte ahi, y NO llama el (no llama a
# generador_banner.py el mismo: ver el reporte final para el porque).
#
# '<codigo>_clip_original.mp4' es una convencion INVENTADA por este
# orquestador (Fase 1): el contrato de la ficha (esquema_ficha.py) no declara
# de donde sale el clip de video crudo del producto -- eso lo trae el
# sourcing manual (o una futura Fase 2), fuera de alcance de esta tarea. Se
# espera que ese archivo ya este puesto a mano en la carpeta de la ficha,
# calcado del patron de '<codigo>_recorte.png'. Ver el reporte final: es el
# gap mas importante que quedo documentado.

def _ruta_recorte(carpeta_ficha: Path, codigo: str) -> Path:
    return carpeta_ficha / f"{codigo}_recorte.png"


def _ruta_clip_original(carpeta_ficha: Path, codigo: str) -> Path:
    return carpeta_ficha / f"{codigo}_clip_original.mp4"


def _carpeta_trabajo(carpeta_ficha: Path, codigo: str) -> Path:
    return carpeta_ficha / f"{codigo}_video_trabajo"


def _codigo_proveedor(ficha: dict) -> str | None:
    entrada = ficha.get("entrada_original")
    if not isinstance(entrada, dict):
        return None
    codigo = entrada.get("codigo_proveedor")
    return codigo.strip() if isinstance(codigo, str) and codigo.strip() else None


def _guardar_ficha(ruta_ficha: Path, ficha: dict) -> None:
    """Guarda la ficha actualizada en disco, atomico (temp + os.replace),
    mismo patron que el resto del proyecto. Hace falta porque publicador.py
    vuelve a LEER la ficha del disco (no recibe el dict en memoria): sin este
    guardado, la galeria producida por motor_galeria nunca llegaria a
    publicador (ver motor_galeria.py --guardar-ficha, mismo problema)."""
    temporal = ruta_ficha.with_name(ruta_ficha.name + ".tmp")
    temporal.write_text(
        json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporal, ruta_ficha)


def _descripcion_youtube(ficha: dict) -> str:
    """Arma la descripcion del video para YouTube: caracteristicas del
    producto (si la ficha las trae) + la misma frase de marca que ya usa la
    voz en off (ver voz_en_off.FRASE_FIJA), para que el texto sea consistente
    entre el video y su descripcion en YouTube."""
    caracteristicas = [
        c.strip() for c in (ficha.get("caracteristicas") or [])
        if isinstance(c, str) and c.strip()
    ]
    partes = list(caracteristicas) + [voz_en_off.FRASE_FIJA]
    return "\n".join(partes)


def _resolver_video_a_publicar(ficha: dict, ruta_ficha: Path, ruta_video_final: Path,
                               publicar_notificacion: Notificador) -> Path | None:
    """Decide COMO llega el video a publicador.ejecutar(): a YouTube (la
    ficha guarda la URL resultante en multimedia.video_youtube y esta funcion
    devuelve None, para NO subir tambien el mp4 crudo a WordPress -- es "en
    vez de", no "ademas de", pedido explicito de Angie) o directo a WordPress
    como siempre (devuelve ruta_video_final sin tocar la ficha), si YouTube
    todavia no esta autorizado o la subida falla.

    NUNCA lanza: un error real de YouTube (cuota agotada -- ver el limite
    documentado en youtube_uploader.py --, red caida, etc.) cae al camino de
    WordPress de siempre en vez de tumbar el pipeline. YouTube es una mejora
    opcional, no puede poner en riesgo la publicacion del borrador."""
    if not youtube_uploader.disponible():
        return ruta_video_final
    publicar_notificacion("Subiendo el video a YouTube...")
    titulo = (
        (ficha.get("producto") or {}).get("nombre_propuesto")
        or _codigo_proveedor(ficha) or "Producto Ekipon"
    )
    try:
        subido = youtube_uploader.subir_video(
            ruta_video_final, titulo=titulo,
            descripcion=_descripcion_youtube(ficha),
        )
    except Exception as error:
        publicar_notificacion(
            f"No se pudo subir el video a YouTube ({error}); se sube el "
            "video directo a la tienda, como antes."
        )
        return ruta_video_final
    if not isinstance(ficha.get("multimedia"), dict):
        ficha["multimedia"] = {}
    ficha["multimedia"]["video_youtube"] = subido["url"]
    _guardar_ficha(ruta_ficha, ficha)
    publicar_notificacion(f"Video en YouTube: {subido['url']}")
    return None


def _interpretar_fallo_publicacion(resultado_publicacion: dict) -> dict:
    """Traduce un codigo_salida != 0 de publicador.ejecutar() al estado del
    pipeline que corresponde: CHECKPOINT 2 (categoria sin match en la
    tienda) si resultado_publicacion trae 'categoria_sugerencias' (lo deja
    publicador.resolver_categoria_en_vivo SOLO cuando esa es la causa real);
    error real en cualquier otro caso (ficha invalida detectada tarde, slug
    vacio, refrescar-galeria sin imagenes, etc. — publicador.py puede
    devolver 1 por varios motivos, y solo el de categoria es el checkpoint).

    Logica pura (sin red ni disco): es la parte de la interpretacion del
    checkpoint 2 que se puede probar con unit tests sin correr el pipeline
    completo (que requiere ffmpeg/ElevenLabs/WooCommerce reales)."""
    if "categoria_sugerencias" in resultado_publicacion:
        motivos = [
            "La categoria de la ficha "
            f"('{resultado_publicacion.get('categoria_buscada', '')}') "
            "no existe en la tienda."
        ]
        sugerencias = resultado_publicacion["categoria_sugerencias"]
        if sugerencias:
            motivos.append("Categorias mas parecidas: " + ", ".join(sugerencias))
        return {
            "estado": "revisar", "motivos": motivos, "etapa": "categoria",
            "categoria_sugerencias": sugerencias,
        }
    return {
        "estado": "error",
        "motivo": (
            "El publicador termino con error (ver la consola del servidor "
            "para el detalle completo)."
        ),
    }


def _paso(publicar_notificacion: Notificador, mensaje: str,
          funcion, *args, **kwargs):
    """Corre un paso del pipeline notificando antes, y traduce CUALQUIER
    excepcion real (cada modulo define su PROPIA clase ErrorRecurso, sin una
    jerarquia comun -- ver el reporte final) a ErrorPipeline con un mensaje
    legible. Nunca deja pasar un traceback crudo hacia publicar_notificacion."""
    publicar_notificacion(mensaje)
    try:
        return funcion(*args, **kwargs)
    except ErrorPipeline:
        raise
    except Exception as error:
        raise ErrorPipeline(f"{mensaje} — fallo: {error}") from error


def _producir_video(ficha: dict, carpeta_ficha: Path, codigo: str,
                    ruta_recorte: Path, ruta_clip_original: Path,
                    publicar_notificacion: Notificador,
                    indice_producto: int) -> Path:
    """Produce el video final completo: portada, guion y prompt de musica
    (IA, con respaldo fijo si la IA falla), normalizado, voz, musica de
    fondo, subtitulos, marca de agua y ensamblado. Devuelve la ruta del
    video final.

    Lanza ErrorPipeline (via _paso) si CUALQUIER paso falla -- quien llama
    (ejecutar_pipeline) decide que hacer con eso: desde que esto se separo
    en su propia funcion (18-ago-2026), un fallo aca ya NO tumba el producto
    entero, se trata igual que "la fuente no traia video" (ver el llamado
    mas abajo). Antes, un DNS caido de ElevenLabs o un ffmpeg que fallaba a
    mitad de normalizar dejaba el producto entero sin publicar, perdiendo
    tambien el colador y la galeria ya armados -- pedido explicito de
    Angie: "cualquier error se debe montar el producto igual, con los
    espacios incompletos", mismo principio que ya se aplicaba a la falta de
    clip fuente."""
    # El banner de FOTOS no se genera aca a proposito: publicador.py
    # ya lo genera y sube solo al publicar, siempre que encuentre
    # '<codigo>_recorte.png' en la carpeta de la ficha (que ya
    # dejamos arriba) -- volver a generarlo aca seria trabajo
    # duplicado. La PORTADA de video si hace falta generarla aca:
    # nada mas la produce.
    carpeta_trabajo = _carpeta_trabajo(carpeta_ficha, codigo)
    carpeta_trabajo.mkdir(parents=True, exist_ok=True)
    ruta_portada = carpeta_trabajo / "portada.png"
    _paso(
        publicar_notificacion,
        "Generando la portada del video...",
        generador_portada.generar_a_archivo, ficha, ruta_recorte, ruta_portada,
    )

    # --- Guion (IA) y prompt de musica (IA, con respaldo fijo) ---
    publicar_notificacion("Redactando el guion de la voz con IA...")
    cuerpo_guion = redactor_ia.redactar_guion_voz(ficha)
    if cuerpo_guion is None:
        publicar_notificacion(
            "No se pudo redactar el guion con IA (sin clave o fallo "
            "de red); se usa el recorte automatico de la descripcion."
        )
    texto_guion = voz_en_off.armar_guion(
        ficha, voz_en_off.PRESUPUESTO_CARACTERES_DEFECTO,
        cuerpo_manual=cuerpo_guion,
    )

    publicar_notificacion("Redactando el estilo de musica con IA...")
    prompt_musica = redactor_ia.redactar_prompt_musica(ficha)
    if prompt_musica is None:
        prompt_musica = redactor_ia.PROMPT_MUSICA_GENERICO
        publicar_notificacion(
            "No se pudo redactar el estilo de musica con IA; se usa "
            "un estilo generico de respaldo."
        )

    # --- normalizar -> voz -> musica -> subtitulos -> marca ------
    ruta_clip_normalizado = carpeta_trabajo / "clip_normalizado.mp4"
    _paso(
        publicar_notificacion,
        "Normalizando el clip de video a 1920x1080...",
        normalizar_video, ruta_clip_original, ruta_clip_normalizado,
    )

    ruta_voz = carpeta_trabajo / "voz.mp3"
    _paso(
        publicar_notificacion,
        "Generando la voz en off...",
        voz_en_off.generar_a_archivo, ficha, ruta_voz,
        indice_producto=indice_producto, cuerpo_manual=cuerpo_guion,
        notificar=publicar_notificacion,
    )

    ruta_clip_con_voz = carpeta_trabajo / "clip_con_voz.mp4"
    _paso(
        publicar_notificacion,
        "Mezclando la voz con el video...",
        voz_en_off.preparar_clip_con_voz,
        ruta_clip_normalizado, ruta_voz, ruta_clip_con_voz,
        # Sin esto, un clip fuente mas corto que la voz (comun: el
        # clip de Alibaba no se elige a medida) tumba TODO el
        # pipeline en vez de resolverse solo -- permitir_estirar ya
        # existia en voz_en_off.py (6-ago-2026, "estirar clip
        # corto") pero el orquestador nunca lo prendia. Verificado
        # en vivo 11-ago-2026: un clip de 39.6s contra una voz de
        # 41.3s (diferencia de 1.7s) fallaba aca antes de este
        # cambio.
        permitir_estirar=True,
    )

    ruta_clip_con_musica = carpeta_trabajo / "clip_con_musica.mp4"
    _paso(
        publicar_notificacion,
        "Agregando musica de fondo...",
        musica.mezclar_musica_de_fondo,
        ruta_clip_con_voz, prompt_musica, ruta_clip_con_musica,
        notificar=publicar_notificacion,
    )

    ruta_clip_con_subtitulos = carpeta_trabajo / "clip_con_subtitulos.mp4"
    _paso(
        publicar_notificacion,
        "Quemando los subtitulos...",
        subtitulos.generar_a_archivo,
        ruta_clip_con_musica, ruta_voz, texto_guion, ruta_clip_con_subtitulos,
    )

    ruta_clip_con_marca = carpeta_trabajo / "clip_con_marca_agua.mp4"
    _paso(
        publicar_notificacion,
        "Agregando la marca de agua...",
        aplicar_marca_agua, ruta_clip_con_subtitulos, ruta_clip_con_marca,
    )

    ruta_video_final = carpeta_ficha / f"{codigo}_video_final.mp4"
    _paso(
        publicar_notificacion,
        "Armando el video final (portada + clip + outros)...",
        ensamblar_video, ruta_portada, ruta_clip_con_marca, ruta_video_final,
    )
    publicar_notificacion(f"Video final listo: {ruta_video_final.name}")
    return ruta_video_final


def ejecutar_pipeline(ruta_ficha: Path, publicar_notificacion: Notificador,
                       produccion: bool = True,
                       indice_producto: int = 0) -> dict:
    """Corre el pipeline completo para una ficha ya investigada. Devuelve un
    dict con 'estado':

      'revisar' -> ya no se usa en la practica: ni el colador de calidad
                   (11-ago-2026) ni la categoria sin match (20-ago-2026)
                   frenan la publicacion -- decision explicita de Angie de
                   montar el producto siempre y dejar lo dudoso anotado en
                   'motivos_revision' del estado 'publicado'. Queda el
                   estado por si algun checkpoint nuevo lo necesita.
      'error'   -> un paso real fallo; 'motivo' trae el mensaje.
      'publicado' -> borrador creado/actualizado con el video adjunto;
                     'producto_id' y 'url_revisar' traen donde revisarlo.

    `produccion` (default True desde el 24-ago-2026, decision explicita de
    Angie tras cerrar la prueba de escala de 20/20 sin bugs: "ya no quiero
    mas clones de tiendas, que trabaje en la tienda real" -- el pipeline
    apunta a la tienda real por defecto, y el checkbox de la pagina ahora
    es para OPTAR por la tienda de pruebas, no al reves): True usa
    cliente_tienda.RUTA_ENV_PRODUCCION (tienda real, ekipon.co); False usa
    las credenciales de pruebas (.env). El candado de seguridad
    (TIENDAS_PERMITIDAS) sigue validando el dominio en cualquiera de los
    dos casos. Todo sigue saliendo como BORRADOR (nunca 'publish' directo)
    -- es Angie quien decide manualmente si publica cada producto.

    `indice_producto` (default 0): posicion de ESTE producto dentro del lote
    (0-based) -- se pasa tal cual a voz_en_off.generar_a_archivo para que la
    voz alterne de verdad entre productos (ver elegir_voz). Bug real, 18-ago-
    2026: quedaba hardcodeado en 0 aca adentro, asi que TODOS los productos
    de un mismo lote sonaban con la misma voz (carlos) sin importar cuantas
    voces hubiera en la rotacion -- lote_masivo.py ya tenia el numero de
    fila, pero nunca llegaba hasta aca.

    NUNCA lanza: toda excepcion se traduce a uno de los tres estados de
    arriba, siempre notificando por publicar_notificacion antes de volver.
    """
    ruta_ficha = Path(ruta_ficha).resolve()
    carpeta_ficha = ruta_ficha.parent

    # --- Carga de la ficha ---------------------------------------------
    # Deliberadamente NO se usa validar_ficha.cargar_json ni
    # publicador.cargar_ficha_validada aca: ambas hacen sys.exit() en vez de
    # devolver un error, pensadas para un CLI de un solo uso -- en un
    # servidor de larga duracion eso tumbaria el proceso entero. Se carga a
    # mano con el mismo criterio (utf-8-sig, mismo patron que el resto del
    # repo) pero devolviendo un estado de error en vez de terminar el proceso.
    publicar_notificacion(f"Leyendo la ficha: {ruta_ficha.name}")
    if not ruta_ficha.is_file():
        motivo = f"No encuentro el archivo de la ficha: {ruta_ficha}"
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}
    try:
        ficha = json.loads(ruta_ficha.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        motivo = f"La ficha no se pudo leer o no es JSON valido: {error}"
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}
    if not isinstance(ficha, dict):
        motivo = "El archivo de la ficha no es un objeto JSON valido."
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}

    codigo = _codigo_proveedor(ficha)
    if not codigo:
        motivo = (
            "La ficha no trae entrada_original.codigo_proveedor: hace falta "
            "como identificador unico del producto en toda la corrida."
        )
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}

    # --- CHECKPOINT 1: colador de calidad -------------------------------
    publicar_notificacion("Revisando si la ficha esta lista para publicar...")
    try:
        revision = revisar_listo_para_publicar(ficha)
    except Exception as error:  # el revisor no deberia lanzar, pero no se
        # deja pasar un traceback si algun dia lo hace.
        motivo = f"El colador de calidad fallo inesperadamente: {error}"
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}

    # Decision de Angie (11-ago-2026): el colador YA NO frena el pipeline.
    # Motivo dado: quiere el producto montado en la tienda (fotos, ficha
    # tecnica, descripcion, video) con los campos dudosos vacios/marcados,
    # y revisar el borrador armado en la tienda en vez de una lista de
    # texto antes de que exista. Los motivos NO se pierden: se notifican
    # igual (abajo) y viajan en el resultado final para que la pagina los
    # muestre junto al link del borrador -- ver "motivos_revision" en el
    # "estado": "publicado" al final de esta funcion.
    motivos_colador = [m.mensaje for m in revision.motivos]
    if motivos_colador:
        publicar_notificacion(
            f"REVISAR — {len(motivos_colador)} motivo(s), se sigue igual "
            "(vas a poder revisarlos en el borrador):"
        )
        for motivo in motivos_colador:
            publicar_notificacion(f"  • {motivo}")

    publicar_notificacion("Arrancando el armado automatico.")

    try:
        # --- Recorte del producto ---------------------------------------
        plan = motor_galeria.plan_de_ficha(ficha)
        if plan is None or not plan.imagen_base:
            raise ErrorPipeline(
                "La ficha no trae multimedia.plan_galeria.imagen_base: no "
                "hay foto base para recortar. Completar el plan de galeria "
                "antes de generar el video."
            )
        ruta_imagen_base = carpeta_ficha / plan.imagen_base
        if not ruta_imagen_base.is_file():
            raise ErrorPipeline(
                f"No encuentro la foto base '{plan.imagen_base}' (relativa a "
                f"{carpeta_ficha})."
            )
        ruta_recorte = _ruta_recorte(carpeta_ficha, codigo)
        _paso(
            publicar_notificacion,
            "Recortando el fondo del producto...",
            generar_recorte, ruta_imagen_base, ruta_recorte,
        )

        # --- Galeria (producto_limpio, medidas, partes senaladas) -------
        carpeta_galeria = carpeta_ficha / f"{codigo}_galeria"
        informe = _paso(
            publicar_notificacion,
            "Armando la galeria de fotos...",
            motor_galeria.producir_galeria, ficha, ruta_recorte, carpeta_galeria,
        )
        motor_galeria.relativizar_a_carpeta_de_ficha(informe, carpeta_ficha)
        motor_galeria.aplicar_informe(ficha, informe)
        incluidas, _omitidas = motor_galeria.imagenes_confirmadas_del_plan(ficha)
        motor_galeria.aplicar_confirmadas(ficha, incluidas)
        _guardar_ficha(ruta_ficha, ficha)
        publicar_notificacion(
            f"Galeria lista: {len(informe['producidos'])} pieza(s) producida(s), "
            f"{len(incluidas)} van a la tienda."
        )

        # --- Video: opcional (pedido de Angie, 14-ago-2026) --------------
        # Antes, si la fuente no traia el clip crudo del producto, esto
        # cortaba TODO el pipeline con un error -- ningun producto se
        # publicaba solo porque le faltaba el video. Ahora el video es una
        # seccion mas que puede faltar, igual que una dimension o una
        # caracteristica: si no hay clip, se salta ENTERA (portada, guion y
        # musica por IA, normalizado, voz, musica, subtitulos, marca de
        # agua, ensamblado -- nada de eso tiene sentido sin un clip base) y
        # se sigue derecho a publicar, dejando el video marcado como
        # pendiente en vez de bloquear el producto completo. El chequeo va
        # ANTES de redactar el guion a proposito: ese paso usa IA (cuesta
        # una llamada real) y no tiene destino si no hay video para pegarle
        # la voz.
        ruta_clip_original = _ruta_clip_original(carpeta_ficha, codigo)
        ruta_video_final: Path | None = None
        if not ruta_clip_original.is_file():
            publicar_notificacion(
                f"No encontre '{ruta_clip_original.name}': la fuente no "
                "trajo video de este producto. Se publica igual, sin "
                "video -- queda pendiente para subirlo despues."
            )
            motivos_colador.append(
                "Video pendiente: la fuente no traia material de video "
                "para este producto."
            )
        else:
            try:
                ruta_video_final = _producir_video(
                    ficha, carpeta_ficha, codigo, ruta_recorte,
                    ruta_clip_original, publicar_notificacion,
                    indice_producto,
                )
            except ErrorPipeline as error:
                # Fallo REAL de la etapa de video (DNS de ElevenLabs, ffmpeg,
                # etc.) -- se degrada igual que "sin clip fuente", NO tumba
                # el producto entero (ver docstring de _producir_video).
                publicar_notificacion(
                    f"No se pudo generar el video ({error}). Se publica "
                    "igual, sin video -- queda pendiente para subirlo "
                    "despues."
                )
                motivos_colador.append(
                    f"Video pendiente: fallo al generarlo ({error})."
                )

    except ErrorPipeline as error:
        publicar_notificacion(f"ERROR: {error}")
        return {"estado": "error", "motivo": str(error)}

    # --- Video: a YouTube si esta autorizado, si no directo a WordPress ----
    # (como siempre). Ver _resolver_video_a_publicar: nunca lanza, cualquier
    # error real de YouTube cae sola al camino de WordPress de siempre. Si
    # no hubo clip (ruta_video_final es None), no hay nada que resolver --
    # se publica derecho sin video.
    ruta_video_a_publicar = None
    if ruta_video_final is not None:
        ruta_video_a_publicar = _resolver_video_a_publicar(
            ficha, ruta_ficha, ruta_video_final, publicar_notificacion,
        )

    # --- Publicacion (CHECKPOINT 2 vive adentro de este paso) -----------
    import publicador  # import diferido: evita el costo de importarlo si el
    # pipeline se corta antes (colador, o cualquier ErrorPipeline de arriba).
    import functools
    from cliente_tienda import ClienteTienda, RUTA_ENV_PRODUCCION

    if produccion:
        publicar_notificacion("Publicando el borrador en la tienda REAL (ekipon.co)...")
        fabrica_cliente = functools.partial(
            ClienteTienda.desde_env, ruta_env=RUTA_ENV_PRODUCCION,
        )
    else:
        publicar_notificacion("Publicando el borrador en la tienda de pruebas...")
        fabrica_cliente = ClienteTienda.desde_env

    resultado_publicacion: dict = {}
    try:
        codigo_salida = publicador.ejecutar(
            ruta_ficha, simular=False, ruta_video=ruta_video_a_publicar,
            resultado=resultado_publicacion,
            motivos_revision=motivos_colador,
            fabrica_cliente=fabrica_cliente,
        )
    except SystemExit as salida:
        # publicador.cargar_ficha_validada() y cliente_tienda (cargar_env,
        # verificar_candado) usan sys.exit() en vez de una excepcion de
        # dominio -- mismatch documentado en el reporte final. Se traduce
        # aca para no tumbar el hilo del servidor.
        motivo = (
            str(salida.code) if isinstance(salida.code, str)
            else "el publicador se detuvo por un problema de configuracion "
            "o de la ficha (ver la consola del servidor para el detalle)."
        )
        publicar_notificacion(f"ERROR al publicar: {motivo}")
        return {"estado": "error", "motivo": motivo}
    except ErrorTienda as error:
        motivo = str(error)
        publicar_notificacion(f"ERROR de la tienda: {motivo}")
        return {"estado": "error", "motivo": motivo}
    except Exception as error:
        motivo = f"{type(error).__name__}: {error}"
        publicar_notificacion(f"ERROR inesperado al publicar: {motivo}")
        return {"estado": "error", "motivo": motivo}

    if codigo_salida != 0:
        resultado_final = _interpretar_fallo_publicacion(resultado_publicacion)
        for motivo in resultado_final.get("motivos") or [resultado_final.get("motivo", "")]:
            publicar_notificacion(f"  • {motivo}")
        return resultado_final

    # Decision de Angie (20-ago-2026): la categoria sin match en la tienda
    # YA NO frena la publicacion -- "que monte el producto sin frenarse por
    # nada", mismo principio que el colador de calidad (CHECKPOINT 1, mas
    # arriba). resolver_categoria_en_vivo publica igual con la categoria
    # mas parecida, pero deja la anotacion en resultado_publicacion para
    # que Angie la vea y la corrija desde el borrador ya armado.
    if "categoria_sugerencias" in resultado_publicacion:
        motivo = (
            "La categoria propuesta "
            f"('{resultado_publicacion.get('categoria_buscada', '')}') "
            "no existe en la tienda; se publico con la mas parecida. "
            "Confirmar la categoria correcta en el borrador."
        )
        motivos_colador.append(motivo)
        publicar_notificacion(f"  • {motivo}")

    producto_id = resultado_publicacion.get("producto_id")
    url_revisar = None
    if producto_id:
        # Mismo formato de URL que ya imprime publicador.py. Se arma sola
        # (sin reconstruir un ClienteTienda, que ya se construyo adentro de
        # publicador.ejecutar()): alcanza con WC_STORE_URL del .env.
        try:
            ruta_env_url = RUTA_ENV_PRODUCCION if produccion else \
                Path(__file__).parent / ".env"
            env = cargar_env(ruta_env_url)
            base = (env.get("WC_STORE_URL") or "").rstrip("/")
            if base:
                url_revisar = f"{base}/wp-admin/post.php?post={producto_id}&action=edit"
        except SystemExit:
            url_revisar = None

    # ruta_video_final (no ruta_video_a_publicar) es la senal correcta de
    # "hubo video": _resolver_video_a_publicar devuelve None tanto cuando NO
    # hubo clip como cuando el video SI se proceso pero se subio a YouTube
    # (va embebido en la ficha, no como archivo aparte) -- confundir los dos
    # casos diria "sin video" en un producto que si lo tiene.
    mensaje_final = (
        "Listo: borrador publicado con el video adjunto."
        if ruta_video_final is not None
        else "Listo: borrador publicado sin video (queda pendiente)."
    )
    publicar_notificacion(mensaje_final)
    return {
        "estado": "publicado",
        "producto_id": producto_id,
        "url_revisar": url_revisar,
        # No vacio solo si el colador dejo motivos (ver arriba): la pagina
        # los muestra junto al link para que la revision pase adentro del
        # borrador ya armado, no antes de que exista.
        "motivos_revision": motivos_colador,
    }
