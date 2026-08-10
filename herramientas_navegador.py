"""Herramientas de navegador para el agente investigador (Fase 2a).

Funciones sincronas, sin estado entre llamadas, sobre Playwright headless
(Chromium) + httpx: navegar una URL, listar las imagenes reales que trae la
pagina, listar (si existe) el video real o el embed de YouTube/Vimeo, y
descargar un archivo puntual (imagen o video) a disco. Cada llamada abre su
propio navegador y lo cierra (try/finally) antes de devolver el control -- no
queda ningun proceso de Chromium huerfano, ni entre llamadas ni si algo falla
a mitad de camino.

`extraer_video` cubre SOLO el caso de un archivo real y descargable
(<video>/<source> con src de extension .mp4/.webm/...) o, si no hay, un
embed de YouTube/Vimeo (que NUNCA se descarga: ver agente_investigador.py,
regla de alcance -- scraping de esas plataformas queda deliberadamente
afuera). `descargar_archivo` es la logica de descarga/guardado atomico
generica; `descargar_imagen` y `descargar_video` son wrappers finos con el
timeout que corresponde a cada tipo de archivo (un clip pesa mucho mas que
una foto).

Deliberadamente SIN sesion persistente ni modo visible: eso es Fase 2b
(Alibaba, perfil propio de Playwright para resolver el CAPTCHA una vez y
reusar la sesion) -- ver agente_investigador.py. Fase 2a cubre solo paginas
de producto NO-Alibaba ("sin trabas": nada que requiera login ni CAPTCHA), asi
que headless alcanza y es mas simple.

Mismo patron de excepcion propia que el resto del proyecto (ErrorRecurso en
voz_en_off.py / musica.py): cualquier fallo de red, timeout, o de
Playwright/httpx se traduce a un mensaje claro en espanol, nunca un
traceback crudo.

NO se prueba con la red real en unit tests (llamadas a paginas/imagenes
reales): ver test_herramientas_navegador.py, que cubre solo la logica pura
(armado de rutas absolutas de imagen, deduplicacion, nombre de archivo
seguro). Se verifica a mano/CLI con una URL real, mismo criterio que
voz_en_off.py/musica.py con sus servicios externos.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

# Tiempo maximo (ms) para que una pagina termine de cargar el DOM antes de
# darla por caida. 30s alcanza para una pagina de producto normal sin ser
# tan largo que una pagina realmente caida cuelgue al agente.
TIMEOUT_NAVEGACION_MS = 30_000

# Timeout (segundos) de las descargas de imagen via httpx.
TIMEOUT_DESCARGA_SEGUNDOS = 30.0

# Timeout (segundos) de las descargas de VIDEO via httpx -- mas alto que el
# de foto a proposito: un clip de producto (unos segundos a un par de
# minutos, calidad de camara de fabricante) suele pesar decenas de MB,
# muy por encima de una foto (cientos de KB a pocos MB). 180s alcanza para
# bajar un archivo de ese tamano incluso desde un link de fabricante sin
# CDN de alta velocidad, sin dejar al agente colgado tanto tiempo que la
# corrida entera se sienta trabada si la red esta realmente caida.
TIMEOUT_DESCARGA_VIDEO_SEGUNDOS = 180.0

# User-Agent de navegador real: algunas tiendas devuelven paginas
# degradadas (o bloquean) al User-Agent por defecto de httpx/Playwright.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Extensiones de imagen reales que vale la pena bajar. Descarta iconos SVG
# de UI, trackers de 1x1, etc. que igual aparecen como <img> en la pagina.
_EXTENSIONES_IMAGEN_VALIDAS = (
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
)

# Extensiones de video real que vale la pena bajar. Cubre los contenedores
# que un <video>/<source> de pagina de producto suele publicar; NO incluye
# nada de streaming adaptativo (.m3u8/.mpd) porque eso no es "un archivo",
# es una lista de fragmentos -- fuera de alcance de este agente.
_EXTENSIONES_VIDEO_VALIDAS = (".mp4", ".webm", ".mov", ".m4v", ".ogv")

# Dominios de embed de video que este agente NUNCA descarga (decision de
# alcance explicita, ver agente_investigador.py): scraping de YouTube/Vimeo
# cae en zona gris de terminos de servicio. Se detectan solo para poder
# anotarlos en video_nota, no para bajarlos.
_DOMINIOS_EMBED_VIDEO = ("youtube.com", "youtu.be", "vimeo.com")


class ErrorRecurso(Exception):
    """No se pudo navegar una pagina o descargar una imagen (timeout, red
    caida, Playwright/httpx fallaron). Mensaje ya en espanol, listo para
    publicar_notificacion / mostrar a Angie -- nunca un traceback crudo."""


def _navegador_headless():
    """Contexto: sync_playwright() + Chromium headless. Import diferido de
    playwright (paquete pesado, opcional para quien solo usa el camino de
    Fase 1 sin el agente investigador) -- si no esta instalado, se traduce a
    ErrorRecurso en vez de un ImportError crudo."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise ErrorRecurso(
            "Playwright no esta instalado (pip install playwright && "
            "playwright install chromium)."
        ) from error
    return sync_playwright()


