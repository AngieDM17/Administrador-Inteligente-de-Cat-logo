"""Valida que los puntos de los callouts caigan SOBRE el producto.

Por que existe: el Investigador sabe QUE partes tiene el producto, pero no
DONDE caen sobre la foto. Ubicarlas es un paso de vision (hoy asistido). Un
modelo mirando una foto puede equivocarse y poner una etiqueta en el aire.

La silueta del recorte es el juez. `recortar_producto.py` deja el fondo
transparente, asi que el canal alfa dice exactamente donde hay producto y
donde no: un punto sobre pixeles transparentes esta mal, sin lugar a
discusion. Es un control DETERMINISTA sobre una salida de IA — no depende de
que el modelo se porte bien.

Un punto invalido no rompe nada: se descarta y esa parte no se dibuja, que es
la misma degradacion limpia de siempre (regla: si no esta verificado, se
omite).

LIMITE — leer antes de confiar de mas
-------------------------------------
Esto verifica que el punto caiga SOBRE el producto. NO verifica que caiga
sobre la parte CORRECTA. La geometria no sabe de semantica: un punto puesto
sobre el motor con la etiqueta "puerto de descarga" pasa este control sin
problema.

Comprobado en el molino (22-jul-2026): la etiqueta "Puerto de descarga"
apuntaba al vacio entre las patas y ESTE CONTROL LA DEJO PASAR, porque habia
una pata a pocos pixeles. Se detecto mirando la imagen renderizada, no el log.

O sea: atrapa el error grosero (una etiqueta en el aire), no el error de
criterio. La revision de la pieza renderizada sigue haciendo falta.


Uso:  python validar_puntos.py <recorte.png> --ficha ficha.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

# Un pixel se considera producto si su alfa supera este valor. rembg deja los
# bordes con alfa parcial; 128 es "solidamente producto", no un borde difuso.
ALPHA_SOLIDO = 128

# Radio de tolerancia, como fraccion del lado menor de la imagen.
#
# CALIBRADO CON DATOS REALES (molino, 22-jul-2026), no elegido a ojo. Medido
# sobre el recorte del molino: un punto bien puesto ("Motor electrico") cae a
# 0,6% del producto; dos puntos correctos pero apuntados a partes DELGADAS
# ("Puerto de descarga", "Soporte robusto") caen a 3,0% y 3,6% — entre las
# patas, o en un puerto hundido; y un punto realmente en el aire cae a mas del
# 10%. Con 1,5% se descartaban las dos etiquetas legitimas.
#
# 5% deja pasar el filo de una pata y sigue rechazando el aire. Ojo: calibrado
# sobre UN producto; revisar contra el lote cuando exista.
TOLERANCIA = 0.05


def punto_sobre_producto(recorte: Image.Image, punto,
                         tolerancia: float = TOLERANCIA) -> bool:
    """True si [x, y] (relativos 0..1) caen sobre la silueta del producto.

    Mira una VENTANA cuadrada de radio `tolerancia` alrededor del punto y
    acepta si hay algun pixel solido dentro. Se mira la ventana entera y no un
    anillo de vecinos a proposito: las partes finas (una pata, un eje) pasan
    entre los puntos de un anillo y se rechazarian por error.
    """
    if not punto or len(punto) != 2:
        return False
    rx, ry = punto
    if not (0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0):
        return False

    alpha = recorte.convert("RGBA").getchannel("A")
    x = min(int(rx * alpha.width), alpha.width - 1)
    y = min(int(ry * alpha.height), alpha.height - 1)

    r = max(0, int(min(alpha.width, alpha.height) * tolerancia))
    caja = (max(0, x - r), max(0, y - r),
            min(alpha.width, x + r + 1), min(alpha.height, y + r + 1))
    # getextrema() devuelve (min, max) del canal: el max dice si hubo solido.
    return alpha.crop(caja).getextrema()[1] >= ALPHA_SOLIDO


def filtrar_callouts(recorte: Image.Image, callouts: list,
                     tolerancia: float = TOLERANCIA) -> dict:
    """Separa los callouts en aceptados, descartados y sin punto.

    - aceptados: tienen punto y cae sobre el producto -> se dibujan.
    - descartados: tienen punto pero cae fuera -> NO se dibujan (punto mal
      ubicado; se informa para poder revisarlo).
    - sin_punto: el Investigador no supo donde cae -> no se dibujan, y eso
      esta bien: nunca se inventa una posicion.
    """
    aceptados, descartados, sin_punto = [], [], []
    for c in callouts or []:
        label = (c.get("label") or "").strip()
        if not label:
            continue
        if not c.get("point"):
            sin_punto.append(label)
        elif punto_sobre_producto(recorte, c["point"], tolerancia):
            aceptados.append(c)
        else:
            descartados.append({"label": label, "point": c["point"],
                                "motivo": "el punto no cae sobre el producto"})
    return {"aceptados": aceptados, "descartados": descartados,
            "sin_punto": sin_punto}


def callouts_de_ficha(ficha: dict) -> list:
    """Callouts crudos de la ficha, antes de validar."""
    tomas = (ficha.get("multimedia") or {}).get("galeria_tomas") or {}
    return tomas.get("callouts") or []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verifica que los puntos de los callouts caigan sobre el producto.")
    parser.add_argument("recorte", help="Recorte PNG con fondo transparente")
    parser.add_argument("--ficha", required=True, help="Ficha del producto")
    args = parser.parse_args()

    ficha = json.loads(Path(args.ficha).read_text(encoding="utf-8-sig"))
    recorte = Image.open(args.recorte).convert("RGBA")
    r = filtrar_callouts(recorte, callouts_de_ficha(ficha))

    print(f"Aceptados: {len(r['aceptados'])}")
    for c in r["aceptados"]:
        print(f"  OK  {c['label']}")
    for d in r["descartados"]:
        print(f"  MAL {d['label']} — {d['motivo']} (point={d['point']})")
    for label in r["sin_punto"]:
        print(f"  --  {label} — sin punto; no se dibuja (nunca se inventa)")


if __name__ == "__main__":
    main()
