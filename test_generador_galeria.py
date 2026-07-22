"""Pruebas del generador de galeria. Offline, imagenes chicas en memoria."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import generador_galeria as gg


def _recorte(w=100, h=140):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([20, 20, w - 20, h - 20], fill=(80, 140, 200, 255))
    return img


class PruebasEnvolver(unittest.TestCase):
    def test_envuelve_por_ancho(self):
        f = ImageFont.truetype(gg.RUTA_FUENTE, 30)
        lineas = gg._envolver("una dos tres cuatro cinco seis siete ocho", f, 120)
        self.assertGreater(len(lineas), 1)

    def test_palabra_sola_no_se_pierde(self):
        f = ImageFont.truetype(gg.RUTA_FUENTE, 30)
        self.assertEqual(gg._envolver("superlargapalabra", f, 40), ["superlargapalabra"])


class PruebasHero(unittest.TestCase):
    def test_tamano_y_modo(self):
        img = gg.hero_producto(_recorte())
        self.assertEqual(img.size, (gg.LADO, gg.LADO))
        self.assertEqual(img.mode, "RGBA")


class PruebasTarjeta(unittest.TestCase):
    def test_tamano(self):
        self.assertEqual(gg.tarjeta_info("TITULO", ["uno", "dos"]).size, (1080, 1080))

    def test_determinista(self):
        a = gg.tarjeta_info("T", ["uno", "dos"])
        b = gg.tarjeta_info("T", ["uno", "dos"])
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_autofit_muchos_items_no_revienta(self):
        items = ["Item bastante largo numero %d con harto texto" % i for i in range(8)]
        self.assertEqual(gg.tarjeta_info("TITULO LARGO", items).size, (1080, 1080))


class PruebasGaleria(unittest.TestCase):
    def test_construir_galeria_hero_mas_tarjetas(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rec = d / "rec.png"
            _recorte().save(rec)
            datos = {"tarjetas": [
                {"slug": "a", "titulo": "A", "items": ["x"]},
                {"slug": "b", "titulo": "B", "items": ["y"]},
            ]}
            rutas = gg.construir_galeria(rec, datos, d / "out")
            self.assertEqual(len(rutas), 3)  # hero + 2 tarjetas
            for r in rutas:
                self.assertTrue(r.exists())
                with Image.open(r) as im:
                    self.assertEqual(im.size, (1080, 1080))

    def test_contact_sheet_se_genera(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            r1 = d / "1.webp"
            Image.new("RGB", (700, 700), (255, 255, 255)).save(r1, "WEBP")
            out = gg.contact_sheet([r1], d / "cs.png")
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