def _abrir_pagina(playwright, url: str):
    """Lanza Chromium headless y abre `url`. Devuelve (browser, page).
    Quien llama es responsable de cerrar `browser` (try/finally)."""
    try:
        browser = playwright.chromium.launch(headless=True)
    except Exception as error:
        raise ErrorRecurso(
            f"no se pudo lanzar Chromium (¿'playwright install chromium' "
            f"corrio bien?): {error}"
        ) from error
    try:
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, timeout=TIMEOUT_NAVEGACION_MS, wait_until="domcontentloaded")
    except Exception as error:
        browser.close()
        raise ErrorRecurso(f"no se pudo abrir '{url}': {error}") from error
    return browser, page


def navegar(url: str) -> str:
    """Abre `url` en un navegador headless y devuelve el texto visible del
    body (sin marcado HTML): lo que el agente lee para identificar el
    producto y extraer specs, en linea con la Fase 1 del SKILL.md (Camino A,
    extraccion directa de la fuente).

    Lanza ErrorRecurso si la pagina no carga o el texto no se puede leer."""
    with _navegador_headless() as playwright:
        browser, page = _abrir_pagina(playwright, url)
        try:
            return page.inner_text("body")
        except Exception as error:
            raise ErrorRecurso(
                f"no se pudo leer el texto de '{url}': {error}"
            ) from error
        finally:
            browser.close()


def _es_imagen_de_producto(url_imagen: str) -> bool:
    """Filtra data: URIs (no son un recurso descargable por URL) y rutas sin
    extension de imagen reconocida (iconos SVG de UI, trackers, etc.).
    Logica pura: no abre red."""
    if not url_imagen or url_imagen.startswith("data:"):
        return False
    ruta = urlparse(url_imagen).path.lower()
    return ruta.endswith(_EXTENSIONES_IMAGEN_VALIDAS)


def extraer_imagenes(url: str) -> list[str]:
    """Devuelve las URLs absolutas de las imagenes <img> reales de la
    pagina de producto en `url` (deduplicadas, en el orden en que aparecen).
    Filtra data: URIs e iconos/SVG sin extension de imagen real -- el
    agente decide despues, con el gate visual, cuales sirven de verdad.

    Lanza ErrorRecurso si la pagina no carga."""
    with _navegador_headless() as playwright:
        browser, page = _abrir_pagina(playwright, url)
        try:
            crudas = page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.currentSrc || e.getAttribute('src') || '')",
            )
        except Exception as error:
            raise ErrorRecurso(
                f"no se pudieron leer las imagenes de '{url}': {error}"
            ) from error
        finally:
            browser.close()

    vistas: set[str] = set()
    resultado: list[str] = []
    for cruda in crudas:
        if not cruda:
            continue
        absoluta = urljoin(url, cruda)
        if not _es_imagen_de_producto(absoluta) or absoluta in vistas:
            continue
        vistas.add(absoluta)
        resultado.append(absoluta)
    return resultado


def _es_video_de_producto(url_video: str) -> bool:
    """Filtra data: URIs y rutas sin extension de video reconocida. Logica
    pura: no abre red. Mismo criterio que _es_imagen_de_producto."""
    if not url_video or url_video.startswith("data:"):
        return False
    ruta = urlparse(url_video).path.lower()
    return ruta.endswith(_EXTENSIONES_VIDEO_VALIDAS)


def _es_embed_youtube_o_vimeo(url_embed: str) -> bool:
    """True si `url_embed` (tipicamente el src de un <iframe>) es un embed
    de YouTube/Vimeo -- por HOSTNAME exacto, nunca substring de la URL
    cruda (mismo criterio que agente_investigador.es_alibaba). Estos NUNCA
    se descargan: ver extraer_video / _tool_extraer_video."""
    if not url_embed:
        return False
    host = (urlparse(url_embed).hostname or "").lower()
    return any(
        host == dominio or host.endswith("." + dominio)
        for dominio in _DOMINIOS_EMBED_VIDEO
    )


