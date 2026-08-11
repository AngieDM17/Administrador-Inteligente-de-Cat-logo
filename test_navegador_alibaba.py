"""Pruebas de navegador_alibaba.py. Offline y sin Playwright real: NUNCA se
lanza un Chromium visible aca -- headless=False colgaria esta corrida
esperando una interaccion humana que jamas llega en este entorno. Toda
`SesionAlibaba._asegurar_contexto` se monkeypatchea para instalar una pagina
falsa en vez de abrir un browser real.

Se prueba SOLO la logica pura de la clase:

- La PRIMERA navegacion de una sesion pausa en evento_continuar.wait() y
  publica un mensaje con el prefijo PREFIJO_ESPERANDO_CONFIRMACION; las
  siguientes NO vuelven a pausar (sea cual sea la tool -- navegar,
  extraer_imagenes o extraer_video -- la que dispare esa primera apertura).
- Pagina vacia tras la confirmacion -> ErrorRecurso (chequeo simple de
  contenido real, no una heuristica de captcha).
- extraer_imagenes/extraer_video filtran con el MISMO criterio que
  herramientas_navegador.py (funciones reusadas, no duplicadas).
- descargar_imagen/descargar_video delegan en herramientas_navegador.py.
- cerrar() no revienta si nunca se abrio un contexto real.
"""

import threading
import unittest
from unittest import mock

import herramientas_navegador as nav
import navegador_alibaba as na


class _PaginaFalsa:
    """Doble de prueba de una playwright.sync_api.Page: solo los metodos
    que SesionAlibaba realmente llama."""

    def __init__(self, texto="Producto Alibaba real", imagenes=None,
                 videos=None, iframes=None):
        self.url = None
        self._texto = texto
        self._imagenes = imagenes or []
        self._videos = videos or []
        self._iframes = iframes or []

    def goto(self, url, timeout=None, wait_until=None):
        self.url = url

    def inner_text(self, selector):
        return self._texto

    def eval_on_selector_all(self, selector, script):
        if selector.startswith("img"):
            return self._imagenes
        if selector.startswith("video"):
            return self._videos
        if selector.startswith("iframe"):
            return self._iframes
        return []


def _sesion_con_pagina_falsa(pagina, evento=None, mensajes=None):
    """SesionAlibaba con _asegurar_contexto parchado para instalar
    `pagina` directo, sin tocar Playwright real."""
    sesion = na.SesionAlibaba(
        publicar_notificacion=(mensajes.append if mensajes is not None else lambda m: None),
        evento_continuar=evento if evento is not None else threading.Event(),
    )

    def _asegurar_contexto_falsa():
        sesion._page = pagina

    sesion._asegurar_contexto = _asegurar_contexto_falsa
    return sesion


class PruebasPrimeraNavegacionPausa(unittest.TestCase):
    def test_primera_navegacion_pausa_y_avisa_con_el_prefijo(self):
        evento = threading.Event()
        evento.set()  # Ya "resuelto" de entrada: el test no cuelga.
        mensajes = []
        sesion = _sesion_con_pagina_falsa(_PaginaFalsa(), evento, mensajes)

        texto = sesion.navegar("https://www.alibaba.com/product-detail/x.html")

        self.assertEqual(texto, "Producto Alibaba real")
        self.assertTrue(
            any(m.startswith(na.PREFIJO_ESPERANDO_CONFIRMACION) for m in mensajes)
        )
        self.assertFalse(sesion._primera_navegacion)

    def test_segunda_navegacion_no_vuelve_a_pausar(self):
        evento = threading.Event()
        evento.set()
        mensajes = []
        sesion = _sesion_con_pagina_falsa(_PaginaFalsa(), evento, mensajes)

        sesion.navegar("https://www.alibaba.com/product-detail/x.html")
        mensajes.clear()
        sesion.navegar("https://www.alibaba.com/product-detail/y.html")

        self.assertEqual(mensajes, [])

    def test_extraer_imagenes_dispara_la_pausa_si_es_la_primera_apertura(self):
        # No importa CUAL tool dispare la primera apertura de pagina de la
        # sesion -- navegar, extraer_imagenes o extraer_video, todas pasan
        # por el mismo _asegurar_pagina.
        evento = threading.Event()
        evento.set()
        mensajes = []
        pagina = _PaginaFalsa(imagenes=["https://img.alibaba.com/foto1.jpg"])
        sesion = _sesion_con_pagina_falsa(pagina, evento, mensajes)

        sesion.extraer_imagenes("https://www.alibaba.com/product-detail/x.html")

        self.assertTrue(
            any(m.startswith(na.PREFIJO_ESPERANDO_CONFIRMACION) for m in mensajes)
        )

    def test_pagina_vacia_tras_confirmar_lanza_error_recurso(self):
        evento = threading.Event()
        evento.set()
        sesion = _sesion_con_pagina_falsa(_PaginaFalsa(texto="   "), evento)

        with self.assertRaises(nav.ErrorRecurso):
            sesion.navegar("https://www.alibaba.com/product-detail/x.html")


