"""Pruebas del generador de portadas (miniatura de video). Offline y sin red:
usan una plantilla y un recorte diminutos hechos en memoria con Pillow.
"""

import json
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import generador_portada as gp

RAIZ = Path(__file__).parent
FICHA_4212 = json.loads((RAIZ / "ficha_revisada_4212.json").read_text(encoding="utf-8-sig"))


def _plantilla(ancho=400, alto=400):
    return Image.new("RGBA", (ancho, alto), (30, 30, 30, 255))


def _recorte(ancho=120, alto=160):
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([20, 20, ancho - 20, alto - 20], fill=(80, 140, 200, 255))
    return img


class PruebasSeleccionDePlantilla(unittest.TestCase):
    def test_categoria_conocida_elige_su_plantilla(self):
        datos = {"producto": {"categoria_propuesta": "Gimnasio"}}
        self.assertEqual(gp.plantilla_portada(datos), gp.PLANTILLAS_POR_CATEGORIA["gimnasio"])

    def test_categoria_desconocida_cae_al_generico(self):
        datos = {"producto": {"categoria_propuesta": "Compresores"}}
        self.assertEqual(gp.plantilla_portada(datos), gp.PLANTILLAS_POR_CATEGORIA[gp.CATEGORIA_GENERICA])

    def test_categoria_vacia_cae_al_generico(self):
        datos = {"producto": {"categoria_propuesta": None}}
        self.assertEqual(gp.plantilla_portada(datos), gp.PLANTILLAS_POR_CATEGORIA[gp.CATEGORIA_GENERICA])

    def test_sin_producto_cae_al_generico(self):
        self.assertEqual(gp.plantilla_portada({}), gp.PLANTILLAS_POR_CATEGORIA[gp.CATEGORIA_GENERICA])

    def test_toma_el_primer_tramo_de_una_ruta_de_categoria(self):
        # Las categorias reales del Investigador llegan como
        # "Industria > Equipos de Soldadura": debe matchear por el primer tramo.
        datos = {"producto": {"categoria_propuesta": "Industria > Equipos de Soldadura"}}
        self.assertEqual(gp.plantilla_portada(datos), gp.PLANTILLAS_POR_CATEGORIA["industria"])

    def test_normaliza_tildes_mayusculas_y_espacios(self):
        datos = {"producto": {"categoria_propuesta": "  Agrícola  "}}
        self.assertEqual(gp.plantilla_portada(datos), gp.PLANTILLAS_POR_CATEGORIA["agro"])

    def test_typo_gimnacio_del_archivo_original_tambien_matchea(self):
        datos = {"producto": {"categoria_propuesta": "Gimnacio"}}
        self.assertEqual(gp.plantilla_portada(datos), gp.PLANTILLAS_POR_CATEGORIA["gimnasio"])

    def test_todas_las_plantillas_de_la_tabla_existen_en_disco(self):
        for ruta in gp.PLANTILLAS_POR_CATEGORIA.values():
            self.assertTrue(ruta.is_file(), f"falta la plantilla {ruta}")
            with Image.open(ruta) as imagen:
                imagen.load()  # fuerza la decodificacion: detecta PNG truncado/corrupto


