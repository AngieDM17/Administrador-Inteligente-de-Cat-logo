"""Pruebas de ensamblar_video_producto. Offline: no corren ffmpeg/ffprobe
reales (herramientas externas pesadas). Solo se prueba la logica pura: el
orden de los 4 tramos (rutas_tramos) y la validacion de archivos de entrada
(_verificar_archivos_entrada). _segmento_portada/_normalizar_tramo/
generar_a_archivo (que si llaman a ffmpeg) se verifican a mano/CLI contra un
video real, igual que quitar_fondo/generar_recorte en recortar_producto.py y
generar_a_archivo en preparar_video_producto.py.
"""

import tempfile
import unittest
from pathlib import Path

import ensamblar_video_producto as evp


class PruebasRutasTramos(unittest.TestCase):
    def test_orden_es_portada_clip_outro1_outro2(self):
        portada = Path("portada.png")
        clip = Path("clip.mp4")
        outro1 = Path("o1.mp4")
        outro2 = Path("o2.mp4")
        self.assertEqual(
            evp.rutas_tramos(portada, clip, outro1, outro2),
            [portada, clip, outro1, outro2],
        )

    def test_outros_caen_a_los_archivos_fijos_por_defecto(self):
        portada = Path("portada.png")
        clip = Path("clip.mp4")
        tramos = evp.rutas_tramos(portada, clip)
        self.assertEqual(tramos[0], portada)
        self.assertEqual(tramos[1], clip)
        self.assertEqual(tramos[2], evp.RUTA_OUTRO_1_DEFECTO)
        self.assertEqual(tramos[3], evp.RUTA_OUTRO_2_DEFECTO)

    def test_outro1_explicito_no_pisa_outro2_por_defecto(self):
        portada = Path("portada.png")
        clip = Path("clip.mp4")
        outro1_custom = Path("otro_outro1.mp4")
        tramos = evp.rutas_tramos(portada, clip, ruta_outro1=outro1_custom)
        self.assertEqual(tramos[2], outro1_custom)
        self.assertEqual(tramos[3], evp.RUTA_OUTRO_2_DEFECTO)


class PruebasVerificarArchivosEntrada(unittest.TestCase):
    def test_todos_existentes_no_lanza(self):
        with tempfile.TemporaryDirectory() as carpeta:
            rutas = []
            for nombre in ("a.png", "b.mp4", "c.mp4", "d.mp4"):
                ruta = Path(carpeta) / nombre
                ruta.write_bytes(b"x")
                rutas.append(ruta)
            evp._verificar_archivos_entrada(rutas)  # no debe lanzar

    def test_alguno_faltante_lanza_error_recurso(self):
        with tempfile.TemporaryDirectory() as carpeta:
            existe = Path(carpeta) / "existe.mp4"
            existe.write_bytes(b"x")
            falta = Path(carpeta) / "no_existe.mp4"
            with self.assertRaises(evp.ErrorRecurso) as contexto:
                evp._verificar_archivos_entrada([existe, falta])
            self.assertIn(str(falta), str(contexto.exception))

    def test_reporta_todos_los_faltantes_no_solo_el_primero(self):
        with tempfile.TemporaryDirectory() as carpeta:
            falta1 = Path(carpeta) / "falta1.mp4"
            falta2 = Path(carpeta) / "falta2.mp4"
            with self.assertRaises(evp.ErrorRecurso) as contexto:
                evp._verificar_archivos_entrada([falta1, falta2])
            mensaje = str(contexto.exception)
            self.assertIn(str(falta1), mensaje)
            self.assertIn(str(falta2), mensaje)


class PruebasConstantes(unittest.TestCase):
    def test_duracion_portada_es_positiva(self):
        self.assertGreater(evp.DURACION_PORTADA_SEGUNDOS, 0)

    def test_rutas_outro_por_defecto_apuntan_a_la_raiz_del_proyecto(self):
        self.assertEqual(evp.RUTA_OUTRO_1_DEFECTO.name, "AI ENERGY OUTRO.mp4")
        self.assertEqual(evp.RUTA_OUTRO_2_DEFECTO.name, "EKIPON OUTRO.mp4")


if __name__ == "__main__":
    unittest.main()
