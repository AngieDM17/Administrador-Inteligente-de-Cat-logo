"""Pruebas de preparar_video_producto. Offline: no corren ffmpeg/ffprobe reales
(herramientas externas pesadas). Solo se prueba la logica pura que decide si
hace falta reescalar y la que arma el filtro de zoom extra (_filtro_zoom_
extra); _dimensiones_video/generar_a_archivo (que sí llaman a ffprobe/ffmpeg)
se verifican a mano/CLI contra clips reales, igual que quitar_fondo/generar_
recorte en recortar_producto.py.
"""

import unittest

import preparar_video_producto as pvp


class PruebasNecesitaReescalar(unittest.TestCase):
    def test_ya_en_1920x1080_no_hace_falta_reescalar(self):
        self.assertFalse(pvp.necesita_reescalar(1920, 1080))

    def test_vertical_720x1280_hace_falta_reescalar(self):
        self.assertTrue(pvp.necesita_reescalar(720, 1280))

    def test_mismo_ancho_alto_distinto_hace_falta_reescalar(self):
        self.assertTrue(pvp.necesita_reescalar(1920, 1081))

    def test_mismo_alto_ancho_distinto_hace_falta_reescalar(self):
        self.assertTrue(pvp.necesita_reescalar(1919, 1080))

    def test_otro_horizontal_hace_falta_reescalar(self):
        self.assertTrue(pvp.necesita_reescalar(1280, 720))


class PruebasFiltroZoomExtra(unittest.TestCase):
    def test_zoom_cero_no_recorta(self):
        # factor=1: la caja de recorte es del mismo tamaño que 1920x1080,
        # asi que el filtro es un no-op (recorta todo el cuadro y lo deja
        # igual). No es el caso que se usa en la practica (generar_a_archivo
        # ni siquiera llama a esta funcion si zoom_extra es 0), pero la
        # funcion tiene que devolver algo coherente igual.
        filtro = pvp._filtro_zoom_extra(0.0)
        self.assertIn("crop=1920:1080", filtro)
        self.assertIn("scale=1920:1080", filtro)

    def test_zoom_mayor_recorta_una_caja_mas_chica(self):
        filtro_chico = pvp._filtro_zoom_extra(0.10)
        filtro_grande = pvp._filtro_zoom_extra(0.20)

        def ancho_recorte(filtro):
            # filtro es "crop=W:H,scale=1920:1080"
            parte_crop = filtro.split(",")[0]
            return int(parte_crop.split("=")[1].split(":")[0])

        # A mas zoom_extra, la caja de recorte tiene que ser mas chica (se ve
        # menos del cuadro original, mas "acercado").
        self.assertLess(ancho_recorte(filtro_grande), ancho_recorte(filtro_chico))
        self.assertLess(ancho_recorte(filtro_chico), 1920)

    def test_siempre_termina_reescalando_a_1920x1080(self):
        for zoom in (0.0, 0.10, 0.15, 0.20, 0.30):
            filtro = pvp._filtro_zoom_extra(zoom)
            self.assertTrue(filtro.endswith("scale=1920:1080"))

    def test_dimensiones_de_recorte_siempre_pares(self):
        # ffmpeg con libx264/yuv420p exige dimensiones pares.
        for zoom in (0.05, 0.1, 0.15, 0.17, 0.23, 0.33):
            filtro = pvp._filtro_zoom_extra(zoom)
            parte_crop = filtro.split(",")[0]
            ancho, alto, _x, _y = parte_crop.split("=")[1].split(":")
            self.assertEqual(int(ancho) % 2, 0)
            self.assertEqual(int(alto) % 2, 0)

    def test_zoom_negativo_se_trata_como_cero(self):
        # max(0.0, zoom_extra) en la implementacion: un valor negativo no
        # agranda el recorte por error.
        self.assertEqual(pvp._filtro_zoom_extra(-0.5), pvp._filtro_zoom_extra(0.0))


if __name__ == "__main__":
    unittest.main()
