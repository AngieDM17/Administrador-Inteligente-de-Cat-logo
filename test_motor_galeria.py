"""Pruebas del motor que lee el plan y produce la galeria.

Lo que se verifica aqui es la conducta del motor, no el dibujo: que degrade
en vez de fallar, que diga POR QUE omitio cada pieza, y que el origen del
dato viaje hasta la imagen producida.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from esquema_ficha import TIPOS_SLOT, Multimedia
from motor_galeria import (
    LADO_SALIDA,
    NOTAS_POR_TIPO,
    aplicar_confirmadas,
    aplicar_informe,
    imagenes_confirmadas_del_plan,
    main,
    plan_de_ficha,
    producir_galeria,
    relativizar_a_carpeta_de_ficha,
)
from publicador import ruta_relativa_segura


def _recorte_en(carpeta: Path, lado: int = 200, nombre: str = "recorte.png") -> Path:
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    cuerpo = Image.new("RGBA", (lado // 2, lado // 2), (255, 78, 3, 255))
    img.paste(cuerpo, (lado // 4, lado // 4))
    ruta = carpeta / nombre
    img.save(ruta)
    return ruta


def _ficha_sin_origen(slots, galeria_tomas=None) -> dict:
    """Ficha cuyo plan NO declara 'imagen_base_origen'.

    El esquema la acepta (sin 'imagen_base' no hay origen que exigir), asi que
    es una entrada real y no un caso de laboratorio. Cada slot que llegue sin
    'origen' propio queda sin nadie que responda por su imagen.
    """
    multimedia = {"plan_galeria": {"slots": slots}}
    if galeria_tomas is not None:
        multimedia["galeria_tomas"] = galeria_tomas
    return {"multimedia": multimedia}


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


class PruebasAvisoDeResolucion(BaseMotor):
    """El recorte chico no rompe nada: sale ampliado y con pinta de terminado.

    Caso real del 22-jul-2026: foto de 228x310 px, recorte de 168x294, y el
    motor devolvio piezas de 1080x1080 sin decir una palabra. Un agrandado de
    ~3,7x que nadie mira dos veces. El motor degrada, no falla, asi que lo que
    se fija aqui es que AVISE con los numeros y siga produciendo.
    """

    def test_recorte_chico_avisa_con_las_medidas_y_el_factor(self):
        ficha = _ficha([{"tipo": "producto_limpio", "fuente": "generado_motor"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)

        avisos = " ".join(informe["avisos"])
        self.assertIn("200x200", avisos)                     # medidas del recorte
        self.assertIn(f"{LADO_SALIDA}x{LADO_SALIDA}", avisos)  # lado de salida
        self.assertIn(f"{LADO_SALIDA / 200:.1f}", avisos)      # factor: 5.4
        self.assertIn("RESOLUCION INSUFICIENTE", avisos)

    def test_el_aviso_no_bloquea_la_produccion(self):
        # Conducta declarada del motor: degradar, no fallar.
        ficha = _ficha([{"tipo": "producto_limpio", "fuente": "generado_motor"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(len(informe["producidos"]), 1)
        self.assertTrue(Path(informe["producidos"][0]["archivo"]).exists())

    def test_recorte_del_tamano_de_salida_no_avisa(self):
        grande = _recorte_en(self.dir, lado=LADO_SALIDA, nombre="recorte_grande.png")
        ficha = _ficha([{"tipo": "producto_limpio", "fuente": "generado_motor"}])
        informe = producir_galeria(ficha, grande, self.destino)
        self.assertEqual(informe["avisos"], [])
        self.assertEqual(len(informe["producidos"]), 1)


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


class PruebasPuenteAlPublicador(BaseMotor):
    """El puente que faltaba: del plan producido al campo que lee el Publicador.

    Lo que se verifica es el criterio de que sube y que no, y que la lista
    resultante cumpla el contrato real de la ficha, no una copia a mano.
    """

    def test_mapea_archivo_a_url_respetando_el_orden_del_plan(self):
        ficha = _ficha([
            {"tipo": "foto_real", "fuente": "foto_real",
             "archivo": "galeria/01-foto_real.webp", "origen": "verificado"},
            {"tipo": "medidas", "fuente": "generado_motor",
             "archivo": "galeria/02-medidas.webp", "origen": "encontrado_web"},
        ])
        incluidas, omitidas = imagenes_confirmadas_del_plan(ficha)
        self.assertEqual(
            [i["url"] for i in incluidas],
            ["galeria/01-foto_real.webp", "galeria/02-medidas.webp"],
        )
        self.assertEqual(omitidas, [])

    def test_slot_sin_archivo_se_omite_con_motivo(self):
        ficha = _ficha([{"tipo": "producto_limpio", "fuente": "generado_motor"}])
        incluidas, omitidas = imagenes_confirmadas_del_plan(ficha)
        self.assertEqual(incluidas, [])
        self.assertEqual(len(omitidas), 1)
        self.assertIn("todavia no se produjo", omitidas[0]["motivo"])
        self.assertEqual(omitidas[0]["tipo"], "producto_limpio")

    def test_imagen_sin_verificar_queda_excluida_con_motivo(self):
        # Nadie firmo esa imagen: no puede llegar sola a la tienda.
        ficha = _ficha([{"tipo": "otro_angulo_ia", "fuente": "imagen_a_imagen",
                         "archivo": "galeria/03-otro_angulo_IA.webp",
                         "origen": "generado_ia_sin_verificar"}])
        incluidas, omitidas = imagenes_confirmadas_del_plan(ficha)
        self.assertEqual(incluidas, [])
        self.assertIn("generado_ia_sin_verificar", omitidas[0]["motivo"])
        self.assertIn("nadie reviso", omitidas[0]["motivo"])

    def test_imagen_confirmada_por_angie_si_entra(self):
        # confirmado_por_angie ES la revision humana: pasa.
        ficha = _ficha([{"tipo": "escena_funcionamiento", "fuente": "escena_ia",
                         "archivo": "galeria/04-escena_IA.webp",
                         "origen": "confirmado_por_angie (22-jul-2026)"}])
        incluidas, omitidas = imagenes_confirmadas_del_plan(ficha)
        self.assertEqual(len(incluidas), 1)
        self.assertEqual(omitidas, [])

    def test_nota_por_defecto_cuando_el_slot_no_trae_nota(self):
        ficha = _ficha([{"tipo": "medidas", "fuente": "generado_motor",
                         "archivo": "galeria/02-medidas.webp",
                         "origen": "encontrado_web"}])
        incluidas, _ = imagenes_confirmadas_del_plan(ficha)
        self.assertEqual(incluidas[0]["nota"], NOTAS_POR_TIPO["medidas"])

    def test_la_nota_del_slot_gana_sobre_la_de_por_defecto(self):
        ficha = _ficha([{"tipo": "medidas", "fuente": "generado_motor",
                         "archivo": "galeria/02-medidas.webp",
                         "origen": "encontrado_web",
                         "nota": "Medidas del equipo con el tanque incluido"}])
        incluidas, _ = imagenes_confirmadas_del_plan(ficha)
        self.assertEqual(incluidas[0]["nota"],
                         "Medidas del equipo con el tanque incluido")

    def test_hay_nota_por_defecto_para_todos_los_tipos_de_slot(self):
        # Sin nota no hay imagen: ImagenGaleria la exige con min_length=1.
        self.assertEqual(set(NOTAS_POR_TIPO), set(TIPOS_SLOT))

    def test_la_lista_valida_contra_el_modelo_real_de_la_ficha(self):
        ficha = _ficha([
            {"tipo": "producto_limpio", "fuente": "generado_motor",
             "archivo": "galeria/01-producto_limpio.webp", "origen": "verificado"},
            {"tipo": "partes_senaladas", "fuente": "generado_motor",
             "archivo": "galeria/02-partes_senaladas.webp",
             "origen": "encontrado_web"},
        ])
        incluidas, _ = imagenes_confirmadas_del_plan(ficha)
        multimedia = Multimedia.model_validate(
            {"imagenes_galeria_confirmadas": incluidas})
        self.assertEqual(len(multimedia.imagenes_galeria_confirmadas), 2)

    def test_calcular_el_puente_no_muta_la_ficha(self):
        ficha = _ficha([{"tipo": "medidas", "fuente": "generado_motor",
                         "archivo": "galeria/02-medidas.webp",
                         "origen": "encontrado_web"}])
        antes = json.dumps(ficha, sort_keys=True)
        imagenes_confirmadas_del_plan(ficha)
        self.assertEqual(json.dumps(ficha, sort_keys=True), antes)

    def test_ficha_sin_plan_no_devuelve_nada_ni_rompe(self):
        self.assertEqual(imagenes_confirmadas_del_plan({"multimedia": {}}), ([], []))

    def test_el_guardado_explicito_escribe_el_campo_del_publicador(self):
        ficha = _ficha([{"tipo": "medidas", "fuente": "generado_motor",
                         "archivo": "galeria/02-medidas.webp",
                         "origen": "encontrado_web"}])
        incluidas, _ = imagenes_confirmadas_del_plan(ficha)
        aplicar_confirmadas(ficha, incluidas)
        self.assertEqual(
            ficha["multimedia"]["imagenes_galeria_confirmadas"], incluidas)

    def test_de_punta_a_punta_lo_producido_llega_al_publicador(self):
        # La entrada de este caso NO esta escrita a mano: la produce el motor.
        ficha = _ficha([{"tipo": "producto_limpio", "fuente": "generado_motor"}])
        aplicar_informe(ficha, producir_galeria(ficha, self.recorte, self.destino))

        incluidas, omitidas = imagenes_confirmadas_del_plan(ficha)
        self.assertEqual(omitidas, [])
        self.assertEqual(len(incluidas), 1)
        self.assertTrue(Path(incluidas[0]["url"]).is_file())

        aplicar_confirmadas(ficha, incluidas)
        multimedia = Multimedia.model_validate(ficha["multimedia"])
        self.assertEqual(len(multimedia.imagenes_galeria_confirmadas), 1)


class PruebasRelativizarALaCarpetaDeLaFicha(BaseMotor):
    """El Publicador busca cada imagen como `carpeta_de_la_ficha / url`, y el
    motor las escribe relativas al directorio desde donde se lo corrio.

    Estas pruebas fijan que las dos bases coincidan. Con la ficha en la RAIZ
    coincidian por casualidad (el unico caso probado hasta el 22-jul-2026, el
    4212); con la ficha en una subcarpeta la imagen existia para el motor y
    faltaba para el Publicador, y el fallo aparecia recien al publicar.
    """

    def test_relativiza_y_el_publicador_la_resuelve(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta_ficha = Path(tmp) / "producto"
            (carpeta_ficha / "galeria").mkdir(parents=True)
            archivo = carpeta_ficha / "galeria" / "01-producto_limpio.webp"
            archivo.write_bytes(b"x")

            informe = {"producidos": [
                {"indice": 1, "tipo": "producto_limpio", "archivo": str(archivo)}
            ]}
            avisos = relativizar_a_carpeta_de_ficha(informe, carpeta_ficha)

            url = informe["producidos"][0]["archivo"]
            self.assertEqual(avisos, [])
            self.assertEqual(url, "galeria/01-producto_limpio.webp")
            # Las dos reglas del Publicador, tal cual las aplica el:
            self.assertTrue(ruta_relativa_segura(url))
            self.assertTrue((carpeta_ficha / url).is_file())

    def test_archivo_fuera_de_la_carpeta_avisa_y_no_reescribe(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            carpeta_ficha = raiz / "producto"
            carpeta_ficha.mkdir(parents=True)
            (raiz / "otra_carpeta").mkdir()
            afuera = raiz / "otra_carpeta" / "01-producto_limpio.webp"
            afuera.write_bytes(b"x")

            informe = {"producidos": [
                {"indice": 1, "tipo": "producto_limpio", "archivo": str(afuera)}
            ]}
            avisos = relativizar_a_carpeta_de_ficha(informe, carpeta_ficha)

            # Se avisa y NO se reescribe: inventar un '..' solo moveria el
            # error, porque el Publicador rechaza esas rutas a proposito.
            self.assertEqual(len(avisos), 1)
            self.assertEqual(informe["producidos"][0]["archivo"], str(afuera))


class PruebasSlotSinOrigen(BaseMotor):
    """Una pieza cuyo origen no se puede determinar se OMITE, no revienta.

    Caso reproducido el 22-jul-2026: plan sin 'imagen_base_origen' y slot sin
    'origen' —combinacion que el esquema ACEPTA—. El motor producia el archivo
    igual, `aplicar_informe` lo volcaba al plan sin origen, y la revalidacion
    moria con ValidationError ('el origen esta vacio'). El motor declara
    "degradar, no fallar" en su propio docstring: esto lo hace cumplir.

    El helper `_ficha()` nunca ejercita esta rama porque siempre escribe
    'imagen_base_origen'; por eso estos casos usan `_ficha_sin_origen()`.
    """

    def test_la_ficha_del_caso_es_valida_para_el_esquema(self):
        # Sin esto lo demas no prueba nada: si el esquema la rechazara, el
        # motor jamas veria esta ficha.
        ficha = _ficha_sin_origen([{"tipo": "producto_limpio",
                                    "fuente": "generado_motor",
                                    "deriva_de": "producto/01.jpg"}])
        self.assertIsNotNone(plan_de_ficha(ficha))

    def test_producto_limpio_sin_origen_se_omite_con_motivo_accionable(self):
        ficha = _ficha_sin_origen([{"tipo": "producto_limpio",
                                    "fuente": "generado_motor",
                                    "deriva_de": "producto/01.jpg"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)

        self.assertEqual(informe["producidos"], [])
        motivo = informe["omitidos"][0]["motivo"]
        self.assertIn("sin origen", motivo)
        # El motivo tiene que decir COMO arreglarlo, no solo que fallo.
        self.assertIn("origen", motivo)
        self.assertIn("imagen_base_origen", motivo)

    def test_no_queda_el_archivo_de_la_pieza_omitida(self):
        # El corte va ANTES de dibujar: no se produce un archivo que nadie
        # firma y que despues nadie borra.
        ficha = _ficha_sin_origen([{"tipo": "producto_limpio",
                                    "fuente": "generado_motor",
                                    "deriva_de": "producto/01.jpg"}])
        producir_galeria(ficha, self.recorte, self.destino)
        self.assertFalse((self.destino / "01-producto_limpio.webp").exists())

    def test_medidas_sin_origen_se_omiten(self):
        # Mismo control para los tres tipos que el motor produce, no solo uno.
        ficha = _ficha_sin_origen(
            [{"tipo": "medidas", "fuente": "generado_motor",
              "deriva_de": "producto/01.jpg"}],
            {"dimensiones": {"alto": "85 cm", "ancho": "43 cm"}},
        )
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(informe["producidos"], [])
        self.assertIn("dimensiones_origen", informe["omitidos"][0]["motivo"])

    def test_partes_senaladas_sin_origen_se_omiten(self):
        ficha = _ficha_sin_origen(
            [{"tipo": "partes_senaladas", "fuente": "generado_motor",
              "deriva_de": "producto/01.jpg"}],
            {"callouts": [{"label": "Motor", "point": [0.5, 0.5]}]},
        )
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(informe["producidos"], [])
        self.assertIn("callouts_origen", informe["omitidos"][0]["motivo"])

    def test_el_origen_del_slot_alcanza_aunque_el_plan_no_lo_traiga(self):
        # El plan no declara origen, pero el slot si: hay quien responde.
        ficha = _ficha_sin_origen([{"tipo": "producto_limpio",
                                    "fuente": "generado_motor",
                                    "deriva_de": "producto/01.jpg",
                                    "origen": "encontrado_web"}])
        informe = producir_galeria(ficha, self.recorte, self.destino)
        self.assertEqual(len(informe["producidos"]), 1)
        self.assertEqual(informe["producidos"][0]["origen"], "encontrado_web")

    def test_el_plan_actualizado_sigue_siendo_valido_sin_origen(self):
        # La cadena completa: producir -> volcar al plan -> revalidar. Aqui es
        # donde saltaba el ValidationError.
        ficha = _ficha_sin_origen([{"tipo": "producto_limpio",
                                    "fuente": "generado_motor",
                                    "deriva_de": "producto/01.jpg"}])
        aplicar_informe(ficha, producir_galeria(ficha, self.recorte, self.destino))
        self.assertIsNotNone(plan_de_ficha(ficha))
        self.assertEqual(imagenes_confirmadas_del_plan(ficha)[0], [])

    def test_el_cli_termina_bien_con_una_pieza_sin_origen(self):
        # La prueba literal del sintoma: `python motor_galeria.py ...` moria con
        # exit 1. Correr main() sin SystemExit es el exit 0 de esa corrida.
        ruta_ficha = self.dir / "ficha.json"
        ruta_ficha.write_text(json.dumps(_ficha_sin_origen(
            [{"tipo": "producto_limpio", "fuente": "generado_motor",
              "deriva_de": "producto/01.jpg"}])), encoding="utf-8")
        argv = ["motor_galeria.py", str(self.recorte), "--ficha", str(ruta_ficha),
                "--destino", str(self.destino)]
        salida = io.StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(salida):
            main()
        self.assertIn("omitido", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
