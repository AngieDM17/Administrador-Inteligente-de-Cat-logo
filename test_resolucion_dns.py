"""Pruebas de resolucion_dns.py. Logica pura: no depende de la red real (se
monkeypatchea socket.getaddrinfo con un doble de prueba), solo verifica que
forzar_ipv4() intercepta las llamadas y restaura el original siempre. Los
reintentos (reintentar_en_fallo_de_red/es_fallo_de_red) se prueban con
funciones falsas y time.sleep anulado -- mismo criterio sin red que
test_cliente_tienda.py."""

import socket
import unittest
from unittest import mock

import resolucion_dns
from resolucion_dns import es_fallo_de_red, forzar_ipv4, reintentar_en_fallo_de_red


class PruebasForzarIpv4(unittest.TestCase):
    def test_restaura_el_original_al_salir(self):
        original = socket.getaddrinfo
        with forzar_ipv4():
            self.assertIsNot(socket.getaddrinfo, original)
        self.assertIs(socket.getaddrinfo, original)

    def test_restaura_el_original_aunque_el_bloque_lance(self):
        original = socket.getaddrinfo
        with self.assertRaises(ValueError):
            with forzar_ipv4():
                raise ValueError("boom")
        self.assertIs(socket.getaddrinfo, original)

    def test_fuerza_af_inet_sin_importar_la_family_pedida(self):
        llamadas = []

        def doble(host, port, family=0, type=0, proto=0, flags=0):
            llamadas.append(family)
            return "resultado-falso"

        original = socket.getaddrinfo
        socket.getaddrinfo = doble
        try:
            with forzar_ipv4():
                resultado = socket.getaddrinfo(
                    "ejemplo.com", 443, socket.AF_INET6
                )
        finally:
            socket.getaddrinfo = original

        self.assertEqual(resultado, "resultado-falso")
        self.assertEqual(llamadas, [socket.AF_INET])

    def test_no_pisa_un_getaddrinfo_ya_reemplazado_fuera_del_bloque(self):
        # forzar_ipv4() debe restaurar exactamente lo que habia ANTES de
        # entrar (aunque fuera ya otro reemplazo), no siempre el socket.
        # getaddrinfo "de fabrica".
        def otro_doble(*a, **k):
            return "otro"

        original = socket.getaddrinfo
        socket.getaddrinfo = otro_doble
        try:
            with forzar_ipv4():
                pass
            self.assertIs(socket.getaddrinfo, otro_doble)
        finally:
            socket.getaddrinfo = original


class PruebasEsFalloDeRed(unittest.TestCase):
    def test_gaierror_es_fallo_de_red(self):
        self.assertTrue(es_fallo_de_red(socket.gaierror(11001, "getaddrinfo failed")))

    def test_texto_getaddrinfo_failed_es_fallo_de_red(self):
        # El SDK de ElevenLabs envuelve el error original en su propia
        # excepcion, pero el texto "getaddrinfo failed" sigue en el mensaje.
        self.assertTrue(es_fallo_de_red(RuntimeError("[Errno 11001] getaddrinfo failed")))

    def test_timeout_es_fallo_de_red(self):
        self.assertTrue(es_fallo_de_red(TimeoutError("timed out")))

    def test_causa_encadenada_se_revisa(self):
        try:
            try:
                raise socket.gaierror(11001, "getaddrinfo failed")
            except socket.gaierror as origen:
                raise RuntimeError("fallo envuelto") from origen
        except RuntimeError as envuelto:
            self.assertTrue(es_fallo_de_red(envuelto))

    def test_error_de_api_no_es_fallo_de_red(self):
        self.assertFalse(es_fallo_de_red(ValueError("invalid_api_key")))
        self.assertFalse(es_fallo_de_red(RuntimeError("quota_exceeded")))


class PruebasReintentarEnFalloDeRed(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(resolucion_dns.time, "sleep", lambda *_: None)
        parche.start()
        self.addCleanup(parche.stop)

    def test_exito_al_primer_intento_no_reintenta(self):
        llamadas = []

        def funcion():
            llamadas.append(1)
            return "ok"

        resultado = reintentar_en_fallo_de_red(funcion)
        self.assertEqual(resultado, "ok")
        self.assertEqual(len(llamadas), 1)

    def test_reintenta_tras_fallo_de_red_y_despues_funciona(self):
        llamadas = []

        def funcion():
            llamadas.append(1)
            if len(llamadas) < 2:
                raise socket.gaierror(11001, "getaddrinfo failed")
            return "ok"

        resultado = reintentar_en_fallo_de_red(funcion)
        self.assertEqual(resultado, "ok")
        self.assertEqual(len(llamadas), 2)

    def test_error_que_no_es_de_red_se_relanza_sin_reintentar(self):
        llamadas = []

        def funcion():
            llamadas.append(1)
            raise ValueError("invalid_api_key")

        with self.assertRaises(ValueError):
            reintentar_en_fallo_de_red(funcion)
        self.assertEqual(len(llamadas), 1)

    def test_agota_los_intentos_y_relanza_el_ultimo_error(self):
        llamadas = []

        def funcion():
            llamadas.append(1)
            raise socket.gaierror(11001, "getaddrinfo failed")

        with self.assertRaises(socket.gaierror):
            reintentar_en_fallo_de_red(funcion)
        self.assertEqual(len(llamadas), resolucion_dns.INTENTOS_RED)

    def test_notifica_en_cada_reintento(self):
        avisos = []

        def funcion():
            if len(avisos) < 1:
                raise TimeoutError("timed out")
            return "ok"

        resultado = reintentar_en_fallo_de_red(funcion, notificar=avisos.append)
        self.assertEqual(resultado, "ok")
        self.assertEqual(len(avisos), 1)
        self.assertIn("reintentando", avisos[0].lower())


if __name__ == "__main__":
    unittest.main()
