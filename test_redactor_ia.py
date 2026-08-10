"""Pruebas de redactor_ia. Offline: no llaman a claude_agent_sdk.query() ni
al CLI de Claude Code real (ver docstring del modulo — NO se prueba con el
SDK/CLI real en unit tests: gastaria cupo real de la suscripcion de Angie,
mismo criterio que voz_en_off.py/musica.py con ElevenLabs). Solo se prueba
la logica pura: el presupuesto de caracteres, la extraccion de datos
seguros para el prompt, y la degradacion a None cuando no hay nada real
que redactar o cuando la consulta a la IA falla (simulado parcheando
_consultar_ia_sincrono, nunca llamando al SDK real).
"""

import unittest
from unittest import mock

import redactor_ia
import voz_en_off


class PruebasPresupuesto(unittest.TestCase):
    def test_presupuesto_cuerpo_es_total_menos_dos_frases_fijas(self):
        overhead_esperado = 2 * len(voz_en_off.FRASE_FIJA) + 2
        esperado = voz_en_off.PRESUPUESTO_CARACTERES_DEFECTO - overhead_esperado
        self.assertEqual(redactor_ia.PRESUPUESTO_CUERPO_GUION, esperado)

    def test_presupuesto_nunca_negativo(self):
        self.assertGreaterEqual(redactor_ia.PRESUPUESTO_CUERPO_GUION, 0)


class PruebasDatosSegurosParaGuion(unittest.TestCase):
    def test_extrae_solo_campos_publicos(self):
        ficha = {
            "producto": {"nombre_propuesto": "TALADRO X"},
            "descripcion_principal": "Un taladro robusto.",
            "caracteristicas": ["Potente", "Liviano", 123],  # 123 se descarta
            "ficha_tecnica": {
                "_origen_global": "verificado",
                "_nota": "interno",
                "POTENCIA": "750 W",
            },
            "identificacion_del_producto": {"advertencias": ["dato sensible"]},
        }
        datos = redactor_ia._datos_seguros_para_guion(ficha)
        self.assertEqual(datos["nombre"], "TALADRO X")
        self.assertEqual(datos["descripcion_principal"], "Un taladro robusto.")
        self.assertEqual(datos["caracteristicas"], ["Potente", "Liviano"])
        self.assertEqual(datos["ficha_tecnica"], {"POTENCIA": "750 W"})
        # Nada de identificacion_del_producto ni claves '_' se filtra.
        self.assertNotIn("_origen_global", datos["ficha_tecnica"])
        self.assertNotIn("advertencias", datos)

    def test_ficha_vacia_no_revienta(self):
        datos = redactor_ia._datos_seguros_para_guion({})
        self.assertEqual(datos["nombre"], "")
        self.assertEqual(datos["descripcion_principal"], "")
        self.assertEqual(datos["caracteristicas"], [])
        self.assertEqual(datos["ficha_tecnica"], {})


class PruebasConsultarIaSincrono(unittest.TestCase):
    """_consultar_ia_sincrono envuelve el _consultar_ia asincrono con
    asyncio.run() y degrada a None ante CUALQUIER excepcion -- se prueba
    parcheando _consultar_ia (una funcion async propia del modulo), nunca
    tocando claude_agent_sdk ni el CLI real."""

    def test_devuelve_lo_que_resuelve_consultar_ia(self):
        async def _consultar_ia_falso(prompt):
            return "Un guion redactado."

        with mock.patch.object(redactor_ia, "_consultar_ia", _consultar_ia_falso):
            self.assertEqual(
                redactor_ia._consultar_ia_sincrono("prompt"),
                "Un guion redactado.",
            )

    def test_excepcion_de_consultar_ia_degrada_a_none(self):
        # CLI ausente, sin sesion iniciada, cupo agotado, red caida: da
        # igual el motivo especifico, _consultar_ia_sincrono nunca lanza.
        with mock.patch.object(
            redactor_ia, "_consultar_ia", side_effect=RuntimeError("sin sesion"),
        ):
            self.assertIsNone(redactor_ia._consultar_ia_sincrono("prompt"))


class PruebasDegradacionSinDatosReales(unittest.TestCase):
    """Sin datos reales que citar (guion) o sin categoria (musica), ninguna
    funcion debe siquiera intentar consultar la IA -- se verifica
    parcheando _consultar_ia_sincrono para que reviente si llega a
    invocarse (mismo patron que agente_investigador con _correr_agente)."""

    def setUp(self):
        parche = mock.patch.object(
            redactor_ia, "_consultar_ia_sincrono",
            side_effect=AssertionError("no deberia consultar la IA"),
        )
        parche.start()
        self.addCleanup(parche.stop)

    def test_guion_sin_descripcion_ni_caracteristicas_devuelve_none(self):
        ficha = {"producto": {"nombre_propuesto": "X"}}
        self.assertIsNone(redactor_ia.redactar_guion_voz(ficha))

    def test_musica_sin_categoria_devuelve_none(self):
        ficha = {"producto": {"nombre_propuesto": "X"}}
        self.assertIsNone(redactor_ia.redactar_prompt_musica(ficha))


class PruebasRedactarConDatosReales(unittest.TestCase):
    """Con datos reales presentes, ambas funciones publicas delegan en
    _consultar_ia_sincrono y devuelven su resultado tal cual (incluido
    None, la misma degradacion de siempre si la IA no responde) -- se
    verifica parcheando _consultar_ia_sincrono, nunca el SDK real."""

    def test_guion_devuelve_lo_que_responde_la_ia(self):
        with mock.patch.object(
            redactor_ia, "_consultar_ia_sincrono", return_value="Guion redactado.",
        ) as parche:
            ficha = {"descripcion_principal": "Un taladro robusto."}
            self.assertEqual(redactor_ia.redactar_guion_voz(ficha), "Guion redactado.")
        parche.assert_called_once()

    def test_musica_devuelve_lo_que_responde_la_ia(self):
        with mock.patch.object(
            redactor_ia, "_consultar_ia_sincrono",
            return_value="ambient background music, no vocals",
        ) as parche:
            ficha = {"producto": {"categoria_propuesta": "Gimnasio"}}
            self.assertEqual(
                redactor_ia.redactar_prompt_musica(ficha),
                "ambient background music, no vocals",
            )
        parche.assert_called_once()

    def test_guion_propaga_none_si_la_ia_no_responde(self):
        with mock.patch.object(
            redactor_ia, "_consultar_ia_sincrono", return_value=None,
        ):
            ficha = {"descripcion_principal": "Un taladro robusto."}
            self.assertIsNone(redactor_ia.redactar_guion_voz(ficha))


class PruebasPromptMusicaGenerico(unittest.TestCase):
    def test_prompt_generico_no_esta_vacio(self):
        self.assertTrue(redactor_ia.PROMPT_MUSICA_GENERICO.strip())

    def test_estilos_por_categoria_todos_en_ingles_sin_vocals(self):
        # Chequeo mecanico simple: cada estilo declara "no vocals" (regla de
        # musica.py: musica de fondo, sin letra que compita con la voz).
        for _categoria, estilo in redactor_ia._ESTILOS_POR_CATEGORIA:
            self.assertIn("no vocals", estilo)


if __name__ == "__main__":
    unittest.main()
