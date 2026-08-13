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
from unittest import mock

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


class PruebasDescripcionYoutube(unittest.TestCase):
    def test_incluye_caracteristicas_y_frase_de_marca(self):
        ficha = {"caracteristicas": ["Motor 2HP", "Tanque 50L", "  ", 123]}
        descripcion = orquestador._descripcion_youtube(ficha)
        self.assertIn("Motor 2HP", descripcion)
        self.assertIn("Tanque 50L", descripcion)
        self.assertIn("Ekipon.co", descripcion)
        # Entradas no-string o vacias no ensucian la descripcion.
        self.assertNotIn("123", descripcion)

    def test_sin_caracteristicas_solo_trae_la_frase_de_marca(self):
        descripcion = orquestador._descripcion_youtube({})
        self.assertIn("Ekipon.co", descripcion)


class PruebasResolverVideoAPublicar(unittest.TestCase):
    """_resolver_video_a_publicar(): decide YouTube vs. WordPress. Se mockea
    orquestador.youtube_uploader entero (disponible/subir_video) -- ninguna
    de estas pruebas toca la red ni sube nada real."""

    def _ficha(self):
        return {
            "entrada_original": {"codigo_proveedor": "TEST-YT"},
            "producto": {"nombre_propuesto": "PRODUCTO DE PRUEBA"},
            "multimedia": {},
        }

    def test_no_disponible_devuelve_ruta_video_final_sin_tocar_la_ficha(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_ficha = Path(carpeta_str) / "ficha.json"
            ficha = self._ficha()
            ruta_ficha.write_text(json.dumps(ficha), encoding="utf-8")
            ruta_video_final = Path(carpeta_str) / "video_final.mp4"
            mensajes = []
            with mock.patch.object(orquestador, "youtube_uploader") as falso:
                falso.disponible.return_value = False
                resultado = orquestador._resolver_video_a_publicar(
                    ficha, ruta_ficha, ruta_video_final, mensajes.append,
                )
            self.assertEqual(resultado, ruta_video_final)
            falso.subir_video.assert_not_called()
            self.assertEqual(ficha["multimedia"], {})

    def test_exito_guarda_url_en_la_ficha_y_devuelve_none(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_ficha = Path(carpeta_str) / "ficha.json"
            ficha = self._ficha()
            ruta_ficha.write_text(json.dumps(ficha), encoding="utf-8")
            ruta_video_final = Path(carpeta_str) / "video_final.mp4"
            mensajes = []
            with mock.patch.object(orquestador, "youtube_uploader") as falso:
                falso.disponible.return_value = True
                falso.subir_video.return_value = {
                    "video_id": "XYZ", "url": "https://www.youtube.com/watch?v=XYZ",
                }
                resultado = orquestador._resolver_video_a_publicar(
                    ficha, ruta_ficha, ruta_video_final, mensajes.append,
                )
            self.assertIsNone(resultado)
            self.assertEqual(
                ficha["multimedia"]["video_youtube"],
                "https://www.youtube.com/watch?v=XYZ",
            )
            # Se guardo en disco: publicador.ejecutar() vuelve a leer la
            # ficha del archivo, no del dict en memoria (ver _guardar_ficha).
            en_disco = json.loads(ruta_ficha.read_text(encoding="utf-8"))
            self.assertEqual(
                en_disco["multimedia"]["video_youtube"],
                "https://www.youtube.com/watch?v=XYZ",
            )
            self.assertTrue(any("YouTube" in m for m in mensajes))

    def test_falla_la_subida_cae_a_wordpress_sin_tumbar_nada(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_ficha = Path(carpeta_str) / "ficha.json"
            ficha = self._ficha()
            ruta_ficha.write_text(json.dumps(ficha), encoding="utf-8")
            ruta_video_final = Path(carpeta_str) / "video_final.mp4"
            mensajes = []
            with mock.patch.object(orquestador, "youtube_uploader") as falso:
                falso.disponible.return_value = True
                falso.subir_video.side_effect = RuntimeError("cuota agotada")
                resultado = orquestador._resolver_video_a_publicar(
                    ficha, ruta_ficha, ruta_video_final, mensajes.append,
                )
            self.assertEqual(resultado, ruta_video_final)
            self.assertEqual(ficha["multimedia"], {})
            self.assertTrue(any("cuota agotada" in m for m in mensajes))
            # La ficha en disco NO cambio: no se guardo nada tras el fallo.
            en_disco = json.loads(ruta_ficha.read_text(encoding="utf-8"))
            self.assertEqual(en_disco["multimedia"], {})


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

    def test_ficha_con_advertencias_ya_no_frena_solo_se_notifica(self):
        # Decision de Angie (11-ago-2026): el colador ya NO detiene el
        # pipeline -- revisar_listo_para_publicar() sigue corriendo y sus
        # motivos se notifican (para que la pagina los muestre en vivo y
        # publicador.py los guarde en el borrador via motivos_revision),
        # pero el pipeline CONTINUA. Con esta ficha minima (sin
        # multimedia.plan_galeria.imagen_base) el resultado final es el
        # MISMO error real que ya prueba test_ficha_lista_pero_sin_plan_
        # galeria_es_error_real (no un checkpoint "revisar"): asi se
        # confirma que de verdad se siguio de largo tras el colador, en vez
        # de pararse ahi.
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
            self.assertNotEqual(resultado["estado"], "revisar")
            self.assertEqual(resultado["estado"], "error")
            self.assertIn("plan_galeria", resultado["motivo"])
            # El motivo del colador SI se notifico (la pagina lo muestra en
            # vivo), aunque no haya frenado el pipeline.
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
