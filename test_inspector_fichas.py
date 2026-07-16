"""Pruebas automaticas del inspector de fichas (esquema_ficha + validar_ficha).

Uso:  python -m unittest test_inspector_fichas -v
Usa las fichas reales del repositorio como casos dorados y mutaciones
puntuales para cubrir cada regla fija del negocio.
"""

import copy
import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from esquema_ficha import FichaEkipon, claves_conocidas, precio_esta_pendiente
from validar_ficha import cargar_json, revisar_advertencias

RAIZ = Path(__file__).parent
FICHA_4212 = json.loads((RAIZ / "ficha_revisada_4212.json").read_text(encoding="utf-8-sig"))
FICHA_NBC250 = json.loads((RAIZ / "ficha_investigada_NBC250.json").read_text(encoding="utf-8-sig"))


def con_cambio(ruta_campo: list[str], valor) -> dict:
    """Copia de la ficha 4212 con un solo campo cambiado."""
    datos = copy.deepcopy(FICHA_4212)
    seccion = datos
    for clave in ruta_campo[:-1]:
        seccion = seccion[clave]
    seccion[ruta_campo[-1]] = valor
    return datos


class PruebasReglasDeNegocio(unittest.TestCase):
    def test_ficha_4212_es_valida(self):
        FichaEkipon.model_validate(FICHA_4212)  # no debe lanzar

    def test_ficha_nbc250_es_invalida(self):
        with self.assertRaises(ValidationError):
            FichaEkipon.model_validate(FICHA_NBC250)

    def test_nombre_en_minusculas_falla(self):
        datos = con_cambio(["producto", "nombre_propuesto"], "Compresor de aire")
        with self.assertRaises(ValidationError):
            FichaEkipon.model_validate(datos)

    def test_sku_manual_falla(self):
        datos = con_cambio(["producto", "sku"], "PENDIENTE - lo asigna la tienda")
        with self.assertRaises(ValidationError):
            FichaEkipon.model_validate(datos)

    def test_origen_con_typo_falla(self):
        datos = con_cambio(["producto", "categoria_confianza"], "confirmada_por_angie")
        with self.assertRaises(ValidationError):
            FichaEkipon.model_validate(datos)

    def test_precio_decimal_falla(self):
        datos = con_cambio(["precios", "precio"], 123.5)
        with self.assertRaises(ValidationError):
            FichaEkipon.model_validate(datos)

    def test_precio_texto_falla(self):
        datos = con_cambio(["precios", "precio"], "16434999")
        with self.assertRaises(ValidationError):
            FichaEkipon.model_validate(datos)

    def test_precio_pendiente_con_marca_pasa(self):
        datos = con_cambio(["precios", "precio"], None)
        datos["precios"]["precio_origen"] = "PENDIENTE_ANGIE (lo define al publicar)"
        FichaEkipon.model_validate(datos)  # no debe lanzar

    def test_precio_pendiente_sin_marca_completa_falla(self):
        # La marca incrustada en otra palabra NO cuenta (limite de palabra).
        datos = con_cambio(["precios", "precio"], None)
        datos["precios"]["precio_origen"] = "confirmado_por_angie xPENDIENTE_ANGIEy"
        with self.assertRaises(ValidationError):
            FichaEkipon.model_validate(datos)

    def test_marca_pendiente_por_palabra_completa(self):
        self.assertTrue(precio_esta_pendiente("nota PENDIENTE_ANGIE nota"))
        self.assertFalse(precio_esta_pendiente("xPENDIENTE_ANGIEy"))
        self.assertFalse(precio_esta_pendiente(None))


class PruebasHerramienta(unittest.TestCase):
    def test_claves_conocidas_acepta_alias_y_nombre(self):
        claves = claves_conocidas(FichaEkipon)
        self.assertIn("_version_ficha", claves)
        self.assertIn("version_ficha", claves)

    def test_ruta_con_salto_arriba_no_se_verifica_en_disco(self):
        datos = copy.deepcopy(FICHA_4212)
        datos["multimedia"]["imagenes_galeria_confirmadas"][0]["url"] = "../../secreto.webp"
        avisos = revisar_advertencias(datos, RAIZ, True)
        self.assertTrue(any("no es una ruta relativa" in aviso for aviso in avisos))
        self.assertFalse(any("secreto.webp" in aviso and "no encontrada" in aviso for aviso in avisos))

    def test_ficha_4212_solo_dos_advertencias_de_drift(self):
        avisos = revisar_advertencias(FICHA_4212, RAIZ, True)
        self.assertEqual(len(avisos), 2)
        self.assertTrue(all("desconocida" in aviso for aviso in avisos))

    def test_archivo_no_utf8_termina_con_codigo_2(self):
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "ficha_cp1252.json"
            ruta.write_bytes('{"codigo": "camión"}'.encode("cp1252"))
            with self.assertRaises(SystemExit) as contexto:
                cargar_json(ruta)
            self.assertEqual(contexto.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
