"""Herramientas de navegador para el agente investigador (Fase 2a).

Tres funciones sincronas, sin estado entre llamadas, sobre Playwright
headless (Chromium) + httpx: navegar una URL, listar las imagenes reales que
trae la pagina, y descargar una imagen puntual a disco. Cada llamada abre su
propio navegador y lo cierra (try/finally) antes de devolver el control -- no
queda ningun proceso de Chromium huerfano, ni entre llamadas ni si algo falla
a mitad de camino.

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


def descargar_imagen(url_imagen: str, ruta_destino: Path) -> Path:
    """Descarga el binario de `url_imagen` (httpx, sin Playwright: no hace
    falta un navegador para bajar un archivo) y lo guarda en `ruta_destino`.
    Guardado atomico (temporal + os.replace), mismo patron que
    voz_en_off.generar_a_archivo / orquestador._guardar_ficha.

    Lanza ErrorRecurso si la descarga falla (red, 404, timeout)."""
    ruta_destino = Path(ruta_destino)
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        respuesta = httpx.get(
            url_imagen, timeout=TIMEOUT_DESCARGA_SEGUNDOS, follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        respuesta.raise_for_status()
    except httpx.HTTPError as error:
        raise ErrorRecurso(
            f"no se pudo descargar la imagen '{url_imagen}': {error}"
        ) from error

    temporal = ruta_destino.with_name(ruta_destino.name + ".tmp")
    try:
        temporal.write_bytes(respuesta.content)
        os.replace(temporal, ruta_destino)
    finally:
        temporal.unlink(missing_ok=True)
    return ruta_destino
