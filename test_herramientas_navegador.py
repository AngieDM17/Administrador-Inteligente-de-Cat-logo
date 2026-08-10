"""Pruebas de herramientas_navegador.py. Offline: no abren Chromium ni tocan
la red real (ver docstring del modulo — NO se prueba con la red real en unit
tests, mismo criterio que voz_en_off.py/musica.py con sus servicios
externos). Se prueba:

- _es_imagen_de_producto: el filtro de URLs de imagen (logica pura).
- descargar_imagen: con httpx.get parcheado (sin red real), que el archivo
  se guarde atomico y que un error HTTP se traduzca a ErrorRecurso.
- extraer_imagenes: dedupe + absolutizacion + filtro, con Playwright
  simulado (un objeto falso con eval_on_selector_all), sin abrir un
  navegador real.
- _es_video_de_producto / _es_embed_youtube_o_vimeo: los filtros de video
  (logica pura).
- extraer_video: archivo real vs. embed de YouTube/Vimeo vs. nada, con
  Playwright simulado (mismo patron que extraer_imagenes).
- descargar_video: reusa descargar_archivo pero con el timeout de video
  (TIMEOUT_DESCARGA_VIDEO_SEGUNDOS), distinto al de foto.
"""

import unittest
from pathlib import Path
from unittest import mock

import herramientas_navegador as nav


class PruebasEsImagenDeProducto(unittest.TestCase):
    def test_extensiones_validas(self):
        for ext in ("jpg", "jpeg", "png", "webp", "gif", "bmp"):
            with self.subTest(ext=ext):
                self.assertTrue(nav._es_imagen_de_producto(f"https://x.com/foto.{ext}"))

    def test_extension_valida_con_query_string(self):
        self.assertTrue(nav._es_imagen_de_producto("https://x.com/foto.jpg?w=800&h=600"))

    def test_data_uri_se_rechaza(self):
        self.assertFalse(nav._es_imagen_de_producto("data:image/png;base64,AAAA"))

    def test_svg_se_rechaza(self):
        # Los iconos de UI casi siempre son SVG: no son fotos de producto.
        self.assertFalse(nav._es_imagen_de_producto("https://x.com/icono.svg"))

    def test_sin_extension_se_rechaza(self):
        self.assertFalse(nav._es_imagen_de_producto("https://x.com/imagen-dinamica"))

    def test_cadena_vacia_se_rechaza(self):
        self.assertFalse(nav._es_imagen_de_producto(""))


class PruebasDescargarImagen(unittest.TestCase):
    def test_guarda_el_contenido_en_ruta_destino(self):
        respuesta_falsa = mock.Mock()
        respuesta_falsa.content = b"contenido-binario-falso"
        respuesta_falsa.raise_for_status = mock.Mock()

        with mock.patch.object(nav.httpx, "get", return_value=respuesta_falsa) as get_falso:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                destino = Path(tmp) / "sub" / "4212_foto_1.jpg"
                resultado = nav.descargar_imagen("https://x.com/foto.jpg", destino)

                self.assertEqual(resultado, destino)
                self.assertTrue(destino.is_file())
                self.assertEqual(destino.read_bytes(), b"contenido-binario-falso")
                # No debe quedar el temporal colgado.
                self.assertFalse((destino.with_name(destino.name + ".tmp")).exists())
        get_falso.assert_called_once()

    def test_error_http_se_traduce_a_error_recurso(self):
        with mock.patch.object(
            nav.httpx, "get",
            side_effect=nav.httpx.HTTPError("boom"),
        ):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                destino = Path(tmp) / "foto.jpg"
                with self.assertRaises(nav.ErrorRecurso):
                    nav.descargar_imagen("https://x.com/foto.jpg", destino)


