"""Revisor de listo-para-publicar — separa las fichas que puede publicar solas
de las que necesitan los ojos de Angie.

NO re-hace el trabajo del Investigador. El Investigador ya deja anotados los
problemas cuando arma la ficha (en identificacion_del_producto.advertencias y en
campos_por_confirmar); este revisor LEE esas notas, les suma unos pocos chequeos
mecanicos que no dependen de ellas (potencia, dimensiones, estado usado), y
emite un veredicto:

  LISTO      -> la ficha puede fluir sin revision humana previa.
  REVISAR    -> tiene al menos un motivo por el que Angie debe mirarla.

Uso:  python revisor_publicacion.py <ruta_ficha.json>

Codigos de salida:
  0 = LISTO (ningun motivo)
  1 = REVISAR (al menos un motivo)
  2 = problema con el archivo (no existe, no se puede leer o no es JSON valido)

Sesgo deliberado: ante la duda, MARCA. Marcar una ficha buena de mas cuesta un
vistazo; dejar pasar una mala cuesta caro. Por eso cualquier motivo -> REVISAR.

LIMITE: el revisor es tan fino como las notas del Investigador. Un problema que
el Investigador no anoto en advertencias/campos_por_confirmar solo se atrapa si
cae en uno de los chequeos mecanicos. No es un muro; es un colador.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Optional

from validar_ficha import cargar_json

# --- Ajustes del revisor ---------------------------------------------------

# Confirmaciones que NO son un problema de calidad: son los puntos normales
# donde el humano SIEMPRE entra (regla de negocio). Si un campo_por_confirmar
# habla de esto, no cuenta como motivo para marcar.
#   - precio: SIEMPRE lo define Angie a mano.
#   - categoria: se resuelve en vivo contra el arbol de la tienda.
_CONFIRMACIONES_ESPERADAS = ("precio", "categor")

# Un campo de ficha_tecnica cuenta como "declara la potencia" si su clave
# contiene alguno de estos (las fichas reales usan POTENCIA, MOTOR DE ELEVACION,
# MOTOR, etc.).
_CLAVES_POTENCIA = ("POTENCIA", "MOTOR")

# Marca que el propio Investigador pone en un valor estimado, no verificado
# (ver _nota de ficha_tecnica en las fichas reales).
_MARCA_SIN_VERIFICAR = "generado_ia_sin_verificar"


# --- Resultado -------------------------------------------------------------

@dataclass(frozen=True)
class Motivo:
    """Una razon por la que la ficha va a revision. 'codigo' es estable (para
    pruebas y para el pipeline); 'mensaje' es lo que lee Angie."""

    codigo: str
    mensaje: str


@dataclass
class ResultadoRevision:
    motivos: list[Motivo] = field(default_factory=list)

    @property
    def listo(self) -> bool:
        return not self.motivos


# --- Navegacion segura sobre el dict crudo ---------------------------------
# Se trabaja sobre el JSON crudo (no sobre el modelo pydantic) para poder
# revisar aunque la ficha tenga algun drift, igual que revisar_advertencias.

def _seccion(datos: dict, clave: str) -> dict:
    valor = datos.get(clave)
    return valor if isinstance(valor, dict) else {}


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else []


def _texto(valor) -> str:
    return valor if isinstance(valor, str) else ""


# --- Chequeos --------------------------------------------------------------

def _revisar_identificacion(datos: dict) -> list[Motivo]:
    ident = _seccion(datos, "identificacion_del_producto")
    motivos: list[Motivo] = []

    resultado = _texto(ident.get("resultado"))
    if resultado and not resultado.startswith("IDENTIFICADO"):
        motivos.append(Motivo(
            "no_identificado",
            "El producto no quedo bien identificado "
            "(resultado dudoso o no identificado).",
        ))

    # Sin link, la identificacion es por inferencia: ficha nivel-familia, se
    # confia menos. Lo dice el propio contrato (origen_identificacion).
    if _texto(ident.get("origen_identificacion")) == "inferencia":
        motivos.append(Motivo(
            "inferencia_sin_link",
            "Ficha de nivel-familia (sin link): las specs son inferidas, "
            "no extraidas del producto exacto. Confiar menos.",
        ))

    advertencias = [_texto(a) for a in _lista(ident.get("advertencias")) if _texto(a)]
    if advertencias:
        motivos.append(Motivo(
            "advertencias_investigador",
            "El investigador dejo "
            f"{len(advertencias)} advertencia(s): " + " | ".join(advertencias),
        ))

    if "usado" in _texto(ident.get("estado_en_proveedor")).lower():
        motivos.append(Motivo(
            "estado_usado",
            "El proveedor marca el equipo como USADO (la tienda vende nuevo).",
        ))

    return motivos


def _revisar_campos_por_confirmar(datos: dict) -> list[Motivo]:
    pendientes = [
        _texto(c) for c in _lista(datos.get("campos_por_confirmar")) if _texto(c)
    ]
    # Se descuentan las confirmaciones normales (precio, categoria): esas no son
    # un problema de calidad, son los puntos donde el humano siempre entra.
    reales = [
        c for c in pendientes
        if not any(esperada in c.lower() for esperada in _CONFIRMACIONES_ESPERADAS)
    ]
    if not reales:
        return []
    return [Motivo(
        "campos_por_confirmar",
        f"Hay {len(reales)} dato(s) por confirmar ademas del precio y la "
        "categoria: " + " | ".join(reales),
    )]


def _revisar_ficha_tecnica(datos: dict) -> list[Motivo]:
    ficha_tecnica = _seccion(datos, "ficha_tecnica")
    motivos: list[Motivo] = []

    # Claves de datos: las tecnicas van en MAYUSCULAS; las de metadatos con '_'.
    claves = [k for k in ficha_tecnica if isinstance(k, str) and not k.startswith("_")]

    tiene_potencia = any(
        any(marca in clave.upper() for marca in _CLAVES_POTENCIA) for clave in claves
    )
    if claves and not tiene_potencia:
        motivos.append(Motivo(
            "sin_potencia",
            "Falta la potencia del motor en la ficha tecnica.",
        ))

    # Specs estimadas por IA, sin verificar: el Investigador las marca en el
    # valor. Merecen un vistazo antes de publicar. Solo se miran los datos (no
    # las metaclaves '_nota'/'_origen_global', que EXPLICAN la marca y la
    # contienen como texto sin ser una spec estimada).
    if any(_MARCA_SIN_VERIFICAR in _texto(ficha_tecnica.get(clave)) for clave in claves):
        motivos.append(Motivo(
            "specs_estimadas",
            "Algunas specs estan estimadas y sin verificar.",
        ))

    return motivos


def _revisar_dimensiones(datos: dict) -> list[Motivo]:
    # La toma de 'medidas' de la galeria se dibuja con estas tres. El peso solo
    # no alcanza para la foto de medidas.
    galeria_tomas = _seccion(datos, "multimedia").get("galeria_tomas")
    dims = galeria_tomas.get("dimensiones") if isinstance(galeria_tomas, dict) else None
    dims = dims if isinstance(dims, dict) else {}
    if any(_texto(dims.get(eje)).strip() for eje in ("alto", "ancho", "fondo")):
        return []
    return [Motivo(
        "sin_dimensiones",
        "Faltan las dimensiones (alto/ancho/fondo): no se puede armar la foto "
        "de medidas.",
    )]


def revisar_listo_para_publicar(datos: dict) -> ResultadoRevision:
    """Corre todos los chequeos sobre una ficha (JSON ya cargado) y devuelve el
    veredicto. No lanza excepciones por datos faltantes: lo ausente se trata
    como motivo, nunca como error."""
    motivos: list[Motivo] = []
    motivos += _revisar_identificacion(datos)
    motivos += _revisar_campos_por_confirmar(datos)
    motivos += _revisar_ficha_tecnica(datos)
    motivos += _revisar_dimensiones(datos)
    return ResultadoRevision(motivos)


# --- CLI -------------------------------------------------------------------

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) != 2:
        print("Uso: python revisor_publicacion.py <ruta_ficha.json>")
        sys.exit(2)

    from pathlib import Path

    ruta = Path(sys.argv[1]).resolve()
    datos = cargar_json(ruta)  # termina con codigo 2 si el archivo falla

    print("Revisor de listo-para-publicar")
    print(f"Ficha: {ruta}")

    resultado = revisar_listo_para_publicar(datos)

    if resultado.listo:
        print("\nLISTO PARA PUBLICAR — ningun motivo para revision previa.")
        sys.exit(0)

    print(f"\nNECESITA REVISION — {len(resultado.motivos)} motivo(s):")
    for numero, motivo in enumerate(resultado.motivos, start=1):
        print(f"  {numero}. {motivo.mensaje}")
    sys.exit(1)


if __name__ == "__main__":
    main()
