"""Pruebas de agente_investigador.py. Offline: no llaman a la API real de
Anthropic ni corren el CLI de Claude Code ni Playwright (ver docstring del
modulo — el agente NO se prueba de punta a punta con la API real en unit
tests, mismo criterio que redactor_ia.py/voz_en_off.py con sus servicios
externos: llamada de red paga, y ademas requiere el CLI de Claude Code
instalado y funcional). Se prueba SOLO la logica pura:

- es_url: distinguir un link de una ruta de archivo local.
- es_alibaba: deteccion de dominio, por hostname exacto (no substring).
- _armar_system_prompt / _leer_skill: el SKILL.md real se lee del disco
  (no se copia a mano) y el apendice de modo headless queda anexado.
- _clave_api: degradacion a None cuando falta ANTHROPIC_API_KEY.
- _slug_codigo: saneamiento del codigo de proveedor para nombre de archivo.
- investigar_producto: rechazo temprano de Alibaba y de falta de clave,
  SIN tocar la red ni importar claude_agent_sdk en esos dos casos.
"""

import unittest
from pathlib import Path
from unittest import mock

import agente_investigador as ai


class PruebasEsUrl(unittest.TestCase):
    def test_http_es_url(self):
        self.assertTrue(ai.es_url("http://ejemplo.com/producto"))

    def test_https_es_url(self):
        self.assertTrue(ai.es_url("https://ejemplo.com/producto"))

    def test_https_con_espacios_alrededor_es_url(self):
        self.assertTrue(ai.es_url("  https://ejemplo.com/producto  "))

    def test_ruta_windows_no_es_url(self):
        self.assertFalse(ai.es_url(r"C:\ruta\a\ficha.json"))

    def test_ruta_relativa_no_es_url(self):
        self.assertFalse(ai.es_url("carpeta/ficha_investigada_4212.json"))

    def test_ftp_no_es_url_reconocida(self):
        # Solo http/https: el resto del sistema (Playwright, httpx) no
        # sabe manejar otros esquemas.
        self.assertFalse(ai.es_url("ftp://ejemplo.com/archivo"))

    def test_cadena_vacia_no_es_url(self):
        self.assertFalse(ai.es_url(""))


class PruebasEsAlibaba(unittest.TestCase):
    def test_dominio_alibaba_exacto(self):
        self.assertTrue(ai.es_alibaba("https://www.alibaba.com/product-detail/x.html"))

    def test_subdominio_alibaba(self):
        self.assertTrue(ai.es_alibaba("https://m.alibaba.com/product/123.html"))

    def test_1688(self):
        self.assertTrue(ai.es_alibaba("https://detail.1688.com/offer/123.html"))

    def test_aliexpress(self):
        self.assertTrue(ai.es_alibaba("https://es.aliexpress.com/item/123.html"))

    def test_tienda_normal_no_es_alibaba(self):
        self.assertFalse(ai.es_alibaba("https://www.fitnessmarket.com.co/producto/x"))

    def test_dominio_que_contiene_alibaba_como_substring_no_cuenta(self):
        # El chequeo es por HOSTNAME, no por substring de la URL cruda: un
        # dominio como 'notalibaba.com' o un path que diga 'alibaba' en otro
        # sitio no debe activar el rechazo de Fase 2a.
        self.assertFalse(ai.es_alibaba("https://notalibaba.com/producto"))
        self.assertFalse(ai.es_alibaba("https://ejemplo.com/reviews-de-alibaba"))


