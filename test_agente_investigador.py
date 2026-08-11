"""Pruebas de agente_investigador.py. Offline: no llaman a la API real de
Anthropic (ni con clave ni con la suscripcion de Claude Code) ni corren el
CLI de Claude Code ni Playwright (ver docstring del modulo — el agente NO se
prueba de punta a punta con la API real en unit tests, mismo criterio que
redactor_ia.py/voz_en_off.py con sus servicios externos: eso gastaria cupo
real de la suscripcion de Angie, y ademas requiere el CLI de Claude Code
instalado y con sesion iniciada). Se prueba SOLO la logica pura:

- es_url: distinguir un link de una ruta de archivo local.
- es_alibaba: deteccion de dominio, por hostname exacto (no substring).
- _armar_system_prompt / _leer_skill: el SKILL.md real se lee del disco
  (no se copia a mano) y el apendice de modo headless queda anexado.
- _mensaje_claro_para_error_sdk: traduccion de excepciones crudas del SDK/
  CLI a mensajes en espanol accionables.
- _slug_codigo: saneamiento del codigo de proveedor para nombre de archivo.
- investigar_producto: Alibaba/1688/AliExpress (Fase 2b, 10-ago-2026) YA NO
  se rechaza antes de tocar el SDK -- se verifica que el link SI llega a
  _correr_agente (simulado con mocks, nunca con la API real) y que el
  `evento_continuar` recibido viaja intacto hasta ahi; y traduccion de
  errores del SDK/CLI cuando _correr_agente revienta.
"""

import tempfile
import threading
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

    def test_apendice_explica_las_tools_de_video(self):
        # El apendice tiene que ensenar el nombre EXACTO del contrato de
        # archivo que orquestador.py espera, y las tres ramas de decision
        # segun lo que devuelva extraer_video (archivo mp4, archivo en otro
        # formato, embed de YouTube/Vimeo, o nada).
        prompt = ai._armar_system_prompt()
        self.assertIn("extraer_video", prompt)
        self.assertIn("descargar_video", prompt)
        self.assertIn("_clip_original.mp4", prompt)

    def test_apendice_prohibe_descargar_embeds_de_youtube_o_vimeo(self):
        prompt = ai._armar_system_prompt()
        self.assertIn("YouTube", prompt)
        self.assertIn("Vimeo", prompt)
        self.assertIn("video_nota", prompt)
        # La instruccion tiene que ser explicita en no bajar el embed, no
        # solo mencionar las plataformas de pasada.
        self.assertIn("NO lo descargues", prompt)


class PruebasMensajeClaroParaErrorSdk(unittest.TestCase):
    """_mensaje_claro_para_error_sdk traduce excepciones crudas del SDK/CLI
    a mensajes en espanol accionables -- logica pura, compara por nombre de
    tipo de excepcion, sin tocar el SDK real."""

    def test_cli_no_encontrado_pide_instalar_el_cli(self):
        class CLINotFoundError(Exception):
            pass

        mensaje = ai._mensaje_claro_para_error_sdk(CLINotFoundError("no bin"))
        self.assertIn("Claude Code", mensaje)
        self.assertIn("npm install", mensaje)

    def test_error_generico_pide_claude_login_y_conserva_el_detalle(self):
        mensaje = ai._mensaje_claro_para_error_sdk(RuntimeError("sin sesion activa"))
        self.assertIn("claude login", mensaje)
        self.assertIn("sin sesion activa", mensaje)


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


