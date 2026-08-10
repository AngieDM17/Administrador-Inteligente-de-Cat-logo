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


if __name__ == "__main__":
    unittest.main()
