"""Pruebas del contrato multimedia.plan_galeria.

El plan describe QUE lleva la galeria de un producto, de que foto real sale
cada pieza y quien responde por ella. Lo que se verifica aqui son las dos
promesas del contrato:

1. Ninguna imagen del producto puede nacer sin una foto real detras
   (asi la generacion texto->imagen queda imposible de expresar).
2. Una recreacion nunca puede presentarse como fotografia, ni al reves.
"""

import unittest

from pydantic import ValidationError

from esquema_ficha import Multimedia, PlanGaleria, SlotGaleria


def _plan(**extra):
    """Plan minimo valido, para no repetir el andamiaje en cada prueba."""
    base = {
        "imagen_base": "molino/01-original.jpg",
        "imagen_base_origen": "encontrado_web",
    }
    base.update(extra)
    return base


class PruebasAnclaje(unittest.TestCase):
    """Toda pieza derivada declara de que imagen real salio."""

    def test_foto_real_no_necesita_base(self):
        p = PlanGaleria.model_validate({
            "slots": [{"tipo": "foto_real", "fuente": "foto_real"}]
        })
        self.assertFalse(p.slots[0].necesita_base())

    def test_slot_generado_sin_ancla_se_rechaza(self):
        # Sin imagen_base ni deriva_de: es exactamente el caso "texto->imagen".
        with self.assertRaises(ValidationError) as ctx:
            PlanGaleria.model_validate({
                "slots": [{"tipo": "otro_angulo_ia", "fuente": "imagen_a_imagen"}]
            })
        self.assertIn("otro_angulo_ia", str(ctx.exception))

    def test_slot_generado_se_ancla_al_imagen_base_del_plan(self):
        p = PlanGaleria.model_validate(_plan(slots=[
            {"tipo": "medidas", "fuente": "generado_motor"}
        ]))
        self.assertTrue(p.slots[0].necesita_base())

    def test_slot_generado_se_ancla_a_su_propio_deriva_de(self):
        # Sin imagen_base en el plan, pero el slot dice de donde sale.
        p = PlanGaleria.model_validate({
            "slots": [{
                "tipo": "partes_senaladas",
                "fuente": "generado_motor",
                "deriva_de": "molino/03-completa.jpg",
            }]
        })
        self.assertEqual(p.slots[0].deriva_de, "molino/03-completa.jpg")

    def test_edicion_manual_tambien_exige_ancla(self):
        # Lo que Angie hace hoy en Canva tambien sale de una foto real.
        with self.assertRaises(ValidationError):
            PlanGaleria.model_validate({
                "slots": [{"tipo": "partes_senaladas", "fuente": "edicion_manual"}]
            })

    def test_imagen_base_sin_origen_se_rechaza(self):
        with self.assertRaises(ValidationError):
            PlanGaleria.model_validate({"imagen_base": "molino/01.jpg"})


class PruebasCoherenciaFuenteOrigen(unittest.TestCase):
    """Una recreacion no se disfraza de foto, ni una foto de recreacion."""

    def test_ia_no_puede_declararse_verificada(self):
        with self.assertRaises(ValidationError) as ctx:
            SlotGaleria.model_validate({
                "tipo": "otro_angulo_ia",
                "fuente": "imagen_a_imagen",
                "origen": "verificado",
            })
        self.assertIn("afirma que es una foto real", str(ctx.exception))

    def test_ia_no_puede_declararse_encontrada_en_web(self):
        with self.assertRaises(ValidationError):
            SlotGaleria.model_validate({
                "tipo": "escena_funcionamiento",
                "fuente": "escena_ia",
                "origen": "encontrado_web",
            })

    def test_ia_con_origen_generado_es_valida(self):
        s = SlotGaleria.model_validate({
            "tipo": "otro_angulo_ia",
            "fuente": "imagen_a_imagen",
            "origen": "generado_ia_sin_verificar",
        })
        self.assertEqual(s.fuente, "imagen_a_imagen")

    def test_ia_revisada_por_angie_es_valida(self):
        # Regla 6: revision humana siempre. Angie puede responder por ella.
        s = SlotGaleria.model_validate({
            "tipo": "escena_funcionamiento",
            "fuente": "escena_ia",
            "origen": "confirmado_por_angie (22-jul-2026)",
        })
        self.assertIn("confirmado_por_angie", s.origen)

    def test_foto_real_no_puede_declararse_generada_por_ia(self):
        with self.assertRaises(ValidationError) as ctx:
            SlotGaleria.model_validate({
                "tipo": "foto_real",
                "fuente": "foto_real",
                "origen": "generado_ia",
            })
        self.assertIn("afirma que la genero una IA", str(ctx.exception))

    def test_generado_ia_sin_verificar_no_se_confunde_con_verificado(self):
        # Limite de palabra: 'verificado' NO esta dentro de
        # 'generado_ia_sin_verificar'. Si se confundieran, este slot
        # legitimo se rechazaria.
        s = SlotGaleria.model_validate({
            "tipo": "otro_angulo_ia",
            "fuente": "imagen_a_imagen",
            "origen": "generado_ia_sin_verificar",
        })
        self.assertIsNotNone(s.origen)


