"""Pruebas automaticas del publicador (cliente_tienda + registro + publicador).

Uso:  python -m unittest test_publicador -v

Todas las pruebas son SIN RED: usan un cliente falso inyectado y una libreta
SQLite temporal. Usa la ficha real 4212 como caso dorado del payload.
"""

import copy
import io
import json
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path

import registro
from cliente_tienda import ClienteTienda, ErrorTienda, forzar_borrador
from esquema_ficha import FichaEkipon
from publicador import (
    anunciar_reemplazo_de_galeria,
    construir_payload,
    construir_payload_actualizacion,
    ejecutar,
    extraer_codigo_proveedor,
    generar_descripcion_html,
    generar_slug,
    precio_a_texto,
    preparar_imagenes,
    publicar,
    resolver_categoria,
    ruta_relativa_segura,
    texto_alt_imagen,
    url_embed_youtube,
)

RAIZ = Path(__file__).parent
RUTA_FICHA_4212 = RAIZ / "ficha_revisada_4212.json"
FICHA_4212 = json.loads(RUTA_FICHA_4212.read_text(encoding="utf-8-sig"))


class ClienteFalso:
    """Doble de prueba del cliente de la tienda: registra cada llamada.

    Nunca toca la red; responde con lo que cada prueba le configure.
    """

    def __init__(self, respuestas_obtener=None, categorias=None):
        self.base = "https://pruebas.ekipon.co"
        self.respuestas_obtener = respuestas_obtener or {}
        self.categorias = categorias or []
        self.llamadas_obtener = []
        self.creaciones = []
        self.subidas = []
        self.actualizaciones = []
        self.videos_subidos = []

    def obtener(self, ruta):
        self.llamadas_obtener.append(ruta)
        return self.respuestas_obtener.get(ruta, [])

    def obtener_paginado(self, ruta):
        self.llamadas_obtener.append(ruta)
        return self.categorias

    def crear_producto(self, payload):
        seguro = forzar_borrador(payload)
        self.creaciones.append(seguro)
        return {"id": 9001, "name": seguro["name"], "status": "draft"}

    def subir_imagen(self, ruta_archivo, alt_text, titulo, slug_medio=None):
        self.subidas.append((Path(ruta_archivo).name, alt_text, titulo, slug_medio))
        indice = 100 + len(self.subidas)
        return {"id": indice, "source_url": f"https://pruebas.ekipon.co/media/{titulo}.png"}

    def actualizar_borrador(self, product_id, payload):
        seguro = forzar_borrador(payload)
        self.actualizaciones.append((product_id, seguro))
        return {"id": product_id, "status": "draft", "name": seguro.get("name")}

    def subir_video(self, ruta_archivo, product_id, titulo):
        self.videos_subidos.append((Path(ruta_archivo).name, product_id, titulo))
        return {"id": 800, "source_url": f"https://pruebas.ekipon.co/media/{titulo}.mp4"}


class ClienteTiendaSinRed(ClienteTienda):
    """ClienteTienda REAL con el transporte reemplazado: cero red.

    Prueba la logica verdadera de actualizar_borrador (el candado de estado)
    registrando cada solicitud en lugar de enviarla.
    """

    def __init__(self, estado_en_tienda):
        super().__init__({
            "WC_STORE_URL": "https://pruebas.ekipon.co",
            "WC_CONSUMER_KEY": "clave-de-prueba",
            "WC_CONSUMER_SECRET": "secreto-de-prueba",
        })
        self.estado_en_tienda = estado_en_tienda
        self.solicitudes = []

    def _solicitar(self, ruta, datos=None, cabeceras_extra=None, metodo=None):
        self.solicitudes.append({"ruta": ruta, "datos": datos, "metodo": metodo})
        if metodo == "PUT":
            return {"id": 555, "status": "draft"}
        return {"id": 555, "status": self.estado_en_tienda}


class PruebasSlug(unittest.TestCase):
    def test_minusculas_y_guiones(self):
        self.assertEqual(
            generar_slug("4212", "COMPRESOR DE AIRE"), "4212-compresor-de-aire"
        )

    def test_acentos_y_enie_se_aplanan(self):
        self.assertEqual(
            generar_slug("77", "TANQUE PULMÓN AÑO – 600 L"),
            "77-tanque-pulmon-ano-600-l",
        )

    def test_largo_maximo_180_sin_guion_final(self):
        slug = generar_slug("1", "A" * 500)
        self.assertLessEqual(len(slug), 180)
        self.assertFalse(slug.endswith("-"))

    def test_slug_de_la_ficha_real(self):
        slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
        self.assertTrue(slug.startswith("4212-sistema-de-aire-comprimido"))
        self.assertNotIn("ó", slug)
        self.assertNotIn("–", slug)


class PruebasBorradorForzado(unittest.TestCase):
    def test_status_publish_explicito_falla_en_voz_alta(self):
        with self.assertRaises(ValueError):
            forzar_borrador({"name": "X", "status": "publish"})

    def test_sin_status_queda_como_borrador(self):
        self.assertEqual(forzar_borrador({"name": "X"})["status"], "draft")

    def test_status_draft_se_mantiene(self):
        self.assertEqual(
            forzar_borrador({"name": "X", "status": "draft"})["status"], "draft"
        )

    def test_no_modifica_el_payload_original(self):
        payload = {"name": "X"}
        forzar_borrador(payload)
        self.assertNotIn("status", payload)


