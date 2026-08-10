"""Pruebas de orquestador.py. Offline: no corren ffmpeg, no llaman a
ElevenLabs/Anthropic/WooCommerce reales (ver docstrings de los modulos que
orquesta — mismo criterio del proyecto: esas integraciones se verifican a
mano/CLI, no con mocks). Se prueba:

- Las funciones puras de nombres de archivo y de codigo de proveedor.
- El CHECKPOINT 1 (colador) de punta a punta: como revisar_listo_para_
  publicar() es pura y el chequeo pasa ANTES de tocar ffmpeg/red, se puede
  correr ejecutar_pipeline() real contra una ficha en disco que dispara el
  checkpoint, sin mockear nada.
- La interpretacion del CHECKPOINT 2 (categoria sin match), aislada en
  _interpretar_fallo_publicacion(): logica pura, no requiere correr el
  pipeline completo (que si necesita ffmpeg/ElevenLabs/WooCommerce reales)
  para probar la DECISION de que codigo_salida=1 es justo ese checkpoint.
"""

import json
import tempfile
import unittest
from pathlib import Path

import orquestador


class PruebasNombresDeArchivo(unittest.TestCase):
    def test_ruta_recorte_seniala_convencion_de_publicador(self):
        carpeta = Path("/tmp/caso")
        self.assertEqual(
            orquestador._ruta_recorte(carpeta, "4212"),
            carpeta / "4212_recorte.png",
        )

    def test_ruta_clip_original(self):
        carpeta = Path("/tmp/caso")
        self.assertEqual(
            orquestador._ruta_clip_original(carpeta, "4212"),
            carpeta / "4212_clip_original.mp4",
        )

    def test_carpeta_trabajo(self):
        carpeta = Path("/tmp/caso")
        self.assertEqual(
            orquestador._carpeta_trabajo(carpeta, "4212"),
            carpeta / "4212_video_trabajo",
        )


class PruebasCodigoProveedor(unittest.TestCase):
    def test_extrae_codigo_presente(self):
        ficha = {"entrada_original": {"codigo_proveedor": " 4212 "}}
        self.assertEqual(orquestador._codigo_proveedor(ficha), "4212")

    def test_ausente_devuelve_none(self):
        self.assertIsNone(orquestador._codigo_proveedor({}))
        self.assertIsNone(orquestador._codigo_proveedor({"entrada_original": {}}))
        self.assertIsNone(
            orquestador._codigo_proveedor({"entrada_original": {"codigo_proveedor": "   "}})
        )


