"""Fuerza resolucion DNS solo IPv4 para llamadas de red puntuales, y
reintenta llamadas a ElevenLabs que fallan por un hipo transitorio de red.

Verificado el 11-ago-2026 diagnosticando un fallo real y reproducible (no el
"DNS intermitente" habitual de esta red, que se resuelve solo con un
reintento): `socket.getaddrinfo('api.elevenlabs.io', 443, socket.AF_INET6)`
falla con `[Errno 11001] getaddrinfo failed` en esta maquina, mientras que
`AF_INET` (IPv4) resuelve bien. httpx/httpcore (que usan tanto el SDK de
ElevenLabs como `anthropic`) intentan resolucion dual-stack por defecto y
terminan fallando por el lado IPv6 roto, aunque el IPv4 (el que de verdad se
usaria) funcione perfecto -- de ahi que se viera como "DNS caido" cuando la
red en si respondia bien.

`reintentar_en_fallo_de_red` (19-ago-2026): aun con forzar_ipv4(), el mismo
hipo intermitente que ya afecta a la tienda (ver INTENTOS_CONEXION en
cliente_tienda.py) le paso a ElevenLabs tres veces en una sola jornada real
(voz_en_off.py y musica.py, sin ningun reintento hasta ahora) -- perdiendo el
video del producto por un DNS que a los pocos segundos volvia a funcionar
solo (verificado en vivo: tres intentos seguidos de resolver el mismo host,
las tres funcionaron). Mismo criterio que cliente_tienda: reintentar solo
fallos de RED (DNS, timeout, conexion rechazada), nunca un error real de la
API (clave invalida, cuota agotada) -- ese no se arregla reintentando."""

from __future__ import annotations

import socket
import time
from contextlib import contextmanager
from typing import Callable, TypeVar

T = TypeVar("T")

# Mismo orden de magnitud que cliente_tienda.INTENTOS_CONEXION/_ESPERA_BASE_SEG,
# pero un poco mas corto: cada intento de ElevenLabs ya tarda varios segundos
# por si mismo (genera audio real), no tiene sentido esperar tanto como con
# una llamada HTTP liviana a la tienda.
INTENTOS_RED = 3
_ESPERA_BASE_SEG = 2.0


def es_fallo_de_red(error: BaseException) -> bool:
    """True si error (o alguna causa encadenada, __cause__/__context__) es un
    problema de RED transitorio -- DNS, timeout, conexion rechazada -- que
    tiene sentido reintentar. False para cualquier otra cosa (clave de API
    invalida, cuota agotada, pedido malformado): reintentar eso no cambia
    nada, solo demora el aviso real. Logica pura: no toca la red."""
    vistos: set[int] = set()
    actual: BaseException | None = error
    while actual is not None and id(actual) not in vistos:
        vistos.add(id(actual))
        if isinstance(actual, (socket.gaierror, TimeoutError, ConnectionError)):
            return True
        texto = str(actual).lower()
        if "getaddrinfo failed" in texto or ("connection" in texto and "refused" in texto):
            return True
        actual = actual.__cause__ or actual.__context__
    return False


def reintentar_en_fallo_de_red(funcion: Callable[[], T],
                               notificar: Callable[[str], None] | None = None
                               ) -> T:
    """Corre funcion() (sin argumentos -- quien llama arma un closure/lambda),
    reintentando con espera creciente si falla por un problema de red
    transitorio (ver es_fallo_de_red). Un error que NO es de red se relanza
    de inmediato, sin reintentar. Agotados los INTENTOS_RED, se relanza el
    ultimo error tal cual (nunca se traga un fallo real)."""
    for intento in range(1, INTENTOS_RED + 1):
        try:
            return funcion()
        except Exception as error:
            if not es_fallo_de_red(error) or intento == INTENTOS_RED:
                raise
            if notificar:
                notificar(
                    f"Hipo de red (intento {intento}/{INTENTOS_RED}), "
                    "reintentando..."
                )
            time.sleep(_ESPERA_BASE_SEG * intento)
    raise AssertionError("inalcanzable: el loop siempre retorna o relanza")


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
