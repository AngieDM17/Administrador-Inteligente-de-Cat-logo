"""Musica de fondo generada con IA para los videos de producto (etapa
Imagenes/Video).

Genera musica real con `cliente.music.compose()` de ElevenLabs (SDK ya
instalado, clave ya verificada con permiso de uso) y la mezcla como capa de
FONDO sobre un clip que YA tiene la voz en off mezclada con el ambiente
(salida de `voz_en_off.preparar_clip_con_voz`): el resultado final trae tres
capas de audio convividas en una sola pista -- voz (la mas alta), ambiente
del clip (bajo, "ducking", ya resuelto por voz_en_off) y musica (la mas baja,
de fondo).

El PROMPT de musica no lo decide este modulo: lo redacta quien orquesta la
generacion del video (un prompt distinto por producto/categoria, ej. algo
energico para gimnasio, mas serio/industrial para herramientas de
construccion). Este modulo solo sabe generar musica a partir de un prompt de
texto ya armado y una duracion, y mezclarla -- no tiene logica de "que genero
segun la categoria".

Uso:  python musica.py <video_con_voz.mp4> "<prompt de musica>"
      [--salida salida.mp4] [--volumen 0.12]

Codigos de salida: 0 = video con musica de fondo generado; 2 = problema de
recurso (clave de ElevenLabs faltante, video de entrada faltante/ilegible, o
ElevenLabs/ffmpeg/ffprobe fallan).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from cliente_tienda import cargar_env

CARPETA_PROYECTO = Path(__file__).parent
RUTA_ENV_DEFECTO = CARPETA_PROYECTO / ".env"

# Mismo formato que voz_en_off.py (mp3, buena calidad, tamano razonable): no
# hay motivo para que la musica de fondo use un formato distinto a la voz.
OUTPUT_FORMAT = "mp3_44100_128"

# Limites reales de music_length_ms documentados en el SDK de ElevenLabs
# (elevenlabs/music/client.py: "Must be between 3000ms and 600000ms").
DURACION_MINIMA_MS = 3000
DURACION_MAXIMA_MS = 600_000

# Margen extra que se le pide a la musica generada por encima de la duracion
# real del video: ElevenLabs no siempre devuelve la duracion pedida al
# milisegundo exacto (verificado generando una muestra real de 10000ms que
# dio 10031ms), asi que se pide de mas y se recorta EXACTO con ffmpeg despues
# en vez de confiar en el largo devuelto por la API.
MARGEN_EXTRA_MS = 2000

# Volumen de la musica de fondo durante la mezcla (amix), como factor sobre
# el audio ya generado por ElevenLabs. El audio YA EXISTENTE del video (voz
# normalizada con loudnorm + ambiente en silencio, ver
# voz_en_off.preparar_clip_con_voz) NO se toca. Bajado de 0.12 a 0.06
# (6-ago-2026): Angie escucho la primera mezcla completa y la musica todavia
# le competia protagonismo a la voz -- "la voz es la que debe llevarse el
# protagonismo".
VOLUMEN_MUSICA_DEFECTO = 0.06


class ErrorRecurso(Exception):
    """No se pudo generar/mezclar la musica de fondo (clave de ElevenLabs
    faltante, video de entrada faltante/ilegible, o ElevenLabs/ffmpeg/ffprobe
    fallidos). Se traduce a un mensaje claro y salida 2, no a un
    traceback."""


def _clave_api() -> str:
    """Lee ELEVENLABS_API_KEY del .env del proyecto con cargar_env() de
    cliente_tienda.py (reusada tal cual, no se reinventa). Lanza ErrorRecurso
    si la clave no esta presente o esta vacia. La clave NUNCA se escribe ni
    se imprime: solo vive en memoria para la llamada HTTP.

    Se duplica (no se importa) desde voz_en_off.py/subtitulos.py: son 3
    lineas, y subtitulos.py ya establecio el precedente de duplicar en vez de
    cruzar imports entre modulos de audio por esto (ver su propia
    _clave_api)."""
    env = cargar_env(RUTA_ENV_DEFECTO)
    clave = env.get("ELEVENLABS_API_KEY", "").strip()
    if not clave:
        raise ErrorRecurso(
            f"falta ELEVENLABS_API_KEY en '{RUTA_ENV_DEFECTO}'."
        )
    return clave


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


def _duracion_segundos(ruta: Path) -> float:
    """Duracion en segundos de ruta (audio o video), via ffprobe. Lanza
    ErrorRecurso si el archivo no existe o ffprobe falla.

    NO se prueba con ffprobe real en unit tests (herramienta externa): ver
    test_musica.py, que solo cubre la logica pura (calcular_duracion_
    generacion_ms/clamp_volumen)."""
    import json

    if not ruta.is_file():
        raise ErrorRecurso(f"no existe el archivo '{ruta}'.")
    comando = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(ruta),
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
        info = json.loads(resultado.stdout)
        return float(info["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        raise ErrorRecurso(
            f"'{ruta}' no parece tener duracion legible ({error})."
        ) from error


def calcular_duracion_generacion_ms(duracion_video_segundos: float) -> int:
    """Cuantos milisegundos pedirle a music.compose() para un video de
    duracion_video_segundos: la duracion real mas MARGEN_EXTRA_MS (para poder
    recortar exacto despues en vez de confiar en el largo devuelto por la
    API), acotado a los limites reales de la API (DURACION_MINIMA_MS /
    DURACION_MAXIMA_MS).

    Logica pura, sin red: es la parte testeable por unit test."""
    if duracion_video_segundos <= 0:
        raise ValueError("duracion_video_segundos tiene que ser mayor a 0.")
    solicitados = round(duracion_video_segundos * 1000) + MARGEN_EXTRA_MS
    return max(DURACION_MINIMA_MS, min(DURACION_MAXIMA_MS, solicitados))


def clamp_volumen(volumen: float) -> float:
    """Acota volumen al rango razonable [0.0, 1.0]: 0.0 = musica muda (no
    tiene sentido pedirla, pero no debe romper el filtro de ffmpeg con un
    valor negativo), 1.0 = musica al mismo volumen que el audio original del
    video (ya no seria "de fondo", pero tampoco es un error de por si -- la
    decision de que tan alto suena queda en manos de quien llama). Logica
    pura: es la parte testeable por unit test."""
    return max(0.0, min(1.0, volumen))


def generar_musica(prompt: str, duracion_ms: int) -> bytes:
    """Llama a cliente.music.compose() de ElevenLabs y devuelve el audio
    (mp3) generado como bytes.

    La respuesta real de compose() (verificado ejecutando una llamada real
    contra la API, no supuesto de memoria) es un GENERADOR de trozos de bytes
    -- mismo patron que text_to_speech.convert() en voz_en_off.py -- asi que
    se unen igual con b"".join().

    Lanza ErrorRecurso si falta la clave o la API devuelve error.

    NO se prueba con la API real en unit tests (llamada de red paga): se
    verifica a mano/CLI, igual que el resto de los modulos de este proyecto
    que dependen de servicios externos."""
    clave = _clave_api()
    try:
        from elevenlabs.client import ElevenLabs
        cliente = ElevenLabs(api_key=clave)
        trozos = cliente.music.compose(
            prompt=prompt,
            music_length_ms=duracion_ms,
            output_format=OUTPUT_FORMAT,
        )
        return b"".join(trozos)
    except ErrorRecurso:
        raise
    except Exception as error:  # el SDK de ElevenLabs lanza distintos tipos
        raise ErrorRecurso(
            f"ElevenLabs fallo al generar la musica: {error}"
        ) from error


def mezclar_musica_de_fondo(ruta_video_con_voz: Path, prompt_musica: str,
                            ruta_salida: Path,
                            volumen_musica: float = VOLUMEN_MUSICA_DEFECTO) -> Path:
    """Genera musica real a partir de prompt_musica (duracion = la del video
    de entrada + margen) y la mezcla como capa de FONDO sobre el audio YA
    EXISTENTE de ruta_video_con_voz (voz + ambiente ya mezclados por
    voz_en_off.preparar_clip_con_voz): ese audio no se toca, la musica nueva
    se baja a volumen_musica antes de mezclar. Guarda el resultado (mismo
    video, audio de 3 capas) en ruta_salida y devuelve ruta_salida. Guardado
    atomico (temporal + os.replace).

    El video NO se recodifica (`-c:v copy`): el filtro solo toca audio.

    Lanza ErrorRecurso si ffmpeg/ffprobe no estan disponibles, el video de
    entrada no existe, o ElevenLabs/ffmpeg fallan.

    NO se prueba con la API/ffmpeg reales en unit tests; se verifica a
    mano/CLI, igual que el resto de los modulos de este proyecto que
    dependen de servicios externos o herramientas pesadas."""
    _verificar_herramientas()
    ruta_video_con_voz = Path(ruta_video_con_voz)
    if not ruta_video_con_voz.is_file():
        raise ErrorRecurso(f"no existe el video '{ruta_video_con_voz}'.")
    volumen_musica = clamp_volumen(volumen_musica)

    duracion_video = _duracion_segundos(ruta_video_con_voz)
    duracion_generacion_ms = calcular_duracion_generacion_ms(duracion_video)
    audio_musica = generar_musica(prompt_musica, duracion_generacion_ms)

    ruta_salida = Path(ruta_salida)
    temporal = ruta_salida.with_name(
        ruta_salida.stem + ".tmp" + ruta_salida.suffix
    )
    with tempfile.TemporaryDirectory() as carpeta_temp:
        ruta_musica_temporal = Path(carpeta_temp) / "musica.mp3"
        ruta_musica_temporal.write_bytes(audio_musica)

        # [0:a] = audio YA mezclado del video (voz+ambiente), INTACTO;
        # [1:a] = musica nueva, bajada a volumen_musica. amix con
        # duration=first deja el resultado con la duracion del PRIMER input
        # (el audio del video, que es el que manda): si la musica vino un
        # poco mas corta o mas larga que el video (el margen la deja mas
        # larga a proposito), amix la recorta/rellena con silencio para
        # calzar, no hace falta un -t explicito.
        # normalize=0: sin esto amix baja el audio YA mezclado del video
        # (la voz) para que la suma con la musica no sature, tapando la voz
        # de nuevo aunque volumen_musica ya venga bajo (mismo problema que
        # en voz_en_off.preparar_clip_con_voz).
        filtro_complejo = (
            f"[1:a]volume={volumen_musica}[musica];"
            "[0:a][musica]amix=inputs=2:duration=first:dropout_transition=0"
            ":normalize=0[audio_final]"
        )
        comando = [
            "ffmpeg", "-y",
            "-i", str(ruta_video_con_voz),
            "-i", str(ruta_musica_temporal),
            "-filter_complex", filtro_complejo,
            "-map", "0:v", "-map", "[audio_final]",
            "-c:v", "copy",
            "-c:a", "aac",
            str(temporal),
        ]
        try:
            resultado = subprocess.run(comando, capture_output=True, text=True)
            if resultado.returncode != 0:
                raise ErrorRecurso(
                    f"ffmpeg fallo al mezclar la musica de fondo sobre "
                    f"'{ruta_video_con_voz}': {resultado.stderr.strip()[-800:]}"
                )
            os.replace(temporal, ruta_salida)
        finally:
            temporal.unlink(missing_ok=True)
    return ruta_salida


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Genera musica de fondo con IA (ElevenLabs) a partir de "
        "un prompt de texto y la mezcla, bajada de volumen, sobre el audio "
        "ya existente (voz+ambiente) de un video de producto."
    )
    parser.add_argument("video", help="clip de video con voz ya mezclada (mp4)")
    parser.add_argument("prompt", help="prompt de texto para la musica "
                        "(ej. 'energetic upbeat corporate background music, "
                        "motivational, no vocals')")
    parser.add_argument("--salida", default=None,
                        help="ruta de salida (default: <video>_musica.mp4)")
    parser.add_argument("--volumen", type=float, default=VOLUMEN_MUSICA_DEFECTO,
                        help=f"volumen de la musica de fondo, 0.0-1.0 "
                        f"(default {VOLUMEN_MUSICA_DEFECTO})")
    args = parser.parse_args()

    ruta_video = Path(args.video).resolve()
    if not ruta_video.is_file():
        print(f"ERROR DE ARCHIVO: no existe el video '{ruta_video}'.")
        sys.exit(2)

    ruta_salida = Path(args.salida).resolve() if args.salida else \
        ruta_video.with_name(ruta_video.stem + "_musica.mp4")

    try:
        mezclar_musica_de_fondo(
            ruta_video, args.prompt, ruta_salida, volumen_musica=args.volumen
        )
    except ErrorRecurso as error:
        print(f"ERROR DE ARCHIVO: {error}")
        sys.exit(2)

    print(f"VIDEO CON MUSICA DE FONDO: {ruta_salida}")


if __name__ == "__main__":
    main()
