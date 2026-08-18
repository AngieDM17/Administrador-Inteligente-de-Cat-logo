"""Pruebas de musica. Offline: no llaman a ElevenLabs ni corren ffmpeg/ffprobe
reales (servicio de red pago / herramienta externa pesada). Solo se prueba la
logica pura: calcular_duracion_generacion_ms (cuanto pedirle a music.compose
para que alcance y sobre para recortar exacto despues) y las constantes de
sonoridad (LOUDNORM_MUSICA_I/TP, mismo mecanismo que la voz en voz_en_off.py).
generar_musica (llama a ElevenLabs) y mezclar_musica_de_fondo (llama a
ElevenLabs y a ffmpeg/ffprobe) se verifican a mano/CLI contra una voz y un
clip reales, mismo criterio que el resto de los modulos de video de este
proyecto (voz_en_off.py, marca_agua.py, subtitulos.py,
preparar_video_producto.py).
"""

import unittest

import musica as mu


class PruebasCalcularDuracionGeneracionMs(unittest.TestCase):
    def test_suma_el_margen_extra_a_la_duracion_del_video(self):
        resultado = mu.calcular_duracion_generacion_ms(42.0)
        self.assertEqual(resultado, round(42.0 * 1000) + mu.MARGEN_EXTRA_MS)

    def test_redondea_segundos_no_enteros(self):
        resultado = mu.calcular_duracion_generacion_ms(41.076)
        self.assertEqual(resultado, round(41.076 * 1000) + mu.MARGEN_EXTRA_MS)

    def test_nunca_baja_del_minimo_de_la_api(self):
        # Un video de 1s + margen (2000ms) da 3000ms exactos: justo el piso
        # documentado por la API. Un video mas corto todavia (irreal en este
        # pipeline, pero la funcion no debe pedir menos del piso) se acota.
        resultado = mu.calcular_duracion_generacion_ms(0.1)
        self.assertEqual(resultado, mu.DURACION_MINIMA_MS)

    def test_nunca_supera_el_maximo_de_la_api(self):
        resultado = mu.calcular_duracion_generacion_ms(1000.0)
        self.assertEqual(resultado, mu.DURACION_MAXIMA_MS)

    def test_duracion_cero_o_negativa_lanza_value_error(self):
        with self.assertRaises(ValueError):
            mu.calcular_duracion_generacion_ms(0)
        with self.assertRaises(ValueError):
            mu.calcular_duracion_generacion_ms(-5.0)


class PruebasConstantes(unittest.TestCase):
    def test_sonoridad_musica_es_mas_floja_que_la_voz(self):
        # LOUDNORM_VOZ_I (voz_en_off.py) esta en -12 LUFS; la musica tiene
        # que quedar mas floja (numero mas negativo) para que la voz siga
        # llevando el protagonismo, pero sin depender de un porcentaje fijo
        # sobre un volumen crudo que varia de una generacion a otra (bug
        # real, 18-ago-2026: "a veces casi no se escucha").
        import voz_en_off
        self.assertLess(mu.LOUDNORM_MUSICA_I, voz_en_off.LOUDNORM_VOZ_I)

    def test_techo_de_pico_deja_margen_bajo_cero(self):
        self.assertLess(mu.LOUDNORM_MUSICA_TP, 0.0)

    def test_margen_extra_es_positivo(self):
        self.assertGreater(mu.MARGEN_EXTRA_MS, 0)

    def test_limites_de_duracion_coinciden_con_la_api(self):
        self.assertEqual(mu.DURACION_MINIMA_MS, 3000)
        self.assertEqual(mu.DURACION_MAXIMA_MS, 600_000)


if __name__ == "__main__":
    unittest.main()
