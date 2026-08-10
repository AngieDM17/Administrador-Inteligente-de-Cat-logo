"""Voz en off de los videos de producto (etapa Imagenes/Video).

Genera la narracion en off con ElevenLabs (dos voces fijas, alternadas por
producto segun el indice en el lote -- no dentro del mismo video) y arma el
guion con una estructura fija confirmada con Angie:

    FRASE_FIJA + cuerpo real del producto (recortado a un presupuesto de
    caracteres por FRASES COMPLETAS) + FRASE_FIJA

El presupuesto de caracteres existe para que la voz dure ~SEGUNDOS_OBJETIVO_VOZ
segundos: sumado a portada (4s) + outro1 (7s) + outro2 (7.067s) del
ensamblador, el video final queda alrededor de 1 minuto. CARACTERES_POR_SEGUNDO
se midio generando una muestra real con ElevenLabs (ver commit que agrega este
modulo): no es una cifra de memoria.

Este modulo tambien arma el CLIP final con voz (`preparar_clip_con_voz`):
recorta el clip normalizado (1920x1080, ver preparar_video_producto.py) a la
duracion exacta de la voz y mezcla el audio ambiente del clip (silenciado,
VOLUMEN_AMBIENTE=0.0) con la narracion a volumen normal -- en el video final
solo se escuchan la voz y la musica de fondo (musica.py), nunca el audio
original del clip. El resultado es lo que se le pasa a
ensamblar_video_producto.generar_a_archivo() como ruta_clip_producto.

Uso:  python voz_en_off.py <ficha.json> [--salida voz.mp3] [--indice 0]

Codigos de salida: 0 = voz generada; 2 = problema de recurso (clave de
ElevenLabs faltante, ficha ilegible, ElevenLabs/ffmpeg/ffprobe fallan, o el
clip no alcanza para cubrir la voz).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from cliente_tienda import cargar_env

FRASE_FIJA = (
    "En Ekipon.co hacemos envíos gratis a todo Colombia, con pago contra "
    "entrega."
)

# Voces fijas confirmadas con Angie, alternadas por producto (no dentro del
# mismo video). El orden de esta lista es el orden de alternancia (indice %
# len(_ORDEN_VOCES), ver elegir_voz). "santiago" sumado el 10-ago-2026: Angie
# pidio voces con mas fuerza/mas llamativas, escucho 3 candidatas de la
# libreria publica de ElevenLabs (busqueda por descriptivos
# confident/powerful/energetic en espanol) y eligio esta ("Enthusiastic,
# Assertive") para que las 3 alternen y den variedad, no para reemplazar a
# Carlos o Gonzalo.
VOCES = {
    "carlos": "4PN5DHmrfIgZksvIrawS",
    "gonzalo": "UUj9OsNVMEpYEFSA8ZI8",
    "santiago": "w7IU2bIH6xHcyfkUUWi3",
}
_ORDEN_VOCES = ["carlos", "gonzalo", "santiago"]

MODEL_ID = "eleven_multilingual_v2"
OUTPUT_FORMAT = "mp3_44100_128"

# Velocidad de habla pasada a VoiceSettings (rango soportado por ElevenLabs:
# 0.7-1.2, default 1.0; valores menores hablan mas lento). Angie reporto que
# la voz salia "muy rapido, cuesta entenderla" a la velocidad default.
# Verificado en la documentacion oficial de ElevenLabs (no supuesto) que 0.7
# es el piso soportado: valores mas bajos degradan la calidad del audio. Se
# probo 0.85 generando una muestra real con la voz "gonzalo" y se confirmo
# a oido que ya se entiende bien, asi que se dejo en ese valor.
VELOCIDAD_VOZ = 0.85

CARPETA_PROYECTO = Path(__file__).parent
RUTA_ENV_DEFECTO = CARPETA_PROYECTO / ".env"

# Medido el 6-ago-2026 generando una muestra real de 268 caracteres con la
# voz "gonzalo" (eleven_multilingual_v2, mp3_44100_128, speed=VELOCIDAD_VOZ
# = 0.85): el audio resultante dio 20.43s, es decir ~13.1 caracteres/segundo.
# Es MAS LENTO que a velocidad default (15.3 caracteres/segundo, medido antes
# de este ajuste): bajar la velocidad de habla no cambia el texto, tarda mas
# en decirlo, asi que el presupuesto de caracteres para llegar a los mismos
# ~42s de voz tiene que ser menor. No es una cifra de memoria: se corrio la
# llamada real contra la API con speed=0.85 y se midio la duracion con
# ffprobe.
CARACTERES_POR_SEGUNDO = 13.1

# Duracion objetivo del tramo de voz: portada (4s) + outro1 (7s) +
# outro2 (7.067s) del ensamblador ya suman ~18.07s, asi que el resto hasta
# los ~60s totales que pidio Angie le queda a voz+clip.
SEGUNDOS_OBJETIVO_VOZ = 42

PRESUPUESTO_CARACTERES_DEFECTO = round(
    CARACTERES_POR_SEGUNDO * SEGUNDOS_OBJETIVO_VOZ
)

# Volumen del audio ORIGINAL del clip durante la mezcla final: en 0.0,
# completamente silenciado. Angie probo el ducking (0.15) para un video de
# YouTube y el ambiente (ruido de fabrica/gimnasio del clip) seguia tapando
# la voz -- pidio que en el video final SOLO se escuchen la voz en off y la
# musica de fondo (musica.py), nunca el audio original del clip (6-ago-2026).
VOLUMEN_AMBIENTE = 0.0

# Sonoridad objetivo de la VOZ en la mezcla final, normalizada con el filtro
# `loudnorm` de ffmpeg (EBU R128: LUFS integrados + techo de pico real), NO
# con un factor fijo de `volume=`. Se detecto el 8-ago-2026 probando un
# segundo producto (voz de Gonzalo) que un factor fijo (antes 1.4x sobre
# volumen normal) rompe apenas cambia la voz: la muestra de Carlos del primer
# video salio de ElevenLabs a -33dB de promedio, pero la de Gonzalo para este
# producto salio a -17dB -- el MISMO 1.4x que en Carlos dejaba margen de sobra
# en Gonzalo casi tocaba 0dB (saturacion). loudnorm targetea una sonoridad
# fija sin importar en que nivel haya salido la sintesis, asi que la voz
# "lleva el protagonismo" (pedido de Angie) de forma pareja entre voces.
# LOUDNORM_I = sonoridad integrada objetivo (LUFS); LOUDNORM_TP = techo de
# pico real (dBTP), con margen bajo 0dB para no saturar nunca.
# Subido de -14 a -12 (8-ago-2026): tras resolver que la musica tapaba la voz
# (6-ago), Angie escucho los 3 videos de la prueba de escala y el balance se
# sintio plano/sin fuerza -- "esa voz no la da tanto". TP se mantiene: sigue
# habiendo margen bajo el techo de pico.
LOUDNORM_VOZ_I = -12
LOUDNORM_VOZ_TP = -1.5


class ErrorRecurso(Exception):
    """No se pudo generar la voz en off o el clip mezclado (clave de
    ElevenLabs faltante, ficha sin texto utilizable, ElevenLabs/ffmpeg/
    ffprobe fallidos, o el clip no alcanza para cubrir la voz). Se traduce a
    un mensaje claro y salida 2, no a un traceback."""


def elegir_voz(indice_producto: int) -> str:
    """Devuelve el NOMBRE de la voz que le toca a indice_producto, alternando
    en el orden de _ORDEN_VOCES por resto de la division (indice_producto %
    len(_ORDEN_VOCES)). Logica pura, sin red: se prueba con unit tests."""
    return _ORDEN_VOCES[indice_producto % len(_ORDEN_VOCES)]


def _partir_en_frases(texto: str) -> list[str]:
    """Parte texto en frases completas (cada una termina en . ! o ?). Mismo
    patron que partir_en_frases() de generador_banner.py: no se reimporta
    porque ese modulo esta pensado para banners de imagen (mide contra una
    caja de pixeles), no contra un presupuesto de caracteres."""
    frases = re.findall(r".*?[.!?](?=\s|$)", texto, flags=re.S)
    return [f.strip() for f in frases if f.strip()]


def _cerrar_en_frases(texto: str, presupuesto_caracteres: int) -> str:
    """Devuelve la mayor cantidad de frases COMPLETAS del inicio de `texto`
    cuyo largo total (con espacios) no supera presupuesto_caracteres. Nunca
    corta a mitad de oracion: si ni una frase entera entra, devuelve cadena
    vacia en vez de un fragmento cortado. Logica pura, sin red."""
    texto = texto.strip()
    if not texto or presupuesto_caracteres <= 0:
        return ""
    if len(texto) <= presupuesto_caracteres:
        return texto
    frases = _partir_en_frases(texto) or [texto]
    for cantidad in range(len(frases), 0, -1):
        candidato = " ".join(frases[:cantidad])
        if len(candidato) <= presupuesto_caracteres:
            return candidato
    return ""


def armar_guion(datos: dict, presupuesto_caracteres: int,
                cuerpo_manual: str | None = None) -> str:
    """Arma el guion completo: FRASE_FIJA + cuerpo + FRASE_FIJA.

    El cuerpo tiene dos fuentes posibles:
    - `cuerpo_manual`: un texto YA REDACTADO (por Claude, por producto) como
      copy de venta -- reformula los datos reales de la ficha con gancho
      comercial, en vez de citarlos literal. Se usa TAL CUAL, sin recortar:
      quien lo escribe ya apunta al largo correcto. Este es el camino
      preferido (decision de Angie, 6-ago-2026): un recorte mecanico de la
      descripcion real a veces deja el guion muy corto porque la siguiente
      frase completa no entra en el presupuesto que sobra y esa sobra se
      pierde -- no hay forma de "acortar la idea" sin redactar de nuevo.
    - Si no se pasa `cuerpo_manual`: cae al comportamiento viejo (compatible
      hacia atras) de tomar `descripcion_banner`/`descripcion_principal` de
      la ficha y recortarla por FRASES COMPLETAS al presupuesto disponible.

    presupuesto_caracteres es el presupuesto del GUION COMPLETO (las dos
    apariciones de FRASE_FIJA incluidas), no solo del cuerpo: la duracion de
    la voz depende del largo total de lo que se lee, y FRASE_FIJA sola ya
    dura ~10s a la velocidad medida de ElevenLabs (ver CARACTERES_POR_
    SEGUNDO). Restar solo el presupuesto del cuerpo e ignorar el costo de
    FRASE_FIJA hacia la voz mucho mas larga que el objetivo -- error real
    detectado el 6-ago-2026 verificando con audio real (50.4s en vez de
    ~42s) antes de este ajuste. Solo aplica al camino automatico:
    `cuerpo_manual` no se recorta, se respeta el largo que ya trae.

    Logica pura, sin red: se prueba con unit tests."""
    if cuerpo_manual is not None:
        cuerpo_recortado = cuerpo_manual.strip()
    else:
        overhead_frases_fijas = 2 * len(FRASE_FIJA) + 2  # +2: los dos espacios
        # de union entre FRASE_FIJA-cuerpo-FRASE_FIJA en el join final.
        presupuesto_cuerpo = max(0, presupuesto_caracteres - overhead_frases_fijas)
        cuerpo = (datos.get("descripcion_banner") or "").strip() or \
            (datos.get("descripcion_principal") or "").strip()
        cuerpo_recortado = _cerrar_en_frases(cuerpo, presupuesto_cuerpo)

    partes = [FRASE_FIJA]
    if cuerpo_recortado:
        partes.append(cuerpo_recortado)
    partes.append(FRASE_FIJA)
    return " ".join(partes)


def _clave_api() -> str:
    """Lee ELEVENLABS_API_KEY del .env del proyecto con cargar_env() de
    cliente_tienda.py (reusada tal cual, no se reinventa). Lanza ErrorRecurso
    si la clave no esta presente o esta vacia. La clave NUNCA se escribe ni
    se imprime: solo vive en memoria para la llamada HTTP."""
    env = cargar_env(RUTA_ENV_DEFECTO)
    clave = env.get("ELEVENLABS_API_KEY", "").strip()
    if not clave:
        raise ErrorRecurso(
            f"falta ELEVENLABS_API_KEY en '{RUTA_ENV_DEFECTO}'."
        )
    return clave


def _sintetizar_voz(guion: str, voz: str) -> bytes:
    """Llama a ElevenLabs (text_to_speech.convert) y devuelve el mp3
    resultante como bytes. Lanza ErrorRecurso si falta la clave o la API
    devuelve error.

    NO se prueba con la API real en unit tests (llamada de red paga): se
    verifica a mano/CLI contra una ficha real, igual que el resto de los
    modulos de este proyecto que dependen de servicios externos."""
    clave = _clave_api()
    voice_id = VOCES[voz]
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs.types import VoiceSettings
        cliente = ElevenLabs(api_key=clave)
        trozos = cliente.text_to_speech.convert(
            voice_id=voice_id, text=guion, model_id=MODEL_ID,
            output_format=OUTPUT_FORMAT,
            voice_settings=VoiceSettings(speed=VELOCIDAD_VOZ),
        )
        return b"".join(trozos)
    except ErrorRecurso:
        raise
    except Exception as error:  # el SDK de ElevenLabs lanza distintos tipos
        raise ErrorRecurso(
            f"ElevenLabs fallo al generar la voz: {error}"
        ) from error


def generar_a_archivo(datos: dict, ruta_salida: Path,
                      indice_producto: int = 0,
                      cuerpo_manual: str | None = None) -> Path:
    """Arma el guion, genera la voz con ElevenLabs (alternando voz segun
    indice_producto) y la guarda en ruta_salida (mp3). Devuelve ruta_salida.
    Guardado atomico (temporal + os.replace).

    `cuerpo_manual`: guion redactado por Claude para este producto (copy de
    venta con los datos reales de la ficha, no recorte literal). Si no se
    pasa, cae al recorte automatico de la descripcion de la ficha (ver
    armar_guion). Camino preferido: pasar siempre `cuerpo_manual`.

    Lanza ErrorRecurso si falta la clave en .env o ElevenLabs devuelve error.

    NO se prueba con la API real en unit tests; se verifica a mano/CLI."""
    voz = elegir_voz(indice_producto)
    guion = armar_guion(datos, PRESUPUESTO_CARACTERES_DEFECTO, cuerpo_manual)
    audio_bytes = _sintetizar_voz(guion, voz)

    ruta_salida = Path(ruta_salida)
    temporal = ruta_salida.with_name(
        ruta_salida.stem + ".tmp" + ruta_salida.suffix
    )
    try:
        temporal.write_bytes(audio_bytes)
        os.replace(temporal, ruta_salida)
    finally:
        temporal.unlink(missing_ok=True)
    return ruta_salida


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
    test_voz_en_off.py, que solo cubre elegir_voz/armar_guion."""
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


