"""Pruebas de marca_agua. Offline: no corren ffmpeg/ffprobe reales
(herramientas externas pesadas). Solo se prueba con Pillow puro la logica de
recorte del logo (recortar_logo_a_contenido); _dimensiones_video/
_preparar_logo_redimensionado/generar_a_archivo (que si llaman a ffmpeg/
ffprobe) se verifican a mano/CLI contra un video real, igual que
quitar_fondo/generar_recorte en recortar_producto.py y generar_a_archivo en
preparar_video_producto.py y ensamblar_video_producto.py.
"""

import unittest

from PIL import Image

import marca_agua as ma


def _imagen_rgba(ancho, alto, color=(0, 0, 0, 0)):
    return Image.new("RGBA", (ancho, alto), color)


class PruebasRecortarLogoAContenido(unittest.TestCase):
    def test_recorta_al_bounding_box_del_contenido_no_transparente(self):
        lienzo = _imagen_rgba(200, 100)
        # Un bloque opaco de 50x30 en una zona centrada-izquierda del
        # lienzo, como el logo real dentro de "Ekipon, marca de agua .png".
        bloque_opaco = _imagen_rgba(50, 30, (255, 0, 0, 255))
        lienzo.paste(bloque_opaco, (20, 40))

        recortado = ma.recortar_logo_a_contenido(lienzo)

        self.assertEqual(recortado.size, (50, 30))

    def test_el_recorte_no_incluye_margen_transparente(self):
        lienzo = _imagen_rgba(200, 100)
        bloque_opaco = _imagen_rgba(10, 10, (255, 0, 0, 255))
        lienzo.paste(bloque_opaco, (95, 45))

        recortado = ma.recortar_logo_a_contenido(lienzo)

        # El lienzo es mucho mas grande que el bloque: si el recorte
        # funcionara mal (ej. devolviera el lienzo entero) esto fallaria.
        self.assertLess(recortado.width, lienzo.width)
        self.assertLess(recortado.height, lienzo.height)
        self.assertEqual(recortado.size, (10, 10))

    def test_contenido_pegado_a_un_borde_se_recorta_justo_a_ese_borde(self):
        lienzo = _imagen_rgba(100, 100)
        bloque_opaco = _imagen_rgba(20, 20, (0, 255, 0, 255))
        lienzo.paste(bloque_opaco, (0, 0))  # pegado a la esquina (0, 0)

        recortado = ma.recortar_logo_a_contenido(lienzo)

        self.assertEqual(recortado.size, (20, 20))

    def test_modo_sin_canal_alfa_lanza_value_error(self):
        lienzo_rgb = Image.new("RGB", (50, 50), (255, 255, 255))
        with self.assertRaises(ValueError):
            ma.recortar_logo_a_contenido(lienzo_rgb)

    def test_imagen_completamente_transparente_lanza_value_error(self):
        lienzo_vacio = _imagen_rgba(50, 50)  # todo (0,0,0,0)
        with self.assertRaises(ValueError):
            ma.recortar_logo_a_contenido(lienzo_vacio)


class PruebasConstantes(unittest.TestCase):
    def test_ancho_marca_agua_frac_es_una_fraccion_valida(self):
        self.assertGreater(ma.ANCHO_MARCA_AGUA_FRAC, 0)
        self.assertLess(ma.ANCHO_MARCA_AGUA_FRAC, 1)

    def test_margen_marca_agua_frac_es_una_fraccion_valida(self):
        self.assertGreater(ma.MARGEN_MARCA_AGUA_FRAC, 0)
        self.assertLess(ma.MARGEN_MARCA_AGUA_FRAC, 1)

    def test_ruta_logo_por_defecto_apunta_al_archivo_fijo(self):
        self.assertEqual(ma.RUTA_LOGO_DEFECTO.name, "Ekipon, marca de agua .png")


if __name__ == "__main__":
    unittest.main()