class PruebasExtraerImagenesYVideo(unittest.TestCase):
    def test_extraer_imagenes_filtra_igual_que_herramientas_navegador(self):
        pagina = _PaginaFalsa(imagenes=[
            "https://img.alibaba.com/foto1.jpg",
            "https://img.alibaba.com/icono.svg",
            "data:image/png;base64,xxx",
        ])
        sesion = _sesion_con_pagina_falsa(pagina, evento=_evento_resuelto())

        urls = sesion.extraer_imagenes("https://www.alibaba.com/product-detail/x.html")

        self.assertEqual(urls, ["https://img.alibaba.com/foto1.jpg"])

    def test_extraer_video_detecta_archivo_real(self):
        pagina = _PaginaFalsa(videos=["https://cdn.alibaba.com/clip.mp4"])
        sesion = _sesion_con_pagina_falsa(pagina, evento=_evento_resuelto())

        resultado = sesion.extraer_video("https://www.alibaba.com/product-detail/x.html")

        self.assertEqual(
            resultado, {"tipo": "archivo", "url": "https://cdn.alibaba.com/clip.mp4"}
        )

    def test_extraer_video_detecta_embed_youtube(self):
        pagina = _PaginaFalsa(iframes=["https://www.youtube.com/embed/abc123"])
        sesion = _sesion_con_pagina_falsa(pagina, evento=_evento_resuelto())

        resultado = sesion.extraer_video("https://www.alibaba.com/product-detail/x.html")

        self.assertEqual(
            resultado, {"tipo": "embed", "url": "https://www.youtube.com/embed/abc123"}
        )

    def test_sin_video_devuelve_none(self):
        sesion = _sesion_con_pagina_falsa(_PaginaFalsa(), evento=_evento_resuelto())
        self.assertIsNone(
            sesion.extraer_video("https://www.alibaba.com/product-detail/x.html")
        )


def _evento_resuelto() -> threading.Event:
    evento = threading.Event()
    evento.set()
    return evento


class PruebasDescargaDelega(unittest.TestCase):
    def test_descargar_imagen_delega_en_herramientas_navegador(self):
        sesion = na.SesionAlibaba(
            publicar_notificacion=lambda m: None, evento_continuar=threading.Event(),
        )
        with mock.patch.object(nav, "descargar_imagen", return_value="ok") as parche:
            resultado = sesion.descargar_imagen("https://x.com/a.jpg", "/tmp/a.jpg")
        parche.assert_called_once_with("https://x.com/a.jpg", "/tmp/a.jpg")
        self.assertEqual(resultado, "ok")

    def test_descargar_video_delega_en_herramientas_navegador(self):
        sesion = na.SesionAlibaba(
            publicar_notificacion=lambda m: None, evento_continuar=threading.Event(),
        )
        with mock.patch.object(nav, "descargar_video", return_value="ok") as parche:
            resultado = sesion.descargar_video("https://x.com/a.mp4", "/tmp/a.mp4")
        parche.assert_called_once_with("https://x.com/a.mp4", "/tmp/a.mp4")
        self.assertEqual(resultado, "ok")


class PruebasCerrar(unittest.TestCase):
    def test_cerrar_sin_haber_abierto_contexto_no_revienta(self):
        sesion = na.SesionAlibaba(
            publicar_notificacion=lambda m: None, evento_continuar=threading.Event(),
        )
        sesion.cerrar()  # No deberia lanzar nada.


if __name__ == "__main__":
    unittest.main()