def factor_estiramiento(duracion_clip: float, duracion_voz: float) -> float:
    """Factor de slow-motion (para el filtro `setpts` de ffmpeg) que hace
    falta para que un clip de duracion_clip segundos pase a durar
    duracion_voz segundos. > 1.0 = mas lento (mas largo), <= 1.0 = no hace
    falta estirar (el clip ya alcanza o sobra).

    Logica pura, sin ffmpeg: es la parte testeable por unit test; la corrida
    real de setpts/atempo se verifica a mano/CLI en
    preparar_clip_con_voz."""
    if duracion_clip <= 0:
        raise ValueError("duracion_clip tiene que ser mayor a 0.")
    return max(1.0, duracion_voz / duracion_clip)


def _cadena_atempo(factor: float) -> str:
    """Arma la cadena de filtros `atempo` de ffmpeg equivalente a aplicar
    `factor` de una sola vez, encadenando varios pasos porque atempo solo
    acepta un rango de 0.5 a 2.0 por filtro. `factor` aca es el factor de
    VELOCIDAD del audio (inverso del factor de estiramiento: estirar el
    video al doble de duracion equivale a tocar el audio a mitad de
    velocidad, atempo=0.5).

    Si factor queda fuera de lo que un numero razonable de pasos de atempo
    puede cubrir en el rango 0.5-2.0 (estiramientos extremos), se encadena
    igual con el minimo de pasos necesario: queda documentado como
    limitacion conocida (ver docstring de preparar_clip_con_voz), no se
    inventa un filtro alternativo. Logica pura: no ejecuta ffmpeg."""
    if factor <= 0:
        raise ValueError("factor tiene que ser mayor a 0.")
    pasos = []
    restante = factor
    # Cada paso de atempo cubre como mucho 0.5x (achicar) o 2.0x (agrandar).
    # Se encadenan pasos de 0.5 (o 2.0) hasta que lo que falta entre ya en
    # un solo paso.
    while restante < 0.5:
        pasos.append(0.5)
        restante /= 0.5
    while restante > 2.0:
        pasos.append(2.0)
        restante /= 2.0
    pasos.append(restante)
    return ",".join(f"atempo={p}" for p in pasos)