class PruebasExtraerImagenes(unittest.TestCase):
    """Simula Playwright con un objeto falso (browser/page) para probar la
    logica de dedupe/absolutizacion/filtro sin abrir Chromium real."""

    def test_dedupe_absolutiza_y_filtra(self):
        pagina_falsa = mock.Mock()
        pagina_falsa.eval_on_selector_all.return_value = [
            "/img/foto1.jpg",              # relativa -> se absolutiza
            "https://x.com/img/foto1.jpg", # misma imagen absoluta -> dedupe
            "https://x.com/img/foto2.png",
            "data:image/png;base64,AAAA",  # se descarta
            "https://x.com/icono.svg",     # se descarta
            "",                             # se descarta
        ]
        browser_falso = mock.Mock()

        with mock.patch.object(
            nav, "_abrir_pagina", return_value=(browser_falso, pagina_falsa),
        ), mock.patch.object(nav, "_navegador_headless") as navegador_falso:
            navegador_falso.return_value.__enter__ = mock.Mock(return_value=object())
            navegador_falso.return_value.__exit__ = mock.Mock(return_value=False)

            resultado = nav.extraer_imagenes("https://x.com/producto")

        self.assertEqual(
            resultado,
            ["https://x.com/img/foto1.jpg", "https://x.com/img/foto2.png"],
        )
        browser_falso.close.assert_called_once()


class PruebasEsVideoDeProducto(unittest.TestCase):
    def test_extensiones_validas(self):
        for ext in ("mp4", "webm", "mov", "m4v", "ogv"):
            with self.subTest(ext=ext):
                self.assertTrue(nav._es_video_de_producto(f"https://x.com/clip.{ext}"))

    def test_extension_valida_con_query_string(self):
        self.assertTrue(nav._es_video_de_producto("https://x.com/clip.mp4?token=abc"))

    def test_data_uri_se_rechaza(self):
        self.assertFalse(nav._es_video_de_producto("data:video/mp4;base64,AAAA"))

    def test_sin_extension_se_rechaza(self):
        self.assertFalse(nav._es_video_de_producto("https://x.com/video-dinamico"))

    def test_cadena_vacia_se_rechaza(self):
        self.assertFalse(nav._es_video_de_producto(""))

    def test_m3u8_no_es_archivo_valido(self):
        # Streaming adaptativo (lista de fragmentos), no "un archivo" -- ver
        # comentario junto a _EXTENSIONES_VIDEO_VALIDAS.
        self.assertFalse(nav._es_video_de_producto("https://x.com/manifest.m3u8"))


class PruebasEsEmbedYoutubeOVimeo(unittest.TestCase):
    def test_youtube_com(self):
        self.assertTrue(
            nav._es_embed_youtube_o_vimeo("https://www.youtube.com/embed/abc123")
        )

    def test_youtu_be(self):
        self.assertTrue(nav._es_embed_youtube_o_vimeo("https://youtu.be/abc123"))

    def test_vimeo(self):
        self.assertTrue(
            nav._es_embed_youtube_o_vimeo("https://player.vimeo.com/video/123")
        )

    def test_dominio_de_fabricante_no_es_embed(self):
        self.assertFalse(
            nav._es_embed_youtube_o_vimeo("https://www.fitnessmarket.com.co/video")
        )

    def test_dominio_que_contiene_youtube_como_substring_no_cuenta(self):
        # Mismo criterio que es_alibaba: hostname exacto, no substring.
        self.assertFalse(nav._es_embed_youtube_o_vimeo("https://notyoutube.com/x"))

    def test_cadena_vacia_se_rechaza(self):
        self.assertFalse(nav._es_embed_youtube_o_vimeo(""))


class PruebasDescargarVideo(unittest.TestCase):
    def test_usa_el_timeout_de_video_no_el_de_foto(self):
        respuesta_falsa = mock.Mock()
        respuesta_falsa.content = b"contenido-binario-falso"
        respuesta_falsa.raise_for_status = mock.Mock()

        with mock.patch.object(nav.httpx, "get", return_value=respuesta_falsa) as get_falso:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                destino = Path(tmp) / "9060C_clip_original.mp4"
                resultado = nav.descargar_video("https://x.com/clip.mp4", destino)

                self.assertEqual(resultado, destino)
                self.assertTrue(destino.is_file())
                self.assertEqual(destino.read_bytes(), b"contenido-binario-falso")

        get_falso.assert_called_once()
        _args, kwargs = get_falso.call_args
        self.assertEqual(kwargs["timeout"], nav.TIMEOUT_DESCARGA_VIDEO_SEGUNDOS)
        self.assertNotEqual(nav.TIMEOUT_DESCARGA_VIDEO_SEGUNDOS, nav.TIMEOUT_DESCARGA_SEGUNDOS)

    def test_error_http_se_traduce_a_error_recurso(self):
        with mock.patch.object(
            nav.httpx, "get",
            side_effect=nav.httpx.HTTPError("boom"),
        ):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                destino = Path(tmp) / "clip.mp4"
                with self.assertRaises(nav.ErrorRecurso):
                    nav.descargar_video("https://x.com/clip.mp4", destino)


