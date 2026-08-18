"""Pruebas de voz_en_off. Offline: no llaman a ElevenLabs ni corren ffmpeg/
ffprobe reales (servicio de red pago / herramienta externa pesada). Solo se
prueba la logica pura: elegir_voz (alternancia por indice), armar_guion
(estructura fija + recorte por frases completas), factor_estiramiento (el
calculo del factor de slow-motion) y _cadena_atempo (como se encadenan los
filtros atempo de ffmpeg, que solo aceptan 0.5-2.0 por paso). generar_a_
archivo (llama a ElevenLabs) y preparar_clip_con_voz (llama a ffmpeg/
ffprobe) se verifican a mano/CLI contra una ficha y un clip reales, mismo
criterio que el resto de los modulos de video de este proyecto (preparar_
video_producto.py, ensamblar_video_producto.py, marca_agua.py).
"""

import unittest

import voz_en_off as vo


class PruebasElegirVoz(unittest.TestCase):
    def test_indice_0_devuelve_carlos(self):
        self.assertEqual(vo.elegir_voz(0), "carlos")
        self.assertEqual(vo.elegir_voz(6), "carlos")
        self.assertEqual(vo.elegir_voz(12), "carlos")

    def test_indice_1_devuelve_gonzalo(self):
        self.assertEqual(vo.elegir_voz(1), "gonzalo")
        self.assertEqual(vo.elegir_voz(7), "gonzalo")
        self.assertEqual(vo.elegir_voz(13), "gonzalo")

    def test_indice_2_devuelve_santiago(self):
        self.assertEqual(vo.elegir_voz(2), "santiago")
        self.assertEqual(vo.elegir_voz(8), "santiago")
        self.assertEqual(vo.elegir_voz(14), "santiago")

    def test_indice_3_devuelve_adberto(self):
        self.assertEqual(vo.elegir_voz(3), "adberto")
        self.assertEqual(vo.elegir_voz(9), "adberto")

    def test_indice_4_devuelve_el_faraon(self):
        self.assertEqual(vo.elegir_voz(4), "el_faraon")
        self.assertEqual(vo.elegir_voz(10), "el_faraon")

    def test_indice_5_devuelve_fernando(self):
        self.assertEqual(vo.elegir_voz(5), "fernando")
        self.assertEqual(vo.elegir_voz(11), "fernando")

    def test_alterna_en_secuencia(self):
        voces = [vo.elegir_voz(i) for i in range(6)]
        self.assertEqual(
            voces,
            ["carlos", "gonzalo", "santiago", "adberto", "el_faraon", "fernando"],
        )


class PruebasArmarGuion(unittest.TestCase):
    def test_descripcion_corta_no_se_recorta(self):
        datos = {"descripcion_principal": "Producto robusto y confiable."}
        guion = vo.armar_guion(datos, presupuesto_caracteres=500)

        self.assertTrue(guion.startswith(vo.FRASE_FIJA))
        self.assertTrue(guion.endswith(vo.FRASE_FIJA))
        self.assertIn("Producto robusto y confiable.", guion)
        # No se rellena artificialmente: la frase fija aparece exactamente
        # dos veces (inicio y cierre), no de mas.
        self.assertEqual(guion.count(vo.FRASE_FIJA), 2)

    def test_descripcion_larga_se_recorta_por_frases_completas(self):
        cuerpo = (
            "Primera frase bien larga sobre el producto y sus beneficios. "
            "Segunda frase que tambien suma bastante texto de relleno. "
            "Tercera frase que ya no deberia entrar en el presupuesto."
        )
        datos = {"descripcion_principal": cuerpo}
        # presupuesto_caracteres es del GUION COMPLETO (las dos FRASE_FIJA
        # incluidas): hay que sumar ese overhead para que le alcance al
        # cuerpo justo para la primera frase pero no para las tres.
        overhead_frases_fijas = 2 * len(vo.FRASE_FIJA) + 2
        presupuesto = (
            overhead_frases_fijas
            + len("Primera frase bien larga sobre el producto y sus beneficios.")
            + 5
        )

        guion = vo.armar_guion(datos, presupuesto_caracteres=presupuesto)

        self.assertIn("Primera frase bien larga sobre el producto y sus beneficios.", guion)
        self.assertNotIn("Segunda frase", guion)
        self.assertNotIn("Tercera frase", guion)
        # Nunca corta a mitad de oracion: si cortara a mitad de la segunda
        # frase, la palabra "relleno" (que solo aparece en ella) se colaria
        # sin su punto final.
        self.assertNotIn("relleno", guion)

    def test_usa_descripcion_banner_si_existe_sobre_descripcion_principal(self):
        datos = {
            "descripcion_banner": "Texto de banner corto.",
            "descripcion_principal": "Texto principal que no deberia usarse.",
        }
        guion = vo.armar_guion(datos, presupuesto_caracteres=500)

        self.assertIn("Texto de banner corto.", guion)
        self.assertNotIn("Texto principal que no deberia usarse.", guion)

    def test_sin_ninguna_descripcion_el_guion_es_solo_la_frase_fija_dos_veces(self):
        guion = vo.armar_guion({}, presupuesto_caracteres=500)

        self.assertEqual(guion, f"{vo.FRASE_FIJA} {vo.FRASE_FIJA}")

    def test_presupuesto_cero_no_deja_pasar_ninguna_frase(self):
        datos = {"descripcion_principal": "Una frase cualquiera del producto."}
        guion = vo.armar_guion(datos, presupuesto_caracteres=0)

        self.assertEqual(guion, f"{vo.FRASE_FIJA} {vo.FRASE_FIJA}")

    def test_cuerpo_manual_se_usa_tal_cual_sin_recortar(self):
        # Un guion redactado a mano (copy de venta) no se recorta aunque
        # supere el presupuesto: quien lo escribe ya apunta al largo
        # correcto (decision de Angie, 6-ago-2026 -- ver memoria de sesion).
        cuerpo = "Copy de venta redactado a mano, mas largo que el presupuesto."
        datos = {"descripcion_principal": "Esto no se deberia usar."}
        guion = vo.armar_guion(datos, presupuesto_caracteres=10,
                               cuerpo_manual=cuerpo)

        self.assertIn(cuerpo, guion)
        self.assertNotIn("Esto no se deberia usar.", guion)
        self.assertTrue(guion.startswith(vo.FRASE_FIJA))
        self.assertTrue(guion.endswith(vo.FRASE_FIJA))

    def test_cuerpo_manual_tiene_prioridad_sobre_la_ficha(self):
        datos = {"descripcion_banner": "Descripcion de la ficha, no del copy."}
        guion = vo.armar_guion(datos, presupuesto_caracteres=500,
                               cuerpo_manual="Copy escrito por Claude.")

        self.assertIn("Copy escrito por Claude.", guion)
        self.assertNotIn("Descripcion de la ficha, no del copy.", guion)