def preparar_clip_con_voz(ruta_clip_normalizado: Path, ruta_voz: Path,
                          ruta_salida: Path,
                          permitir_estirar: bool = False) -> Path:
    """Recorta ruta_clip_normalizado a la duracion exacta de ruta_voz y
    mezcla su audio original (silenciado, VOLUMEN_AMBIENTE=0.0) con la
    voz a volumen normal. Guarda el resultado (mp4, video+audio mezclado) en
    ruta_salida y devuelve ruta_salida. Guardado atomico.

    Si el clip es MAS CORTO que la voz:
    - permitir_estirar=False (default, mismo comportamiento de siempre): se
      lanza ErrorRecurso dejando constancia clara de cuanto falta. No se
      inventa una solucion de loop/freeze-frame.
    - permitir_estirar=True: en vez de fallar, se alarga el clip con
      slow-motion (filtro `setpts` de ffmpeg) hasta que dure exactamente lo
      mismo que la voz (pedido explicito de Angie: "ponerlo mas lento para
      que encaje con el tiempo de la voz" cuando no hay un segundo clip para
      unir). El audio ORIGINAL del clip (el ambiente, no la voz) se estira
      en el mismo factor con `atempo` para que no se desincronice del video;
      la voz nunca se toca, siempre suena a velocidad normal. atempo solo
      acepta un rango de 0.5-2.0 por filtro: para factores fuera de ese
      rango se encadenan varios `atempo` seguidos (ver _cadena_atempo). Esto
      tiene un limite practico: estiramientos muy extremos (clip muchisimo
      mas corto que la voz) igual se resuelven encadenando pasos, pero el
      resultado de audio de ambiente a velocidades muy alejadas de 1.0
      degrada en calidad -- limitacion conocida, no resuelta por este
      cambio.

    Lanza ErrorRecurso si ffmpeg/ffprobe no estan disponibles, algun archivo
    de entrada no existe, el clip no alcanza (con permitir_estirar=False), o
    ffmpeg falla al mezclar/estirar.

    NO se prueba con ffmpeg real en unit tests; se verifica a mano/CLI."""
    _verificar_herramientas()
    ruta_clip_normalizado = Path(ruta_clip_normalizado)
    ruta_voz = Path(ruta_voz)
    if not ruta_clip_normalizado.is_file():
        raise ErrorRecurso(f"no existe el clip '{ruta_clip_normalizado}'.")
    if not ruta_voz.is_file():
        raise ErrorRecurso(f"no existe la voz '{ruta_voz}'.")

    duracion_voz = _duracion_segundos(ruta_voz)
    duracion_clip = _duracion_segundos(ruta_clip_normalizado)
    if duracion_clip < duracion_voz and not permitir_estirar:
        raise ErrorRecurso(
            f"el clip '{ruta_clip_normalizado}' dura {duracion_clip:.1f}s "
            f"pero la voz dura {duracion_voz:.1f}s: EL CLIP NO ALCANZA para "
            "cubrir toda la narracion. Hace falta un clip mas largo (no se "
            "resuelve con loop/freeze-frame por ahora)."
        )

    estirar = duracion_clip < duracion_voz  # ya se sabe permitir_estirar=True
    factor = factor_estiramiento(duracion_clip, duracion_voz) if estirar else 1.0

    ruta_salida = Path(ruta_salida)
    temporal = ruta_salida.with_name(
        ruta_salida.stem + ".tmp" + ruta_salida.suffix
    )
    # [0:a] = audio original del clip, silenciado (VOLUMEN_AMBIENTE=0.0) y
    # estirado si hace falta; [1:a] = la voz, normalizada a sonoridad fija
    # con loudnorm (ver LOUDNORM_VOZ_I/TP) en vez de un factor `volume=` fijo
    # -- distintas voces/textos de ElevenLabs salen de la sintesis a niveles
    # muy distintos (verificado: Carlos a -33dB, Gonzalo a -17dB de promedio
    # crudo), asi que un mismo multiplicador satura una y deja floja la otra.
    # amix con duration=first porque el video ya se recorta (-t duracion_voz)
    # a la duracion de la voz. normalize=0 es necesario: sin el, amix baja
    # TODOS los inputs (la voz incluida) para que la suma no sature, aunque
    # el ambiente ya este en silencio -- eso fue lo que dejaba la voz mas
    # floja de lo esperado.
    filtro_loudnorm_voz = (
        f"loudnorm=I={LOUDNORM_VOZ_I}:TP={LOUDNORM_VOZ_TP}:LRA=11"
    )
    if estirar:
        cadena_atempo = _cadena_atempo(1 / factor)
        filtro_video = f"[0:v]setpts={factor}*PTS[video_final]"
        filtro_audio = (
            f"[0:a]{cadena_atempo},volume={VOLUMEN_AMBIENTE}[ambiente];"
            f"[1:a]{filtro_loudnorm_voz}[voz];"
            "[ambiente][voz]amix=inputs=2:duration=first:dropout_transition=0"
            ":normalize=0[audio_final]"
        )
        filtro_complejo = f"{filtro_video};{filtro_audio}"
        mapa_video = "[video_final]"
    else:
        filtro_complejo = (
            f"[0:a]volume={VOLUMEN_AMBIENTE}[ambiente];"
            f"[1:a]{filtro_loudnorm_voz}[voz];"
            "[ambiente][voz]amix=inputs=2:duration=first:dropout_transition=0"
            ":normalize=0[audio_final]"
        )
        mapa_video = "0:v"
    comando = ["ffmpeg", "-y"]
    if not estirar:
        # Sin estirar, el clip alcanza y sobra: recortar el INPUT a
        # duracion_voz evita decodificar de mas (no hace falta si se va a
        # estirar: ahi el filtro setpts necesita el clip completo).
        comando += ["-t", str(duracion_voz)]
    comando += [
        "-i", str(ruta_clip_normalizado),
        "-i", str(ruta_voz),
        "-filter_complex", filtro_complejo,
        "-map", mapa_video, "-map", "[audio_final]",
        "-t", str(duracion_voz),
        "-c:v", "libx264", "-crf", "19", "-preset", "fast",
        "-c:a", "aac",
        str(temporal),
    ]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0:
            raise ErrorRecurso(
                f"ffmpeg fallo al mezclar voz+clip: "
                f"{resultado.stderr.strip()[-800:]}"
            )
        os.replace(temporal, ruta_salida)
    finally:
        temporal.unlink(missing_ok=True)
    return ruta_salida


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Genera la voz en off (ElevenLabs) de un producto a "
        "partir de su ficha, alternando entre las voces carlos/gonzalo segun "
        "el indice del producto en el lote."
    )
    parser.add_argument("ruta_ficha", help="ruta al .json de la ficha")
    parser.add_argument("--salida", default=None,
                        help="ruta de salida (default: <ficha>_voz.mp3)")
    parser.add_argument("--indice", type=int, default=0,
                        help="indice del producto en el lote (alterna la voz)")
    parser.add_argument("--cuerpo-archivo", default=None,
                        help="archivo .txt con el guion redactado a mano "
                        "(copy de venta); si se pasa, no se recorta la "
                        "descripcion de la ficha, se usa este texto tal cual")
    args = parser.parse_args()

    ruta_ficha = Path(args.ruta_ficha).resolve()
    if not ruta_ficha.is_file():
        print(f"ERROR DE ARCHIVO: no existe la ficha '{ruta_ficha}'.")
        sys.exit(2)
    try:
        datos = json.loads(ruta_ficha.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"ERROR DE ARCHIVO: '{ruta_ficha}' no es JSON valido ({error}).")
        sys.exit(2)

    cuerpo_manual = None
    if args.cuerpo_archivo:
        ruta_cuerpo = Path(args.cuerpo_archivo).resolve()
        if not ruta_cuerpo.is_file():
            print(f"ERROR DE ARCHIVO: no existe '{ruta_cuerpo}'.")
            sys.exit(2)
        cuerpo_manual = ruta_cuerpo.read_text(encoding="utf-8")

    ruta_salida = Path(args.salida).resolve() if args.salida else \
        ruta_ficha.with_name(ruta_ficha.stem + "_voz.mp3")

    try:
        generar_a_archivo(datos, ruta_salida, indice_producto=args.indice,
                          cuerpo_manual=cuerpo_manual)
    except ErrorRecurso as error:
        print(f"ERROR DE ARCHIVO: {error}")
        sys.exit(2)

    print(f"VOZ GENERADA: {ruta_salida}  (voz: {elegir_voz(args.indice)})")


if __name__ == "__main__":
    main()
