"""Pruebas de subtitulos. Offline: no llaman a la API real de ElevenLabs
(forced_alignment.create, servicio de red pago) ni a ffmpeg real (herramienta
externa pesada). Solo se prueba la logica pura que arma el .srt a partir de
una alineacion FABRICADA A MANO (simulando lo que devolveria
forced_alignment.create ya convertido a dicts por alinear_audio):
agrupar_palabras_en_lineas, _formato_tiempo_srt y armar_srt.

alinear_audio/quemar_subtitulos/generar_a_archivo (que si llaman a
ElevenLabs/ffmpeg) se verifican a mano/CLI contra un guion y audio reales,
igual que _sintetizar_voz en voz_en_off.py y generar_a_archivo en
marca_agua.py/preparar_video_producto.py.
"""

import unittest

import subtitulos as sub


def _palabra(texto, inicio, fin):
    return {"texto": texto, "inicio": inicio, "fin": fin}


class PruebasFormatoTiempoSrt(unittest.TestCase):
    def test_cero_segundos(self):
        self.assertEqual(sub._formato_tiempo_srt(0.0), "00:00:00,000")

    def test_milisegundos_redondean_correcto(self):
        self.assertEqual(sub._formato_tiempo_srt(1.234), "00:00:01,234")

    def test_pasa_el_minuto(self):
        self.assertEqual(sub._formato_tiempo_srt(65.5), "00:01:05,500")

    def test_pasa_la_hora(self):
        self.assertEqual(sub._formato_tiempo_srt(3661.001), "01:01:01,001")

    def test_negativo_se_trata_como_cero(self):
        self.assertEqual(sub._formato_tiempo_srt(-1.0), "00:00:00,000")

    def test_redondeo_de_milisegundos_no_se_come_el_segundo(self):
        # 1.9995s redondeado a milisegundos completos es 2.000s, no 1.9995
        # truncado a "01,999" ni desbordado a un campo de ms invalido.
        self.assertEqual(sub._formato_tiempo_srt(1.9995), "00:00:02,000")


class PruebasAgruparPalabrasEnLineas(unittest.TestCase):
    def test_lista_vacia_da_lista_vacia(self):
        self.assertEqual(sub.agrupar_palabras_en_lineas([]), [])

    def test_agrupa_en_bloques_de_como_mucho_el_maximo(self):
        # 10 palabras sin puntuacion, maximo 6 -> primer bloque de 6, resto
        # de 4 (>= minimo 3, no se funde con el anterior).
        palabras = [_palabra(f"p{i}", i * 0.5, i * 0.5 + 0.4) for i in range(10)]

        lineas = sub.agrupar_palabras_en_lineas(palabras, minimo=3, maximo=6)

        self.assertEqual(len(lineas), 2)
        self.assertEqual(lineas[0]["texto"], "p0 p1 p2 p3 p4 p5")
        self.assertEqual(lineas[1]["texto"], "p6 p7 p8 p9")

    def test_corta_en_puntuacion_de_cierre_de_oracion(self):
        palabras = [
            _palabra("Hola", 0.0, 0.3),
            _palabra("mundo.", 0.3, 0.6),
            _palabra("Esto", 0.6, 0.9),
            _palabra("es", 0.9, 1.0),
            _palabra("una", 1.0, 1.2),
            _palabra("prueba.", 1.2, 1.6),
        ]

        lineas = sub.agrupar_palabras_en_lineas(palabras, minimo=2, maximo=6)

        self.assertEqual(len(lineas), 2)
        self.assertEqual(lineas[0]["texto"], "Hola mundo.")
        self.assertEqual(lineas[1]["texto"], "Esto es una prueba.")

    def test_no_corta_en_puntuacion_si_no_llego_al_minimo(self):
        # "mundo." termina oracion pero solo hay 1 palabra: con minimo=3 no
        # alcanza a cortar ahi, sigue acumulando.
        palabras = [
            _palabra("mundo.", 0.0, 0.3),
            _palabra("Sigue", 0.3, 0.6),
            _palabra("aca.", 0.6, 0.9),
        ]

        lineas = sub.agrupar_palabras_en_lineas(palabras, minimo=3, maximo=6)

        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas[0]["texto"], "mundo. Sigue aca.")

    def test_resto_final_corto_se_funde_con_la_linea_anterior(self):
        # 8 palabras, maximo 4: primer bloque de 4, quedan 4 en el segundo
        # bloque -- exactamente el minimo, no se funde (caso limite).
        # Con 7 palabras el resto (3) es igual al minimo tampoco se funde;
        # probamos con 6 para que el resto (2) quede POR DEBAJO del minimo=3
        # y se funda con el bloque anterior.
        palabras = [_palabra(f"p{i}", i * 0.5, i * 0.5 + 0.4) for i in range(6)]

        lineas = sub.agrupar_palabras_en_lineas(palabras, minimo=3, maximo=4)

        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas[0]["texto"], "p0 p1 p2 p3 p4 p5")

    def test_resto_final_que_alcanza_el_minimo_queda_como_linea_propia(self):
        palabras = [_palabra(f"p{i}", i * 0.5, i * 0.5 + 0.4) for i in range(7)]

        lineas = sub.agrupar_palabras_en_lineas(palabras, minimo=3, maximo=4)

        self.assertEqual(len(lineas), 2)
        self.assertEqual(lineas[0]["texto"], "p0 p1 p2 p3")
        self.assertEqual(lineas[1]["texto"], "p4 p5 p6")

    def test_tiempos_de_la_linea_son_inicio_de_la_primera_y_fin_de_la_ultima(self):
        palabras = [
            _palabra("Hola", 1.0, 1.3),
            _palabra("como", 1.3, 1.6),
            _palabra("estas", 1.6, 2.0),
        ]

        lineas = sub.agrupar_palabras_en_lineas(palabras, minimo=3, maximo=6)

        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas[0]["inicio"], 1.0)
        self.assertEqual(lineas[0]["fin"], 2.0)

    def test_unica_palabra_de_todo_el_guion_queda_sola(self):
        # unico caso donde SI puede quedar una linea corta (por debajo del
        # minimo): cuando es la unica palabra de todo el guion, no hay
        # ninguna linea anterior con la que fundirse.
        palabras = [_palabra("Hola.", 0.0, 0.5)]

        lineas = sub.agrupar_palabras_en_lineas(palabras, minimo=3, maximo=6)

        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas[0]["texto"], "Hola.")


