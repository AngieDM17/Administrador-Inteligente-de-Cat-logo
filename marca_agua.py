"""Marca de agua del logo Ekipon sobre el clip de producto (etapa Imagenes/Video).

Pedido textual de Angie: "el logo de ekipon que va en la parte de arriba a la
derecha, no toca ninguno de los bordes, siempre los respeta". O sea: el logo
va CHICO (es marca de agua, no protagonista) en la esquina SUPERIOR DERECHA,
con margen respecto a los bordes de arriba y de la derecha -- nunca pegado.

El archivo fijo "Ekipon, marca de agua .png" (raiz del proyecto) es un lienzo
1920x1080 RGBA con el logo dibujado en una zona centrada-izquierda del
lienzo, no pegado a sus bordes: para usarlo como marca de agua chica primero
hay que recortarlo a su contenido real (bounding box del canal alfa), si no
la "marca de agua" terminaria siendo casi tan ancha como el video entero.

Este modulo se aplica SOLO al clip de producto (el tramo del medio del video
final), no a la portada (que ya trae su logo integrado en la plantilla de
generador_portada.py) ni a los outros (animaciones de marca ya armadas
aparte). La integracion a ensamblar_video_producto.py queda para un paso
aparte: por ahora este modulo es independiente y se prueba solo.

Uso:  python marca_agua.py <video.mp4> [--salida salida.mp4] [--logo logo.png]

Codigos de salida: 0 = video con marca de agua generado; 2 = problema de
archivo (entrada/logo faltante o ilegible, o ffmpeg/ffprobe no disponibles o
fallan).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

CARPETA_PROYECTO = Path(__file__).parent
RUTA_LOGO_DEFECTO = CARPETA_PROYECTO / "Ekipon, marca de agua .png"

# Ancho de la marca de agua como fraccion del ancho del video (1920*0.14 ~=
# 270px). Calibrado a ojo (ver test_marca_agua.py / verificacion manual): con
# 0.14 el logo se lee nitido sin competirle protagonismo al video.
ANCHO_MARCA_AGUA_FRAC = 0.14

# Margen respecto a los bordes superior/derecho, como fraccion del alto/ancho
# del video. Calibrado a ojo para que el logo "no toque ningun borde" (pedido
# textual de Angie) sin quedar flotando lejos de la esquina.
MARGEN_MARCA_AGUA_FRAC = 0.03


class ErrorRecurso(Exception):
    """No se pudo generar la marca de agua (video/logo faltante o ilegible,
    ffmpeg/ffprobe ausentes o fallidos). Se traduce a un mensaje claro y
    salida 2, no a un traceback."""


def recortar_logo_a_contenido(imagen: Image.Image) -> Image.Image:
    """Recorta `imagen` (RGBA) a la caja minima que contiene todo pixel no
    transparente, usando Image.getbbox() sobre el canal alfa. Logica pura
    (sin ffmpeg ni disco): es la parte testeable por unit test.

    El archivo de logo fijo trae el dibujo dentro de un lienzo mas grande
    que el; si se usara tal cual como marca de agua, redimensionar el
    LIENZO a un ancho chico dejaria el logo real diminuto (todo ese espacio
    transparente alrededor tambien se encogeria). Recortar primero al
    contenido real es lo que permite despues escalar solo el logo.

    No hardcodea las coordenadas del logo actual: si el archivo cambia,
    getbbox() las recalcula solo.

    Lanza ValueError si la imagen no tiene canal alfa o esta completamente
    transparente (getbbox() no encuentra nada que recortar)."""
    if imagen.mode != "RGBA":
        raise ValueError(
            f"la imagen de logo debe tener canal alfa (RGBA); vino en modo "
            f"'{imagen.mode}'."
        )
    caja = imagen.getbbox()
    if caja is None:
        raise ValueError(
            "la imagen de logo esta completamente transparente: no hay "
            "contenido que recortar."
        )
    return imagen.crop(caja)


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
    innecesaria para probar logica): ver test_marca_agua.py, que solo cubre
    recortar_logo_a_contenido()."""
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


def _preparar_logo_redimensionado(ruta_logo: Path, ancho_video: int,
                                  ruta_logo_salida: Path) -> None:
    """Recorta el logo a su contenido real y lo reescala a
    ANCHO_MARCA_AGUA_FRAC * ancho_video (alto proporcional), guardandolo como
    PNG en ruta_logo_salida para que ffmpeg lo use con overlay.

    Lanza ErrorRecurso si el logo no existe, no es una imagen legible, o no
    tiene contenido (transparente por completo)."""
    if not ruta_logo.is_file():
        raise ErrorRecurso(f"no existe el archivo de logo '{ruta_logo}'.")
    try:
        logo = Image.open(ruta_logo).convert("RGBA")
    except Exception as error:  # Pillow lanza distintos tipos segun el caso
        raise ErrorRecurso(
            f"'{ruta_logo}' no parece una imagen legible ({error})."
        ) from error
    try:
        logo_recortado = recortar_logo_a_contenido(logo)
    except ValueError as error:
        raise ErrorRecurso(str(error)) from error

    ancho_destino = max(1, round(ancho_video * ANCHO_MARCA_AGUA_FRAC))
    alto_destino = max(
        1,
        round(ancho_destino * logo_recortado.height / logo_recortado.width),
    )
    logo_final = logo_recortado.resize(
        (ancho_destino, alto_destino), Image.LANCZOS
    )
    logo_final.save(ruta_logo_salida)


