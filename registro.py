"""Libreta de control del Publicador Ekipon (registro local en SQLite).

Guarda que producto se creo por cada codigo de proveedor, para que el
publicador nunca duplique: antes de crear, consulta aqui y en la tienda.

El archivo ekipon.db vive junto a este modulo y se crea solo al primer uso.
Esta ignorado por git (es estado local, no codigo).
"""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

RUTA_DB_POR_DEFECTO = Path(__file__).parent / "ekipon.db"


class ErrorRegistro(Exception):
    """Falla al leer o escribir la libreta local (ej. base bloqueada por otra
    corrida). Se traduce a un mensaje claro en vez de un traceback crudo."""

_CREAR_TABLA = """
CREATE TABLE IF NOT EXISTS publicaciones (
    codigo      TEXT PRIMARY KEY,
    product_id  INTEGER,
    slug        TEXT UNIQUE,
    estado      TEXT,
    actualizado TEXT
)
"""


def conectar(ruta_db: Path | str | None = None) -> sqlite3.Connection:
    """Abre (y crea si hace falta) la libreta. Acepta ruta propia para pruebas."""
    conexion = sqlite3.connect(str(ruta_db or RUTA_DB_POR_DEFECTO))
    conexion.row_factory = sqlite3.Row
    conexion.execute(_CREAR_TABLA)
    conexion.commit()
    return conexion


def obtener_publicacion(codigo: str, ruta_db: Path | str | None = None) -> dict | None:
    """Devuelve el registro del codigo como dict, o None si no existe."""
    # closing() cierra la conexion de verdad: el 'with' de sqlite3 solo
    # maneja la transaccion, y en Windows un archivo abierto queda bloqueado.
    try:
        with closing(conectar(ruta_db)) as conexion:
            fila = conexion.execute(
                "SELECT codigo, product_id, slug, estado, actualizado "
                "FROM publicaciones WHERE codigo = ?",
                (codigo,),
            ).fetchone()
    except sqlite3.Error as error:
        raise ErrorRegistro(
            f"no se pudo leer la libreta local (ekipon.db): {error}. "
            "¿Hay otra corrida del publicador abierta?"
        ) from error
    return dict(fila) if fila else None


def registrar_publicacion(
    codigo: str,
    product_id: int,
    slug: str,
    estado: str,
    ruta_db: Path | str | None = None,
) -> None:
    """Anota (o actualiza) la publicacion de un codigo, con fecha ISO."""
    ahora = datetime.now().isoformat(timespec="seconds")
    try:
        with closing(conectar(ruta_db)) as conexion:
            conexion.execute(
                "INSERT INTO publicaciones (codigo, product_id, slug, estado, actualizado) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(codigo) DO UPDATE SET "
                "product_id = excluded.product_id, slug = excluded.slug, "
                "estado = excluded.estado, actualizado = excluded.actualizado",
                (codigo, product_id, slug, estado, ahora),
            )
            conexion.commit()
    except sqlite3.Error as error:
        raise ErrorRegistro(
            f"no se pudo escribir en la libreta local (ekipon.db): {error}. "
            "¿Hay otra corrida del publicador abierta?"
        ) from error
