"""Pruebas de recortar_producto. Offline: no cargan rembg (solo se prueban las
funciones puras; quitar_fondo/generar_recorte necesitan el modelo y no se tocan).
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
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


class PruebasLimpiarHalo(unittest.TestCase):
    """El halo blanco = borde de alfa parcial y color casi-blanco (fondo que
    rembg no termino de quitar). Se elimina sin tocar el producto."""

    def _imagen(self):
        a = np.zeros((5, 5, 4), dtype=np.uint8)
        a[0, 0] = [30, 30, 30, 255]     # producto oscuro SOLIDO -> se mantiene
        a[1, 1] = [250, 250, 250, 120]  # HALO blanco parcial -> fuera
        a[2, 2] = [20, 20, 20, 120]     # cable oscuro parcial -> se mantiene
        a[3, 3] = [230, 230, 230, 255]  # marco plateado SOLIDO -> se mantiene
        a[4, 4] = [190, 190, 190, 120]  # HALO plateado parcial -> fuera (dip/chin)
        return Image.fromarray(a, "RGBA")

    def test_halo_blanco_parcial_se_vuelve_transparente(self):
        out = np.array(rp.limpiar_halo(self._imagen()))
        self.assertEqual(out[1, 1, 3], 0)

    def test_halo_plateado_parcial_se_vuelve_transparente(self):
        # El caso que Angie detecto en la dip/chin: fringe plateado (no blanco).
        out = np.array(rp.limpiar_halo(self._imagen()))
        self.assertEqual(out[4, 4, 3], 0)

    def test_producto_solido_no_se_erosiona(self):
        out = np.array(rp.limpiar_halo(self._imagen()))
        self.assertEqual(out[0, 0, 3], 255)   # oscuro solido
        self.assertEqual(out[3, 3, 3], 255)   # plateado solido (no es halo)

    def test_borde_oscuro_parcial_se_mantiene(self):
        # Un cable/eje fino tiene borde de alfa parcial pero NO es claro: intacto.
        out = np.array(rp.limpiar_halo(self._imagen()))
        self.assertEqual(out[2, 2, 3], 120)


if __name__ == "__main__":
    unittest.main()
