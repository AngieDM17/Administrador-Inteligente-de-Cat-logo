"""Pruebas del generador de banners. Offline y sin red: usan una plantilla y un
recorte diminutos hechos en memoria con Pillow.
"""

import json
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import generador_banner as gb

RAIZ = Path(__file__).parent
FICHA_4212 = json.loads((RAIZ / "ficha_revisada_4212.json").read_text(encoding="utf-8-sig"))


def _plantilla(ancho=400, alto=400):
    return Image.new("RGBA", (ancho, alto), (20, 20, 20, 255))


def _recorte(ancho=120, alto=160):
    # Rectangulo opaco centrado sobre transparente (con margen transparente,
    # para comprobar que el alpha deja ver el fondo del chrome).
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([20, 20, ancho - 20, alto - 20], fill=(80, 140, 200, 255))
    return img


class PruebasTexto(unittest.TestCase):
    def test_corta_en_el_separador(self):
        self.assertEqual(
            gb.titulo_banner(FICHA_4212), "SISTEMA DE AIRE COMPRIMIDO 3 PIEZAS"
        )

    def test_sin_separador_devuelve_el_nombre(self):
        datos = {"producto": {"nombre_propuesto": "BICIMOTO ELECTRICA EB10"}}
        self.assertEqual(gb.titulo_banner(datos), "BICIMOTO ELECTRICA EB10")

    def test_corta_con_pipe(self):
        datos = {"producto": {"nombre_propuesto": "COMPRESOR X | detalle interno"}}
        self.assertEqual(gb.titulo_banner(datos), "COMPRESOR X")

    def test_descripcion_colapsa_espacios(self):
        datos = {"descripcion_principal": "  hola   mundo \n de   prueba "}
        self.assertEqual(gb.descripcion_banner(datos), "hola mundo de prueba")

    def test_descripcion_banner_limpia_marcas_internas(self):
        datos = {"descripcion_banner": "Aire limpio y seco.  [encontrado_web]"}
        self.assertEqual(gb.descripcion_banner(datos), "Aire limpio y seco.")

    def test_titulo_banner_limpia_marcas_internas(self):
        datos = {"producto": {"nombre_propuesto": "COMPRESOR X  [confirmado_por_angie]"}}
        self.assertEqual(gb.titulo_banner(datos), "COMPRESOR X")

    def test_descripcion_banner_prefiere_el_campo_corto(self):
        datos = {"descripcion_banner": "Gancho corto.", "descripcion_principal": "Texto largo largo."}
        self.assertEqual(gb.descripcion_banner(datos), "Gancho corto.")

    def test_descripcion_banner_cae_a_la_principal_si_no_hay_corta(self):
        datos = {"descripcion_banner": "   ", "descripcion_principal": "La principal."}
        self.assertEqual(gb.descripcion_banner(datos), "La principal.")

    def test_partir_en_frases(self):
        frases = gb.partir_en_frases("Uno. Dos y dos! Tres?")
        self.assertEqual(frases, ["Uno.", "Dos y dos!", "Tres?"])

    def test_cerrar_en_frases_no_corta_a_mitad(self):
        texto = "Primera frase corta. Segunda frase que ya no entra en la caja chica."
        # Caja angosta y baja: solo entra la primera frase completa.
        resultado = gb.cerrar_en_frases(texto, (0, 0, 200, 60), gb.RUTA_FUENTE, 20, 2, 1.1)
        self.assertEqual(resultado, "Primera frase corta.")
        self.assertTrue(resultado.endswith("."))


