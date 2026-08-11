"""Pruebas de resolucion_dns.py. Logica pura: no depende de la red real (se
monkeypatchea socket.getaddrinfo con un doble de prueba), solo verifica que
forzar_ipv4() intercepta las llamadas y restaura el original siempre."""

import socket
import unittest

from resolucion_dns import forzar_ipv4


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


if __name__ == "__main__":
    unittest.main()