class PruebasArmarSrt(unittest.TestCase):
    def test_lista_vacia_da_string_vacio(self):
        self.assertEqual(sub.armar_srt([]), "")

    def test_un_bloque_bien_formado(self):
        lineas = [{"texto": "Hola mundo", "inicio": 0.0, "fin": 1.5}]

        contenido = sub.armar_srt(lineas)

        self.assertEqual(
            contenido,
            "1\n00:00:00,000 --> 00:00:01,500\nHola mundo\n\n",
        )

    def test_varios_bloques_numerados_en_orden(self):
        lineas = [
            {"texto": "Primera linea", "inicio": 0.0, "fin": 1.0},
            {"texto": "Segunda linea", "inicio": 1.0, "fin": 2.2},
            {"texto": "Tercera linea", "inicio": 2.2, "fin": 3.0},
        ]

        contenido = sub.armar_srt(lineas)
        bloques = contenido.strip("\n").split("\n\n")

        self.assertEqual(len(bloques), 3)
        self.assertTrue(bloques[0].startswith("1\n"))
        self.assertTrue(bloques[1].startswith("2\n"))
        self.assertTrue(bloques[2].startswith("3\n"))
        self.assertIn("Segunda linea", bloques[1])

    def test_formato_de_timestamp_en_el_bloque(self):
        lineas = [{"texto": "x", "inicio": 65.25, "fin": 70.0}]

        contenido = sub.armar_srt(lineas)

        self.assertIn("00:01:05,250 --> 00:01:10,000", contenido)


class PruebasEscaparRutaParaFiltro(unittest.TestCase):
    def test_convierte_barras_invertidas_a_normales(self):
        from pathlib import PureWindowsPath

        resultado = sub._escapar_ruta_para_filtro(
            PureWindowsPath(r"C:\Users\Angie\sub.srt")
        )

        self.assertNotIn("\\U", resultado)  # sin barra invertida sin escapar
        self.assertIn("/Users/Angie/sub.srt", resultado)

    def test_escapa_los_dos_puntos_de_la_unidad(self):
        from pathlib import PureWindowsPath

        resultado = sub._escapar_ruta_para_filtro(
            PureWindowsPath(r"C:\Users\Angie\sub.srt")
        )

        self.assertIn("C\\:", resultado)


if __name__ == "__main__":
    unittest.main()
