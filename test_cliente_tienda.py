"""Pruebas del cliente de la tienda — foco en los reintentos de conexion.

El DNS de la tienda de pruebas resuelve de forma intermitente. `_solicitar`
reintenta los fallos de conexion, con dos reglas de seguridad:
- Un fallo de DNS (getaddrinfo) ocurre ANTES de enviar el pedido -> seguro
  reintentar aunque sea un POST (el servidor no vio nada).
- Otro corte de conexion solo se reintenta en LECTURAS (GET): un POST/PUT pudo
  aplicarse en el servidor aunque falle la respuesta, y reintentarlo duplicaria.
- Un error HTTP real (401, 404, ...) NUNCA se reintenta.

Todo se prueba con `_ABRIDOR.open` simulado y `time.sleep` anulado: sin red,
sin espera real.
"""

import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import cliente_tienda
from cliente_tienda import ClienteTienda, ErrorTienda

_ENV = {
    "WC_STORE_URL": "https://pruebas.ekipon.co",
    "WC_CONSUMER_KEY": "ck",
    "WC_CONSUMER_SECRET": "cs",
}


class _Resp:
    """Respuesta simulada usable como context manager."""

    def __init__(self, payload):
        self._bytes = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._bytes


def _dns_error():
    return urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))


def _secuencia_open(items):
    """Devuelve un fake de open() que consume `items`: si es excepcion la lanza,
    si no la usa como respuesta. Registra cuantas veces se llamo."""
    caja = {"n": 0}

    def fake_open(peticion, timeout=None):
        caja["n"] += 1
        x = items.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    return fake_open, caja


class PruebasReintentos(unittest.TestCase):
    def setUp(self):
        self.cli = ClienteTienda(dict(_ENV))
        parche = mock.patch.object(cliente_tienda.time, "sleep", lambda *_: None)
        parche.start()
        self.addCleanup(parche.stop)

    def _con_open(self, items):
        fake, caja = _secuencia_open(items)
        parche = mock.patch.object(cliente_tienda._ABRIDOR, "open", side_effect=fake)
        parche.start()
        self.addCleanup(parche.stop)
        return caja

    def test_dns_falla_dos_veces_luego_resuelve_en_get(self):
        caja = self._con_open([_dns_error(), _dns_error(), _Resp({"ok": True})])
        resultado = self.cli._solicitar("/wp-json/wc/v3/products")
        self.assertEqual(resultado, {"ok": True})
        self.assertEqual(caja["n"], 3)  # reintento hasta resolver

    def test_dns_se_reintenta_incluso_en_post(self):
        # Un POST con fallo de DNS: seguro reintentar (el pedido no salio).
        caja = self._con_open([_dns_error(), _Resp({"id": 1})])
        resultado = self.cli._solicitar(
            "/wp-json/wc/v3/products", datos=b"{}",
            cabeceras_extra={"Content-Type": "application/json"},
        )
        self.assertEqual(resultado, {"id": 1})
        self.assertEqual(caja["n"], 2)

    def test_dns_agota_los_intentos_y_falla(self):
        caja = self._con_open([_dns_error()] * cliente_tienda.INTENTOS_CONEXION)
        with self.assertRaises(ErrorTienda) as ctx:
            self.cli._solicitar("/wp-json/wc/v3/products")
        self.assertEqual(caja["n"], cliente_tienda.INTENTOS_CONEXION)
        self.assertIn("tras", str(ctx.exception))

    def test_error_http_no_se_reintenta(self):
        caja = self._con_open([
            urllib.error.HTTPError("u", 401, "Unauthorized", {}, None),
        ])
        with self.assertRaises(ErrorTienda) as ctx:
            self.cli._solicitar("/wp-json/wc/v3/products")
        self.assertEqual(caja["n"], 1)  # un solo intento, sin reintento
        self.assertEqual(ctx.exception.codigo_http, 401)

    def test_corte_no_dns_no_se_reintenta_en_post(self):
        # Un corte que NO es DNS, en un POST, no se reintenta (podria duplicar).
        caja = self._con_open([
            urllib.error.URLError(ConnectionResetError("reset")),
        ])
        with self.assertRaises(ErrorTienda):
            self.cli._solicitar("/wp-json/wc/v3/products", datos=b"{}")
        self.assertEqual(caja["n"], 1)

    def test_corte_no_dns_si_se_reintenta_en_get(self):
        # El mismo corte en un GET (lectura, sin efectos) si se reintenta.
        caja = self._con_open([
            urllib.error.URLError(ConnectionResetError("reset")),
            _Resp({"ok": True}),
        ])
        resultado = self.cli._solicitar("/wp-json/wc/v3/products")
        self.assertEqual(resultado, {"ok": True})
        self.assertEqual(caja["n"], 2)


class _ClienteSubirVideoSinRed(ClienteTienda):
    """ClienteTienda REAL con el transporte reemplazado: cero red. Registra
    cada solicitud para poder verificar la ruta, el metodo implicito
    (POST via datos=) y el cuerpo enviado."""

    def __init__(self, medios_existentes=None):
        super().__init__(dict(_ENV))
        self.medios_existentes = medios_existentes or []
        self.solicitudes = []

    def _solicitar(self, ruta, datos=None, cabeceras_extra=None, metodo=None):
        self.solicitudes.append({
            "ruta": ruta, "datos": datos, "cabeceras": cabeceras_extra,
        })
        if "media?search=" in ruta:
            return self.medios_existentes
        if ruta.startswith("/wp-json/wp/v2/media?post="):
            return {"id": 900}
        if ruta == "/wp-json/wp/v2/media/900":
            return {"id": 900, "title": {"rendered": "4212-video"}}
        return {}


class PruebasSubirVideo(unittest.TestCase):
    """subir_video: mismo patron de idempotencia por titulo que
    subir_imagen, pero con Content-Type de video y asociado al producto via
    ?post=<id> en la subida (ver docstring de subir_video)."""

    def test_sube_con_content_type_video_y_post_id(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_video = Path(carpeta) / "final.mp4"
            ruta_video.write_bytes(b"contenido-de-prueba")

            cliente = _ClienteSubirVideoSinRed()
            medio = cliente.subir_video(ruta_video, product_id=9001, titulo="4212-video")

            self.assertEqual(medio["id"], 900)
            subida = next(
                s for s in cliente.solicitudes
                if s["ruta"].startswith("/wp-json/wp/v2/media?post=")
            )
            self.assertEqual(subida["ruta"], "/wp-json/wp/v2/media?post=9001")
            self.assertEqual(subida["cabeceras"]["Content-Type"], "video/mp4")

    def test_idempotente_por_titulo_no_sube_de_nuevo(self):
        cliente = _ClienteSubirVideoSinRed(
            medios_existentes=[{"id": 700, "title": {"rendered": "4212-video"}}]
        )
        medio = cliente.subir_video(
            Path("no-existe.mp4"), product_id=9001, titulo="4212-video"
        )
        self.assertEqual(medio["id"], 700)
        # Ninguna solicitud de subida real: solo la busqueda por titulo.
        self.assertEqual(len(cliente.solicitudes), 1)

    def test_archivo_faltante_lanza_error_tienda(self):
        cliente = _ClienteSubirVideoSinRed()
        with self.assertRaises(ErrorTienda):
            cliente.subir_video(
                Path("no-existe.mp4"), product_id=9001, titulo="titulo-nuevo"
            )


if __name__ == "__main__":
    unittest.main()