class PruebasAjusteTexto(unittest.TestCase):
    def test_caja_px_convierte_fracciones(self):
        self.assertEqual(gb._caja_px((0.0, 0.0, 0.5, 0.5), 400, 400), (0, 0, 200, 200))

    def test_texto_corto_usa_tamano_grande(self):
        fuente, lineas = gb.ajustar_texto(
            "HOLA", (0, 0, 400, 200), gb.RUTA_FUENTE, 80, 20, 3, 1.05
        )
        self.assertEqual(fuente.size, 80)
        self.assertEqual(lineas, ["HOLA"])

    def test_texto_largo_encoge_y_no_pasa_de_max_lineas(self):
        texto = "palabra " * 60
        fuente, lineas = gb.ajustar_texto(
            texto, (0, 0, 200, 120), gb.RUTA_FUENTE, 40, 10, 3, 1.1
        )
        self.assertLessEqual(len(lineas), 3)
        self.assertGreaterEqual(fuente.size, 10)
        self.assertTrue(lineas[-1].endswith("…"))  # se recorto con elipsis

    def test_envolver_respeta_el_ancho(self):
        from PIL import ImageFont
        fuente = ImageFont.truetype(gb.RUTA_FUENTE, 30)
        palabras = "una dos tres cuatro cinco seis".split()
        anchos = {p: fuente.getlength(p) for p in set(palabras)}
        lineas = gb._envolver(palabras, anchos, fuente.getlength(" "), 120)
        self.assertGreater(len(lineas), 1)

    def test_ajustar_texto_no_revienta_si_max_menor_min(self):
        # tam_max < tam_min no debe lanzar TypeError (rango vacio): se clampa.
        fuente, lineas = gb.ajustar_texto("HOLA", (0, 0, 200, 200), gb.RUTA_FUENTE, 5, 10, 3, 1.1)
        self.assertTrue(lineas)

    def test_cerrar_en_frases_devuelve_todo_si_ninguna_entra(self):
        texto = "Frase larguisima que no entra ni al minimo en una caja diminuta."
        self.assertEqual(gb.cerrar_en_frases(texto, (0, 0, 10, 10), gb.RUTA_FUENTE, 8, 1, 1.1), texto)


class PruebasComposicion(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._carpeta = tempfile.TemporaryDirectory()
        self.dir = Path(self._carpeta.name)
        self.plantilla = self.dir / "chrome.png"
        self.recorte = self.dir / "recorte.png"
        _plantilla().save(self.plantilla)
        _recorte().save(self.recorte)

    def tearDown(self):
        self._carpeta.cleanup()

    def test_banner_tiene_el_tamano_de_la_plantilla(self):
        banner = gb.componer_banner(self.plantilla, FICHA_4212, self.recorte)
        self.assertEqual(banner.size, (400, 400))
        self.assertEqual(banner.mode, "RGBA")

    def test_es_determinista(self):
        a = gb.componer_banner(self.plantilla, FICHA_4212, self.recorte)
        b = gb.componer_banner(self.plantilla, FICHA_4212, self.recorte)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_el_recorte_transparente_deja_ver_el_fondo(self):
        # Una esquina de la caja de imagen (transparente en el recorte) debe
        # conservar el color del chrome, no taparse con un rectangulo opaco.
        banner = gb.componer_banner(self.plantilla, FICHA_4212, self.recorte)
        self.assertEqual(banner.getpixel((5, 5))[:3], (20, 20, 20))

    def test_plantilla_corrupta_da_error_recurso(self):
        mala = self.dir / "mala.png"
        mala.write_text("esto no es una imagen", encoding="utf-8")
        with self.assertRaises(gb.ErrorRecurso):
            gb.componer_banner(mala, FICHA_4212, self.recorte)

    def test_recorte_totalmente_transparente_no_rompe(self):
        vacio = self.dir / "vacio.png"
        Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(vacio)
        banner = gb.componer_banner(self.plantilla, FICHA_4212, vacio)
        self.assertEqual(banner.size, (400, 400))

    def test_plantilla_minuscula_no_da_tamano_de_fuente_cero(self):
        # Con una plantilla muy baja, tam_min redondea a 0: no debe reventar.
        chica = self.dir / "chica.png"
        Image.new("RGBA", (60, 12), (20, 20, 20, 255)).save(chica)
        banner = gb.componer_banner(chica, FICHA_4212, self.recorte)
        self.assertEqual(banner.size, (60, 12))

    def test_descripcion_de_una_palabra_larga_no_rompe(self):
        # Ejercita la rama de justificado sin dividir por cero (guard len>1).
        datos = dict(FICHA_4212, descripcion_banner="Superlargapalabrasinespacios.")
        banner = gb.componer_banner(self.plantilla, datos, self.recorte)
        self.assertEqual(banner.size, (400, 400))

    def test_ficha_invalida_termina_con_1(self):
        datos = json.loads(json.dumps(FICHA_4212))
        datos["producto"]["sku"] = "manual mal puesto"
        ruta = self.dir / "ficha_mala.json"
        ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(SystemExit) as ctx:
            gb.cargar_ficha_validada(ruta)
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