class PruebasSystemPrompt(unittest.TestCase):
    def test_leer_skill_incluye_contenido_real_del_archivo(self):
        contenido = ai._leer_skill()
        # Frase estable del SKILL.md real (Fase 0): si esto falla, o el
        # SKILL.md cambio de forma incompatible, o la ruta esta mal.
        self.assertIn("Investigador Ekipon v0.3", contenido)
        self.assertIn("Fase 0", contenido)

    def test_leer_skill_ausente_lanza_error_investigacion(self):
        ruta_falsa = Path("no_existe") / "SKILL.md"
        with mock.patch.object(ai, "RUTA_SKILL", ruta_falsa):
            with self.assertRaises(ai.ErrorInvestigacion):
                ai._leer_skill()

    def test_armar_system_prompt_incluye_skill_y_apendice(self):
        prompt = ai._armar_system_prompt()
        self.assertIn("Investigador Ekipon v0.3", prompt)
        self.assertIn("Apendice — modo headless", prompt)
        # El apendice va DESPUES del SKILL.md (se agrega, no se antepone
        # tapando las reglas de fondo).
        self.assertLess(
            prompt.index("Investigador Ekipon v0.3"),
            prompt.index("Apendice — modo headless"),
        )

    def test_apendice_no_contradice_las_reglas_fijas(self):
        # Chequeo mecanico simple: las tres reglas de negocio que el
        # apendice tiene que repetir explicitamente (precio, codigo exacto,
        # MercadoLibre) siguen presentes en el prompt final.
        prompt = ai._armar_system_prompt()
        self.assertIn("PENDIENTE_ANGIE", prompt)
        self.assertIn("9060C", prompt)
        self.assertIn("MercadoLibre", prompt)


class PruebasClaveApi(unittest.TestCase):
    def test_sin_clave_devuelve_none(self):
        with mock.patch.object(ai, "cargar_env", return_value={}):
            self.assertIsNone(ai._clave_api())

    def test_clave_vacia_devuelve_none(self):
        with mock.patch.object(ai, "cargar_env", return_value={"ANTHROPIC_API_KEY": "   "}):
            self.assertIsNone(ai._clave_api())

    def test_con_clave_la_devuelve(self):
        with mock.patch.object(
            ai, "cargar_env", return_value={"ANTHROPIC_API_KEY": "sk-ant-falsa"},
        ):
            self.assertEqual(ai._clave_api(), "sk-ant-falsa")


class PruebasSlugCodigo(unittest.TestCase):
    def test_codigo_simple(self):
        ficha = {"entrada_original": {"codigo_proveedor": "9060C"}}
        self.assertEqual(ai._slug_codigo(ficha), "9060C")

    def test_codigo_con_espacios_y_simbolos(self):
        ficha = {"entrada_original": {"codigo_proveedor": " NBC 250/A "}}
        self.assertEqual(ai._slug_codigo(ficha), "NBC_250_A")

    def test_sin_codigo_cae_a_producto(self):
        self.assertEqual(ai._slug_codigo({}), "producto")
        self.assertEqual(
            ai._slug_codigo({"entrada_original": {"codigo_proveedor": "   "}}),
            "producto",
        )


class PruebasInvestigarProductoRechazoTemprano(unittest.TestCase):
    """Los dos casos que se deciden ANTES de tocar el SDK/la red: link de
    Alibaba, y falta de clave. Ninguno de los dos debe importar
    claude_agent_sdk ni Playwright -- se verifica parcheando
    _correr_agente para que reviente si llega a invocarse."""

    def setUp(self):
        parche = mock.patch.object(
            ai, "_correr_agente",
            side_effect=AssertionError("no deberia llegar a correr el agente"),
        )
        parche.start()
        self.addCleanup(parche.stop)

    def test_link_alibaba_se_rechaza_sin_tocar_la_red(self):
        mensajes = []
        resultado = ai.investigar_producto(
            "https://www.alibaba.com/product-detail/x.html",
            Path("carpeta_no_usada"), mensajes.append,
        )
        self.assertEqual(resultado["estado"], "error")
        self.assertIn("Alibaba", resultado["motivo"])
        self.assertTrue(any("Alibaba" in m for m in mensajes))

    def test_sin_clave_se_rechaza_sin_tocar_la_red(self):
        with mock.patch.object(ai, "cargar_env", return_value={}):
            mensajes = []
            resultado = ai.investigar_producto(
                "https://www.fitnessmarket.com.co/producto/x",
                Path("carpeta_no_usada"), mensajes.append,
            )
        self.assertEqual(resultado["estado"], "error")
        self.assertIn("ANTHROPIC_API_KEY", resultado["motivo"])


if __name__ == "__main__":
    unittest.main()
