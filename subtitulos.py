"""Subtitulos quemados sobre el clip con voz (etapa Imagenes/Video).

Alinea el AUDIO real de la voz en off contra el TEXTO EXACTO que se le paso a
ElevenLabs (forced alignment: "en que segundo se dijo cada palabra"), agrupa
esas palabras en lineas cortas legibles, y las quema sobre el video con
ffmpeg -- una capa `drawtext` por linea, cada una visible solo en su rango de
tiempo (filtro `enable='between(t,inicio,fin)'`).

Por que drawtext y no el filtro `subtitles` (libass): se probo primero con
`subtitles`+`force_style` para poner la tipografia Montserrat y el contorno
naranja de marca (pedido de Angie, 6-ago-2026), pero en Windows libass resuelve
las fuentes contra el proveedor del sistema (DirectWrite/GDI) -- fontsdir,
instalar la fuente para el usuario e incluso registrarla en caliente con
AddFontResourceEx no alcanzaron: se verifico comparando pixel a pixel dos
renders (FontName=Montserrat vs FontName=Arial) y salieron IDENTICOS, o sea
force_style ignoraba el nombre de fuente en silencio y siempre caia a Arial
(FontSize si se aplicaba, confirmado con el mismo metodo -- el problema es
puntual del nombre de fuente, no de force_style en general). `drawtext` con
`fontfile=` carga el .ttf directo por FreeType, sin pasar por el proveedor de
fuentes del sistema: no depende de que la fuente este instalada ni de que el
cache de fuentes de Windows se haya refrescado.

Por que forced alignment y no medir el texto "a ojo": el guion real (ver
voz_en_off.armar_guion) no se lee a velocidad constante -- ElevenLabs no
reparte el tiempo por caracter de forma pareja -- asi que estimar los tiempos
dividiendo la duracion del audio entre la cantidad de caracteres desincroniza
el subtitulo cada vez mas a medida que avanza el video. La API de
forced_alignment de ElevenLabs (cliente.forced_alignment.create) devuelve la
marca de tiempo real de cada palabra a partir del audio ya generado, asi que
el subtitulo queda sincronizado con lo que efectivamente se escucha.

IMPORTANTE: el texto que se pasa a alinear_audio() tiene que ser el mismo
string EXACTO que se le paso a voz_en_off.generar_a_archivo() como
cuerpo_manual (envuelto en armar_guion con las FRASE_FIJA de apertura/cierre):
si el texto no coincide con lo que efectivamente se dijo, la alineacion sale
mal (la API alinea contra el texto que se le da, no contra lo que "cree" que
se dijo).

Uso:  python subtitulos.py <video_con_voz.mp4> <voz.mp3> <guion.txt>
      [--salida salida.mp4]

Codigos de salida: 0 = video con subtitulos generado; 2 = problema de recurso
(clave de ElevenLabs faltante, archivos de entrada faltantes/ilegibles, o
ElevenLabs/ffmpeg fallan).
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

# Cantidad de palabras por linea de subtitulo. Un piso de 3 evita lineas de
# una sola palabra (se leen como un volcado tecnico, no como un subtitulo);
# un techo de 6 evita el otro extremo, el parrafo entero pegado en pantalla.
# Calibrado a ojo (pedido de Angie: "que se vea como un subtitulo real de
# video"), no hay una cifra oficial de la industria que aplique aca.
PALABRAS_MIN_POR_LINEA = 3
PALABRAS_MAX_POR_LINEA = 6

# Estilo del filtro `drawtext` (uno por linea, ver quemar_subtitulos). Fuente
# Montserrat cargada directo del archivo (ver comentario arriba sobre por que
# no se usa `subtitles`+force_style) y contorno naranja de marca (mismo
# #FF4E03 que generador_portada.py) para sostener la identidad visual --
# pedido de Angie, 6-ago-2026. Texto blanco legible sobre cualquier fondo,
# sombra suave detras del contorno. Tamano y margen inferior calibrados a ojo
# contra un frame real (mismo criterio que generador_portada.py).
RUTA_FUENTE_SUBTITULOS = CARPETA_PROYECTO / "fonts" / "Montserrat-Regular.ttf"

# El build de ffmpeg de este equipo trae fontconfig habilitado, y el filtro
# `drawtext` lo consulta (via harfbuzz) para resolver familias genericas
# ("Sans") aunque se le de `fontfile=` explicito. Se probaron dos fallas
# reales en orden: (1) sin NINGUN fonts.conf, ffmpeg se cae (access
# violation, verificado corriendo el comando a mano); (2) con un fonts.conf
# VACIO ya no se cae, pero falla con "Cannot find a valid font for the
# family Sans" porque no hay ninguna fuente registrada para resolver ese
# fallback. quemar_subtitulos arma esta config al vuelo (registrando la
# fuente y el alias Sans/sans-serif -> Montserrat) en la carpeta temporal
# de cada corrida -- no es un archivo fijo del repo porque tiene que vivir
# en una ruta sin tildes (ver docstring de _construir_filtro_drawtext).
COLOR_BORDE_SUBTITULOS = "0xFF4E03"
TAMANO_FUENTE_SUBTITULOS = 54
GROSOR_BORDE_SUBTITULOS = 4
MARGEN_INFERIOR_SUBTITULOS = 160


class ErrorRecurso(Exception):
    """No se pudo generar el video con subtitulos (clave de ElevenLabs
    faltante, archivos de entrada faltantes/ilegibles, o ElevenLabs/ffmpeg
    fallidos). Se traduce a un mensaje claro y salida 2, no a un
    traceback."""


def _verificar_herramientas() -> None:
    """Confirma que ffmpeg esta en el PATH antes de usarlo, para dar un
    mensaje claro en vez de un traceback de FileNotFoundError. (No hace falta
    ffprobe aca: este modulo no necesita medir dimensiones/duracion, solo
    quemar el filtro de subtitulos.)"""
    if shutil.which("ffmpeg") is None:
        raise ErrorRecurso(
            "no se encontro ffmpeg en el PATH del sistema. Instalalo (ej. "
            "'winget install ffmpeg') y volve a intentar."
        )


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


def alinear_audio(ruta_audio: Path, texto: str) -> list[dict]:
    """Llama a forced_alignment.create() de ElevenLabs con el audio real y el
    TEXTO EXACTO que se le paso a la sintesis, y devuelve la lista de
    palabras alineadas como dicts {"texto": str, "inicio": float,
    "fin": float} (segundos desde el arranque del audio).

    La respuesta real de la API (ForcedAlignmentResponseModel) trae ademas
    `characters` (alineacion por caracter) y `loss` (confianza global); este
    modulo solo necesita `words` para armar lineas de subtitulo, asi que el
    resto no se expone.

    Lanza ErrorRecurso si falta la clave o la API devuelve error.

    NO se prueba con la API real en unit tests (llamada de red paga): se
    verifica a mano/CLI contra una ficha real, igual que el resto de los
    modulos de este proyecto que dependen de servicios externos."""
    if not ruta_audio.is_file():
        raise ErrorRecurso(f"no existe el archivo de audio '{ruta_audio}'.")
    clave = _clave_api()
    try:
        from elevenlabs.client import ElevenLabs

        from resolucion_dns import forzar_ipv4
        cliente = ElevenLabs(api_key=clave)
        with forzar_ipv4(), open(ruta_audio, "rb") as archivo_audio:
            respuesta = cliente.forced_alignment.create(
                file=archivo_audio, text=texto
            )
    except ErrorRecurso:
        raise
    except Exception as error:  # el SDK de ElevenLabs lanza distintos tipos
        raise ErrorRecurso(
            f"ElevenLabs fallo al alinear el audio: {error}"
        ) from error
    return [
        {"texto": palabra.text, "inicio": palabra.start, "fin": palabra.end}
        for palabra in respuesta.words
    ]


def agrupar_palabras_en_lineas(
    palabras: list[dict],
    minimo: int = PALABRAS_MIN_POR_LINEA,
    maximo: int = PALABRAS_MAX_POR_LINEA,
) -> list[dict]:
    """Agrupa la lista plana de palabras alineadas en lineas de subtitulo de
    `minimo` a `maximo` palabras cada una, devolviendo dicts {"texto": str,
    "inicio": float, "fin": float} (inicio de la primera palabra del grupo,
    fin de la ultima).

    Reglas de corte (en este orden de prioridad):
    1. Nunca mas de `maximo` palabras en una linea.
    2. Si ya hay al menos `minimo` palabras y la palabra actual termina una
       oracion (., ! o ?), se cierra la linea ahi -- los cortes coinciden con
       pausas naturales del habla en vez de caer a mitad de idea.
    3. El resto final de palabras (menos de `minimo`) se funde con la linea
       anterior en vez de quedar como una linea huerfana de 1-2 palabras
       sueltas al final.

    Logica pura, sin red ni ffmpeg: es la parte testeable por unit test
    (ver test_subtitulos.py, con una alineacion fabricada a mano)."""
    if not palabras:
        return []

    lineas: list[list[dict]] = []
    actual: list[dict] = []
    for palabra in palabras:
        actual.append(palabra)
        texto_palabra = palabra["texto"].strip()
        termina_oracion = bool(texto_palabra) and texto_palabra[-1] in ".!?"
        if len(actual) >= maximo or (len(actual) >= minimo and termina_oracion):
            lineas.append(actual)
            actual = []

    if actual:
        if lineas and len(actual) < minimo:
            lineas[-1] = lineas[-1] + actual
        else:
            lineas.append(actual)

    return [
        {
            "texto": " ".join(p["texto"] for p in grupo).strip(),
            "inicio": grupo[0]["inicio"],
            "fin": grupo[-1]["fin"],
        }
        for grupo in lineas
    ]


def _formato_tiempo_srt(segundos: float) -> str:
    """Convierte segundos (float) al formato de timestamp SRT
    HH:MM:SS,mmm. Logica pura: se prueba con unit tests."""
    if segundos < 0:
        segundos = 0.0
    milisegundos_totales = round(segundos * 1000)
    horas, resto = divmod(milisegundos_totales, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    seg, ms = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{seg:02d},{ms:03d}"


def armar_srt(lineas: list[dict]) -> str:
    """Arma el contenido completo de un archivo .srt (numerado desde 1, con
    linea en blanco entre bloques) a partir de la lista de lineas de
    subtitulo que devuelve agrupar_palabras_en_lineas(). Logica pura, sin
    disco: se prueba con unit tests."""
    bloques = []
    for numero, linea in enumerate(lineas, start=1):
        bloques.append(
            f"{numero}\n"
            f"{_formato_tiempo_srt(linea['inicio'])} --> "
            f"{_formato_tiempo_srt(linea['fin'])}\n"
            f"{linea['texto']}\n"
        )
    return "\n".join(bloques) + ("\n" if bloques else "")


def _escapar_ruta_para_filtro(ruta: Path) -> str:
    """Escapa una ruta de archivo para usarla dentro del argumento del
    filtro `subtitles=` de ffmpeg. El filtro parsea su propio argumento con
    reglas de libass: los dos puntos de la letra de unidad de Windows
    ("C:") y las barras invertidas rompen el parseo si no se escapan, y las
    comillas simples delimitan el valor completo del filtro. Se resuelve
    convirtiendo las barras invertidas a barras normales (ffmpeg las acepta
    en Windows) y escapando ":" como "\\:" -- el patron documentado para usar
    `subtitles=`/`ass=` con rutas absolutas de Windows."""
    texto = str(ruta).replace("\\", "/")
    return texto.replace(":", "\\:")


def _construir_filtro_drawtext(lineas: list[dict], carpeta_temp: Path,
                               ruta_fuente: Path) -> str:
    """Arma la cadena de filtros `drawtext` (uno por linea de subtitulo,
    encadenados con ',') a partir de `lineas` (ver agrupar_palabras_en_lineas).
    Cada linea se escribe a su propio archivo de texto en carpeta_temp y se
    referencia con `textfile=` en vez de `text=` inline -- asi el contenido
    real (que puede traer comas, dos puntos, comillas) nunca tiene que
    escaparse dentro del filtro: solo la RUTA del archivo, con las mismas
    reglas que _escapar_ruta_para_filtro ya usa para rutas de Windows.

    Cada drawtext queda activo solo en su rango de tiempo real
    (`enable='between(t,inicio,fin)'`), centrado horizontalmente segun el
    ancho real del texto (`x=(w-text_w)/2`) para que cada linea, sin importar
    su largo, quede centrada.

    `font='Montserrat'` va SIEMPRE junto a `fontfile=`, aunque parezca
    redundante: sin el, este build de ffmpeg (harfbuzz+fontconfig) intenta
    resolver una familia generica ("Sans") para el shaping del texto y falla
    con "Cannot find a valid font for the family Sans" -- verificado
    reproduciendo el error a mano. Dandole el nombre real de familia
    (registrado en fontconfig_minimo.conf, ver RUTA_FONTCONFIG_MINIMO) ese
    fallback nunca se dispara.

    `ruta_fuente` es la fuente YA COPIADA a carpeta_temp (ver
    quemar_subtitulos): la carpeta del proyecto tiene una tilde
    ("Catálogo") y se verifico que ese caracter le llega corrupto a
    ffmpeg/fontconfig en la ruta de `fontfile=`, haciendo que ni cargue el
    archivo ni resuelva la familia por nombre (mismo sintoma en ambos
    casos: "Cannot find a valid font"). La carpeta temporal del sistema
    (tempfile) no tiene tildes, asi que evita el problema de raiz en vez de
    andar escapando el caracter."""
    fuente_escapada = _escapar_ruta_para_filtro(ruta_fuente)
    filtros = []
    for indice, linea in enumerate(lineas):
        ruta_texto = carpeta_temp / f"linea_{indice:03d}.txt"
        ruta_texto.write_text(linea["texto"], encoding="utf-8")
        texto_escapado = _escapar_ruta_para_filtro(ruta_texto)
        filtros.append(
            f"drawtext=fontfile='{fuente_escapada}':font='Montserrat'"
            f":textfile='{texto_escapado}'"
            f":fontsize={TAMANO_FUENTE_SUBTITULOS}:fontcolor=white"
            f":bordercolor={COLOR_BORDE_SUBTITULOS}:borderw={GROSOR_BORDE_SUBTITULOS}"
            ":shadowcolor=black@0.6:shadowx=2:shadowy=2:box=0"
            ":x=(w-text_w)/2"
            f":y=h-text_h-{MARGEN_INFERIOR_SUBTITULOS}"
            f":enable='between(t,{linea['inicio']:.3f},{linea['fin']:.3f})'"
        )
    return ",".join(filtros)


def quemar_subtitulos(ruta_video: Path, lineas: list[dict],
                      ruta_salida: Path) -> Path:
    """Quema `lineas` (ver agrupar_palabras_en_lineas) sobre ruta_video con
    una cadena de filtros `drawtext` (ver _construir_filtro_drawtext) y
    guarda el resultado en ruta_salida. Devuelve ruta_salida. Guardado
    atomico (temporal + os.replace).

    Lanza ErrorRecurso si ffmpeg no esta disponible, el video de entrada no
    existe, o ffmpeg falla al quemar el filtro.

    NO se prueba con ffmpeg real en unit tests (herramienta externa pesada);
    la corrida real se verifica a mano/CLI, igual que marca_agua.py y
    preparar_video_producto.py."""
    _verificar_herramientas()
    ruta_video = Path(ruta_video)
    if not ruta_video.is_file():
        raise ErrorRecurso(f"no existe el video '{ruta_video}'.")
    if not RUTA_FUENTE_SUBTITULOS.is_file():
        raise ErrorRecurso(
            f"no existe la fuente de subtitulos '{RUTA_FUENTE_SUBTITULOS}'."
        )

    ruta_salida = Path(ruta_salida)
    temporal = ruta_salida.with_name(
        ruta_salida.stem + ".tmp" + ruta_salida.suffix
    )
    with tempfile.TemporaryDirectory() as carpeta_temp_str:
        carpeta_temp = Path(carpeta_temp_str)
        # La fuente y la config de fontconfig se copian a la carpeta
        # temporal del SISTEMA (sin tildes) en vez de usarse desde
        # 'fonts/' dentro del proyecto: se verifico que la tilde de
        # 'Catálogo' en la ruta del proyecto llega corrupta a
        # ffmpeg/fontconfig y rompe la carga de la fuente (ver docstring
        # de _construir_filtro_drawtext).
        ruta_fuente_temp = carpeta_temp / RUTA_FUENTE_SUBTITULOS.name
        shutil.copyfile(RUTA_FUENTE_SUBTITULOS, ruta_fuente_temp)
        ruta_fuente_temp_escapada = _escapar_ruta_para_filtro(carpeta_temp)
        ruta_cache_temp = carpeta_temp / "cache_fontconfig"
        ruta_cache_temp.mkdir()
        ruta_conf_temp = carpeta_temp / "fontconfig.conf"
        ruta_conf_temp.write_text(
            "<?xml version=\"1.0\"?>\n"
            "<!DOCTYPE fontconfig SYSTEM \"fonts.dtd\">\n"
            "<fontconfig>\n"
            f"  <dir>{ruta_fuente_temp_escapada}</dir>\n"
            f"  <cachedir>{_escapar_ruta_para_filtro(ruta_cache_temp)}</cachedir>\n"
            "  <alias><family>Sans</family>"
            "<prefer><family>Montserrat</family></prefer></alias>\n"
            "  <alias><family>sans-serif</family>"
            "<prefer><family>Montserrat</family></prefer></alias>\n"
            "</fontconfig>\n",
            encoding="utf-8",
        )

        filtro = _construir_filtro_drawtext(lineas, carpeta_temp, ruta_fuente_temp)
        comando = [
            "ffmpeg", "-y",
            "-i", str(ruta_video),
            "-vf", filtro,
            "-c:v", "libx264", "-crf", "19", "-preset", "fast",
            "-c:a", "copy",
            str(temporal),
        ]
        entorno = os.environ.copy()
        entorno["FONTCONFIG_FILE"] = str(ruta_conf_temp)
        try:
            resultado = subprocess.run(
                comando, capture_output=True, text=True, env=entorno
            )
            if resultado.returncode != 0:
                raise ErrorRecurso(
                    f"ffmpeg fallo al quemar los subtitulos sobre "
                    f"'{ruta_video}': {resultado.stderr.strip()[-800:]}"
                )
            os.replace(temporal, ruta_salida)
        finally:
            temporal.unlink(missing_ok=True)
    return ruta_salida


def generar_a_archivo(ruta_video_con_voz: Path, ruta_voz_mp3: Path,
                      texto_guion: str, ruta_salida: Path) -> Path:
    """Encadena el modulo completo: alinea el audio contra texto_guion,
    arma las lineas de subtitulo, guarda un .srt temporal, y lo quema sobre
    ruta_video_con_voz. Guarda el resultado final en ruta_salida y la
    devuelve.

    texto_guion tiene que ser el string EXACTO que se le paso a
    voz_en_off.generar_a_archivo() (el guion completo, con las FRASE_FIJA de
    apertura/cierre ya incluidas) -- es el mismo texto que efectivamente se
    sintetizo en ruta_voz_mp3, y por lo tanto el que hay que alinear.

    Lanza ErrorRecurso si falta la clave de ElevenLabs, algun archivo de
    entrada no existe, o ElevenLabs/ffmpeg fallan."""
    ruta_video_con_voz = Path(ruta_video_con_voz)
    ruta_voz_mp3 = Path(ruta_voz_mp3)
    ruta_salida = Path(ruta_salida)

    palabras = alinear_audio(ruta_voz_mp3, texto_guion)
    lineas = agrupar_palabras_en_lineas(palabras)
    quemar_subtitulos(ruta_video_con_voz, lineas, ruta_salida)
    return ruta_salida


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Alinea la voz en off con el guion real (ElevenLabs "
        "forced alignment), arma un .srt y lo quema sobre el video con voz."
    )
    parser.add_argument("video", help="clip de video con voz ya mezclada (mp4)")
    parser.add_argument("voz", help="audio de la voz en off (mp3)")
    parser.add_argument("guion", help="archivo .txt con el guion EXACTO que "
                        "se le paso a ElevenLabs para generar `voz`")
    parser.add_argument("--salida", default=None,
                        help="ruta de salida (default: <video>_subtitulos.mp4)")
    args = parser.parse_args()

    ruta_video = Path(args.video).resolve()
    ruta_voz = Path(args.voz).resolve()
    ruta_guion = Path(args.guion).resolve()
    if not ruta_video.is_file():
        print(f"ERROR DE ARCHIVO: no existe el video '{ruta_video}'.")
        sys.exit(2)
    if not ruta_voz.is_file():
        print(f"ERROR DE ARCHIVO: no existe la voz '{ruta_voz}'.")
        sys.exit(2)
    if not ruta_guion.is_file():
        print(f"ERROR DE ARCHIVO: no existe el guion '{ruta_guion}'.")
        sys.exit(2)
    texto_guion = ruta_guion.read_text(encoding="utf-8")

    ruta_salida = Path(args.salida).resolve() if args.salida else \
        ruta_video.with_name(ruta_video.stem + "_subtitulos.mp4")

    try:
        generar_a_archivo(ruta_video, ruta_voz, texto_guion, ruta_salida)
    except ErrorRecurso as error:
        print(f"ERROR DE ARCHIVO: {error}")
        sys.exit(2)

    print(f"VIDEO CON SUBTITULOS: {ruta_salida}")


if __name__ == "__main__":
    main()
