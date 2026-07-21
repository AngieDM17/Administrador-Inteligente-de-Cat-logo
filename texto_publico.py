"""Utilidades de texto PUBLICO compartidas entre módulos del motor Ekipon.

Vive aparte (no dentro del Publicador ni del generador de banner) para que ambos
la reutilicen sin importarse mutuamente — evita un import circular ahora que el
Publicador genera el banner.
"""

import re


def limpiar_valor_publico(texto: str) -> str:
    """Quita las marcas internas de origen ("[encontrado_web]", etc.) de un
    valor antes de mostrarlo al publico. La version completa con origenes vive
    SOLO en la ficha JSON (fuente de verdad); a la tienda viaja limpio."""
    sin_marcas = re.sub(r"\s*\[[^\]]*\]", "", texto)
    return " ".join(sin_marcas.split())