class PruebasCheckpointColador(unittest.TestCase):
    """Checkpoint 1 de punta a punta: sin mocks, porque revisar_listo_para_
    publicar() es logica pura que corre ANTES que cualquier paso de red o
    ffmpeg. Cubre el caso "falta el codigo_proveedor" (error real, antes del
    colador) y el caso REVISAR real (colador dispara)."""

    def _escribir_ficha(self, carpeta: Path, datos: dict) -> Path:
        ruta = carpeta / "ficha.json"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        return ruta

    def test_ficha_inexistente_es_error_no_checkpoint(self):
        mensajes = []
        resultado = orquestador.ejecutar_pipeline(
            Path("no_existe_esta_ficha_de_prueba.json"), mensajes.append
        )
        self.assertEqual(resultado["estado"], "error")
        self.assertIn("motivo", resultado)

    def test_sin_codigo_proveedor_es_error_antes_del_colador(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            carpeta = Path(carpeta_str)
            ruta = self._escribir_ficha(carpeta, {"entrada_original": {}})
            mensajes = []
            resultado = orquestador.ejecutar_pipeline(ruta, mensajes.append)
            self.assertEqual(resultado["estado"], "error")
            self.assertIn("codigo_proveedor", resultado["motivo"])

    def test_ficha_con_advertencias_dispara_checkpoint_revisar(self):
        # identificacion_del_producto.advertencias no vacio -> motivo real
        # segun revisor_publicacion._revisar_identificacion. No hace falta
        # una ficha completa: el colador trabaja sobre el dict crudo.
        ficha = {
            "entrada_original": {"codigo_proveedor": "TEST-1"},
            "identificacion_del_producto": {
                "resultado": "IDENTIFICADO",
                "advertencias": ["specs sin confirmar con el proveedor"],
            },
            "producto": {},
            "ficha_tecnica": {},
            "multimedia": {},
            "campos_por_confirmar": [],
        }
        with tempfile.TemporaryDirectory() as carpeta_str:
            carpeta = Path(carpeta_str)
            ruta = self._escribir_ficha(carpeta, ficha)
            mensajes = []
            resultado = orquestador.ejecutar_pipeline(ruta, mensajes.append)
            self.assertEqual(resultado["estado"], "revisar")
            self.assertEqual(resultado["etapa"], "colador")
            self.assertTrue(resultado["motivos"])
            self.assertTrue(any("advertencia" in m.lower() for m in resultado["motivos"]))
            # Se notifico el motivo por publicar_notificacion, no solo se
            # devolvio en el dict (asi la pagina lo muestra en vivo).
            self.assertTrue(any("advertencia" in m.lower() or "REVISAR" in m for m in mensajes))

    def test_ficha_lista_pero_sin_plan_galeria_es_error_real(self):
        # Una ficha que pasa el colador (sin motivos) pero no trae
        # multimedia.plan_galeria.imagen_base: se detiene con un error real
        # (no un checkpoint), sin intentar tocar ffmpeg/red. Esto tambien
        # prueba que el pipeline arranca los pasos reales tras el colador.
        ficha = {
            "entrada_original": {"codigo_proveedor": "TEST-2"},
            "identificacion_del_producto": {"resultado": "IDENTIFICADO"},
            "producto": {"es_motorizado": False},
            "ficha_tecnica": {},
            "multimedia": {
                "galeria_tomas": {"dimensiones": {"alto": "1 m", "ancho": "1 m", "fondo": "1 m"}},
            },
            "campos_por_confirmar": [],
        }
        with tempfile.TemporaryDirectory() as carpeta_str:
            carpeta = Path(carpeta_str)
            ruta = self._escribir_ficha(carpeta, ficha)
            mensajes = []
            resultado = orquestador.ejecutar_pipeline(ruta, mensajes.append)
            self.assertEqual(resultado["estado"], "error")
            self.assertIn("imagen_base", resultado["motivo"])


class PruebasInterpretarFalloPublicacion(unittest.TestCase):
    """Checkpoint 2 (categoria sin match): logica pura, aislada de la
    corrida real del pipeline."""

    def test_con_sugerencias_es_checkpoint_revisar(self):
        resultado_publicacion = {
            "categoria_buscada": "Compresor",
            "categoria_sugerencias": ["Compresores", "Compresores industriales"],
        }
        resultado = orquestador._interpretar_fallo_publicacion(resultado_publicacion)
        self.assertEqual(resultado["estado"], "revisar")
        self.assertEqual(resultado["etapa"], "categoria")
        self.assertEqual(
            resultado["categoria_sugerencias"],
            ["Compresores", "Compresores industriales"],
        )
        self.assertTrue(any("Compresor" in m for m in resultado["motivos"]))

    def test_sin_categoria_sugerencias_es_error_real(self):
        # codigo_salida=1 por CUALQUIER otro motivo (slug vacio, ficha
        # invalida detectada tarde, refrescar-galeria sin imagenes...): NO
        # debe interpretarse como el checkpoint de categoria.
        resultado = orquestador._interpretar_fallo_publicacion({})
        self.assertEqual(resultado["estado"], "error")
        self.assertIn("motivo", resultado)

    def test_categoria_sin_sugerencias_igual_es_checkpoint(self):
        # Categoria no matchea pero el arbol de la tienda no tenia nada
        # parecido: sigue siendo el checkpoint de categoria, solo que sin
        # sugerencias que ofrecer.
        resultado = orquestador._interpretar_fallo_publicacion(
            {"categoria_buscada": "Categoria Rara", "categoria_sugerencias": []}
        )
        self.assertEqual(resultado["estado"], "revisar")
        self.assertEqual(resultado["etapa"], "categoria")


if __name__ == "__main__":
    unittest.main()