class PruebasFactorEstiramiento(unittest.TestCase):
    def test_clip_mas_corto_devuelve_factor_mayor_a_uno(self):
        # Voz el doble de larga que el clip: hay que ponerlo a mitad de
        # velocidad (factor 2.0) para que dure lo mismo.
        self.assertAlmostEqual(vo.factor_estiramiento(10.0, 20.0), 2.0)

    def test_clip_mas_largo_no_hace_falta_estirar(self):
        # El clip ya alcanza y sobra: factor 1.0 (no estirar), nunca menor a
        # 1.0 (no se "acelera" el clip, esa no es la funcion de este calculo).
        self.assertEqual(vo.factor_estiramiento(30.0, 20.0), 1.0)

    def test_clip_misma_duracion_no_hace_falta_estirar(self):
        self.assertEqual(vo.factor_estiramiento(20.0, 20.0), 1.0)

    def test_duracion_clip_cero_o_negativa_lanza_valueerror(self):
        with self.assertRaises(ValueError):
            vo.factor_estiramiento(0.0, 20.0)
        with self.assertRaises(ValueError):
            vo.factor_estiramiento(-5.0, 20.0)


class PruebasCadenaAtempo(unittest.TestCase):
    def test_factor_dentro_de_rango_da_un_solo_paso(self):
        self.assertEqual(vo._cadena_atempo(0.8), "atempo=0.8")
        self.assertEqual(vo._cadena_atempo(1.5), "atempo=1.5")

    def test_factor_menor_a_0_5_encadena_varios_pasos(self):
        # 0.25 = 0.5 * 0.5: dos pasos de atempo, cada uno dentro de rango.
        cadena = vo._cadena_atempo(0.25)
        pasos = [float(p.split("=")[1]) for p in cadena.split(",")]
        self.assertTrue(all(0.5 <= p <= 2.0 for p in pasos))
        producto = 1.0
        for p in pasos:
            producto *= p
        self.assertAlmostEqual(producto, 0.25)

    def test_factor_mayor_a_2_encadena_varios_pasos(self):
        cadena = vo._cadena_atempo(4.0)
        pasos = [float(p.split("=")[1]) for p in cadena.split(",")]
        self.assertTrue(all(0.5 <= p <= 2.0 for p in pasos))
        producto = 1.0
        for p in pasos:
            producto *= p
        self.assertAlmostEqual(producto, 4.0)

    def test_factor_extremo_sigue_dando_pasos_validos(self):
        # Estiramiento muy grande (clip muchisimo mas corto que la voz):
        # sigue resolviendose encadenando pasos, cada uno dentro de rango.
        cadena = vo._cadena_atempo(1 / 10.0)
        pasos = [float(p.split("=")[1]) for p in cadena.split(",")]
        self.assertTrue(all(0.5 <= p <= 2.0 for p in pasos))
        producto = 1.0
        for p in pasos:
            producto *= p
        self.assertAlmostEqual(producto, 0.1)

    def test_factor_invalido_lanza_valueerror(self):
        with self.assertRaises(ValueError):
            vo._cadena_atempo(0.0)
        with self.assertRaises(ValueError):
            vo._cadena_atempo(-1.0)


if __name__ == "__main__":
    unittest.main()
