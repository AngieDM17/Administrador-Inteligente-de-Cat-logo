"""Pruebas del generador de callouts (partes senaladas). Offline."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import generador_callouts as gc


def _recorte(w=100, h=140):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([20, 20, w - 20, h - 20], fill=(80, 140, 200, 255))
    return img


class PruebasColocar(unittest.TestCase):
    def test_recorte_entra_en_la_zona_derecha(self):
        _, (px, py, pw, ph) = gc._colocar_recorte(_recorte(200, 300), 700)
        self.assertLessEqual(pw, int(700 * 0.98) - int(700 * 0.42))
        self.assertLessEqual(ph, int(700 * 0.94) - int(700 * 0.06))
        self.assertGreaterEqual(px, int(700 * 0.42))


class PruebasCallouts(unittest.TestCase):
    def _con_recorte(self, datos, nombre="o.webp"):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rec = d / "r.png"
            _recorte().save(rec)
            return gc.generar_callouts(rec, datos, d / nombre)

    def test_tamano_y_modo(self):
        img = self._con_recorte({"callouts": [{"label": "Uno", "point": [0.5, 0.3]}]})
        self.assertEqual(img.size, (1080, 1080))
        self.assertEqual(img.mode, "RGBA")

    def test_sin_callouts_no_rompe(self):
        self.assertEqual(self._con_recorte({"callouts": []}).size, (1080, 1080))

    def test_determinista(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rec = d / "r.png"
            _recorte().save(rec)
            datos = {"callouts": [{"label": "Motor eléctrico", "point": [0.6, 0.4]}]}
            a = gc.generar_callouts(rec, datos, d / "a.webp")
            b = gc.generar_callouts(rec, datos, d / "b.webp")
            self.assertEqual(a.tobytes(), b.tobytes())


class PruebasDatosDeFicha(unittest.TestCase):
    def test_solo_entran_las_partes_con_posicion(self):
        ficha = {"multimedia": {"galeria_tomas": {"callouts": [
            {"label": "Con punto", "point": [0.5, 0.5]},
            {"label": "Sin punto", "point": None},
        ]}}}
        datos = gc.datos_de_ficha(ficha)
        self.assertEqual([c["label"] for c in datos["callouts"]], ["Con punto"])

    def test_ficha_sin_tomas_no_rompe(self):
        self.assertEqual(gc.datos_de_ficha({}), {"callouts": []})


if __name__ == "__main__":
    unittest.main()