class PruebasPayloadFichaReal(unittest.TestCase):
    def setUp(self):
        self.imagenes = [{"id": 100 + n, "alt": f"alt {n}"} for n in range(8)]
        self.payload = construir_payload(
            FICHA_4212, "4212", "4212-sistema", 428, self.imagenes
        )

    def test_nombre_y_precio_como_texto(self):
        self.assertEqual(
            self.payload["name"], FICHA_4212["producto"]["nombre_propuesto"]
        )
        self.assertEqual(self.payload["regular_price"], "16434999")

    def test_tipo_estado_y_slug(self):
        self.assertEqual(self.payload["type"], "simple")
        self.assertEqual(self.payload["status"], "draft")
        self.assertEqual(self.payload["slug"], "4212-sistema")

    def test_categoria_y_etiquetas(self):
        self.assertEqual(self.payload["categories"], [{"id": 428}])
        self.assertEqual(len(self.payload["tags"]), 7)
        self.assertEqual(
            self.payload["tags"][0], {"name": "sistema de aire comprimido"}
        )

    def test_descripcion_lleva_ficha_y_caracteristicas(self):
        # La descripcion es HTML NATIVO (ficha tecnica + caracteristicas): el
        # tema la renderiza en la pestaña Descripcion sin depender de Elementor.
        desc = self.payload["description"]
        self.assertIn("600 L", desc)          # una fila real de la ficha tecnica
        self.assertIn("<strong", desc)
        self.assertIn("#ff4e03", desc)        # titulo de caracteristicas en naranja
        self.assertIn("<ul", desc)
        self.assertIn("<li", desc)

    def test_meta_ficha_tecnica_lleva_filas_limpias(self):
        meta = {m["key"]: m["value"] for m in self.payload["meta_data"]}
        tabla = json.loads(meta["ekipon_ficha_tecnica"])
        # El valor publico va LIMPIO: sin la marca interna [encontrado_web]
        self.assertEqual(tabla["TANQUE — CAPACIDAD"], "600 L (0,6 m³)")
        # Las claves internas (_origen_global, _nota) no viajan
        self.assertNotIn("_origen_global", meta["ekipon_ficha_tecnica"])
        self.assertNotIn("Claves en MAYÚSCULAS", meta["ekipon_ficha_tecnica"])

    def test_meta_caracteristicas_lleva_la_lista(self):
        meta = {m["key"]: m["value"] for m in self.payload["meta_data"]}
        caracteristicas = json.loads(meta["ekipon_caracteristicas"])
        self.assertEqual(caracteristicas, FICHA_4212["caracteristicas"])

    def test_sin_video_porque_es_nulo(self):
        # La ficha 4212 trae video_youtube: null → no hay meta de video.
        claves = {m["key"] for m in self.payload["meta_data"]}
        self.assertNotIn("ekipon_video_url", claves)

    def test_meta_codigo_proveedor_presente(self):
        claves = {m["key"]: m["value"] for m in self.payload["meta_data"]}
        self.assertEqual(claves["ekipon_codigo_proveedor"], "4212")
        self.assertEqual(claves["ekipon_ficha_version"], "1.4")
        # ficha_tecnica y caracteristicas viajan como JSON valido
        json.loads(claves["ekipon_ficha_tecnica"])
        self.assertEqual(len(json.loads(claves["ekipon_caracteristicas"])), 6)

    def test_sin_sku_y_sin_video_nulo(self):
        self.assertNotIn("sku", self.payload)
        claves = {m["key"] for m in self.payload["meta_data"]}
        # La ficha 4212 trae video_youtube: null → no debe generar meta.
        self.assertNotIn("ekipon_video_url", claves)

    def test_imagenes_en_orden(self):
        self.assertEqual(self.payload["images"], self.imagenes)

    def test_no_inyecta_elementor(self):
        # La descripcion nativa reemplaza la inyeccion de plantilla Elementor
        # (que no renderizaba de forma confiable). No debe viajar _elementor_*.
        claves = {m["key"] for m in self.payload["meta_data"]}
        self.assertNotIn("_elementor_data", claves)
        self.assertNotIn("_elementor_edit_mode", claves)


class PruebasUrlEmbedYoutube(unittest.TestCase):
    """url_embed_youtube: logica pura, sin red."""

    def test_watch_url(self):
        self.assertEqual(
            url_embed_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
        )

    def test_youtu_be_corto(self):
        self.assertEqual(
            url_embed_youtube("https://youtu.be/dQw4w9WgXcQ"),
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
        )

    def test_ya_embed(self):
        self.assertEqual(
            url_embed_youtube("https://www.youtube.com/embed/dQw4w9WgXcQ"),
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
        )

    def test_con_parametros_extra(self):
        self.assertEqual(
            url_embed_youtube(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&t=30s"
            ),
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
        )

    def test_url_no_youtube_devuelve_none(self):
        self.assertIsNone(url_embed_youtube("https://vimeo.com/12345678"))

    def test_vacio_o_none_devuelve_none(self):
        self.assertIsNone(url_embed_youtube(""))
        self.assertIsNone(url_embed_youtube(None))


