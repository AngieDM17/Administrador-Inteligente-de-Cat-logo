"""Pruebas del contrato nuevo de la ficha: multimedia.galeria_tomas.

Es lo que el Investigador emite para que la etapa de imagenes salga sola.
Las reglas del proyecto que se verifican aqui: dato sin origen = dato
inventado, y jamas se acepta una posicion inventada.
"""

import unittest

from pydantic import ValidationError

from esquema_ficha import DimensionesProducto, GaleriaTomas, Multimedia


class PruebasCallouts(unittest.TestCase):
    def test_callouts_validos(self):
        gt = GaleriaTomas.model_validate({
            "callouts": [{"label": "Tolva", "point": [0.5, 0.1]}],
            "callouts_origen": "encontrado_web",
        })
        self.assertEqual(len(gt.callouts), 1)

    def test_point_es_opcional(self):
        # El Investigador sabe QUE partes hay, no DONDE caen: point puede faltar.
        gt = GaleriaTomas.model_validate({
            "callouts": [{"label": "Tolva"}],
            "callouts_origen": "encontrado_web",
        })
        self.assertIsNone(gt.callouts[0].point)

    def test_callouts_sin_origen_se_rechazan(self):
        with self.assertRaises(ValidationError):
            GaleriaTomas.model_validate({"callouts": [{"label": "Tolva"}]})

    def test_point_fuera_de_rango_se_rechaza(self):
        with self.assertRaises(ValidationError):
            GaleriaTomas.model_validate({
                "callouts": [{"label": "Tolva", "point": [5, 0.1]}],
                "callouts_origen": "encontrado_web",
            })

    def test_point_de_largo_invalido_se_rechaza(self):
        with self.assertRaises(ValidationError):
            GaleriaTomas.model_validate({
                "callouts": [{"label": "Tolva", "point": [0.1]}],
                "callouts_origen": "encontrado_web",
            })


class PruebasDimensiones(unittest.TestCase):
    def test_dimensiones_validas(self):
        gt = GaleriaTomas.model_validate({
            "dimensiones": {"alto": "85 cm", "peso": "20 kg"},
            "dimensiones_origen": "encontrado_web",
        })
        self.assertEqual(gt.dimensiones.alto, "85 cm")

    def test_dimensiones_sin_origen_se_rechazan(self):
        with self.assertRaises(ValidationError):
            GaleriaTomas.model_validate({"dimensiones": {"alto": "85 cm"}})

    def test_dimensiones_todas_vacias_no_exigen_origen(self):
        # Nada verificado = nada que declarar; no debe frenar el pipeline.
        gt = GaleriaTomas.model_validate({"dimensiones": {}})
        self.assertFalse(gt.dimensiones.hay_alguna())

    def test_hay_alguna(self):
        self.assertTrue(DimensionesProducto(alto="1 m").hay_alguna())
        self.assertFalse(DimensionesProducto().hay_alguna())


class PruebasMultimedia(unittest.TestCase):
    def test_galeria_tomas_es_opcional_en_multimedia(self):
        # Las fichas viejas (sin la seccion) siguen siendo validas.
        self.assertIsNone(Multimedia.model_validate({}).galeria_tomas)

    def test_multimedia_acepta_galeria_tomas(self):
        m = Multimedia.model_validate({"galeria_tomas": {
            "dimensiones": {"alto": "85 cm"},
            "dimensiones_origen": "encontrado_web",
        }})
        self.assertEqual(m.galeria_tomas.dimensiones.alto, "85 cm")


if __name__ == "__main__":
    unittest.main()
