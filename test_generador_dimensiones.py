"""Pruebas del generador de dimensiones/tamano. Offline."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import generador_dimensiones as gd


def _recorte(w=100, h=140):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([20, 20, w - 20, h - 20], fill=(80, 140, 200, 255))
    return img


class PruebasDimensiones(unittest.TestCase):
    def _generar(self, datos, nombre="o.webp"):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rec = d / "r.png"
            _recorte().save(rec)
            return gd.generar_dimensiones(rec, datos, d / nombre)

    def test_tamano_y_modo(self):
        img = self._generar({"alto": "85 cm", "ancho": "43,5 cm", "peso": "20 kg"})
        self.assertEqual(img.size, (1080, 1080))
        self.assertEqual(img.mode, "RGBA")

    def test_datos_vacios_no_rompe(self):
        # Sin ninguna medida, igual compone el lienzo con el producto.
        self.assertEqual(self._generar({}).size, (1080, 1080))

    def test_determinista(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rec = d / "r.png"
            _recorte().save(rec)
            datos = {"alto": "85 cm", "ancho": "43,5 cm", "peso": "20 kg", "fondo": "46,5 cm"}
            a = gd.generar_dimensiones(rec, datos, d / "a.webp")
            b = gd.generar_dimensiones(rec, datos, d / "b.webp")
            self.assertEqual(a.tobytes(), b.tobytes())


class PruebasDatosDeFicha(unittest.TestCase):
    def test_toma_medidas_de_la_ficha_y_omite_vacias(self):
        ficha = {"multimedia": {"galeria_tomas": {"dimensiones": {
            "alto": "85 cm", "ancho": None, "peso": "20 kg"}}}}
        self.assertEqual(gd.datos_de_ficha(ficha), {"alto": "85 cm", "peso": "20 kg"})

    def test_ficha_sin_tomas_no_rompe(self):
        self.assertEqual(gd.datos_de_ficha({}), {})


if __name__ == "__main__":
    unittest.main()