class PruebasDescripcionVideoYoutube(unittest.TestCase):
    """generar_descripcion_html(): el iframe de YouTube se arma bien a partir
    de multimedia.video_youtube (camino PRINCIPAL desde 11-ago-2026 --
    ver youtube_uploader.py). video_url_subido sigue mandando si por algun
    motivo las dos cosas llegaran a estar presentes (jerarquia ya existente,
    no deberia darse con el diseno actual del orquestador)."""

    def _datos(self, video_youtube):
        return {
            "producto": {"nombre_propuesto": "PRODUCTO DE PRUEBA"},
            "ficha_tecnica": {},
            "caracteristicas": [],
            "multimedia": {"video_youtube": video_youtube},
        }

    def test_arma_iframe_con_ancho_alto_como_atributos(self):
        # No position:absolute/padding-top: probado en vivo 12-ago-2026 que
        # WordPress borra el atributo style DEL IFRAME (aunque lo respeta en
        # el <div> de alrededor) -- width/height como atributos HTML comunes
        # SI sobreviven (mismo mecanismo que el oEmbed nativo de WordPress).
        # aspect-ratio:16/9 en el <div> (13-ago-2026, celular): probado
        # contra la tienda real que sobrevive y le da al iframe una relacion
        # de aspecto correcta en cualquier ancho, en vez del height="400"
        # fijo de antes (que en celular quedaba casi cuadrado).
        html_desc = generar_descripcion_html(
            self._datos("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        )
        self.assertIn(
            '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"', html_desc
        )
        self.assertIn('width="100%"', html_desc)
        self.assertIn('height="100%"', html_desc)
        self.assertIn("aspect-ratio:16/9", html_desc)
        self.assertIn("allowfullscreen", html_desc)
        # El iframe no debe llevar atributo style: se borra al guardar (12-ago-2026).
        indice_iframe = html_desc.index("<iframe")
        indice_cierre = html_desc.index(">", indice_iframe)
        self.assertNotIn("style=", html_desc[indice_iframe:indice_cierre])
        # Nunca <style> ni class[]: WordPress los borra al guardar (11-ago-2026).
        self.assertNotIn("<style", html_desc)
        self.assertNotIn('class="', html_desc)

    def test_url_no_youtube_degrada_a_link_de_texto(self):
        html_desc = generar_descripcion_html(self._datos("https://vimeo.com/12345678"))
        self.assertNotIn("<iframe", html_desc)
        self.assertIn("Ver video del producto", html_desc)

    def test_video_subido_gana_al_de_youtube(self):
        datos = self._datos("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        html_desc = generar_descripcion_html(
            datos, video_url_subido="https://tienda.example.com/video.mp4"
        )
        self.assertIn("<video", html_desc)
        self.assertNotIn("<iframe", html_desc)

    def test_sin_video_no_arma_nada(self):
        html_desc = generar_descripcion_html(self._datos(None))
        self.assertNotIn("<iframe", html_desc)
        self.assertNotIn("Ver video del producto", html_desc)


class PruebasPayloadActualizacion(unittest.TestCase):
    def setUp(self):
        self.payload = construir_payload_actualizacion(FICHA_4212, "4212", 428)

    def test_solo_campos_textuales(self):
        self.assertEqual(
            sorted(self.payload),
            sorted([
                "name", "regular_price", "categories", "tags",
                "short_description", "description", "meta_data",
            ]),
        )

    def test_nunca_lleva_imagenes_ni_slug_ni_status(self):
        # Sin la clave 'images' la tienda conserva la galeria existente.
        self.assertNotIn("images", self.payload)
        self.assertNotIn("slug", self.payload)
        self.assertNotIn("status", self.payload)

    def test_actualizar_refresca_la_descripcion_html(self):
        # Actualizar tambien refresca la descripcion nativa (ficha tecnica).
        self.assertIn("<strong", self.payload["description"])

    def test_contenido_textual_coincide_con_la_ficha(self):
        self.assertEqual(
            self.payload["name"], FICHA_4212["producto"]["nombre_propuesto"]
        )
        self.assertEqual(self.payload["regular_price"], "16434999")
        self.assertEqual(self.payload["categories"], [{"id": 428}])
        self.assertIn("<strong", self.payload["description"])

    def test_con_imagenes_explicitas_si_lleva_images(self):
        # Unica forma de que una actualizacion toque la galeria: pedirlo.
        imagenes = [{"id": 11, "alt": "toma 1"}, {"id": 12, "alt": "toma 2"}]
        payload = construir_payload_actualizacion(
            FICHA_4212, "4212", 428, imagenes=imagenes
        )
        self.assertEqual(payload["images"], imagenes)

    def test_lista_vacia_de_imagenes_no_es_lo_mismo_que_omitirlas(self):
        # imagenes=[] es una orden explicita de dejar el producto sin galeria;
        # imagenes=None (el defecto) es 'no toques nada'.
        payload = construir_payload_actualizacion(
            FICHA_4212, "4212", 428, imagenes=[]
        )
        self.assertEqual(payload["images"], [])


class PruebasActualizarBorrador(unittest.TestCase):
    """Candado de actualizar_borrador con el ClienteTienda REAL (sin red)."""

    def test_producto_publicado_falla_sin_enviar_put(self):
        cliente = ClienteTiendaSinRed(estado_en_tienda="publish")
        with self.assertRaises(ErrorTienda) as contexto:
            cliente.actualizar_borrador(555, {"name": "X"})
        self.assertIn("publish", str(contexto.exception))
        metodos = [s["metodo"] for s in cliente.solicitudes]
        self.assertNotIn("PUT", metodos)  # solo hubo el GET de verificacion
        self.assertEqual(len(cliente.solicitudes), 1)

    def test_producto_en_borrador_envia_put_con_status_draft(self):
        cliente = ClienteTiendaSinRed(estado_en_tienda="draft")
        respuesta = cliente.actualizar_borrador(555, {"name": "X"})
        self.assertEqual(respuesta["status"], "draft")
        puts = [s for s in cliente.solicitudes if s["metodo"] == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertIn("/wp-json/wc/v3/products/555", puts[0]["ruta"])
        enviado = json.loads(puts[0]["datos"].decode("utf-8"))
        self.assertEqual(enviado["status"], "draft")

    def test_status_publish_explicito_en_el_payload_falla(self):
        cliente = ClienteTiendaSinRed(estado_en_tienda="draft")
        with self.assertRaises(ValueError):
            cliente.actualizar_borrador(555, {"name": "X", "status": "publish"})
        metodos = [s["metodo"] for s in cliente.solicitudes]
        self.assertNotIn("PUT", metodos)


class PruebasFuncionesPuras(unittest.TestCase):
    def test_codigo_proveedor_de_la_ficha_real(self):
        self.assertEqual(extraer_codigo_proveedor(FICHA_4212), "4212")

    def test_codigo_ausente_devuelve_none(self):
        self.assertIsNone(extraer_codigo_proveedor({"entrada_original": {}}))

    def test_texto_alt_combina_base_y_nota(self):
        self.assertEqual(texto_alt_imagen("Base ", " Nota"), "Base — Nota")
        self.assertEqual(texto_alt_imagen(None, "Nota"), "Nota")
        self.assertEqual(texto_alt_imagen("Base", "  "), "Base")

    def test_resolver_categoria_sin_distinguir_mayusculas(self):
        categorias = [{"id": 428, "name": "Compresores"}, {"id": 1, "name": "Taladros"}]
        categoria, sugerencias = resolver_categoria(categorias, "compresores")
        self.assertEqual(categoria["id"], 428)
        self.assertEqual(sugerencias, [])

    def test_resolver_categoria_ausente_sugiere_parecidas(self):
        categorias = [{"id": 428, "name": "Compresores"}]
        categoria, sugerencias = resolver_categoria(categorias, "Compresor")
        self.assertIsNone(categoria)
        self.assertIn("Compresores", sugerencias)

    def test_resolver_categoria_con_rama_completa_matchea_la_hoja(self):
        categorias = [{"id": 9, "name": "Escritorios"}]
        categoria, sugerencias = resolver_categoria(
            categorias, "Oficina > Escritorios"
        )
        self.assertEqual(categoria["id"], 9)
        self.assertEqual(sugerencias, [])

    def test_resolver_categoria_con_rama_de_varios_niveles_matchea_la_hoja(self):
        categorias = [{"id": 5, "name": "Molinos"}]
        categoria, sugerencias = resolver_categoria(
            categorias, "Industria > Maquinaria para alimentos > Molinos"
        )
        self.assertEqual(categoria["id"], 5)
        self.assertEqual(sugerencias, [])


class PruebasRegistro(unittest.TestCase):
    def setUp(self):
        self._carpeta = tempfile.TemporaryDirectory()
        self.ruta_db = Path(self._carpeta.name) / "prueba.db"

    def tearDown(self):
        self._carpeta.cleanup()

    def test_obtener_inexistente_devuelve_none(self):
        self.assertIsNone(registro.obtener_publicacion("999", self.ruta_db))

    def test_registrar_y_leer(self):
        registro.registrar_publicacion("4212", 9001, "4212-x", "borrador_creado", self.ruta_db)
        fila = registro.obtener_publicacion("4212", self.ruta_db)
        self.assertEqual(fila["product_id"], 9001)
        self.assertEqual(fila["slug"], "4212-x")
        self.assertEqual(fila["estado"], "borrador_creado")
        self.assertIn("T", fila["actualizado"])  # marca de tiempo ISO

    def test_upsert_actualiza_sin_duplicar(self):
        registro.registrar_publicacion("4212", 9001, "4212-x", "borrador_creado", self.ruta_db)
        registro.registrar_publicacion("4212", 9002, "4212-y", "existente", self.ruta_db)
        fila = registro.obtener_publicacion("4212", self.ruta_db)
        self.assertEqual(fila["product_id"], 9002)
        self.assertEqual(fila["estado"], "existente")
        # closing(): el 'with' de sqlite3 no cierra la conexion y en Windows
        # el archivo quedaria bloqueado para el tearDown.
        with closing(registro.conectar(self.ruta_db)) as conexion:
            total = conexion.execute("SELECT COUNT(*) FROM publicaciones").fetchone()[0]
        self.assertEqual(total, 1)


class PruebasIdempotencia(unittest.TestCase):
    def setUp(self):
        self._carpeta = tempfile.TemporaryDirectory()
        self.ruta_db = Path(self._carpeta.name) / "prueba.db"

    def tearDown(self):
        self._carpeta.cleanup()

    def test_producto_existente_por_slug_no_se_duplica(self):
        slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
        cliente = ClienteFalso(respuestas_obtener={
            f"/wp-json/wc/v3/products?slug={slug}&status=any": [
                {"id": 555, "slug": slug, "status": "draft"}
            ]
        })
        codigo_salida = publicar(
            FICHA_4212, "4212", slug, RAIZ, cliente, self.ruta_db
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(cliente.creaciones, [])  # NO se creo nada
        self.assertEqual(cliente.subidas, [])     # NI se subieron imagenes
        fila = registro.obtener_publicacion("4212", self.ruta_db)
        self.assertEqual(fila["product_id"], 555)

    def test_creacion_completa_con_cliente_falso(self):
        slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
        cliente = ClienteFalso(categorias=[{"id": 428, "name": "Compresores"}])
        codigo_salida = publicar(
            FICHA_4212, "4212", slug, RAIZ, cliente, self.ruta_db
        )
        self.assertEqual(codigo_salida, 0)
        # 8 imagenes de la galeria + 1 banner (existe 4212_recorte.png en RAIZ)
        self.assertEqual(len(cliente.subidas), 9)
        self.assertEqual(len(cliente.creaciones), 1)
        payload = cliente.creaciones[0]
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["categories"], [{"id": 428}])
        # El banner viaja como meta Y como <img> dentro de la descripcion HTML,
        # que el tema renderiza en la pestaña Descripcion sin Elementor.
        metas = {m["key"]: m["value"] for m in payload["meta_data"]}
        self.assertIn("ekipon_banner_url", metas)
        self.assertIn("<strong", payload["description"])
        self.assertIn("<img", payload["description"])
        self.assertEqual(len(payload["images"]), 8)  # el banner NO va en la galeria
        fila = registro.obtener_publicacion("4212", self.ruta_db)
        self.assertEqual(fila["product_id"], 9001)
        self.assertEqual(fila["estado"], "borrador_creado")

    def test_sin_recorte_se_publica_sin_banner(self):
        # Un codigo sin <codigo>_recorte.png: no se genera banner, no rompe.
        cliente = ClienteFalso(categorias=[{"id": 428, "name": "Compresores"}])
        codigo_salida = publicar(
            FICHA_4212, "SINRECORTE", "sinrecorte-slug", RAIZ, cliente, self.ruta_db
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(len(cliente.subidas), 8)  # solo galeria, sin banner
        metas = {m["key"]: m["value"] for m in cliente.creaciones[0]["meta_data"]}
        self.assertNotIn("ekipon_banner_url", metas)
        desc = cliente.creaciones[0]["description"]
        self.assertIn("<strong", desc)   # la ficha tecnica sigue en la descripcion
        self.assertNotIn("<img", desc)  # pero sin banner (no hay recorte)

    def test_banner_corrupto_se_publica_sin_banner(self):
        # Un recorte existente pero corrupto no debe abortar: se degrada a None.
        from publicador import generar_y_subir_banner
        with tempfile.TemporaryDirectory() as carpeta:
            recorte = Path(carpeta) / "X_recorte.png"
            recorte.write_text("no soy una imagen", encoding="utf-8")
            cliente = ClienteFalso()
            banner = generar_y_subir_banner(
                FICHA_4212, "X", "x-slug", Path(carpeta), cliente
            )
        self.assertIsNone(banner)
        self.assertEqual(cliente.subidas, [])  # no se subio nada

    def test_fallo_de_tienda_al_subir_banner_se_propaga(self):
        # La subida es critica: si la tienda falla, NO se degrada en silencio.
        from publicador import generar_y_subir_banner

        class ClienteQueFallaAlSubir(ClienteFalso):
            def subir_imagen(self, *args, **kwargs):
                raise ErrorTienda("la tienda rechazo la subida")

        cliente = ClienteQueFallaAlSubir()
        with self.assertRaises(ErrorTienda):
            generar_y_subir_banner(FICHA_4212, "4212", "un-slug", RAIZ, cliente)

    def test_categoria_inexistente_termina_con_1_sin_crear(self):
        slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
        cliente = ClienteFalso(categorias=[{"id": 1, "name": "Taladros"}])
        codigo_salida = publicar(
            FICHA_4212, "4212", slug, RAIZ, cliente, self.ruta_db
        )
        self.assertEqual(codigo_salida, 1)
        self.assertEqual(cliente.creaciones, [])
        self.assertEqual(cliente.subidas, [])


class PruebasActualizacion(unittest.TestCase):
    """Camino --actualizar del pipeline: PUT de texto, sin tocar imagenes."""

    def setUp(self):
        self._carpeta = tempfile.TemporaryDirectory()
        self.ruta_db = Path(self._carpeta.name) / "prueba.db"
        self.slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])

    def tearDown(self):
        self._carpeta.cleanup()

    def _cliente_con_existente(self):
        return ClienteFalso(
            respuestas_obtener={
                f"/wp-json/wc/v3/products?slug={self.slug}&status=any": [
                    {"id": 555, "slug": self.slug, "status": "draft"}
                ]
            },
            categorias=[{"id": 428, "name": "Compresores"}],
        )

    def test_con_bandera_actualiza_texto_sin_imagenes(self):
        cliente = self._cliente_con_existente()
        codigo_salida = publicar(
            FICHA_4212, "4212", self.slug, RAIZ, cliente, self.ruta_db,
            actualizar=True,
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(len(cliente.actualizaciones), 1)  # hubo el PUT
        # Se sube SOLO el banner (1), nunca las 8 fotos de la galeria
        self.assertEqual(len(cliente.subidas), 1)
        self.assertEqual(cliente.subidas[0][2], "4212-banner")
        self.assertEqual(cliente.creaciones, [])    # y nada se creo
        product_id, payload = cliente.actualizaciones[0]
        self.assertEqual(product_id, 555)
        self.assertNotIn("images", payload)  # la galeria no se toca ni borra
        self.assertEqual(payload["status"], "draft")
        # El banner viaja como meta Y como <img> en la descripcion HTML.
        metas = {m["key"]: m["value"] for m in payload["meta_data"]}
        self.assertIn("ekipon_banner_url", metas)
        self.assertIn("<img", payload["description"])
        fila = registro.obtener_publicacion("4212", self.ruta_db)
        self.assertEqual(fila["product_id"], 555)
        self.assertEqual(fila["estado"], "borrador_actualizado")

    def test_sin_bandera_no_hay_put_ni_cambios(self):
        cliente = self._cliente_con_existente()
        codigo_salida = publicar(
            FICHA_4212, "4212", self.slug, RAIZ, cliente, self.ruta_db
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(cliente.actualizaciones, [])  # sin flag: sin PUT
        self.assertEqual(cliente.creaciones, [])
        self.assertEqual(cliente.subidas, [])

    def test_categoria_inexistente_termina_con_1_sin_put(self):
        cliente = ClienteFalso(
            respuestas_obtener={
                f"/wp-json/wc/v3/products?slug={self.slug}&status=any": [
                    {"id": 555, "slug": self.slug, "status": "draft"}
                ]
            },
            categorias=[{"id": 1, "name": "Taladros"}],
        )
        codigo_salida = publicar(
            FICHA_4212, "4212", self.slug, RAIZ, cliente, self.ruta_db,
            actualizar=True,
        )
        self.assertEqual(codigo_salida, 1)
        self.assertEqual(cliente.actualizaciones, [])

    def test_sin_refrescar_galeria_la_actualizacion_no_manda_images(self):
        # Pin del comportamiento por defecto: una actualizacion no puede
        # borrar una galeria viva.
        cliente = self._cliente_con_existente()
        codigo_salida = publicar(
            FICHA_4212, "4212", self.slug, RAIZ, cliente, self.ruta_db,
            actualizar=True, refrescar_galeria=False,
        )
        self.assertEqual(codigo_salida, 0)
        _, payload = cliente.actualizaciones[0]
        self.assertNotIn("images", payload)
        self.assertEqual(len(cliente.subidas), 1)  # solo el banner

    def test_con_refrescar_galeria_si_manda_images(self):
        cliente = self._cliente_con_existente()
        codigo_salida = publicar(
            FICHA_4212, "4212", self.slug, RAIZ, cliente, self.ruta_db,
            actualizar=True, refrescar_galeria=True,
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(len(cliente.subidas), 9)  # 8 galeria + 1 banner
        _, payload = cliente.actualizaciones[0]
        self.assertEqual(len(payload["images"]), 8)
        self.assertEqual(payload["status"], "draft")  # sigue siendo borrador
        # Las imagenes viajan con su texto alt, igual que al crear.
        self.assertTrue(all(img["alt"] for img in payload["images"]))

    def test_refrescar_galeria_con_categoria_inexistente_no_sube_nada(self):
        # La galeria no se toca si la actualizacion ni siquiera va a ocurrir.
        cliente = ClienteFalso(
            respuestas_obtener={
                f"/wp-json/wc/v3/products?slug={self.slug}&status=any": [
                    {"id": 555, "slug": self.slug, "status": "draft"}
                ]
            },
            categorias=[{"id": 1, "name": "Taladros"}],
        )
        codigo_salida = publicar(
            FICHA_4212, "4212", self.slug, RAIZ, cliente, self.ruta_db,
            actualizar=True, refrescar_galeria=True,
        )
        self.assertEqual(codigo_salida, 1)
        self.assertEqual(cliente.actualizaciones, [])
        self.assertEqual(cliente.subidas, [])

    def test_refrescar_galeria_sin_imagenes_no_borra_la_galeria_viva(self):
        # "No hay nada que subir" y "borra todo" no pueden ser la misma orden.
        # Esta ficha es VALIDA y su galeria confirmada esta vacia — que es lo
        # que devuelve motor_galeria.imagenes_confirmadas_del_plan cuando
        # ningun slot tiene archivo o todos vienen sin firmar. Sin el corte,
        # subir_galeria([]) devolvia [] (que no es None) y el PUT viajaba con
        # 'images': [], o sea con la orden de vaciar la galeria del producto.
        ficha = copy.deepcopy(FICHA_4212)
        ficha["multimedia"]["imagenes_galeria_confirmadas"] = []
        FichaEkipon.model_validate(ficha)  # sigue cumpliendo el contrato

        cliente = self._cliente_con_existente()
        codigo_salida = publicar(
            ficha, "4212", self.slug, RAIZ, cliente, self.ruta_db,
            actualizar=True, refrescar_galeria=True,
        )
        self.assertNotEqual(codigo_salida, 0)
        self.assertEqual(cliente.actualizaciones, [])  # ningun PUT
        self.assertEqual(cliente.subidas, [])          # ni siquiera el banner

    def test_producto_inexistente_con_bandera_crea_normalmente(self):
        cliente = ClienteFalso(categorias=[{"id": 428, "name": "Compresores"}])
        codigo_salida = publicar(
            FICHA_4212, "4212", self.slug, RAIZ, cliente, self.ruta_db,
            actualizar=True,
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(cliente.actualizaciones, [])
        self.assertEqual(len(cliente.creaciones), 1)
        self.assertEqual(len(cliente.subidas), 9)  # 8 galeria + 1 banner


class PruebasAvisoDeReemplazo(unittest.TestCase):
    """Refrescar la galeria pisa imagenes vivas: no puede pasar en silencio."""

    def test_el_aviso_nombra_el_reemplazo_y_cada_imagen(self):
        preparadas = [
            {"ruta": Path("galeria/01-producto_limpio.webp"), "alt": "toma 1",
             "titulo": "01", "slug_medio": "4212-01"},
            {"ruta": Path("galeria/02-medidas.webp"), "alt": "toma 2",
             "titulo": "02", "slug_medio": "4212-02"},
        ]
        salida = io.StringIO()
        with redirect_stdout(salida):
            anunciar_reemplazo_de_galeria(preparadas)
        texto = salida.getvalue()
        self.assertIn("REEMPLAZADA", texto)
        self.assertIn("01-producto_limpio.webp", texto)
        self.assertIn("02-medidas.webp", texto)
        self.assertIn("toma 2", texto)


class PruebasSimulacro(unittest.TestCase):
    def test_simular_no_construye_cliente_ni_toca_red(self):
        contador = {"fabricas": 0}

        def fabrica_prohibida():
            contador["fabricas"] += 1
            raise AssertionError("el simulacro NO debe construir el cliente")

        codigo_salida = ejecutar(
            RUTA_FICHA_4212, simular=True, fabrica_cliente=fabrica_prohibida
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(contador["fabricas"], 0)

    def test_simular_con_actualizar_sigue_sin_red(self):
        def fabrica_prohibida():
            raise AssertionError("el simulacro NO debe construir el cliente")

        codigo_salida = ejecutar(
            RUTA_FICHA_4212, simular=True,
            fabrica_cliente=fabrica_prohibida, actualizar=True,
        )
        self.assertEqual(codigo_salida, 0)

    def test_simular_refrescar_galeria_sigue_sin_red(self):
        # La bandera se puede ensayar entera sin tocar la tienda.
        def fabrica_prohibida():
            raise AssertionError("el simulacro NO debe construir el cliente")

        codigo_salida = ejecutar(
            RUTA_FICHA_4212, simular=True, fabrica_cliente=fabrica_prohibida,
            actualizar=True, refrescar_galeria=True,
        )
        self.assertEqual(codigo_salida, 0)


class PruebasLimpiezaPublica(unittest.TestCase):
    """La vidriera no muestra cocina interna: ni marcas ni origenes."""

    def test_clave_no_publica_se_omite(self):
        import publicador

        tabla = publicador.ficha_tecnica_publica(
            {"ficha_tecnica": {
                "MARCA FÍSICA (no pública)": "申江龙 (tanque) / IO Tools",
                "TANQUE — CAPACIDAD": "600 L  [encontrado_web]",
            }}
        )
        blob = json.dumps(tabla, ensure_ascii=False)
        # La clave no publica y su valor (la marca) no viajan al publico.
        self.assertNotIn("MARCA", blob)
        self.assertNotIn("IO Tools", blob)
        self.assertIn("TANQUE — CAPACIDAD", tabla)

    def test_marcas_de_origen_se_limpian_del_valor(self):
        import publicador

        tabla = publicador.ficha_tecnica_publica(
            {"ficha_tecnica": {
                "COMPRESOR": "Incluido  [confirmado_por_angie]; specs PENDIENTE",
                "TANQUE": "600 L (0,6 m³)  [encontrado_web]",
            }}
        )
        blob = json.dumps(tabla, ensure_ascii=False)
        self.assertNotIn("[confirmado_por_angie]", blob)
        self.assertNotIn("[encontrado_web]", blob)
        self.assertEqual(tabla["COMPRESOR"], "Incluido; specs PENDIENTE")
        self.assertEqual(tabla["TANQUE"], "600 L (0,6 m³)")

    def test_limpiar_valor_publico_colapsa_espacios(self):
        import publicador

        self.assertEqual(
            publicador.limpiar_valor_publico("Vertical, con patas  [verificado por foto]"),
            "Vertical, con patas",
        )

    def test_ficha_4212_no_expone_marca_ni_origenes(self):
        import publicador

        tabla = publicador.ficha_tecnica_publica(FICHA_4212)
        blob = json.dumps(tabla, ensure_ascii=False)
        self.assertNotIn("no pública", blob)
        self.assertNotIn("IO Tools", blob)
        self.assertNotIn("[encontrado_web]", blob)
        self.assertNotIn("[confirmado_por_angie", blob)

    def test_meta_ficha_tecnica_tambien_viaja_limpia(self):
        # Los meta_data alimentan las futuras plantillas dinamicas: si llevan
        # cocina interna, la fuga publica queda agendada. Viajan limpios.
        import publicador

        payload = publicador.construir_payload(
            FICHA_4212, "4212", "un-slug", 428, []
        )
        meta = {m["key"]: m["value"] for m in payload["meta_data"]}
        self.assertNotIn("IO Tools", meta["ekipon_ficha_tecnica"])
        self.assertNotIn("no pública", meta["ekipon_ficha_tecnica"])
        self.assertNotIn("[encontrado_web]", meta["ekipon_ficha_tecnica"])
        self.assertIn("600 L (0,6 m³)", meta["ekipon_ficha_tecnica"])


class PruebasCorreccionesReview(unittest.TestCase):
    """Blindaje de los hallazgos de la revision 4R (16-jul-2026)."""

    def test_slug_vacio_lanza_error(self):
        # nombre y codigo sin letras ni numeros -> slug vacio -> ValueError
        with self.assertRaises(ValueError):
            generar_slug("---", "!!!")

    def test_precio_pendiente_no_produce_texto_none(self):
        self.assertEqual(precio_a_texto(None), "")
        self.assertEqual(precio_a_texto(16434999), "16434999")

    def test_payload_precio_pendiente_va_vacio_no_none(self):
        datos = json.loads(json.dumps(FICHA_4212))  # copia
        datos["precios"]["precio"] = None
        datos["precios"]["precio_origen"] = "PENDIENTE_ANGIE"
        payload = construir_payload(datos, "4212", "un-slug", 428, [])
        self.assertEqual(payload["regular_price"], "")
        self.assertNotIn("None", payload["regular_price"])

    def test_ruta_relativa_segura_rechaza_traversal_y_absolutas(self):
        self.assertTrue(ruta_relativa_segura("4212_imagenes/foto-01.webp"))
        self.assertFalse(ruta_relativa_segura("../../.env"))
        self.assertFalse(ruta_relativa_segura("..\\..\\secreto"))
        self.assertFalse(ruta_relativa_segura("/etc/passwd"))
        self.assertFalse(ruta_relativa_segura("https://malo/x"))
        self.assertFalse(ruta_relativa_segura("C:/Windows/x"))

    def test_preparar_imagenes_rechaza_url_con_traversal(self):
        datos = json.loads(json.dumps(FICHA_4212))
        datos["multimedia"]["imagenes_galeria_confirmadas"][0]["url"] = "../../.env"
        with self.assertRaises(SystemExit) as ctx:
            preparar_imagenes(datos, RAIZ)
        self.assertEqual(ctx.exception.code, 1)

    def test_titulo_de_imagen_lleva_el_codigo_para_no_colisionar(self):
        # subir_imagen deduplica por TITULO, y el motor nombra las piezas igual
        # para todos (01-producto_limpio.webp). Sin el codigo adelante, la
        # portada de un producto reutilizaba la de otro ya subido (bug 50268:
        # el taladro tomo la portada de la picadora). El titulo debe ser unico.
        datos = {
            "entrada_original": {"codigo_proveedor": "TALADRO-X"},
            "seo": {"texto_alt_base": "alt"},
            "multimedia": {"imagenes_galeria_confirmadas": [
                {"url": "4212_imagenes/4212-sistema-01-conjunto.webp", "nota": "x"}
            ]},
        }
        prep = preparar_imagenes(datos, RAIZ)
        self.assertEqual(prep[0]["titulo"], "TALADRO-X-4212-sistema-01-conjunto")

    def test_subida_reutiliza_por_titulo_sin_volver_a_subir(self):
        # Un medio ya subido (mismo titulo, que WordPress fija en la subida) se
        # reutiliza aunque su segunda llamada haya fallado antes: cero duplicados.
        cliente = ClienteTiendaSinRed("draft")

        def obtener(ruta):
            if "media?search=" in ruta:
                # El medio existe con el titulo pero SIN slug (2da llamada fallo)
                return [{"id": 700, "title": {"rendered": "4212-sistema-01"}}]
            return []

        cliente.obtener = obtener
        medio = cliente.subir_imagen(
            RAIZ / "x.webp", "alt", "4212-sistema-01", "4212-sistema-01"
        )
        self.assertEqual(medio["id"], 700)
        self.assertEqual(cliente.solicitudes, [])  # ni un POST de subida

    def test_subida_no_confunde_titulos_parecidos(self):
        # search puede traer varios; solo se reutiliza el de titulo EXACTO.
        cliente = ClienteTiendaSinRed("draft")
        cliente.obtener = lambda ruta: (
            [{"id": 701, "title": {"rendered": "4212-sistema-01-otra"}}]
            if "media?search=" in ruta else []
        )
        imagen_real = RAIZ / "4212_imagenes" / "4212-sistema-01-conjunto.webp"
        medio = cliente.subir_imagen(
            imagen_real, "alt", "4212-sistema-01", "4212-sistema-01"
        )
        # Titulo no coincide exacto -> sube de nuevo (hay POSTs registrados)
        self.assertNotEqual(cliente.solicitudes, [])

    def test_ledger_fast_path_reusa_producto_anotado(self):
        # Con el producto ya en la libreta, buscar_existente lo confirma en vivo
        # y no llega a la busqueda por slug.
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_db = Path(carpeta) / "prueba.db"
            slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
            registro.registrar_publicacion("4212", 555, slug, "borrador_creado", ruta_db)
            cliente = ClienteFalso(respuestas_obtener={
                "/wp-json/wc/v3/products/555": {"id": 555, "status": "draft"}
            })
            codigo_salida = publicar(FICHA_4212, "4212", slug, RAIZ, cliente, ruta_db)
            self.assertEqual(codigo_salida, 0)
            self.assertEqual(cliente.creaciones, [])
            self.assertIn("/wp-json/wc/v3/products/555", cliente.llamadas_obtener)

    def test_slug_vacio_termina_con_1_sin_traceback(self):
        # Una ficha valida por esquema pero con nombre/codigo solo de simbolos
        # NO debe reventar con traceback: el flujo lo traduce a salida 1.
        datos = json.loads(json.dumps(FICHA_4212))
        datos["entrada_original"]["codigo_proveedor"] = "---"
        datos["producto"]["nombre_propuesto"] = "!!!"
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "ficha_simbolos.json"
            ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            codigo_salida = ejecutar(ruta, simular=True)
        self.assertEqual(codigo_salida, 1)

    def test_short_description_va_limpia_de_marcas(self):
        datos = json.loads(json.dumps(FICHA_4212))
        datos["descripcion_principal"] = "Sistema completo  [confirmado_por_angie]"
        payload = construir_payload(datos, "4212", "un-slug", 428, [])
        self.assertEqual(payload["short_description"], "Sistema completo")
        self.assertNotIn("[confirmado_por_angie]", payload["short_description"])

    def test_registro_traduce_error_de_sqlite(self):
        # Una ruta de DB imposible (un archivo como carpeta) provoca ErrorRegistro.
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / "noesdir"
            archivo.write_text("x", encoding="utf-8")
            ruta_imposible = archivo / "sub.db"
            with self.assertRaises(registro.ErrorRegistro):
                registro.obtener_publicacion("4212", ruta_imposible)


class PruebasResultadoYVideo(unittest.TestCase):
    """Los parametros aditivos `resultado`/`ruta_video` de publicar(): sirven
    para que orquestador.py distinga el CHECKPOINT 2 (categoria sin match)
    de cualquier otro motivo de fallo, y obtenga el producto_id para subir el
    video. Ninguno de los dos cambia el contrato int existente (codigo_salida
    sigue siendo 0/1): se leen del dict aparte."""

    def setUp(self):
        self._carpeta = tempfile.TemporaryDirectory()
        self.ruta_db = Path(self._carpeta.name) / "prueba.db"

    def tearDown(self):
        self._carpeta.cleanup()

    def test_categoria_sin_match_anota_sugerencias_en_resultado(self):
        slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
        cliente = ClienteFalso(categorias=[{"id": 1, "name": "Compresores usados"}])
        resultado = {}
        codigo_salida = publicar(
            FICHA_4212, "4212", slug, RAIZ, cliente, self.ruta_db,
            resultado=resultado,
        )
        self.assertEqual(codigo_salida, 1)
        self.assertEqual(resultado["categoria_buscada"], "Compresores")
        self.assertIn("Compresores usados", resultado["categoria_sugerencias"])
        # Checkpoint de categoria: nunca se creo el producto.
        self.assertNotIn("producto_id", resultado)

    def test_creacion_completa_anota_producto_id_en_resultado(self):
        slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
        cliente = ClienteFalso(categorias=[{"id": 428, "name": "Compresores"}])
        resultado = {}
        codigo_salida = publicar(
            FICHA_4212, "4212", slug, RAIZ, cliente, self.ruta_db,
            resultado=resultado,
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(resultado["producto_id"], 9001)
        self.assertNotIn("categoria_sugerencias", resultado)

    def test_con_ruta_video_sube_y_asocia_meta_al_crear(self):
        slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
        cliente = ClienteFalso(categorias=[{"id": 428, "name": "Compresores"}])
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_video = Path(carpeta) / "final.mp4"
            ruta_video.write_bytes(b"x")
            codigo_salida = publicar(
                FICHA_4212, "4212", slug, RAIZ, cliente, self.ruta_db,
                ruta_video=ruta_video,
            )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(len(cliente.videos_subidos), 1)
        nombre, product_id, titulo = cliente.videos_subidos[0]
        self.assertEqual(product_id, 9001)
        self.assertEqual(titulo, "4212-video")
        # La asociacion via meta_data llega como una actualizacion aparte.
        actualizaciones_9001 = [
            payload for (pid, payload) in cliente.actualizaciones if pid == 9001
        ]
        metas_de_video = [
            m for payload in actualizaciones_9001
            for m in payload.get("meta_data", []) if m["key"] == "ekipon_video_id"
        ]
        self.assertEqual(len(metas_de_video), 1)
        # Bug real del 11-ago-2026: el video se subia pero la descripcion
        # nunca lo mostraba (quedaba "adjunto" e invisible). Ahora una
        # SEGUNDA actualizacion trae la descripcion regenerada con el
        # <video> real incrustado (la URL que devuelve el subir_video falso
        # de arriba, no un link de YouTube).
        descripciones_con_video = [
            payload["description"] for payload in actualizaciones_9001
            if "description" in payload
            and "<video" in payload["description"]
            and "https://pruebas.ekipon.co/media/4212-video.mp4" in payload["description"]
        ]
        self.assertEqual(len(descripciones_con_video), 1)

    def test_sin_ruta_video_no_sube_nada(self):
        slug = generar_slug("4212", FICHA_4212["producto"]["nombre_propuesto"])
        cliente = ClienteFalso(categorias=[{"id": 428, "name": "Compresores"}])
        codigo_salida = publicar(
            FICHA_4212, "4212", slug, RAIZ, cliente, self.ruta_db,
        )
        self.assertEqual(codigo_salida, 0)
        self.assertEqual(cliente.videos_subidos, [])


if __name__ == "__main__":
    unittest.main()
