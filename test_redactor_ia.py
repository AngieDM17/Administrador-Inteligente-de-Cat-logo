"""Pruebas de redactor_ia. Offline: no llaman a la API real de Anthropic (ver
docstring del modulo — NO se prueba con la API real en unit tests, mismo
criterio que voz_en_off.py/musica.py con ElevenLabs). Solo se prueba la
logica pura: el presupuesto de caracteres, la extraccion de datos seguros
para el prompt, y la degradacion a None cuando falta la clave o no hay nada
real que redactar.
"""

import unittest
from pathlib import Path
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


class PruebasDegradacionSinRed(unittest.TestCase):
    """Ambas funciones publicas devuelven None sin tocar la red cuando falta
    la clave o no hay nada real que redactar — se verifica parcheando
    cargar_env para simular un .env sin ANTHROPIC_API_KEY."""

    def setUp(self):
        parche = mock.patch.object(redactor_ia, "cargar_env", return_value={})
        parche.start()
        self.addCleanup(parche.stop)

    def test_redactar_guion_sin_clave_devuelve_none(self):
        ficha = {"descripcion_principal": "Algo real."}
        self.assertIsNone(redactor_ia.redactar_guion_voz(ficha))

    def test_redactar_prompt_musica_sin_clave_devuelve_none(self):
        ficha = {"producto": {"categoria_propuesta": "Gimnasio"}}
        self.assertIsNone(redactor_ia.redactar_prompt_musica(ficha))


class PruebasDegradacionSinDatos(unittest.TestCase):
    """Con clave presente pero sin datos reales que citar, ninguna funcion
    debe siquiera intentar la llamada de red (se verifica con una clave falsa
    y sin parchear anthropic: si intentara importar/llamar, fallaria o
    tardaria; en cambio devuelve None de inmediato por la guarda temprana)."""

    def setUp(self):
        parche = mock.patch.object(
            redactor_ia, "cargar_env", return_value={"ANTHROPIC_API_KEY": "clave-falsa"}
        )
        parche.start()
        self.addCleanup(parche.stop)

    def test_guion_sin_descripcion_ni_caracteristicas_devuelve_none(self):
        ficha = {"producto": {"nombre_propuesto": "X"}}
        self.assertIsNone(redactor_ia.redactar_guion_voz(ficha))

    def test_musica_sin_categoria_devuelve_none(self):
        ficha = {"producto": {"nombre_propuesto": "X"}}
        self.assertIsNone(redactor_ia.redactar_prompt_musica(ficha))


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