def generar_a_archivo(ruta_video: Path, ruta_salida: Path,
                      ruta_logo: Path = None) -> Path:
    """Superpone el logo Ekipon como marca de agua en la esquina superior
    derecha del video, con margen respecto a ambos bordes, y guarda el
    resultado en ruta_salida. Devuelve ruta_salida.

    ruta_logo cae al archivo fijo "Ekipon, marca de agua .png" de la raiz del
    proyecto si no se pasa explicitamente.

    El logo se recorta a su contenido real y se reescala con Pillow a un PNG
    temporal (mas simple y confiable que hacer el recorte+escala con filtros
    de ffmpeg), y despues se compone con el filtro `overlay` de ffmpeg sobre
    el video, sin recodificar el audio (`-c:a copy`).

    Guardado atomico (temporal + os.replace): si el proceso muere a mitad de
    camino no queda un archivo a medias pisando uno previo valido.

    Lanza ErrorRecurso si ffmpeg/ffprobe no estan disponibles, el video o el
    logo no son legibles, o ffmpeg falla al componer.

    NO se prueba con ffmpeg real en unit tests (herramienta externa pesada);
    la corrida real se verifica a mano/CLI, igual que preparar_video_producto
    y ensamblar_video_producto."""
    _verificar_herramientas()
    ruta_logo = ruta_logo or RUTA_LOGO_DEFECTO
    ancho_video, _ = _dimensiones_video(ruta_video)

    margen_x = round(ancho_video * MARGEN_MARCA_AGUA_FRAC)
    margen_y = margen_x  # mismo margen fraccional en x/y; se calcula sobre
    # el ancho para no depender de si el video es horizontal o no.

    temporal = ruta_salida.with_name(
        ruta_salida.stem + ".tmp" + ruta_salida.suffix
    )
    with tempfile.TemporaryDirectory() as carpeta_temp:
        ruta_logo_redimensionado = Path(carpeta_temp) / "logo.png"
        _preparar_logo_redimensionado(
            ruta_logo, ancho_video, ruta_logo_redimensionado
        )

        # overlay=W-w-margen_x:margen_y ancla el logo a la esquina superior
        # derecha (W = ancho del video, w = ancho del logo) con margen fijo
        # respecto a ambos bordes, tal como lo pidio Angie.
        filtro_overlay = f"overlay=W-w-{margen_x}:{margen_y}"
        comando = [
            "ffmpeg", "-y",
            "-i", str(ruta_video),
            "-i", str(ruta_logo_redimensionado),
            "-filter_complex", filtro_overlay,
            "-c:v", "libx264", "-crf", "19", "-preset", "fast",
            "-c:a", "copy",
            str(temporal),
        ]
        try:
            resultado = subprocess.run(comando, capture_output=True, text=True)
            if resultado.returncode != 0:
                raise ErrorRecurso(
                    f"ffmpeg fallo al componer la marca de agua sobre "
                    f"'{ruta_video}': {resultado.stderr.strip()[-800:]}"
                )
            os.replace(temporal, ruta_salida)
        finally:
            temporal.unlink(missing_ok=True)
    return ruta_salida


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Superpone el logo Ekipon como marca de agua chica en la "
        "esquina superior derecha del video, con margen respecto a ambos "
        "bordes."
    )
    parser.add_argument("video", help="clip de video de entrada (mp4)")
    parser.add_argument("--salida", default=None,
                        help="ruta de salida (default: <video>_marca_agua.mp4)")
    parser.add_argument("--logo", default=None,
                        help="override del logo (default: 'Ekipon, marca de "
                        "agua .png' en la raiz del proyecto)")
    args = parser.parse_args()

    ruta_video = Path(args.video).resolve()
    ruta_salida = Path(args.salida).resolve() if args.salida else \
        ruta_video.with_name(ruta_video.stem + "_marca_agua.mp4")
    ruta_logo = Path(args.logo).resolve() if args.logo else None

    try:
        generar_a_archivo(ruta_video, ruta_salida, ruta_logo)
    except ErrorRecurso as error:
        print(f"ERROR DE ARCHIVO: {error}")
        sys.exit(2)

    print(f"VIDEO CON MARCA DE AGUA: {ruta_salida}")


if __name__ == "__main__":
    main()