class PruebasComposicion(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._carpeta = tempfile.TemporaryDirectory()
        self.dir = Path(self._carpeta.name)
        self.plantilla = self.dir / "plantilla.png"
        self.recorte = self.dir / "recorte.png"
        _plantilla().save(self.plantilla)
        _recorte().save(self.recorte)

    def tearDown(self):
        self._carpeta.cleanup()

    def test_portada_tiene_el_tamano_de_la_plantilla(self):
        portada = gp.componer_portada(self.plantilla, FICHA_4212, self.recorte)
        self.assertEqual(portada.size, (400, 400))
        self.assertEqual(portada.mode, "RGBA")

    def test_es_determinista(self):
        a = gp.componer_portada(self.plantilla, FICHA_4212, self.recorte)
        b = gp.componer_portada(self.plantilla, FICHA_4212, self.recorte)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_el_recorte_transparente_deja_ver_el_fondo(self):
        portada = gp.componer_portada(self.plantilla, FICHA_4212, self.recorte)
        self.assertEqual(portada.getpixel((5, 5))[:3], (30, 30, 30))

    def test_el_halo_del_recorte_queda_transparente(self):
        # Regresion: componer_portada() debe limpiar el halo (borde con alfa
        # parcial + color claro que deja rembg) ANTES de pegar el recorte,
        # igual que ya se hace para el banner de fotos. Arma un recorte del
        # MISMO tamano que la caja de recorte de la portada (168x300 sobre un
        # lienzo de 400x400) para que pegar_recorte no lo escale ni lo
        # recorte (bbox = lienzo completo, porque el halo tiene alfa > 0 en
        # todos lados) y la posicion quede exacta y predecible.
        ancho_recorte, alto_recorte = 168, 300
        recorte_con_halo = Image.new("RGBA", (ancho_recorte, alto_recorte), (230, 230, 230, 120))
        ImageDraw.Draw(recorte_con_halo).rectangle(
            [30, 30, ancho_recorte - 30, alto_recorte - 30], fill=(80, 140, 200, 255)
        )
        recorte_con_halo.save(self.recorte)

        portada = gp.componer_portada(self.plantilla, FICHA_4212, self.recorte)

        # (5, 5) del recorte cae en la zona de halo (fuera del rectangulo
        # solido) y, con la caja de recorte de CONFIG_PORTADA, mapea 1:1 al
        # pixel (224+5, 80+5) = (229, 85) del lienzo de 400x400.
        pixel_halo = portada.getpixel((229, 85))[:3]
        self.assertEqual(pixel_halo, (30, 30, 30),
                         "el halo del recorte no quedo transparente: se ve un "
                         f"borde blancuzco en vez del fondo de la plantilla ({pixel_halo})")

    def test_generar_a_archivo_guarda_png(self):
        salida = self.dir / "salida.png"
        ruta = gp.generar_a_archivo(FICHA_4212, self.recorte, salida, ruta_plantilla=self.plantilla)
        self.assertTrue(ruta.is_file())
        with Image.open(ruta) as im:
            self.assertEqual(im.size, (400, 400))

    def test_no_lleva_caja_de_descripcion(self):
        # Contrato: la portada solo agrega titulo + recorte, nunca descripcion,
        # a diferencia del banner (que si dibuja una caja de descripcion). Se
        # ejerce componer_portada() con dos fichas que solo difieren en la
        # descripcion: si el pixel a pixel da identico, queda probado que el
        # contenido de "descripcion_banner"/"descripcion_principal" nunca se
        # dibuja (no basta con mirar la forma de CONFIG_PORTADA).
        ficha_con_otra_descripcion = json.loads(json.dumps(FICHA_4212))
        ficha_con_otra_descripcion["descripcion_banner"] = "TEXTO COMPLETAMENTE DISTINTO"
        ficha_con_otra_descripcion["descripcion_principal"] = "Otro texto largo que no deberia aparecer jamas en la portada."

        portada_original = gp.componer_portada(self.plantilla, FICHA_4212, self.recorte)
        portada_con_otra_descripcion = gp.componer_portada(
            self.plantilla, ficha_con_otra_descripcion, self.recorte
        )
        self.assertEqual(portada_original.tobytes(), portada_con_otra_descripcion.tobytes())


class PruebasTituloBicolor(unittest.TestCase):
    """Pedido de Angie (4-ago): la primera palabra del titulo de la portada va
    en naranja de marca, el resto en negro. Se pinta sobre un lienzo blanco
    chico y controlado (sin depender de la plantilla real) y se verifica
    contando pixeles del color exacto — determinista, sin asumir formas de
    glifos de la fuente Anton, solo que dibuja en el color pedido."""

    NARANJA = (0xFF, 0x4E, 0x03)
    NEGRO = (0, 0, 0)
    BLANCO = (255, 255, 255)

    def _cfg(self, **overrides):
        base = {
            "color": "#000000",
            "color_primera_palabra": "#FF4E03",
            "mayusculas": True,
            "tam_max_frac": 0.15,
            "tam_min_frac": 0.05,
            "max_lineas": 2,
            "interlineado": 1.1,
            "alineacion": "left",
            "_fuente_path": gp.RUTA_FUENTE_TITULO_PORTADA,
        }
        base.update(overrides)
        return base

    def _contar_color(self, imagen, color):
        pix = imagen.load()
        ancho, alto = imagen.size
        return [(x, y) for y in range(alto) for x in range(ancho)
                if pix[x, y][:3] == color]

    def test_primera_palabra_naranja_resto_negro(self):
        lienzo = Image.new("RGBA", (400, 400), (255, 255, 255, 255))
        gp.dibujar_titulo_portada(lienzo, "hola mundo", (10, 10, 390, 200), self._cfg())

        naranja = self._contar_color(lienzo, self.NARANJA)
        negro = self._contar_color(lienzo, self.NEGRO)
        self.assertTrue(naranja, "la primera palabra deberia pintarse en naranja de marca")
        self.assertTrue(negro, "el resto del titulo deberia pintarse en negro")
        # La primera palabra ("HOLA") se dibuja antes y a la izquierda de la
        # segunda ("MUNDO") en alineacion left: su tinta debe quedar mas a la
        # izquierda que la del resto del titulo.
        self.assertLess(max(x for x, _ in naranja), min(x for x, _ in negro))

    def test_una_sola_palabra_queda_toda_en_naranja(self):
        # Si el titulo tiene una sola palabra, no hay "resto": todo el titulo
        # es la primera palabra y debe quedar en naranja, sin negro.
        lienzo = Image.new("RGBA", (400, 400), (255, 255, 255, 255))
        gp.dibujar_titulo_portada(lienzo, "solo", (10, 10, 390, 200), self._cfg())

        self.assertTrue(self._contar_color(lienzo, self.NARANJA))
        self.assertFalse(self._contar_color(lienzo, self.NEGRO))

    def test_sin_color_primera_palabra_pinta_todo_del_color_base(self):
        # Sin la clave color_primera_palabra, dibujar_titulo_portada cae al
        # color base para toda la linea (comportamiento de un solo color).
        lienzo = Image.new("RGBA", (400, 400), (255, 255, 255, 255))
        cfg = self._cfg()
        del cfg["color_primera_palabra"]
        gp.dibujar_titulo_portada(lienzo, "hola mundo", (10, 10, 390, 200), cfg)

        self.assertFalse(self._contar_color(lienzo, self.NARANJA))
        self.assertTrue(self._contar_color(lienzo, self.NEGRO))

    def test_texto_vacio_no_dibuja_nada(self):
        lienzo = Image.new("RGBA", (400, 400), (255, 255, 255, 255))
        gp.dibujar_titulo_portada(lienzo, "", (10, 10, 390, 200), self._cfg())
        self.assertFalse(self._contar_color(lienzo, self.NARANJA))
        self.assertFalse(self._contar_color(lienzo, self.NEGRO))

    def test_respeta_la_alineacion_centrada(self):
        # El bicolor no debe romper el centrado que ya calcula ajustar_texto:
        # el bloque de tinta (ambos colores juntos) debe quedar centrado
        # dentro de la caja, igual que con un solo color.
        lienzo = Image.new("RGBA", (400, 400), (255, 255, 255, 255))
        caja_px = (0, 10, 400, 200)
        gp.dibujar_titulo_portada(lienzo, "hola mundo", caja_px, self._cfg(alineacion="center"))

        tinta_x = [x for (x, _) in self._contar_color(lienzo, self.NARANJA) + self._contar_color(lienzo, self.NEGRO)]
        centro_tinta = (min(tinta_x) + max(tinta_x)) / 2
        centro_caja = (caja_px[0] + caja_px[2]) / 2
        self.assertAlmostEqual(centro_tinta, centro_caja, delta=2)

    def test_config_portada_usa_la_fuente_anton(self):
        self.assertEqual(Path(gp.CONFIG_PORTADA["fuente_titulo"]).name, "Anton-Regular.ttf")
        self.assertTrue(Path(gp.CONFIG_PORTADA["fuente_titulo"]).is_file())


class PruebasIntegracionTituloBicolor(unittest.TestCase):
    """Extremo a extremo: componer_portada() (con la CONFIG_PORTADA real, no
    una a medida) tiene que terminar pintando la primera palabra del titulo
    en naranja y el resto en negro sobre la plantilla real de una categoria."""

    def setUp(self):
        import tempfile
        self._carpeta = tempfile.TemporaryDirectory()
        self.dir = Path(self._carpeta.name)
        self.plantilla = self.dir / "plantilla.png"
        self.recorte = self.dir / "recorte.png"
        _plantilla().save(self.plantilla)
        _recorte().save(self.recorte)

    def tearDown(self):
        self._carpeta.cleanup()

    def test_titulo_de_la_ficha_sale_bicolor(self):
        # FICHA_4212 -> titulo_banner() = "SISTEMA DE AIRE COMPRIMIDO 3 PIEZAS":
        # multipalabra, asi que debe verse naranja Y negro en la portada final.
        portada = gp.componer_portada(self.plantilla, FICHA_4212, self.recorte)
        pix = portada.load()
        ancho, alto = portada.size
        naranja = any(pix[x, y][:3] == (0xFF, 0x4E, 0x03) for y in range(alto) for x in range(ancho))
        negro = any(pix[x, y][:3] == (0, 0, 0) for y in range(alto) for x in range(ancho))
        self.assertTrue(naranja, "la portada real deberia tener la primera palabra en naranja")
        self.assertTrue(negro, "la portada real deberia tener el resto del titulo en negro")


class PruebasErroresDeArchivo(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._carpeta = tempfile.TemporaryDirectory()
        self.dir = Path(self._carpeta.name)

    def tearDown(self):
        self._carpeta.cleanup()

    def test_plantilla_faltante_da_error_recurso(self):
        recorte = self.dir / "recorte.png"
        _recorte().save(recorte)
        with self.assertRaises(gp.ErrorRecurso):
            gp.componer_portada(self.dir / "no_existe.png", FICHA_4212, recorte)

    def test_recorte_faltante_da_error_recurso(self):
        plantilla = self.dir / "plantilla.png"
        _plantilla().save(plantilla)
        with self.assertRaises(gp.ErrorRecurso):
            gp.componer_portada(plantilla, FICHA_4212, self.dir / "no_existe.png")

    def test_plantilla_corrupta_da_error_recurso(self):
        mala = self.dir / "mala.png"
        mala.write_text("esto no es una imagen", encoding="utf-8")
        recorte = self.dir / "recorte.png"
        _recorte().save(recorte)
        with self.assertRaises(gp.ErrorRecurso):
            gp.componer_portada(mala, FICHA_4212, recorte)

    def test_ficha_invalida_termina_con_1(self):
        datos = json.loads(json.dumps(FICHA_4212))
        datos["producto"]["sku"] = "manual mal puesto"
        ruta = self.dir / "ficha_mala.json"
        ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(SystemExit) as ctx:
            gp.cargar_ficha_validada(ruta)
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
