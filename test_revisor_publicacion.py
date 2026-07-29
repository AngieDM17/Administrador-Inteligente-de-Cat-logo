"""Pruebas del revisor de listo-para-publicar.

Dos niveles:
- Contra fichas REALES producidas por el Investigador (ESTIBADORA, TALADRO):
  la entrada la produjo el paso anterior, no esta escrita a mano.
- Unitarias por chequeo: sobre una ficha limpia base a la que se le rompe una
  cosa a la vez, para probar que cada motivo salta cuando debe y solo entonces.
"""

import json
import unittest
from pathlib import Path

from revisor_publicacion import revisar_listo_para_publicar

RAIZ = Path(__file__).parent


def _cargar(nombre: str) -> dict:
    return json.loads((RAIZ / nombre).read_text(encoding="utf-8-sig"))


def _codigos(datos: dict) -> set[str]:
    return {m.codigo for m in revisar_listo_para_publicar(datos).motivos}


def _ficha_limpia() -> dict:
    """Ficha minima que debe salir LISTO: identificada por link, sin
    advertencias, con potencia y dimensiones, y sin pendientes mas alla del
    precio y la categoria (los puntos normales del humano)."""
    return {
        "identificacion_del_producto": {
            "resultado": "IDENTIFICADO — producto exacto de la fuente",
            "origen_identificacion": "link",
            "advertencias": [],
            "estado_en_proveedor": "Publicado activo, nuevo.",
        },
        "campos_por_confirmar": [
            "Precio de venta Ekipon (lo define Angie).",
            "Categoria en el arbol EN VIVO de WooCommerce.",
        ],
        "ficha_tecnica": {
            "_origen_global": "encontrado_web",
            "TIPO": "Molino",
            "POTENCIA": "2 HP",
        },
        "multimedia": {
            "galeria_tomas": {
                "dimensiones": {
                    "alto": "58 cm",
                    "ancho": "43 cm",
                    "fondo": "46 cm",
                    "peso": "20 kg",
                }
            }
        },
    }


class PruebasFichasReales(unittest.TestCase):
    def test_estibadora_necesita_revision(self):
        datos = _cargar("ficha_investigada_ESTIBADORA.json")
        codigos = _codigos(datos)
        self.assertFalse(revisar_listo_para_publicar(datos).listo)
        # Trae advertencias del investigador (color, capacidad) y no tiene
        # dimensiones estructuradas (omitio la toma de medidas).
        self.assertIn("advertencias_investigador", codigos)
        self.assertIn("sin_dimensiones", codigos)
        # Tiene pendientes reales (color/modelo, capacidad, voltaje) ademas de
        # precio y categoria.
        self.assertIn("campos_por_confirmar", codigos)
        # NO debe marcar specs estimadas: el texto 'generado_ia_sin_verificar'
        # solo aparece en la metaclave _nota (que lo explica), no en un dato.
        self.assertNotIn("specs_estimadas", codigos)

    def test_taladro_necesita_revision(self):
        datos = _cargar("ficha_investigada_TALADRO.json")
        codigos = _codigos(datos)
        self.assertFalse(revisar_listo_para_publicar(datos).listo)
        # Camino B: sin link, por inferencia.
        self.assertIn("inferencia_sin_link", codigos)
        self.assertIn("advertencias_investigador", codigos)


class PruebasFichaLimpia(unittest.TestCase):
    def test_ficha_limpia_pasa(self):
        resultado = revisar_listo_para_publicar(_ficha_limpia())
        self.assertTrue(resultado.listo, [m.mensaje for m in resultado.motivos])

    def test_solo_precio_y_categoria_no_marca(self):
        # Los pendientes normales (precio, categoria) no cuentan como motivo.
        self.assertNotIn("campos_por_confirmar", _codigos(_ficha_limpia()))


