"""Inspector de fichas Ekipon — valida una ficha contra el contrato v1.4.

Uso:  python validar_ficha.py <ruta_ficha.json> [--sin-imagenes]

Salida:
- "FICHA VALIDA" mas advertencias (si las hay), o
- lista numerada de errores concretos: campo + que esta mal + que se esperaba.

Codigos de salida:
  0 = ficha valida (puede tener advertencias)
  1 = ficha invalida (al menos un error de contrato o regla de negocio)
  2 = problema con el archivo (no existe, no se puede leer o no es JSON valido)

Los ERRORES bloquean (rompen reglas fijas del negocio o el contrato).
Las ADVERTENCIAS no bloquean: señalan drift entre la ficha y la plantilla
v1.4 (claves desconocidas, secciones ausentes, imagenes no encontradas).
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from esquema_ficha import (
    MODELOS_POR_SECCION,
    VERSION_CONTRATO,
    FichaEkipon,
    claves_conocidas,
)

# Traduccion al español de los tipos de error estandar de pydantic.
# Los errores de reglas de negocio (value_error) ya vienen en español
# desde esquema_ficha.py.
_TRADUCCIONES = {
    "missing": "falta este campo obligatorio en la ficha",
    "string_type": "debe ser texto (cadena entre comillas)",
    "string_too_short": "no puede estar vacio",
    "int_type": "debe ser un numero entero, sin comillas y sin decimales",
    "list_type": "debe ser una lista [...]",
    "dict_type": "debe ser una seccion (objeto JSON entre llaves)",
    "model_type": "debe ser una seccion (objeto JSON entre llaves)",
    "model_attributes_type": "debe ser una seccion (objeto JSON entre llaves)",
    "none_required": "debe ser null",
    "bool_type": "no puede ser verdadero/falso; se esperaba otro tipo",
}


def ruta_de_campo(loc: tuple) -> str:
    """Convierte la ubicacion de pydantic en una ruta legible: a.b[0].c"""
    partes = []
    for tramo in loc:
        if isinstance(tramo, int):
            partes[-1] = f"{partes[-1]}[{tramo}]" if partes else f"[{tramo}]"
        else:
            partes.append(str(tramo))
    return ".".join(partes) if partes else "(ficha completa)"


def describir_error(error: dict) -> str:
    """Arma una linea de error en español: campo + problema + esperado."""
    campo = ruta_de_campo(error["loc"])
    tipo = error["type"]

    if tipo == "value_error":
        # Mensaje de regla de negocio escrito por nosotros en esquema_ficha.py.
        mensaje = error["msg"].removeprefix("Value error, ")
        return f"{campo}: {mensaje}"

    mensaje = _TRADUCCIONES.get(tipo, f"valor no valido (detalle tecnico: {tipo})")
    linea = f"{campo}: {mensaje}"
    if tipo != "missing" and "input" in error:
        recibido = json.dumps(error["input"], ensure_ascii=False, default=str)
        if len(recibido) > 60:
            recibido = recibido[:60] + "..."
        linea += f". Se recibio: {recibido}"
    return linea


def revisar_advertencias(datos: dict, carpeta_ficha: Path, verificar_imagenes: bool) -> list[str]:
    """Detecta drift que no bloquea: claves desconocidas, version, imagenes.

    Trabaja sobre el JSON crudo (no sobre el modelo) para poder reportar
    drift aunque la ficha tenga errores de validacion.
    """
    advertencias = []

    # 1. Version del contrato.
    version = datos.get("_version_ficha")
    if version is None:
        advertencias.append(
            "la ficha no declara _version_ficha; este inspector valida el "
            f"contrato v{VERSION_CONTRATO}"
        )
    elif version != VERSION_CONTRATO:
        advertencias.append(
            f"_version_ficha es '{version}' y este inspector valida el "
            f"contrato v{VERSION_CONTRATO}"
        )

    # 2. Secciones de nivel superior que la plantilla v1.4 no contempla.
    conocidas_raiz = claves_conocidas(FichaEkipon)
    for clave in datos:
        if clave not in conocidas_raiz:
            advertencias.append(
                f"seccion de nivel superior desconocida para la plantilla "
                f"v{VERSION_CONTRATO}: '{clave}' (se acepta pero se reporta)"
            )

    # 3. Claves desconocidas dentro de secciones conocidas
    #    (ficha_tecnica queda fuera: sus claves tecnicas son libres).
    for seccion, modelo in MODELOS_POR_SECCION.items():
        contenido = datos.get(seccion)
        if not isinstance(contenido, dict):
            continue
        conocidas = claves_conocidas(modelo)
        for clave in contenido:
            if clave not in conocidas:
                advertencias.append(
                    f"clave desconocida en {seccion}: '{clave}' "
                    f"(no esta en la plantilla v{VERSION_CONTRATO})"
                )

    # 4. Galeria estandar e imagenes en disco.
    multimedia = datos.get("multimedia")
    if isinstance(multimedia, dict):
        imagenes = multimedia.get("imagenes_galeria_confirmadas")
        if imagenes is None:
            advertencias.append(
                "multimedia no trae imagenes_galeria_confirmadas (la seccion "
                "estandar de galeria de la plantilla v1.4)"
            )
        elif isinstance(imagenes, list) and verificar_imagenes:
            for indice, imagen in enumerate(imagenes):
                if not isinstance(imagen, dict):
                    continue
                url = imagen.get("url")
                if not isinstance(url, str) or not url:
                    continue  # el esquema ya lo marca como error
                # Solo rutas relativas simples: nada de URLs, rutas absolutas
                # ni saltos hacia arriba (..) que salgan de la carpeta del caso.
                if (
                    url.startswith(("http://", "https://", "/", "\\"))
                    or ":" in url[:3]
                    or ".." in url.replace("\\", "/").split("/")
                ):
                    advertencias.append(
                        f"multimedia.imagenes_galeria_confirmadas[{indice}].url "
                        f"no es una ruta relativa ('{url}'); no se verifico en disco"
                    )
                elif not (carpeta_ficha / url).is_file():
                    advertencias.append(
                        f"imagen no encontrada en disco: '{url}' (relativa a "
                        f"{carpeta_ficha})"
                    )

    return advertencias


def cargar_json(ruta: Path) -> dict:
    """Lee y decodifica el archivo; termina con codigo 2 si algo falla."""
    if not ruta.is_file():
        print(f"ERROR DE ARCHIVO: no existe o no se puede leer '{ruta}'.")
        sys.exit(2)
    try:
        # utf-8-sig: tolera el BOM que agregan algunos editores de Windows.
        texto = ruta.read_text(encoding="utf-8-sig")
    except OSError as error:
        print(f"ERROR DE ARCHIVO: no se pudo leer '{ruta}': {error}")
        sys.exit(2)
    except UnicodeDecodeError:
        print(
            f"ERROR DE ARCHIVO: '{ruta}' no esta guardado en UTF-8 (la "
            "codificacion estandar de las fichas). Guardarlo como UTF-8 y reintentar."
        )
        sys.exit(2)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as error:
        print(
            f"ERROR DE JSON: el archivo no es JSON valido "
            f"(linea {error.lineno}, columna {error.colno}): {error.msg}"
        )
        sys.exit(2)
    except RecursionError:
        print("ERROR DE JSON: la estructura del archivo esta anidada demasiado profundo.")
        sys.exit(2)
    if not isinstance(datos, dict):
        print("ERROR DE JSON: el contenido no es un objeto JSON (se esperaba { ... }).")
        sys.exit(2)
    return datos


def imprimir_lista(titulo: str, lineas: list[str]) -> None:
    print(f"\n{titulo}")
    for numero, linea in enumerate(lineas, start=1):
        print(f"  {numero}. {linea}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description=f"Valida una ficha Ekipon contra el contrato v{VERSION_CONTRATO}."
    )
    parser.add_argument("ruta_ficha", help="ruta al archivo .json de la ficha")
    parser.add_argument(
        "--sin-imagenes",
        action="store_true",
        help="no verificar que los archivos de imagen referenciados existan en disco",
    )
    argumentos = parser.parse_args()

    ruta = Path(argumentos.ruta_ficha).resolve()
    datos = cargar_json(ruta)

    print(f"Inspector de fichas Ekipon — contrato v{VERSION_CONTRATO}")
    print(f"Ficha: {ruta}")

    errores = []
    try:
        FichaEkipon.model_validate(datos)
    except ValidationError as fallo:
        errores = [describir_error(error) for error in fallo.errors()]

    advertencias = revisar_advertencias(
        datos, ruta.parent, verificar_imagenes=not argumentos.sin_imagenes
    )

    if errores:
        imprimir_lista(f"FICHA INVALIDA — {len(errores)} error(es):", errores)
    else:
        print("\nFICHA VALIDA — cumple el contrato y las reglas fijas del negocio.")

    if advertencias:
        imprimir_lista(
            f"Advertencias ({len(advertencias)}) — no bloquean, señalan drift:",
            advertencias,
        )
    elif not errores:
        print("Sin advertencias.")

    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
