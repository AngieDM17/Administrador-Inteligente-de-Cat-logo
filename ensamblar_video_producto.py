"""Ensamblador final del video de producto Ekipon (etapa Imagenes/Video).

Arma el video que se sube a YouTube concatenando, EN ESTE ORDEN FIJO
(confirmado con Angie, no esta a discusion):

    1. Portada (imagen estatica de generador_portada.py) mostrada unos
       segundos, convertida a un segmento de video.
    2. Clip del producto, ya normalizado a 1920x1080 por
       preparar_video_producto.py.
    3. AI ENERGY OUTRO.mp4 (animacion de logo fija, con su propio audio).
    4. EKIPON OUTRO.mp4 (animacion de logo fija, con su propio audio).

Los dos outros son archivos fijos en la raiz del proyecto: no se generan, se
reutilizan tal cual. La portada no trae audio propio, asi que se le agrega una
pista de audio silenciosa -- el filtro concat de ffmpeg exige que todos los
tramos tengan la misma cantidad de streams (si a uno le falta el de audio,
falla) -- para que quede pareja con el resto.

Todavia NO hay voz en off, subtitulos ni marca de agua: quedan afuera de este
armado a proposito (dependen de una decision de compra pendiente de Angie).

Uso:  python ensamblar_video_producto.py <portada.png> <clip_producto.mp4> \
          [--salida final.mp4]

Codigos de salida: 0 = video ensamblado; 2 = problema de archivo (entrada
faltante/ilegible, outro faltante, o ffmpeg/ffprobe no disponibles o fallan).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Duracion de la portada en el video final. Constante facil de ajustar: es una
# decision de diseno de Angie, no una que se deduzca de otro dato.
DURACION_PORTADA_SEGUNDOS = 4

RESOLUCION_YOUTUBE = (1920, 1080)

# Cuadros por segundo COMUN a los 4 tramos. Sin esto, el demuxer concat con
# "-c copy" mezcla tramos a fps distinta (ej. la portada sale a 25 por
# defecto, los outros/el clip vienen a 30) y el video final queda mal
# armado: la duracion del stream de video no coincide con la del audio,
# y las animaciones se ven "estiradas" mas tiempo del que duran en realidad.
# Verificado el 5-ago-2026: sin -r, el final daba 51.6s en vez de ~43s.
FPS_SALIDA = 30

# Volumen del audio de los outros (AI ENERGY / EKIPON) en el video final.
# Los archivos originales traen su musica de fondo a un nivel de broadcast
# (medido: -15dB promedio, picos en 0dB) pensado para reproducirse solos --
# muy por encima del segmento de voz+musica que viene justo antes (voz al
# frente, musica de fondo baja). Angie lo escucho en el video completo y
# pidio bajarlo (6-ago-2026): "los dos ultimos videos de las animaciones
# tienen el audio muy fuerte". 0.35 (~-9dB) los deja parejos con el resto
# sin silenciarlos del todo -- siguen siendo animaciones con su propio audio,
# no video mudo.
VOLUMEN_AUDIO_OUTROS = 0.35

CARPETA_PROYECTO = Path(__file__).parent
RUTA_OUTRO_1_DEFECTO = CARPETA_PROYECTO / "AI ENERGY OUTRO.mp4"
RUTA_OUTRO_2_DEFECTO = CARPETA_PROYECTO / "EKIPON OUTRO.mp4"


class ErrorRecurso(Exception):
    """No se pudo ensamblar el video (algun tramo falta/ilegible, ffmpeg/
    ffprobe ausentes o fallidos). Se traduce a un mensaje claro y salida 2,
    no a un traceback."""


def rutas_tramos(ruta_portada_imagen: Path, ruta_clip_producto: Path,
                 ruta_outro1: Path = None, ruta_outro2: Path = None) -> list[Path]:
    """Devuelve, EN ORDEN, las 4 rutas de entrada que van al video final:
    portada, clip de producto, outro1, outro2. Logica pura (sin ffmpeg): es
    la parte testeable por unit test. Los outros caen a los dos archivos
    fijos de la raiz del proyecto si no se pasan explicitamente."""
    outro1 = ruta_outro1 or RUTA_OUTRO_1_DEFECTO
    outro2 = ruta_outro2 or RUTA_OUTRO_2_DEFECTO
    return [ruta_portada_imagen, ruta_clip_producto, outro1, outro2]


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


def _verificar_archivos_entrada(rutas: list[Path]) -> None:
    """Lanza ErrorRecurso con un mensaje claro si alguna de las rutas de
    entrada (portada, clip, outro1, outro2) no existe. Se verifica ANTES de
    invocar ffmpeg para no fallar a mitad de una corrida larga por un archivo
    que faltaba desde el principio."""
    faltantes = [str(r) for r in rutas if not r.is_file()]
    if faltantes:
        raise ErrorRecurso(
            "no existen los siguientes archivos de entrada: "
            + ", ".join(faltantes)
        )


def _segmento_portada(ruta_portada_imagen: Path, ruta_salida: Path) -> None:
    """Convierte la imagen estatica de portada en un clip de video de
    DURACION_PORTADA_SEGUNDOS, 1920x1080, con una pista de audio silenciosa
    (anullsrc) para que el concat no falle por streams de audio faltantes.
    Se recodifica a libx264/aac igual que preve el resto del pipeline."""
    comando = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(ruta_portada_imagen),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(DURACION_PORTADA_SEGUNDOS),
        "-vf", f"scale={RESOLUCION_YOUTUBE[0]}:{RESOLUCION_YOUTUBE[1]}",
        "-r", str(FPS_SALIDA),
        "-c:v", "libx264", "-crf", "19", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(ruta_salida),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise ErrorRecurso(
            f"ffmpeg fallo al armar el segmento de portada: "
            f"{resultado.stderr.strip()[-800:]}"
        )


def _normalizar_tramo(ruta_entrada: Path, ruta_salida: Path,
                      volumen_audio: float = 1.0) -> None:
    """Recodifica un tramo (clip de producto u outro) a un codec/formato
    parejo (libx264/aac, 1920x1080) para que el concat por filtro funcione
    aunque los tramos originales tengan codecs/parametros de audio distintos.
    No asume que el clip ya viene en 1920x1080: lo fuerza con scale+pad para
    no romper el concat si algun tramo llega con otra resolucion.

    volumen_audio ajusta el volumen del audio propio del tramo (factor sobre
    el original, 1.0 = sin cambios) -- lo usan los outros para no quedar mas
    fuertes que el resto del video (ver VOLUMEN_AUDIO_OUTROS)."""
    filtro_video = (
        f"scale={RESOLUCION_YOUTUBE[0]}:{RESOLUCION_YOUTUBE[1]}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={RESOLUCION_YOUTUBE[0]}:{RESOLUCION_YOUTUBE[1]}:(ow-iw)/2:(oh-ih)/2"
    )
    comando = [
        "ffmpeg", "-y", "-i", str(ruta_entrada),
        "-vf", filtro_video,
        "-af", f"volume={volumen_audio}",
        "-r", str(FPS_SALIDA),
        "-c:v", "libx264", "-crf", "19", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        str(ruta_salida),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise ErrorRecurso(
            f"ffmpeg fallo al normalizar el tramo '{ruta_entrada}': "
            f"{resultado.stderr.strip()[-800:]}"
        )


def generar_a_archivo(ruta_portada_imagen: Path, ruta_clip_producto: Path,
                      ruta_salida: Path, ruta_outro1: Path = None,
                      ruta_outro2: Path = None) -> Path:
    """Arma el video final (portada + clip de producto + outro1 + outro2) y
    lo guarda en ruta_salida. Devuelve ruta_salida.

    Cada tramo se recodifica primero a un formato parejo (libx264/aac,
    1920x1080, mismo sample rate/canales de audio) en un directorio temporal,
    y despues se concatenan con el demuxer concat de ffmpeg (mas robusto que
    el filtro concat cuando los tramos ya vienen parejos). Guardado atomico
    del archivo final (temporal + os.replace), igual que el resto del
    pipeline de video/imagenes.

    Lanza ErrorRecurso si ffmpeg/ffprobe no estan disponibles, algun archivo
    de entrada (portada, clip, outro1, outro2) no existe, o ffmpeg falla en
    cualquier paso.

    NO se prueba con ffmpeg real en unit tests (herramienta externa pesada);
    la corrida real se verifica a mano/CLI, igual que preparar_video_producto
    y recortar_producto."""
    _verificar_herramientas()
    tramos_entrada = rutas_tramos(ruta_portada_imagen, ruta_clip_producto,
                                  ruta_outro1, ruta_outro2)
    _verificar_archivos_entrada(tramos_entrada)

    ruta_salida = Path(ruta_salida)
    carpeta_temp = ruta_salida.parent / f".{ruta_salida.stem}_tmp_tramos"
    carpeta_temp.mkdir(parents=True, exist_ok=True)
    temporal_final = ruta_salida.with_name(
        ruta_salida.stem + ".tmp" + ruta_salida.suffix
    )
    try:
        ruta_portada_video = carpeta_temp / "0_portada.mp4"
        _segmento_portada(ruta_portada_imagen, ruta_portada_video)

        ruta_clip_normalizado = carpeta_temp / "1_clip.mp4"
        _normalizar_tramo(ruta_clip_producto, ruta_clip_normalizado)

        ruta_outro1_normalizado = carpeta_temp / "2_outro1.mp4"
        _normalizar_tramo(tramos_entrada[2], ruta_outro1_normalizado,
                         volumen_audio=VOLUMEN_AUDIO_OUTROS)

        ruta_outro2_normalizado = carpeta_temp / "3_outro2.mp4"
        _normalizar_tramo(tramos_entrada[3], ruta_outro2_normalizado,
                         volumen_audio=VOLUMEN_AUDIO_OUTROS)

        tramos_normalizados = [
            ruta_portada_video, ruta_clip_normalizado,
            ruta_outro1_normalizado, ruta_outro2_normalizado,
        ]
        ruta_lista = carpeta_temp / "lista.txt"
        contenido_lista = "\n".join(
            f"file '{t.resolve().as_posix()}'" for t in tramos_normalizados
        )
        ruta_lista.write_text(contenido_lista, encoding="utf-8")

        comando = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(ruta_lista),
            "-c", "copy",
            str(temporal_final),
        ]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0:
            raise ErrorRecurso(
                f"ffmpeg fallo al concatenar los tramos: "
                f"{resultado.stderr.strip()[-800:]}"
            )
        os.replace(temporal_final, ruta_salida)
    finally:
        temporal_final.unlink(missing_ok=True)
        shutil.rmtree(carpeta_temp, ignore_errors=True)
    return ruta_salida


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Arma el video final de producto: portada + clip de "
        "producto + AI ENERGY OUTRO + EKIPON OUTRO, en ese orden."
    )
    parser.add_argument("portada", help="imagen de portada (PNG/JPG)")
    parser.add_argument("clip_producto", help="clip de producto normalizado (mp4)")
    parser.add_argument("--salida", default=None,
                        help="ruta de salida (default: <clip>_final.mp4)")
    parser.add_argument("--outro1", default=None,
                        help="override del primer outro (default: AI ENERGY OUTRO.mp4)")
    parser.add_argument("--outro2", default=None,
                        help="override del segundo outro (default: EKIPON OUTRO.mp4)")
    args = parser.parse_args()

    ruta_portada = Path(args.portada).resolve()
    ruta_clip = Path(args.clip_producto).resolve()
    ruta_salida = Path(args.salida).resolve() if args.salida else \
        ruta_clip.with_name(ruta_clip.stem + "_final.mp4")
    ruta_outro1 = Path(args.outro1).resolve() if args.outro1 else None
    ruta_outro2 = Path(args.outro2).resolve() if args.outro2 else None

    try:
        generar_a_archivo(ruta_portada, ruta_clip, ruta_salida, ruta_outro1, ruta_outro2)
    except ErrorRecurso as error:
        print(f"ERROR DE ARCHIVO: {error}")
        sys.exit(2)

    print(f"VIDEO ENSAMBLADO: {ruta_salida}")


if __name__ == "__main__":
    main()