class PruebasChequeos(unittest.TestCase):
    def test_campo_por_confirmar_real_marca(self):
        datos = _ficha_limpia()
        datos["campos_por_confirmar"].append("Voltaje exacto de la bateria.")
        self.assertIn("campos_por_confirmar", _codigos(datos))

    def test_resultado_dudoso_marca(self):
        datos = _ficha_limpia()
        datos["identificacion_del_producto"]["resultado"] = "IDENTIFICACION_DUDOSA — ..."
        self.assertIn("no_identificado", _codigos(datos))

    def test_advertencias_marca(self):
        datos = _ficha_limpia()
        datos["identificacion_del_producto"]["advertencias"] = ["El tipo contradice el nombre."]
        self.assertIn("advertencias_investigador", _codigos(datos))

    def test_inferencia_marca(self):
        datos = _ficha_limpia()
        datos["identificacion_del_producto"]["origen_identificacion"] = "inferencia"
        self.assertIn("inferencia_sin_link", _codigos(datos))

    def test_estado_usado_marca(self):
        datos = _ficha_limpia()
        datos["identificacion_del_producto"]["estado_en_proveedor"] = "Equipo USADO, buen estado."
        self.assertIn("estado_usado", _codigos(datos))

    def test_falta_potencia_marca(self):
        datos = _ficha_limpia()
        del datos["ficha_tecnica"]["POTENCIA"]
        self.assertIn("sin_potencia", _codigos(datos))

    def test_potencia_via_motor_no_marca(self):
        # Una clave 'MOTOR DE ELEVACION' cuenta como declarar la potencia.
        datos = _ficha_limpia()
        del datos["ficha_tecnica"]["POTENCIA"]
        datos["ficha_tecnica"]["MOTOR DE ELEVACION"] = "1.6 kW"
        self.assertNotIn("sin_potencia", _codigos(datos))

    def test_no_motorizado_no_exige_potencia(self):
        # Producto SIN motor (escalera, silla, gimnasio): declarar es_motorizado
        # False libra del chequeo de potencia. Sin esto, todo producto manual
        # daba falso positivo 'sin_potencia'.
        datos = _ficha_limpia()
        del datos["ficha_tecnica"]["POTENCIA"]
        datos["producto"] = {"es_motorizado": False}
        self.assertNotIn("sin_potencia", _codigos(datos))

    def test_no_motorizado_ficha_limpia_pasa(self):
        # El verde: una ficha de producto sin motor, sin pendientes reales y con
        # dimensiones, debe salir LISTO.
        datos = _ficha_limpia()
        del datos["ficha_tecnica"]["POTENCIA"]
        datos["producto"] = {"es_motorizado": False}
        resultado = revisar_listo_para_publicar(datos)
        self.assertTrue(resultado.listo, [m.mensaje for m in resultado.motivos])

    def test_motorizado_true_sin_potencia_marca(self):
        # Declarado motorizado y sin potencia -> sigue marcando.
        datos = _ficha_limpia()
        del datos["ficha_tecnica"]["POTENCIA"]
        datos["producto"] = {"es_motorizado": True}
        self.assertIn("sin_potencia", _codigos(datos))

    def test_sin_campo_motor_asume_motorizado(self):
        # Ausencia del campo -> se asume motorizado (fichas viejas): exige potencia.
        datos = _ficha_limpia()
        del datos["ficha_tecnica"]["POTENCIA"]
        self.assertIn("sin_potencia", _codigos(datos))

    def test_specs_estimadas_marca(self):
        datos = _ficha_limpia()
        datos["ficha_tecnica"]["CAPACIDAD"] = "150 kg/h [generado_ia_sin_verificar]"
        self.assertIn("specs_estimadas", _codigos(datos))

    def test_sin_dimensiones_marca(self):
        datos = _ficha_limpia()
        datos["multimedia"]["galeria_tomas"]["dimensiones"] = {
            "alto": None, "ancho": None, "fondo": None, "peso": "20 kg",
        }
        self.assertIn("sin_dimensiones", _codigos(datos))

    def test_dimensiones_presentes_no_marca(self):
        self.assertNotIn("sin_dimensiones", _codigos(_ficha_limpia()))


if __name__ == "__main__":
    unittest.main()
