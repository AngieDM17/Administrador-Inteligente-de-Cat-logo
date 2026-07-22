"""Pruebas de recortar_producto. Offline: no cargan rembg (solo se prueban las
funciones puras; quitar_fondo/generar_recorte necesitan el modelo y no se tocan).
"""

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import recortar_producto as rp


def _recorte(w=100, h=100):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([30, 20, 70, 80], fill=(200, 50, 50, 255))
    return img


class PruebasRecorteContenido(unittest.TestCase):
    def test_recorta_a_la_caja_del_contenido(self):
        out = rp.recortar_a_contenido(_recorte(100, 100), margen=0.0)
        self.assertEqual(out.size, (41, 61))  # bbox del rectangulo opaco

    def test_margen_agranda_la_caja(self):
        out = rp.recortar_a_contenido(_recorte(100, 100), margen=0.2)
        self.assertGreater(out.width, 41)
        self.assertGreater(out.height, 61)

    def test_todo_transparente_no_recorta(self):
        vacio = Image.new("RGBA", (50, 40), (0, 0, 0, 0))
        self.assertEqual(rp.recortar_a_contenido(vacio).size, (50, 40))


class PruebasFondo(unittest.TestCase):
    def test_sobre_fondo_aplana_a_rgb(self):
        out = rp._sobre_fondo(_recorte(20, 20), (255, 255, 255, 255))
        self.assertEqual(out.mode, "RGB")
        self.assertEqual(out.getpixel((0, 0)), (255, 255, 255))  # esquina transparente


class PruebasPreview(unittest.TestCase):
    def test_preview_se_genera(self):
        with tempfile.TemporaryDirectory() as d:
            salida = Path(d) / "prev.png"
            out = rp.generar_preview(_recorte(), _recorte(), salida)
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
