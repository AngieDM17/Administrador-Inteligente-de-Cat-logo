"""Generador de la toma "dimensiones/tamano" de la galeria Ekipon.

Muestra el TAMANO real del producto: el recorte limpio (foto REAL) con lineas
de medida (alto, ancho) y un sello de peso, todo desde los datos de la ficha.
Es la forma honesta y precisa de comunicar la escala sin depender de una foto
con persona. Determinista: el mismo producto sale igual siempre.

Formato de salida: WebP 1080x1080 (estandar de la tienda) + preview PNG.

Uso:  python generador_dimensiones.py <recorte.png> --datos <dims.json>
                                      --salida <out.webp> [--preview preview.png]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RUTA_FUENTE = str(Path(__file__).parent / "fonts" / "OpenSans-Bold.ttf")
NARANJA = "#FF4E03"
OSCURO = "#1A1A1A"
BLANCO = "#FFFFFF"
LADO = 1080
# Las constantes de layout se afinaron a 700 px; se escalan al lado real para
# mantener las proporciones a cualquier tamano de lienzo.
_ESCALA = LADO / 700.0


def _px(valor: float) -> int:
    return int(round(valor * _ESCALA))


def _fuente(tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(RUTA_FUENTE, _px(tam))


def _texto_centrado(dibujo, xy, texto, fuente, fill):
    x, y = xy
    caja = dibujo.textbbox((0, 0), texto, font=fuente)
    dibujo.text((x - (caja[2] - caja[0]) / 2, y - (caja[3] - caja[1]) / 2),
                texto, font=fuente, fill=fill)


def _medida_vertical(dibujo, x, y0, y1, etiqueta, fuente):
    """Linea de medida vertical con topes; etiqueta a la izquierda."""
    tick = _px(15)
    dibujo.line([(x, y0), (x, y1)], fill=NARANJA, width=_px(3))
    dibujo.line([(x - tick, y0), (x + tick, y0)], fill=NARANJA, width=_px(3))
    dibujo.line([(x - tick, y1), (x + tick, y1)], fill=NARANJA, width=_px(3))
    _texto_centrado(dibujo, (x - _px(45), (y0 + y1) / 2), etiqueta, fuente, OSCURO)


def _medida_horizontal(dibujo, y, x0, x1, etiqueta, fuente):
    """Linea de medida horizontal con topes; etiqueta debajo."""
    tick = _px(15)
    dibujo.line([(x0, y), (x1, y)], fill=NARANJA, width=_px(3))
    dibujo.line([(x0, y - tick), (x0, y + tick)], fill=NARANJA, width=_px(3))
    dibujo.line([(x1, y - tick), (x1, y + tick)], fill=NARANJA, width=_px(3))
    _texto_centrado(dibujo, ((x0 + x1) / 2, y + _px(30)), etiqueta, fuente, OSCURO)


def datos_de_ficha(ficha: dict) -> dict:
    """Extrae las medidas de la ficha (multimedia.galeria_tomas.dimensiones).

    Devuelve solo las claves con valor: lo que la ficha no trae verificado se
    OMITE (no se dibuja esa medida), nunca se inventa ni frena el pipeline."""
    tomas = (ficha.get("multimedia") or {}).get("galeria_tomas") or {}
    dims = tomas.get("dimensiones") or {}
    return {k: v for k, v in dims.items()
            if k in ("alto", "ancho", "fondo", "peso") and v}


def generar_dimensiones(recorte_path: Path, datos: dict, salida: Path,
                        lado: int = LADO) -> Image.Image:
    lienzo = Image.new("RGBA", (lado, lado), BLANCO)
    recorte = Image.open(recorte_path).convert("RGBA")

    # Zona del producto: margen izq (medida vertical) y abajo (medida horizontal).
    zona = (_px(150), _px(70), lado - _px(40), lado - _px(120))
    zw, zh = zona[2] - zona[0], zona[3] - zona[1]
    ratio = min(zw / recorte.width, zh / recorte.height)
    nuevo = (max(1, int(recorte.width * ratio)), max(1, int(recorte.height * ratio)))
    escalado = recorte.resize(nuevo, Image.LANCZOS)
    px = zona[0] + (zw - nuevo[0]) // 2
    py = zona[1] + (zh - nuevo[1]) // 2
    lienzo.alpha_composite(escalado, (px, py))

    dibujo = ImageDraw.Draw(lienzo)
    f = _fuente(26)

    if datos.get("alto"):
        _medida_vertical(dibujo, px - _px(55), py, py + nuevo[1],
                         f"Alto\n{datos['alto']}", f)
    if datos.get("ancho"):
        _medida_horizontal(dibujo, py + nuevo[1] + _px(55), px, px + nuevo[0],
                           f"Ancho {datos['ancho']}", f)

    # Sellos de peso y fondo, arriba a la derecha.
    fb = _fuente(28)
    extras = []
    if datos.get("peso"):
        extras.append(("Peso", datos["peso"]))
    if datos.get("fondo"):
        extras.append(("Fondo", datos["fondo"]))
    by = _px(30)
    for titulo, valor in extras:
        texto = f"{titulo}: {valor}"
        w = dibujo.textlength(texto, font=fb)
        bw, bh = int(w) + _px(36), _px(46)
        bx = lado - bw - _px(30)
        dibujo.rounded_rectangle([bx, by, bx + bw, by + bh], radius=_px(12), fill=NARANJA)
        _texto_centrado(dibujo, (bx + bw / 2, by + bh / 2), texto, fb, BLANCO)
        by += bh + _px(14)

    lienzo.convert("RGB").save(salida, "WEBP", quality=90)
    return lienzo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera la toma de dimensiones/tamano de un producto.")
    parser.add_argument("recorte")
    parser.add_argument("--ficha", help="Ficha del producto (multimedia.galeria_tomas)")
    parser.add_argument("--datos", help="JSON suelto con las medidas (alternativa)")
    parser.add_argument("--salida", required=True)
    parser.add_argument("--preview", default=None)
    args = parser.parse_args()

    if args.ficha:
        ficha = json.loads(Path(args.ficha).read_text(encoding="utf-8-sig"))
        datos = datos_de_ficha(ficha)
    elif args.datos:
        datos = json.loads(Path(args.datos).read_text(encoding="utf-8"))
    else:
        parser.error("hace falta --ficha o --datos")

    img = generar_dimensiones(Path(args.recorte), datos, Path(args.salida))
    print("DIMENSIONES:", args.salida)
    if args.preview:
        img.convert("RGB").save(args.preview, "PNG")
        print("PREVIEW:", args.preview)


if __name__ == "__main__":
    main()
