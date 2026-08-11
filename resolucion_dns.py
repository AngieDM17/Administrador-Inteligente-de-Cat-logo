"""Fuerza resolucion DNS solo IPv4 para llamadas de red puntuales.

Verificado el 11-ago-2026 diagnosticando un fallo real y reproducible (no el
"DNS intermitente" habitual de esta red, que se resuelve solo con un
reintento): `socket.getaddrinfo('api.elevenlabs.io', 443, socket.AF_INET6)`
falla con `[Errno 11001] getaddrinfo failed` en esta maquina, mientras que
`AF_INET` (IPv4) resuelve bien. httpx/httpcore (que usan tanto el SDK de
ElevenLabs como `anthropic`) intentan resolucion dual-stack por defecto y
terminan fallando por el lado IPv6 roto, aunque el IPv4 (el que de verdad se
usaria) funcione perfecto -- de ahi que se viera como "DNS caido" cuando la
red en si respondia bien.
"""

from __future__ import annotations

import socket
from contextlib import contextmanager


@contextmanager
def forzar_ipv4():
    """Monkeypatchea socket.getaddrinfo para devolver SOLO resultados IPv4
    mientras el bloque `with` esta activo. Alcance: todo el proceso durante
    ese tiempo (no solo la libreria que lo pidio) -- aceptable aca porque
    estos modulos son sincronos y no corren otra llamada de red en paralelo
    durante la ventana en que se usa. Restaura el original siempre, incluso
    si el bloque lanza."""
    original = socket.getaddrinfo

    def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = _getaddrinfo_ipv4
    try:
        yield
    finally:
        socket.getaddrinfo = original
