"""Pruebas de youtube_uploader.py. TODO OFFLINE a proposito:

- NUNCA se llama a InstalledAppFlow.run_local_server() real ni a la API real
  de YouTube: eso abriria un navegador real (se colgaria esperando una
  interaccion humana que no existe en este entorno) y gastaria cupo real de
  la API (ver el limite de 10.000 unidades/dia documentado en el modulo).
- Los tests que necesitan simular una respuesta exitosa de la API inyectan
  modulos FALSOS en sys.modules (google.oauth2.credentials,
  google.auth.transport.requests, googleapiclient.*) -- las librerias reales
  de Google no hace falta que esten instaladas para correr esta suite.
- token_youtube.json de prueba: SIEMPRE un archivo temporal con forma de
  token FALSO (nunca uno real ni las credenciales reales del repo).

Uso:  python -m unittest test_youtube_uploader -v
"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import youtube_uploader
from youtube_uploader import ErrorRecurso, disponible, subir_video


def _escribir_token(carpeta: Path, datos: dict) -> Path:
    ruta = carpeta / "token_youtube.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


class PruebasDisponible(unittest.TestCase):
    """disponible(): chequeo liviano, sin red ni API real."""

    def test_sin_archivo_es_false(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta = Path(carpeta_str) / "no_existe.json"
            self.assertFalse(disponible(ruta))

    def test_con_refresh_token_es_true(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta = _escribir_token(
                Path(carpeta_str),
                {"refresh_token": "falso-123", "token": "falso-abc"},
            )
            self.assertTrue(disponible(ruta))

    def test_sin_refresh_token_es_false(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta = _escribir_token(Path(carpeta_str), {"token": "falso-abc"})
            self.assertFalse(disponible(ruta))

    def test_refresh_token_vacio_es_false(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta = _escribir_token(Path(carpeta_str), {"refresh_token": "   "})
            self.assertFalse(disponible(ruta))

    def test_json_invalido_es_false(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta = Path(carpeta_str) / "token_youtube.json"
            ruta.write_text("esto no es json{{{", encoding="utf-8")
            self.assertFalse(disponible(ruta))

    def test_json_no_es_objeto_es_false(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta = Path(carpeta_str) / "token_youtube.json"
            ruta.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertFalse(disponible(ruta))


class PruebasSubirVideoSinAutorizar(unittest.TestCase):
    """subir_video() nunca abre un navegador: si falta el token, traduce el
    problema a un ErrorRecurso con instrucciones claras."""

    def test_video_inexistente_es_error_antes_de_mirar_el_token(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_video = Path(carpeta_str) / "no_existe.mp4"
            ruta_token = Path(carpeta_str) / "token_youtube.json"
            with self.assertRaises(ErrorRecurso) as cm:
                subir_video(
                    ruta_video, titulo="T", descripcion="D", ruta_token=ruta_token,
                )
            self.assertIn("no existe", str(cm.exception))

    def test_sin_token_pide_autorizar_primero(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_video = Path(carpeta_str) / "video.mp4"
            ruta_video.write_bytes(b"contenido de prueba, no es un mp4 real")
            ruta_token = Path(carpeta_str) / "token_youtube.json"
            with self.assertRaises(ErrorRecurso) as cm:
                subir_video(
                    ruta_video, titulo="T", descripcion="D", ruta_token=ruta_token,
                )
            self.assertIn("--autorizar", str(cm.exception))

    def test_token_sin_refresh_token_tambien_pide_autorizar(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_video = Path(carpeta_str) / "video.mp4"
            ruta_video.write_bytes(b"contenido de prueba")
            ruta_token = _escribir_token(Path(carpeta_str), {"token": "solo-esto"})
            with self.assertRaises(ErrorRecurso) as cm:
                subir_video(
                    ruta_video, titulo="T", descripcion="D", ruta_token=ruta_token,
                )
            self.assertIn("--autorizar", str(cm.exception))


def _instalar_modulos_google_falsos(video_id="VIDEO_FALSO_123",
                                    texto_error_api: str | None = None):
    """Arma modulos FALSOS que reemplazan a las librerias reales de Google en
    sys.modules durante un test, para probar subir_video() de punta a punta
    sin llamar a la API real ni necesitar las librerias instaladas.

    `texto_error_api` (opcional): si se pasa, execute() lanza el HttpError
    FALSO de este mismo set de modulos (misma identidad de clase que la que
    subir_video() importa via 'from googleapiclient.errors import HttpError'
    -- si se armara con una clase de OTRO set, el 'except HttpError' del
    codigo real no la atraparia)."""

    class CredencialesFalsas:
        valid = True
        expired = False
        refresh_token = "falso-refresh"

        @classmethod
        def from_authorized_user_file(cls, ruta, scopes):
            return cls()

        def to_json(self):
            return json.dumps({"refresh_token": "falso-refresh"})

    modulo_credentials = types.ModuleType("google.oauth2.credentials")
    modulo_credentials.Credentials = CredencialesFalsas

    class RequestFalsa:
        pass

    modulo_transport = types.ModuleType("google.auth.transport.requests")
    modulo_transport.Request = RequestFalsa

    class HttpErrorFalso(Exception):
        pass

    modulo_errors = types.ModuleType("googleapiclient.errors")
    modulo_errors.HttpError = HttpErrorFalso

    class MediaFileUploadFalso:
        def __init__(self, *args, **kwargs):
            pass

    modulo_http = types.ModuleType("googleapiclient.http")
    modulo_http.MediaFileUpload = MediaFileUploadFalso

    class PeticionFalsa:
        def execute(self):
            if texto_error_api is not None:
                raise HttpErrorFalso(texto_error_api)
            return {"id": video_id}

    class VideosFalso:
        def insert(self, part, body, media_body):
            return PeticionFalsa()

    class YoutubeFalso:
        def videos(self):
            return VideosFalso()

    modulo_discovery = types.ModuleType("googleapiclient.discovery")
    modulo_discovery.build = lambda nombre, version, credentials: YoutubeFalso()

    return {
        "google.oauth2.credentials": modulo_credentials,
        "google.auth.transport.requests": modulo_transport,
        "googleapiclient.discovery": modulo_discovery,
        "googleapiclient.errors": modulo_errors,
        "googleapiclient.http": modulo_http,
    }


class PruebasSubirVideoConGoogleFalso(unittest.TestCase):
    """subir_video() de punta a punta con la libreria de Google reemplazada
    por modulos falsos en sys.modules -- ninguna llamada real a la API."""

    def test_arma_bien_la_url_resultante(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_video = Path(carpeta_str) / "video.mp4"
            ruta_video.write_bytes(b"contenido de prueba")
            ruta_token = _escribir_token(
                Path(carpeta_str), {"refresh_token": "falso-refresh"}
            )
            modulos_falsos = _instalar_modulos_google_falsos(video_id="ABC123xyz89")
            with mock.patch.dict(sys.modules, modulos_falsos):
                resultado = subir_video(
                    ruta_video, titulo="Producto de prueba",
                    descripcion="Descripcion de prueba", ruta_token=ruta_token,
                )
            self.assertEqual(resultado["video_id"], "ABC123xyz89")
            self.assertEqual(
                resultado["url"], "https://www.youtube.com/watch?v=ABC123xyz89"
            )

    def test_error_de_la_api_se_traduce_a_errorrecurso(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_video = Path(carpeta_str) / "video.mp4"
            ruta_video.write_bytes(b"contenido de prueba")
            ruta_token = _escribir_token(
                Path(carpeta_str), {"refresh_token": "falso-refresh"}
            )
            modulos_falsos = _instalar_modulos_google_falsos(
                texto_error_api="cuota diaria agotada"
            )
            with mock.patch.dict(sys.modules, modulos_falsos):
                with self.assertRaises(ErrorRecurso) as cm:
                    subir_video(
                        ruta_video, titulo="T", descripcion="D",
                        ruta_token=ruta_token,
                    )
            self.assertIn("cuota diaria agotada", str(cm.exception))

    def test_respuesta_sin_id_es_errorrecurso(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_video = Path(carpeta_str) / "video.mp4"
            ruta_video.write_bytes(b"contenido de prueba")
            ruta_token = _escribir_token(
                Path(carpeta_str), {"refresh_token": "falso-refresh"}
            )
            modulos_falsos = _instalar_modulos_google_falsos(video_id=None)
            # Forzar una respuesta sin "id".
            modulo_discovery = modulos_falsos["googleapiclient.discovery"]

            class VideosSinId:
                def insert(self, part, body, media_body):
                    class Peticion:
                        def execute(self):
                            return {}
                    return Peticion()

            class YoutubeSinId:
                def videos(self):
                    return VideosSinId()

            modulo_discovery.build = lambda nombre, version, credentials: YoutubeSinId()
            with mock.patch.dict(sys.modules, modulos_falsos):
                with self.assertRaises(ErrorRecurso) as cm:
                    subir_video(
                        ruta_video, titulo="T", descripcion="D",
                        ruta_token=ruta_token,
                    )
            self.assertIn("id de video", str(cm.exception))


class PruebasAutorizar(unittest.TestCase):
    """autorizar(): solo se prueba el camino de error (credenciales
    faltantes) -- el camino feliz llama a InstalledAppFlow.run_local_server(),
    que abre un navegador real y no se corre en tests."""

    def test_sin_credenciales_lanza_error_claro(self):
        with tempfile.TemporaryDirectory() as carpeta_str:
            ruta_credenciales = Path(carpeta_str) / "credenciales_youtube.json"
            ruta_token = Path(carpeta_str) / "token_youtube.json"
            with self.assertRaises(ErrorRecurso) as cm:
                youtube_uploader.autorizar(
                    ruta_credenciales=ruta_credenciales, ruta_token=ruta_token,
                )
            self.assertIn("credenciales_youtube.json", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