class PruebasInvestigarProductoAlibabaYaNoSeRechaza(unittest.TestCase):
    """Fase 2b (10-ago-2026): al contrario de la Fase 2a original, un link
    de Alibaba/1688/AliExpress YA NO se rechaza antes de tocar el SDK --
    investigar_producto tiene que LLEGAR a invocar _correr_agente para ese
    link (navegador_alibaba.SesionAlibaba vive puertas adentro de
    _correr_agente, no se prueba aca con un browser real, ver
    test_navegador_alibaba.py) y pasarle intacto el `evento_continuar` que
    hace posible la pausa de login/CAPTCHA."""

    def test_link_alibaba_llega_a_correr_agente_con_el_evento_continuar(self):
        evento = threading.Event()
        llamada = {}

        async def _correr_agente_falso(link, carpeta_destino,
                                        publicar_notificacion, evento_continuar):
            llamada["link"] = link
            llamada["evento_continuar"] = evento_continuar
            return None  # simula "el agente no devolvio ficha estructurada"

        with mock.patch.object(ai, "_correr_agente", side_effect=_correr_agente_falso):
            with tempfile.TemporaryDirectory() as carpeta:
                mensajes = []
                resultado = ai.investigar_producto(
                    "https://www.alibaba.com/product-detail/x.html",
                    Path(carpeta), mensajes.append, evento_continuar=evento,
                )

        self.assertEqual(
            llamada.get("link"), "https://www.alibaba.com/product-detail/x.html",
        )
        self.assertIs(llamada.get("evento_continuar"), evento)
        # No es el mensaje viejo de rechazo temprano ("Alibaba..."): la
        # investigacion SI corrio, y esto es lo que pasa cuando el agente
        # (falso, en este test) no devuelve una ficha.
        self.assertEqual(resultado["estado"], "error")
        self.assertIn("no devolvio una ficha estructurada", resultado["motivo"])

    def test_sin_evento_continuar_se_crea_uno_propio_y_no_revienta(self):
        # Quien llama sin pensar en Alibaba (ej. un test, o un uso futuro
        # que no lo necesite) no esta obligado a pasar evento_continuar.
        llamada = {}

        async def _correr_agente_falso(link, carpeta_destino,
                                        publicar_notificacion, evento_continuar):
            llamada["evento_continuar"] = evento_continuar
            return None

        with mock.patch.object(ai, "_correr_agente", side_effect=_correr_agente_falso):
            with tempfile.TemporaryDirectory() as carpeta:
                ai.investigar_producto(
                    "https://www.alibaba.com/product-detail/x.html",
                    Path(carpeta), lambda m: None,
                )

        self.assertIsInstance(llamada.get("evento_continuar"), threading.Event)


class PruebasInvestigarProductoTraduceErroresDelSdk(unittest.TestCase):
    """Cuando _correr_agente revienta con una excepcion del SDK/CLI (CLI
    ausente, sin sesion iniciada, cupo agotado, red caida), investigar_
    producto la traduce a un mensaje claro en espanol -- nunca deja pasar
    un traceback crudo. Se simula la excepcion parcheando _correr_agente;
    en NINGUN caso se toca la API/CLI real."""

    def test_excepcion_del_sdk_se_traduce_a_mensaje_claro(self):
        with mock.patch.object(
            ai, "_correr_agente", side_effect=RuntimeError("sin sesion activa"),
        ):
            with tempfile.TemporaryDirectory() as carpeta:
                mensajes = []
                resultado = ai.investigar_producto(
                    "https://www.fitnessmarket.com.co/producto/x",
                    Path(carpeta), mensajes.append,
                )
        self.assertEqual(resultado["estado"], "error")
        self.assertIn("claude login", resultado["motivo"])
        self.assertTrue(any("claude login" in m for m in mensajes))

    def test_import_error_avisa_que_falta_el_paquete(self):
        with mock.patch.object(
            ai, "_correr_agente", side_effect=ImportError("no module named x"),
        ):
            with tempfile.TemporaryDirectory() as carpeta:
                mensajes = []
                resultado = ai.investigar_producto(
                    "https://www.fitnessmarket.com.co/producto/x",
                    Path(carpeta), mensajes.append,
                )
        self.assertEqual(resultado["estado"], "error")
        self.assertIn("claude-agent-sdk", resultado["motivo"])


if __name__ == "__main__":
    unittest.main()
