"""Subida del video de producto al canal de YouTube de Ekipon.

Decision de Angie (11-ago-2026): en vez de subir el mp4 crudo directo a la
mediateca de WordPress (lo que ya funcionaba, ver publicador._adjuntar_video),
el video sube a su canal de YouTube (ya existente) y el producto muestra ese
video EMBEBIDO en la descripcion (ver publicador.generar_descripcion_html).
Motivo doble: ahorrar espacio/ancho de banda del hosting de la tienda, y sumar
valor de marketing (el video tambien queda visible en el canal).

Este modulo tiene DOS caminos separados a proposito:

1. `autorizar()` -- flujo OAuth interactivo, DE UNA SOLA VEZ, A MANO. Abre el
   navegador de Angie para que inicie sesion y apruebe el permiso; guarda el
   resultado (con refresh_token) en token_youtube.json. Se corre aparte, NUNCA
   como parte de una corrida automatica del pipeline:

       python youtube_uploader.py --autorizar

   Las corridas siguientes se refrescan solas con el refresh_token guardado
   -- no hace falta repetir este paso salvo que Angie revoque el permiso o se
   borre token_youtube.json.

2. `subir_video()` -- la subida real, pensada para correr DENTRO del pipeline
   automatico (ver orquestador.py). Nunca abre un navegador ella sola: si no
   hay un token utilizable todavia, lanza ErrorRecurso con instrucciones claras
   en vez de colgarse esperando una interaccion humana que no existe en una
   corrida de servidor sin supervision.

`disponible()` es el chequeo liviano (sin llamar a la API real) que usa
orquestador.py para decidir si intenta YouTube o cae al camino de siempre
(subida directa a WordPress, ver publicador._adjuntar_video) -- asi nada de lo
que ya funciona hoy se rompe para quien no haya hecho el tramite de YouTube.

Cupo de la API (dejarlo DOCUMENTADO, no hay forma de "ahorrar" del lado
nuestro): la cuota por defecto de la YouTube Data API v3 es 10.000
unidades/dia, y video.insert() cuesta 1.600 unidades -- o sea, un maximo de
~6 subidas por dia salvo que Angie le pida a Google mas cupo (tramite de
revision de Google, no es instantaneo). Si el cupo se agota, subir_video()
lanza ErrorRecurso con el error real de la API; el orquestador cae al camino
de WordPress de siempre en vez de tumbar la corrida.

Privacidad: los videos suben como PUBLICOS (privacyStatus="public") --
decision ya tomada por Angie, cualquiera los puede encontrar buscando en
YouTube.

Credenciales (NUNCA se leen ni se imprimen en ningun log/reporte):
  credenciales_youtube.json -- credencial OAuth "Aplicacion de escritorio"
    descargada de Google Cloud Console (proyecto "Ekipon Videos"). Gitignored.
  token_youtube.json -- token de acceso + refresh_token que genera autorizar()
    la primera vez. Gitignored. Se regenera solo con el refresh_token.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CARPETA_PROYECTO = Path(__file__).parent
RUTA_CREDENCIALES_DEFECTO = CARPETA_PROYECTO / "credenciales_youtube.json"
RUTA_TOKEN_DEFECTO = CARPETA_PROYECTO / "token_youtube.json"

# Scope minimo necesario para subir videos (no pide lectura del canal ni de
# analiticas, que no hacen falta aca).
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CATEGORIA_YOUTUBE_HERRAMIENTAS_Y_BRICOLAJE = "26"  # "Howto & Style"


class ErrorRecurso(Exception):
    """No se pudo subir el video a YouTube (todavia no se autorizo el acceso,
    el token quedo invalido, o la API de YouTube devolvio un error real --
    cuota agotada, red caida, etc.). Se traduce a un mensaje claro en
    español, nunca a un traceback crudo."""


def autorizar(ruta_credenciales: Path = RUTA_CREDENCIALES_DEFECTO,
              ruta_token: Path = RUTA_TOKEN_DEFECTO) -> None:
    """Flujo de autorizacion OAuth interactivo, DE UNA SOLA VEZ.

    Abre el navegador del sistema (via webbrowser.open(), que delega al SO --
    no lanza un proceso GUI propio como Playwright, no deberia toparse con el
    problema de "spawn UNKNOWN" que dio Chromium headed en Windows) para que
    Angie inicie sesion con la cuenta de YouTube y apruebe el permiso de
    subida. Al aprobar, guarda las credenciales resultantes (con el
    refresh_token) en ruta_token -- las corridas siguientes de subir_video()
    las reusan y se refrescan solas, sin volver a pedir autorizacion.

    Se corre A MANO, nunca como parte del pipeline automatico:

        python youtube_uploader.py --autorizar

    Lanza ErrorRecurso si no encuentra credenciales_youtube.json (el tramite
    de Google Cloud todavia no se hizo) o si las librerias de Google no estan
    instaladas (falta 'pip install -r requirements.txt'). El chequeo del
    archivo va ANTES del import de la libreria a proposito: da un mensaje
    util aunque todavia no se haya corrido 'pip install'."""
    if not ruta_credenciales.is_file():
        raise ErrorRecurso(
            f"no encuentro '{ruta_credenciales.name}' en la carpeta del "
            "proyecto. Hace falta la credencial OAuth de tipo 'Aplicacion de "
            "escritorio' descargada de Google Cloud Console (proyecto "
            "'Ekipon Videos')."
        )
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as error:
        raise ErrorRecurso(
            "faltan las librerias de Google (google-auth-oauthlib): corre "
            "'pip install -r requirements.txt'."
        ) from error
    flow = InstalledAppFlow.from_client_secrets_file(str(ruta_credenciales), SCOPES)
    credenciales = flow.run_local_server(port=0)
    ruta_token.write_text(credenciales.to_json(), encoding="utf-8")
    print(f"Autorizacion guardada en '{ruta_token}'. Ya podes correr subir_video().")


def disponible(ruta_token: Path = RUTA_TOKEN_DEFECTO) -> bool:
    """True si ruta_token existe y tiene pinta de traer un refresh_token
    utilizable. Chequeo LIVIANO a proposito: NO llama a la API real (eso lo
    hace subir_video() cuando de verdad hace falta). Es lo que usa
    orquestador.py para decidir si intenta YouTube o cae al camino de
    siempre (subida directa a WordPress)."""
    if not ruta_token.is_file():
        return False
    try:
        datos = json.loads(ruta_token.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(datos, dict):
        return False
    return bool(str(datos.get("refresh_token") or "").strip())


def _credenciales_utilizables(ruta_token: Path):
    """Carga y (si hace falta) refresca las credenciales guardadas. Lanza
    ErrorRecurso con un mensaje claro si todavia no se autorizo el acceso o
    el token quedo invalido sin refresh_token que lo salve. NUNCA abre un
    navegador -- eso es trabajo exclusivo de autorizar(), a mano.

    El chequeo de disponible() va ANTES del import de las librerias de
    Google a proposito: da el mensaje util ("corre --autorizar primero") sin
    depender de si 'pip install -r requirements.txt' ya se corrio."""
    if not disponible(ruta_token):
        raise ErrorRecurso(
            "todavia no se autorizo el acceso a YouTube, corre "
            "'python youtube_uploader.py --autorizar' primero."
        )
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as error:
        raise ErrorRecurso(
            "faltan las librerias de Google (google-auth): corre "
            "'pip install -r requirements.txt'."
        ) from error
    credenciales = Credentials.from_authorized_user_file(str(ruta_token), SCOPES)
    if not credenciales.valid:
        if credenciales.expired and credenciales.refresh_token:
            try:
                credenciales.refresh(Request())
            except Exception as error:
                raise ErrorRecurso(
                    "el acceso a YouTube quedo invalido y no se pudo "
                    f"refrescar ({error}). Corre "
                    "'python youtube_uploader.py --autorizar' de nuevo."
                ) from error
            ruta_token.write_text(credenciales.to_json(), encoding="utf-8")
        else:
            raise ErrorRecurso(
                "el acceso a YouTube quedo invalido. Corre "
                "'python youtube_uploader.py --autorizar' de nuevo."
            )
    return credenciales


def subir_video(ruta_video: Path, titulo: str, descripcion: str,
                 tags: list[str] | None = None,
                 ruta_token: Path = RUTA_TOKEN_DEFECTO) -> dict:
    """Sube ruta_video al canal de YouTube autorizado, como PUBLICO (decision
    ya tomada por Angie). Devuelve {"video_id": ..., "url": ...}.

    Lanza ErrorRecurso si: no existe ruta_video, todavia no se autorizo el
    acceso (ver autorizar()), o la API de YouTube devuelve un error real
    (cuota agotada -- ver el limite documentado arriba del modulo --, video
    invalido, red caida, etc.). NUNCA abre un navegador: en medio de una
    corrida automatica del pipeline eso la rompería sin supervision."""
    ruta_video = Path(ruta_video)
    if not ruta_video.is_file():
        raise ErrorRecurso(f"no existe el archivo de video '{ruta_video}'.")
    # Las credenciales se resuelven ANTES de importar googleapiclient a
    # proposito: si todavia no se autorizo el acceso, el mensaje es
    # "corre --autorizar primero" (el error util), no un mensaje de libreria
    # faltante que tape la causa real.
    credenciales = _credenciales_utilizables(ruta_token)
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError as error:
        raise ErrorRecurso(
            "faltan las librerias de Google (google-api-python-client): "
            "corre 'pip install -r requirements.txt'."
        ) from error

    youtube = build("youtube", "v3", credentials=credenciales)
    cuerpo = {
        "snippet": {
            "title": titulo,
            "description": descripcion,
            "tags": tags or [],
            "categoryId": CATEGORIA_YOUTUBE_HERRAMIENTAS_Y_BRICOLAJE,
        },
        "status": {"privacyStatus": "public"},
    }
    media = MediaFileUpload(str(ruta_video), chunksize=-1, resumable=True)
    try:
        peticion = youtube.videos().insert(
            part="snippet,status", body=cuerpo, media_body=media,
        )
        respuesta = peticion.execute()
    except HttpError as error:
        raise ErrorRecurso(f"la API de YouTube devolvio un error: {error}") from error
    video_id = respuesta.get("id")
    if not video_id:
        raise ErrorRecurso(
            "la API de YouTube no devolvio un id de video en la respuesta "
            f"({respuesta!r})."
        )
    return {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--autorizar", action="store_true",
        help="corre el flujo de autorizacion OAuth interactivo, una sola vez.",
    )
    args = parser.parse_args()
    if not args.autorizar:
        parser.print_help()
        return 1
    try:
        autorizar()
    except ErrorRecurso as error:
        print(f"ERROR: {error}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
