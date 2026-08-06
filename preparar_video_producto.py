"""Normalizador de clips de video de producto al formato YouTube 1920x1080
(etapa Imagenes/Video).

Los clips que llegan de Alibaba suelen venir verticales (720x1280 es el caso
tipico) y hay que adaptarlos al horizontal 1920x1080 antes de armar el video
final. Si el clip YA viene en 1920x1080 no se toca: se copia tal cual, sin
re-codificar de mas. Si no, se aplica la formula confirmada contra el ajuste
manual real que hace Angie en CapCut: escalar por ANCHO a 1920 manteniendo la
proporcion, y recortar el sobrante de alto CENTRADO
(`scale=1920:-1,crop=1920:1080`; el crop sin x/y explicitos ya centra solo).
No hay mas casos: es una regla de dos ramas, no un detector de aspect ratios.

Uso:  python preparar_video_producto.py <entrada.mp4> [--salida salida.mp4]

Codigos de salida: 0 = video normalizado; 2 = problema de archivo (entrada
faltante/ilegible, o ffmpeg/ffprobe no disponibles o fallan).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RESOLUCION_YOUTUBE = (1920, 1080)


class ErrorRecurso(Exception):
    """No se pudo preparar el video (entrada ilegible, ffmpeg/ffprobe
    ausentes o fallidos). Se traduce a un mensaje claro y salida 2, no a un
    traceback."""


def necesita_reescalar(ancho: int, alto: int) -> bool:
    """True si el clip NO esta ya en 1920x1080 exacto y por lo tanto hay que
    escalarlo+recortarlo centrado. Logica pura (sin ffmpeg): es la parte
    testeable por unit test; la decision real se toma con las dimensiones que
    devuelve ffprobe en _dimensiones_video."""
    return (ancho, alto) != RESOLUCION_YOUTUBE


def _verificar_herramientas() -> None:
    """Confirma que ffmpeg y ffprobe estan en el PATH antes de usarlos, para
    dar un mensaje claro en vez de un traceback de FileNotFoundError."""
    faltantes = [h for h in ("ffmpeg", "ffprobe") if shutil.which(h) is None]
    if faltantes:
        raise ErrorRecurso(
            "no se encontro " + " ni ".join(faltantes) + " en el PATH del "
            "sistema. Instalalos (ej. 'winget install ffmpeg') y volve a "
            "intentar."
        )


def _dimensiones_video(ruta: Path) -> tuple[int, int]:
    """Ancho y alto del primer stream de video de ruta, via ffprobe. Lanza
    ErrorRecurso si el archivo no existe, no tiene stream de video legible, o
    ffprobe falla.

    NO se prueba con ffprobe real en unit tests (herramienta externa, lenta e
    innecesaria para probar logica): ver test_preparar_video_producto.py, que
    solo cubre necesita_reescalar()."""
    if not ruta.is_file():
        raise ErrorRecurso(f"no existe el archivo de entrada '{ruta}'.")
    comando = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(ruta),
    ]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise ErrorRecurso(
            "no se encontro ffprobe en el PATH del sistema."
        ) from error
    if resultado.returncode != 0:
        raise ErrorRecurso(
            f"ffprobe no pudo leer '{ruta}': {resultado.stderr.strip()}"
        )
    try:
        datos = json.loads(resultado.stdout)
        stream = datos["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as error:
        raise ErrorRecurso(
            f"'{ruta}' no parece tener un stream de video legible ({error})."
        ) from error


def _filtro_zoom_extra(zoom_extra: float) -> str:
    """Filtro ffmpeg que aplica un zoom adicional de zoom_extra (fraccion,
    ej. 0.18 = 18%) sobre una imagen que YA esta en 1920x1080: recorta una
    caja mas chica ANCLADA ARRIBA (asi el recorte se come el borde de ABAJO,
    no reparte el recorte entre arriba y abajo) y la vuelve a escalar a
    1920x1080. Sirve para sacar del encuadre subtitulos quemados que el
    proveedor (Alibaba) suele dejar pegados al borde inferior, pedido
    explicito de Angie ("ampliar la escala para que eso no se vea").

    Verificado el 6-ago-2026 contra un clip real de Alibaba con subtitulo
    quemado ("ED-F021 Cable Crossover Machine", banda inferior): un recorte
    CENTRADO (probado primero) no sirve -- el subtitulo queda en la misma
    posicion relativa, solo mas grande. Anclar el recorte arriba (crop con
    y=0) es lo que efectivamente saca la banda inferior del cuadro.

    Se disena para encadenarse DESPUES del filtro que ya lleva el clip a
    1920x1080 (o para aplicarse solo si el clip ya estaba en 1920x1080): al
    operar siempre sobre una imagen 1920x1080, el resultado no depende de la
    proporcion original del clip de entrada (evita distorsionar clips que no
    son 16:9, a diferencia de escalar a un ancho/alto exacto calculado sobre
    las dimensiones originales). Logica pura (arma el string del filtro); no
    ejecuta ffmpeg."""
    factor = 1 + max(0.0, zoom_extra)
    ancho_recorte = round(1920 / factor)
    alto_recorte = round(1080 / factor)
    # ffmpeg exige dimensiones pares para libx264 (yuv420p); redondeamos
    # hacia abajo para no pasarnos de 1920x1080 al recortar.
    ancho_recorte -= ancho_recorte % 2
    alto_recorte -= alto_recorte % 2
    x = (1920 - ancho_recorte) // 2  # centrado en horizontal
    return f"crop={ancho_recorte}:{alto_recorte}:{x}:0,scale=1920:1080"


def generar_a_archivo(ruta_entrada: Path, ruta_salida: Path,
                      zoom_extra: float = 0.0) -> Path:
    """Normaliza el clip a 1920x1080 y lo guarda en ruta_salida. Devuelve
    ruta_salida. Guardado atomico (temporal + os.replace): si el proceso
    muere a mitad de camino no queda un archivo a medias pisando uno previo
    valido.

    Si el clip YA esta en 1920x1080 y zoom_extra es 0 se copia tal cual (no
    se re-codifica de mas). Si hace falta reescalar a 1920x1080, o si
    zoom_extra > 0 (incluso con un clip que ya esta en 1920x1080), se corre
    ffmpeg con el filtro `scale=1920:-1,crop=1920:1080` (o con el zoom extra
    aplicado, ver _filtro_zoom_extra) y se preserva el audio sin recodificar
    (`-c:a copy`).

    zoom_extra es una fraccion adicional de recorte centrado MAS ALLA del
    que ya hace falta para llegar a 1920x1080 (ej. 0.15 = 15% extra de los
    bordes). Sirve para sacar del encuadre subtitulos en ingles quemados
    cerca de los bordes en clips de Alibaba (pedido de Angie). Default 0.0:
    no cambia el comportamiento de las llamadas existentes.

    Lanza ErrorRecurso si ffmpeg/ffprobe no estan disponibles, la entrada no
    es un video legible, o ffmpeg falla al re-codificar.

    NO se prueba con ffmpeg real en unit tests (herramienta externa pesada);
    la corrida real se verifica a mano/CLI contra los clips de ejemplo, igual
    que quitar_fondo/generar_recorte en recortar_producto.py."""
    _verificar_herramientas()
    ancho, alto = _dimensiones_video(ruta_entrada)

    # El temporal conserva la extension real (".tmp" va ANTES, no despues):
    # ffmpeg elige el formato de salida por extension, y "salida.mp4.tmp" no
    # matchea ningun muxer conocido.
    temporal = ruta_salida.with_name(ruta_salida.stem + ".tmp" + ruta_salida.suffix)
    try:
        filtros = []
        if necesita_reescalar(ancho, alto):
            filtros.append("scale=1920:-1,crop=1920:1080")
        if zoom_extra > 0:
            filtros.append(_filtro_zoom_extra(zoom_extra))
        if filtros:
            filtro = ",".join(filtros)
            comando = [
                "ffmpeg", "-y", "-i", str(ruta_entrada),
                "-vf", filtro,
                "-c:v", "libx264", "-crf", "19", "-preset", "fast",
                "-c:a", "copy",
                str(temporal),
            ]
            resultado = subprocess.run(comando, capture_output=True, text=True)
            if resultado.returncode != 0:
                raise ErrorRecurso(
                    f"ffmpeg fallo al normalizar '{ruta_entrada}': "
                    f"{resultado.stderr.strip()[-800:]}"
                )
        else:
            shutil.copyfile(ruta_entrada, temporal)
        os.replace(temporal, ruta_salida)
    finally:
        temporal.unlink(missing_ok=True)  # no-op si ya se renombro con exito
    return ruta_salida


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Normaliza un clip de producto a 1920x1080 (YouTube): lo "
        "deja tal cual si ya esta en ese formato, o lo escala+recorta "
        "centrado si no."
    )
    parser.add_argument("entrada", help="clip de video de entrada (mp4)")
    parser.add_argument("--salida", default=None,
                        help="ruta de salida (default: <entrada>_1080p.mp4)")
    parser.add_argument("--zoom-extra", type=float, default=0.0,
                        help="fraccion de recorte centrado extra (ej. 0.15 "
                        "= 15%%), mas alla del que ya hace falta para "
                        "llegar a 1920x1080. Usar cuando el clip trae "
                        "subtitulos quemados cerca de los bordes (default "
                        "0.0: sin zoom extra)")
    args = parser.parse_args()

    ruta_entrada = Path(args.entrada).resolve()
    ruta_salida = Path(args.salida).resolve() if args.salida else \
        ruta_entrada.with_name(ruta_entrada.stem + "_1080p.mp4")

    try:
        generar_a_archivo(ruta_entrada, ruta_salida, zoom_extra=args.zoom_extra)
        ancho, alto = _dimensiones_video(ruta_salida)
    except ErrorRecurso as error:
        print(f"ERROR DE ARCHIVO: {error}")
        sys.exit(2)

    print(f"VIDEO NORMALIZADO: {ruta_salida}  ({ancho}x{alto})")


if __name__ == "__main__":
    main()
