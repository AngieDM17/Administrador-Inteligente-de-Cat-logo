"""Sesion de navegador VISIBLE y persistente para Alibaba (Fase 2b).

Fase 2a (`herramientas_navegador.py`) cubre paginas "sin trabas": Chromium
headless, sin sesion, abre-y-cierra en cada llamada. Alibaba exige sesion
logueada y a veces un CAPTCHA -- nada de eso se puede resolver sin una
persona mirando la pantalla. Este modulo agrega `SesionAlibaba`: una unica
ventana de Chromium VISIBLE (`headless=False`) con un perfil PROPIO y
persistente en disco (`navegador_perfil_alibaba/`, gitignored -- separado
del Chrome real de Angie, para no chocar si ella lo tiene abierto al mismo
tiempo), que vive durante TODA una corrida de `investigar_producto()` para
un link de Alibaba.

--- Mecanismo de pausa (sin heuristica de CAPTCHA) ---

En vez de tratar de adivinar si aparecio un CAPTCHA (fragil: la UI de
Alibaba cambia, un falso negativo publicaria con la sesion rota sin que
nadie se entere), el diseno es mas simple y mas honesto: la PRIMERA vez que
esta sesion abre una pagina (sea por `navegar`, `extraer_imagenes` o
`extraer_video` -- lo que el agente llame primero), SIEMPRE se detiene y
publica un mensaje con el prefijo `PREFIJO_ESPERANDO_CONFIRMACION` pidiendole
a Angie que confirme desde la pagina (app.py traduce ese prefijo a un evento
SSE de tipo "necesita_confirmacion", ver app.py). La tool bloquea en
`evento_continuar.wait()` -- ese Event lo crea `app.py` por job y lo pasa
para abajo hasta aca via `agente_investigador.investigar_producto(...,
evento_continuar=...)`. Cuando Angie hace clic en "Continuar" en la pagina,
`POST /continuar/{job_id}` hace `evento_continuar.set()` y esta sesion
despierta, confirma que la pagina tiene contenido real (chequeo simple, NO
una heuristica de captcha) y sigue. Navegaciones siguientes en la MISMA
instancia (mismo producto) ya no pausan.

--- Un solo hilo dedicado, no `asyncio.to_thread` suelto por llamada ---

La API sincrona de Playwright exige que todas las llamadas sobre una misma
conexion se hagan desde el MISMO hilo de sistema operativo que la abrio --
no alcanza con "algun" hilo, porque el pool por defecto de
`asyncio.to_thread` puede repartir cada llamada a un hilo distinto. Por eso
esta clase mantiene su PROPIO `ThreadPoolExecutor(max_workers=1)`: todo lo
que toca `self._context`/`self._page` se somete a ese unico worker
(`_en_hilo_sesion`), fijo durante toda la vida de la instancia. Los metodos
publicos (`navegar`, `extraer_imagenes`, etc.) siguen siendo funciones
sincronas normales -- quien los llama (las tools de `agente_investigador.py`)
los sigue envolviendo en `asyncio.to_thread`, exactamente igual que a las
funciones stateless de `herramientas_navegador.py`; ese envoltorio de afuera
solo necesita un hilo cualquiera para BLOQUEARSE mientras el trabajo real de
Playwright ocurre siempre en el mismo hilo dedicado de adentro.

--- Credenciales ---

Este modulo NUNCA pide, ve, ni guarda el usuario/contrasenia de Alibaba de
Angie. Ella inicia sesion ELLA MISMA, a mano, en la ventana visible; lo unico
que este codigo hace es abrir esa ventana, esperar, y despues leer la pagina
ya autenticada (lectura de solo-lectura, igual que cualquier otra pagina).

--- Verificacion ---

NO se prueba con Playwright real en unit tests (headless=False abriria una
ventana visible y colgaria el proceso esperando una interaccion humana que
nunca llega en este entorno). Ver test_navegador_alibaba.py: toda la logica
(pausa en la primera navegacion, chequeo de pagina vacia, filtrado de
imagenes/video, delegacion de descargas) se prueba con una pagina falsa
inyectada via monkeypatch de `_asegurar_contexto`, nunca con un browser real.
Se prueba a mano/con Angie presente la primera vez, ver el reporte de la
sesion que agrego este modulo.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from threading import Event
from typing import Callable
from urllib.parse import urljoin

import herramientas_navegador as nav

Notificador = Callable[[str], None]

CARPETA_PROYECTO = Path(__file__).parent

# Perfil propio y persistente de Playwright para Alibaba -- separado del
# Chrome real de Angie. Vive en la RAIZ del repo (mismo nivel que
# investigaciones/, galeria_motor/, etc: carpetas de estado local, no de
# codigo) y esta gitignored (tiene cookies reales de su cuenta).
CARPETA_PERFIL_ALIBABA_DEFECTO = CARPETA_PROYECTO / "navegador_perfil_alibaba"

# Prefijo que distingue un mensaje de "necesita confirmacion humana" de un
# mensaje de progreso normal. app.py lo reconoce (ver notificar() en
# _correr_pipeline) y lo traduce a un evento SSE de tipo
# "necesita_confirmacion" en vez de "progreso" -- ver app.py.
PREFIJO_ESPERANDO_CONFIRMACION = "ESPERANDO CONFIRMACION:"


class SesionAlibaba:
    """Una ventana de Chromium visible + perfil persistente, viva durante
    toda una corrida de `investigar_producto()` para un link de Alibaba.
    Misma interfaz (mismos nombres y firmas) que los metodos de
    `herramientas_navegador.py`, para que `agente_investigador._correr_agente`
    pueda armar las tools MCP indistintamente sobre este objeto o sobre el
    modulo stateless -- el modelo no necesita saber cual de los dos hay
    por debajo."""

    def __init__(self, publicar_notificacion: Notificador,
                 evento_continuar: Event,
                 carpeta_perfil: Path | None = None) -> None:
        self._publicar_notificacion = publicar_notificacion
        self._evento_continuar = evento_continuar
        self._carpeta_perfil = Path(carpeta_perfil or CARPETA_PERFIL_ALIBABA_DEFECTO)
        self._primera_navegacion = True
        self._playwright = None
        self._context = None
        self._page = None
        self._url_actual: str | None = None
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sesion-alibaba"
        )

    # ---------------------------------------------------------------- #
    # Interfaz publica (misma forma que herramientas_navegador.py)
    # ---------------------------------------------------------------- #

    def navegar(self, url: str) -> str:
        """Se asegura de estar en `url` (pausa si es la primera pagina de
        la sesion, ver `_asegurar_pagina`) y devuelve el texto visible de
        la pagina."""
        self._asegurar_pagina(url)
        return self._en_hilo_sesion(self._texto_interno)

    def extraer_imagenes(self, url: str) -> list[str]:
        """URLs absolutas de imagenes REALES de la pagina en `url`,
        deduplicadas, mismo filtro que
        `herramientas_navegador._es_imagen_de_producto` (reusado, no
        duplicado)."""
        self._asegurar_pagina(url)
        crudas = self._en_hilo_sesion(self._imagenes_crudas_interno)

        vistas: set[str] = set()
        resultado: list[str] = []
        for cruda in crudas:
            if not cruda:
                continue
            absoluta = urljoin(url, cruda)
            if not nav._es_imagen_de_producto(absoluta) or absoluta in vistas:
                continue
            vistas.add(absoluta)
            resultado.append(absoluta)
        return resultado

    def extraer_video(self, url: str) -> dict | None:
        """Mismo contrato que `herramientas_navegador.extraer_video`:
        {"tipo": "archivo"|"embed", "url": ...} o None. Mismo filtro
        reusado (`_es_video_de_producto` / `_es_embed_youtube_o_vimeo`)."""
        self._asegurar_pagina(url)
        crudas_archivo, crudas_iframe = self._en_hilo_sesion(self._video_crudo_interno)

        for cruda in crudas_archivo:
            if not cruda:
                continue
            absoluta = urljoin(url, cruda)
            if nav._es_video_de_producto(absoluta):
                return {"tipo": "archivo", "url": absoluta}

        for cruda in crudas_iframe:
            if not cruda:
                continue
            absoluta = urljoin(url, cruda)
            if nav._es_embed_youtube_o_vimeo(absoluta):
                return {"tipo": "embed", "url": absoluta}

        return None

    def descargar_imagen(self, url_imagen: str, ruta_destino) -> Path:
        """Descarga por HTTP (httpx, sin Playwright de por medio -- no hace
        falta el navegador para bajar un archivo). Delega en
        `herramientas_navegador.descargar_imagen`: no se duplica la logica
        de descarga/guardado atomico."""
        return nav.descargar_imagen(url_imagen, ruta_destino)

    def descargar_video(self, url_video: str, ruta_destino) -> Path:
        """Igual que `descargar_imagen`: delega en
        `herramientas_navegador.descargar_video` (timeout largo de video)."""
        return nav.descargar_video(url_video, ruta_destino)

    def cerrar(self) -> None:
        """Cierra el browser_context (y detiene Playwright), pero NUNCA
        borra `carpeta_perfil` en disco -- las cookies quedan guardadas
        para la proxima corrida. Segura de llamar aunque nunca se haya
        abierto un contexto real (ej. una corrida que fallo antes de la
        primera navegacion)."""
        try:
            self._en_hilo_sesion(self._cerrar_interno)
        finally:
            self._executor.shutdown(wait=False)

    def __enter__(self) -> "SesionAlibaba":
        return self

    def __exit__(self, *exc) -> bool:
        self.cerrar()
        return False

    # ---------------------------------------------------------------- #
    # Logica de pausa/reanudacion -- punto de entrada UNICO para las 3
    # tools que abren pagina, asi el orden en que el agente las llame no
    # importa: la pausa siempre pasa en la primera apertura real de
    # pagina de la corrida, la dispare la tool que la dispare.
    # ---------------------------------------------------------------- #

    def _asegurar_pagina(self, url: str) -> None:
        es_primera = self._primera_navegacion
        self._en_hilo_sesion(self._ir_a_interno, url)

        if not es_primera:
            return

        self._primera_navegacion = False
        self._publicar_notificacion(
            f"{PREFIJO_ESPERANDO_CONFIRMACION} se abrio una ventana de "
            f"Chrome para Alibaba en {url}. Inicia sesion en Alibaba o "
            "resolve lo que pida (login, verificacion), y hace clic en "
            "'Ya resolvi, continuar' cuando la pagina del producto se vea "
            "bien."
        )
        self._evento_continuar.wait()
        self._evento_continuar.clear()

        # Chequeo simple de contenido real -- a proposito NO es una
        # heuristica de deteccion de CAPTCHA (fragil, la UI de Alibaba
        # puede cambiar): solo confirma que la pagina no siga en
        # blanco/con un error obvio tras la confirmacion de Angie.
        texto = self._en_hilo_sesion(self._texto_interno)
        if not texto.strip():
            raise nav.ErrorRecurso(
                f"la pagina de Alibaba en '{url}' sigue vacia despues de "
                "la confirmacion -- puede que el login o el captcha no "
                "haya quedado resuelto. Volve a intentar."
            )

    # ---------------------------------------------------------------- #
    # Funciones que corren DENTRO del hilo dedicado (via _en_hilo_sesion)
    # -- son las unicas que tocan self._context/self._page directamente.
    # ---------------------------------------------------------------- #

    def _en_hilo_sesion(self, funcion, *args):
        return self._executor.submit(funcion, *args).result()

    def _asegurar_contexto(self) -> None:
        if self._context is not None:
            return
        from playwright.sync_api import sync_playwright

        self._carpeta_perfil.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._carpeta_perfil),
                headless=False,
            )
        except Exception as error:
            self._playwright.stop()
            self._playwright = None
            raise nav.ErrorRecurso(
                f"no se pudo abrir Chromium visible para Alibaba "
                f"(¿'playwright install chromium' corrio bien?): {error}"
            ) from error
        self._page = (
            self._context.pages[0] if self._context.pages
            else self._context.new_page()
        )

    def _ir_a_interno(self, url: str) -> None:
        self._asegurar_contexto()
        if self._url_actual == url:
            return
        try:
            self._page.goto(
                url, timeout=nav.TIMEOUT_NAVEGACION_MS, wait_until="domcontentloaded"
            )
        except Exception as error:
            raise nav.ErrorRecurso(f"no se pudo abrir '{url}': {error}") from error
        self._url_actual = url

    def _texto_interno(self) -> str:
        try:
            return self._page.inner_text("body")
        except Exception as error:
            raise nav.ErrorRecurso(
                f"no se pudo leer el texto de la pagina: {error}"
            ) from error

    def _imagenes_crudas_interno(self) -> list[str]:
        try:
            return self._page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.currentSrc || e.getAttribute('src') || '')",
            )
        except Exception as error:
            raise nav.ErrorRecurso(
                f"no se pudieron leer las imagenes de la pagina: {error}"
            ) from error

    def _video_crudo_interno(self) -> tuple[list[str], list[str]]:
        try:
            crudas_archivo = self._page.eval_on_selector_all(
                "video, video source",
                "els => els.map(e => e.currentSrc || e.getAttribute('src') || '')",
            )
            crudas_iframe = self._page.eval_on_selector_all(
                "iframe",
                "els => els.map(e => e.getAttribute('src') || '')",
            )
        except Exception as error:
            raise nav.ErrorRecurso(
                f"no se pudo leer el video de la pagina: {error}"
            ) from error
        return crudas_archivo, crudas_iframe

    def _cerrar_interno(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