def extraer_video(url: str) -> dict | None:
    """Busca el video de la pagina de producto en `url`. Primero un archivo
    real y descargable (<video>/<source> con src de extension .mp4/.webm/
    .mov/...); si no hay, un embed de YouTube/Vimeo (<iframe>). Devuelve:

      {"tipo": "archivo", "url": <url absoluta del mp4/webm/...>}
      {"tipo": "embed", "url": <url absoluta del iframe>}
      None                                    -- no hay ningun video

    Un dict (no una lista como extraer_imagenes) porque el agente necesita
    distinguir el TIPO antes de decidir que hacer: descargar el archivo
    real con descargar_video, o solo anotar el embed en video_nota sin
    bajarlo -- nunca scraping de YouTube/Vimeo (decision de alcance, ver
    agente_investigador.py).

    Lanza ErrorRecurso si la pagina no carga."""
    with _navegador_headless() as playwright:
        browser, page = _abrir_pagina(playwright, url)
        try:
            crudas_archivo = page.eval_on_selector_all(
                "video, video source",
                "els => els.map(e => e.currentSrc || e.getAttribute('src') || '')",
            )
            crudas_iframe = page.eval_on_selector_all(
                "iframe",
                "els => els.map(e => e.getAttribute('src') || '')",
            )
        except Exception as error:
            raise ErrorRecurso(
                f"no se pudo leer el video de '{url}': {error}"
            ) from error
        finally:
            browser.close()

    for cruda in crudas_archivo:
        if not cruda:
            continue
        absoluta = urljoin(url, cruda)
        if _es_video_de_producto(absoluta):
            return {"tipo": "archivo", "url": absoluta}

    for cruda in crudas_iframe:
        if not cruda:
            continue
        absoluta = urljoin(url, cruda)
        if _es_embed_youtube_o_vimeo(absoluta):
            return {"tipo": "embed", "url": absoluta}

    return None


def descargar_archivo(url_archivo: str, ruta_destino: Path, *,
                       timeout_segundos: float = TIMEOUT_DESCARGA_SEGUNDOS) -> Path:
    """Descarga el binario de `url_archivo` (httpx, sin Playwright: no hace
    falta un navegador para bajar un archivo) y lo guarda en `ruta_destino`.
    Guardado atomico (temporal + os.replace), mismo patron que
    voz_en_off.generar_a_archivo / orquestador._guardar_ficha.

    Generica: la usan descargar_imagen (timeout de foto) y descargar_video
    (timeout mas largo, ver TIMEOUT_DESCARGA_VIDEO_SEGUNDOS) para no
    duplicar la logica de descarga/guardado atomico entre las dos.

    Lanza ErrorRecurso si la descarga falla (red, 404, timeout)."""
    ruta_destino = Path(ruta_destino)
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        respuesta = httpx.get(
            url_archivo, timeout=timeout_segundos, follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        respuesta.raise_for_status()
    except httpx.HTTPError as error:
        raise ErrorRecurso(
            f"no se pudo descargar '{url_archivo}': {error}"
        ) from error

    temporal = ruta_destino.with_name(ruta_destino.name + ".tmp")
    try:
        temporal.write_bytes(respuesta.content)
        os.replace(temporal, ruta_destino)
    finally:
        temporal.unlink(missing_ok=True)
    return ruta_destino


def descargar_imagen(url_imagen: str, ruta_destino: Path) -> Path:
    """Descarga una imagen real a `ruta_destino`. Wrapper fino sobre
    descargar_archivo con el timeout de foto (TIMEOUT_DESCARGA_SEGUNDOS) --
    se mantiene como funcion propia para no romper nada que ya la llame por
    este nombre.

    Lanza ErrorRecurso si la descarga falla (red, 404, timeout)."""
    return descargar_archivo(
        url_imagen, ruta_destino, timeout_segundos=TIMEOUT_DESCARGA_SEGUNDOS
    )


def descargar_video(url_video: str, ruta_destino: Path) -> Path:
    """Descarga un video real a `ruta_destino`. Wrapper fino sobre
    descargar_archivo con el timeout mas largo de video
    (TIMEOUT_DESCARGA_VIDEO_SEGUNDOS: un clip pesa bastante mas que una
    foto). NUNCA se llama con un embed de YouTube/Vimeo -- eso lo filtra
    quien llama (ver _tool_descargar_video en agente_investigador.py), esta
    funcion no valida el origen, solo baja lo que le pasen.

    Decision sobre el contenedor real vs. la extension pedida: esta funcion
    NO convierte ni renombra el contenido -- guarda los bytes tal cual bajo
    el nombre que le dan en `ruta_destino`. Si la fuente es realmente un
    .mp4, el nombre puede (y para el clip principal del producto, DEBE) ser
    literal '<codigo>_clip_original.mp4' -- ese es el contrato que espera
    orquestador.py. Si la fuente es otro contenedor (.webm/.mov/...), quien
    llama tiene que guardarlo con su extension REAL (nunca mentir
    renombrando a .mp4 un archivo que no lo es) y anotar en video_nota que
    hace falta convertirlo a mano antes de que el orquestador lo encuentre
    -- ver el apendice de agente_investigador.py.

    Lanza ErrorRecurso si la descarga falla (red, 404, timeout)."""
    return descargar_archivo(
        url_video, ruta_destino, timeout_segundos=TIMEOUT_DESCARGA_VIDEO_SEGUNDOS
    )
