"""Pruebas del motor que lee el plan y produce la galeria.

Lo que se verifica aqui es la conducta del motor, no el dibujo: que degrade
en vez de fallar, que diga POR QUE omitio cada pieza, y que el origen del
dato viaje hasta la imagen producida.
"""

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from motor_galeria import aplicar_informe, plan_de_ficha, producir_galeria


def _recorte_en(carpeta: Path, lado: int = 200) -> Path:
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    cuerpo = Image.new("RGBA", (lado // 2, lado // 2), (255, 78, 3, 255))
    img.paste(cuerpo, (lado // 4, lado // 4))
    ruta = carpeta / "recorte.png"
    img.save(ruta)
    return ruta


def _ficha(slots, galeria_tomas=None) -> dict:
    multimedia = {
        "plan_galeria": {
            "imagen_base": "producto/01.jpg",
            "imagen_base_origen": "encontrado_web",
            "slots": slots,
        }
    }
    if galeria_tomas is not None:
        multimedia["galeria_tomas"] = galeria_tomas
    return {"multimedia": multimedia}


class BaseMotor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.recorte = _recorte_en(self.dir)
        self.destino = self.dir / "galeria"

    def tearDown(self):
        self._tmp.cleanup()


class PruebasPlanDeFicha(BaseMotor):
    def test_ficha_sin_plan_devuelve_none(self):
        self.assertIsNone(plan_de_ficha({"multimedia": {}}))

    def test_ignora_las_claves_de_comentario(self):
        # La plantilla del Investigador trae claves _comentario, _regla_dura...
        ficha = _ficha([{"tipo": "foto_real", "fuente": "foto_real"}])
        ficha["multimedia"]["plan_galeria"]["_comentario"] = "texto de ayuda"
        self.assertEqual(len(plan_de_ficha(ficha).slots), 1)


class PruebasProduccion(BaseMotor):
    def test_producto_limpio_se_produce(self):
        ficha = _ficha([{"tipo": "producto_limpio", "fuente": "generado_motor"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(len(informe["producidos"]), 1)
        self.assertTrue(Path(informe["producidos"][0]["archivo"]).exists())

    def test_medidas_hereda_el_origen_de_la_ficha(self):
        ficha = _ficha(
            [{"tipo": "medidas", "fuente": "generado_motor"}],
            {"dimensiones": {"alto": "85 cm", "ancho": "43 cm"},
             "dimensiones_origen": "encontrado_web"},
        )
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(informe["producidos"][0]["origen"], "encontrado_web")

    def test_medidas_sin_datos_se_omite_con_motivo(self):
        ficha = _ficha([{"tipo": "medidas", "fuente": "generado_motor"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(informe["producidos"], [])
        self.assertIn("no trae medidas", informe["omitidos"][0]["motivo"])

    def test_callout_con_punto_valido_se_dibuja(self):
        ficha = _ficha(
            [{"tipo": "partes_senaladas", "fuente": "generado_motor"}],
            {"callouts": [{"label": "Motor", "point": [0.5, 0.5]}],
             "callouts_origen": "encontrado_web"},
        )
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(len(informe["producidos"]), 1)
        self.assertEqual(informe["producidos"][0]["origen"], "encontrado_web")

    def test_callout_mal_ubicado_se_descarta_y_se_avisa(self):
        ficha = _ficha(
            [{"tipo": "partes_senaladas", "fuente": "generado_motor"}],
            {"callouts": [{"label": "Tolva", "point": [0.95, 0.95]}],
             "callouts_origen": "encontrado_web"},
        )
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(informe["producidos"], [])
        self.assertIn("ningun callout con punto valido", informe["omitidos"][0]["motivo"])
        self.assertTrue(any("Tolva" in a for a in informe["avisos"]))

    def test_tipos_de_material_real_se_omiten_explicando(self):
        ficha = _ficha([{"tipo": "foto_real", "fuente": "foto_real"},
                        {"tipo": "accesorios", "fuente": "foto_real"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)
        motivos = " ".join(o["motivo"] for o in informe["omitidos"])
        self.assertEqual(len(informe["omitidos"]), 2)
        self.assertIn("carpeta del producto", motivos)

    def test_slot_no_automatizado_se_omite_sin_romper(self):
        ficha = _ficha([{"tipo": "otro_angulo_ia", "fuente": "imagen_a_imagen"},
                        {"tipo": "producto_limpio", "fuente": "generado_motor"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)
        # El slot que no sabe hacer no impide producir el que si.
        self.assertEqual(len(informe["producidos"]), 1)
        self.assertEqual(len(informe["omitidos"]), 1)

    def test_ficha_sin_plan_avisa_y_no_produce(self):
        informe = producir_galeria({"multimedia": {}}, self.recorte, self.destino)
        self.assertEqual(informe["producidos"], [])
        self.assertTrue(informe["avisos"])

    def test_recorte_inexistente_falla_con_mensaje_util(self):
        ficha = _ficha([{"tipo": "producto_limpio", "fuente": "generado_motor"}])
        with self.assertRaises(FileNotFoundError) as ctx:
            producir_galeria(ficha, self.dir / "no_existe.png", self.destino)
        self.assertIn("recortar_producto.py", str(ctx.exception))

    def test_los_archivos_se_numeran_por_orden_del_plan(self):
        ficha = _ficha([{"tipo": "foto_real", "fuente": "foto_real"},
                        {"tipo": "producto_limpio", "fuente": "generado_motor"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)
        # El producto_limpio es el segundo slot: conserva su indice.
        self.assertIn("02-producto_limpio", informe["producidos"][0]["archivo"])


class PruebasAplicarInforme(BaseMotor):
    def test_vuelca_archivo_y_origen_al_plan(self):
        ficha = _ficha(
            [{"tipo": "medidas", "fuente": "generado_motor"}],
            {"dimensiones": {"alto": "85 cm"}, "dimensiones_origen": "encontrado_web"},
        )
        informe = producir_galeria(ficha, self.recorte, self.destino)
        aplicar_informe(ficha, informe)
        slot = ficha["multimedia"]["plan_galeria"]["slots"][0]
        self.assertTrue(slot["archivo"].endswith(".webp"))
        self.assertEqual(slot["origen"], "encontrado_web")

    def test_producir_no_muta_la_ficha_por_su_cuenta(self):
        ficha = _ficha([{"tipo": "producto_limpio", "fuente": "generado_motor"}])
        antes = json.dumps(ficha, sort_keys=True)
        producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(json.dumps(ficha, sort_keys=True), antes)

    def test_el_plan_actualizado_sigue_siendo_valido(self):
        ficha = _ficha(
            [{"tipo": "medidas", "fuente": "generado_motor"}],
            {"dimensiones": {"alto": "85 cm"}, "dimensiones_origen": "encontrado_web"},
        )
        aplicar_informe(ficha, producir_galeria(ficha, self.recorte, self.destino))
        self.assertIsNotNone(plan_de_ficha(ficha))


if __name__ == "__main__":
    unittest.main()