class PruebasExtraerVideo(unittest.TestCase):
    """Simula Playwright con un objeto falso (mismo patron que
    PruebasExtraerImagenes) para probar la logica de deteccion sin abrir
    Chromium real. eval_on_selector_all se llama dos veces adentro de
    extraer_video (una para <video>/<source>, otra para <iframe>): el mock
    devuelve, en orden, la lista de "archivo" y despues la de "iframe"."""

    def _simular(self, crudas_archivo, crudas_iframe):
        pagina_falsa = mock.Mock()
        pagina_falsa.eval_on_selector_all.side_effect = [crudas_archivo, crudas_iframe]
        browser_falso = mock.Mock()
        return pagina_falsa, browser_falso

    def test_archivo_mp4_real_se_detecta(self):
        pagina_falsa, browser_falso = self._simular(
            ["/media/clip.mp4"], [],
        )
        with mock.patch.object(
            nav, "_abrir_pagina", return_value=(browser_falso, pagina_falsa),
        ), mock.patch.object(nav, "_navegador_headless") as navegador_falso:
            navegador_falso.return_value.__enter__ = mock.Mock(return_value=object())
            navegador_falso.return_value.__exit__ = mock.Mock(return_value=False)

            resultado = nav.extraer_video("https://x.com/producto")

        self.assertEqual(
            resultado, {"tipo": "archivo", "url": "https://x.com/media/clip.mp4"},
        )
        browser_falso.close.assert_called_once()

    def test_embed_youtube_se_detecta_cuando_no_hay_archivo_real(self):
        pagina_falsa, browser_falso = self._simular(
            [], ["https://www.youtube.com/embed/abc123"],
        )
        with mock.patch.object(
            nav, "_abrir_pagina", return_value=(browser_falso, pagina_falsa),
        ), mock.patch.object(nav, "_navegador_headless") as navegador_falso:
            navegador_falso.return_value.__enter__ = mock.Mock(return_value=object())
            navegador_falso.return_value.__exit__ = mock.Mock(return_value=False)

            resultado = nav.extraer_video("https://x.com/producto")

        self.assertEqual(
            resultado,
            {"tipo": "embed", "url": "https://www.youtube.com/embed/abc123"},
        )

    def test_archivo_real_tiene_prioridad_sobre_embed(self):
        pagina_falsa, browser_falso = self._simular(
            ["/media/clip.mp4"], ["https://vimeo.com/embed/123"],
        )
        with mock.patch.object(
            nav, "_abrir_pagina", return_value=(browser_falso, pagina_falsa),
        ), mock.patch.object(nav, "_navegador_headless") as navegador_falso:
            navegador_falso.return_value.__enter__ = mock.Mock(return_value=object())
            navegador_falso.return_value.__exit__ = mock.Mock(return_value=False)

            resultado = nav.extraer_video("https://x.com/producto")

        self.assertEqual(resultado["tipo"], "archivo")

    def test_nada_devuelve_none(self):
        pagina_falsa, browser_falso = self._simular([], [])
        with mock.patch.object(
            nav, "_abrir_pagina", return_value=(browser_falso, pagina_falsa),
        ), mock.patch.object(nav, "_navegador_headless") as navegador_falso:
            navegador_falso.return_value.__enter__ = mock.Mock(return_value=object())
            navegador_falso.return_value.__exit__ = mock.Mock(return_value=False)

            resultado = nav.extraer_video("https://x.com/producto")

        self.assertIsNone(resultado)

    def test_iframe_de_otro_sitio_no_cuenta_como_embed(self):
        # Un iframe de mapa/chat embebido en la pagina no es un video: no
        # debe confundirse con un embed de YouTube/Vimeo.
        pagina_falsa, browser_falso = self._simular(
            [], ["https://maps.google.com/embed?x=1"],
        )
        with mock.patch.object(
            nav, "_abrir_pagina", return_value=(browser_falso, pagina_falsa),
        ), mock.patch.object(nav, "_navegador_headless") as navegador_falso:
            navegador_falso.return_value.__enter__ = mock.Mock(return_value=object())
            navegador_falso.return_value.__exit__ = mock.Mock(return_value=False)

            resultado = nav.extraer_video("https://x.com/producto")

        self.assertIsNone(resultado)


if __name__ == "__main__":
    unittest.main()