class PruebasArchivoYOrigen(unittest.TestCase):
    def test_slot_planificado_sin_archivo_no_exige_origen(self):
        # Todavia no se produjo: no hay nada que declarar.
        s = SlotGaleria.model_validate({"tipo": "medidas", "fuente": "generado_motor"})
        self.assertIsNone(s.origen)

    def test_slot_con_archivo_exige_origen(self):
        with self.assertRaises(ValidationError):
            SlotGaleria.model_validate({
                "tipo": "medidas",
                "fuente": "generado_motor",
                "archivo": "galeria/06-medidas.webp",
            })

    def test_archivo_vacio_se_rechaza(self):
        with self.assertRaises(ValidationError):
            SlotGaleria.model_validate({
                "tipo": "medidas", "fuente": "generado_motor", "archivo": "   ",
            })

    def test_imagen_de_ia_exige_sufijo_IA_en_el_archivo(self):
        with self.assertRaises(ValidationError) as ctx:
            SlotGaleria.model_validate({
                "tipo": "otro_angulo_ia",
                "fuente": "imagen_a_imagen",
                "origen": "generado_ia_sin_verificar",
                "archivo": "galeria/07-angulo.webp",
            })
        self.assertIn("_IA", str(ctx.exception))

    def test_imagen_de_ia_con_sufijo_IA_es_valida(self):
        s = SlotGaleria.model_validate({
            "tipo": "otro_angulo_ia",
            "fuente": "imagen_a_imagen",
            "origen": "generado_ia_sin_verificar",
            "archivo": "galeria/07-angulo_IA.webp",
        })
        self.assertTrue(s.archivo.endswith("_IA.webp"))

    def test_pieza_del_motor_no_exige_sufijo_IA(self):
        # El motor no es IA: dibuja datos reales de la ficha.
        s = SlotGaleria.model_validate({
            "tipo": "medidas",
            "fuente": "generado_motor",
            "origen": "encontrado_web",
            "archivo": "galeria/06-medidas.webp",
        })
        self.assertIsNotNone(s.archivo)


class PruebasVocabulario(unittest.TestCase):
    def test_tipo_desconocido_se_rechaza(self):
        with self.assertRaises(ValidationError):
            SlotGaleria.model_validate({"tipo": "video_promocional", "fuente": "foto_real"})

    def test_fuente_desconocida_se_rechaza(self):
        with self.assertRaises(ValidationError):
            SlotGaleria.model_validate({"tipo": "foto_real", "fuente": "photoshop"})


class PruebasPlanCompleto(unittest.TestCase):
    def test_galeria_del_proceso_manual_de_angie(self):
        """Los 8 slots del proceso real, mezclando material y mecanismos."""
        p = PlanGaleria.model_validate(_plan(slots=[
            {"tipo": "portada_variantes", "fuente": "compuesto",
             "origen": "encontrado_web"},
            {"tipo": "persona_escala", "fuente": "escena_ia",
             "origen": "generado_ia_sin_verificar"},
            {"tipo": "partes_senaladas", "fuente": "generado_motor",
             "origen": "encontrado_web"},
            {"tipo": "escena_funcionamiento", "fuente": "escena_ia",
             "origen": "generado_ia_sin_verificar"},
            {"tipo": "foto_real", "fuente": "foto_real",
             "origen": "encontrado_web"},
            {"tipo": "medidas", "fuente": "generado_motor",
             "origen": "encontrado_web"},
            {"tipo": "otro_angulo_ia", "fuente": "imagen_a_imagen",
             "origen": "generado_ia_sin_verificar"},
            {"tipo": "accesorios", "fuente": "foto_real",
             "origen": "confirmado_por_angie"},
        ]))
        self.assertEqual(len(p.slots), 8)
        self.assertTrue(p.hay_slots())

    def test_galeria_corta_es_valida(self):
        # La cuota de 8 esta muerta: se llena lo que el material permita.
        p = PlanGaleria.model_validate(_plan(slots=[
            {"tipo": "producto_limpio", "fuente": "generado_motor",
             "origen": "encontrado_web"},
        ]))
        self.assertEqual(len(p.slots), 1)

    def test_plan_vacio_es_valido(self):
        self.assertFalse(PlanGaleria.model_validate({}).hay_slots())


class PruebasMultimedia(unittest.TestCase):
    def test_plan_galeria_es_opcional(self):
        # Las fichas viejas (4212, NBC250) siguen siendo validas.
        self.assertIsNone(Multimedia.model_validate({}).plan_galeria)

    def test_multimedia_acepta_plan_galeria(self):
        m = Multimedia.model_validate({"plan_galeria": _plan(slots=[
            {"tipo": "foto_real", "fuente": "foto_real", "origen": "encontrado_web"},
        ])})
        self.assertEqual(m.plan_galeria.slots[0].tipo, "foto_real")

    def test_plan_y_galeria_tomas_conviven(self):
        # No se superponen: uno dice QUE se arma, el otro trae los DATOS.
        m = Multimedia.model_validate({
            "plan_galeria": _plan(slots=[
                {"tipo": "medidas", "fuente": "generado_motor",
                 "origen": "encontrado_web"},
            ]),
            "galeria_tomas": {
                "dimensiones": {"alto": "85 cm"},
                "dimensiones_origen": "encontrado_web",
            },
        })
        self.assertEqual(m.plan_galeria.slots[0].tipo, "medidas")
        self.assertEqual(m.galeria_tomas.dimensiones.alto, "85 cm")


if __name__ == "__main__":
    unittest.main()
