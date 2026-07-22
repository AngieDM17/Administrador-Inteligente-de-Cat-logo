"""Generador de la toma "partes senaladas" (callouts) de la galeria Ekipon.

Toma el recorte limpio del producto (foto REAL) y le dibuja etiquetas de marca
apuntando a sus partes, con lineas guia. Las etiquetas y los puntos vienen de
los datos del producto (de la ficha), nunca hardcodeados: asi el mismo motor
sirve para cualquier producto sin afirmar una parte que no tenga.

Formato de salida: WebP 1080x1080 (estandar de la tienda) + preview PNG.

Uso:  python generador_callouts.py <recorte.png> --datos <callouts.json>
                                   --salida <out.webp> [--preview preview.png]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RUTA_FUENTE = str(Path(__file__).parent / "fonts" / "OpenSans-Bold.ttf")
NARANJA = "#FF4E03"
BLANCO = "#FFFFFF"
LADO = 1080
# Constantes de layout afinadas a 700 px; se escalan al lado real.
_ESCALA = LADO / 700.0


def _px(valor: float) -> int:
    return int(round(valor * _ESCALA))


def _fuente(tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(RUTA_FUENTE, _px(tam))


def _envolver(texto: str, fuente: ImageFont.FreeTypeFont, ancho_max: int) -> list[str]:
    palabras, lineas, actual = texto.split(), [], ""
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if fuente.getlength(prueba) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _colocar_recorte(recorte: Image.Image, lado: int) -> tuple[Image.Image, tuple]:
    """Escala el recorte para ocupar la zona derecha del lienzo (dejando la
    columna izquierda para las etiquetas) y devuelve la posicion colocada."""
    zona = (int(lado * 0.42), int(lado * 0.06), int(lado * 0.98), int(lado * 0.94))
    zw, zh = zona[2] - zona[0], zona[3] - zona[1]
    ratio = min(zw / recorte.width, zh / recorte.height)
    nuevo = (max(1, int(recorte.width * ratio)), max(1, int(recorte.height * ratio)))
    escalado = recorte.resize(nuevo, Image.LANCZOS)
    px = zona[0] + (zw - nuevo[0]) // 2
    py = zona[1] + (zh - nuevo[1]) // 2
    return escalado, (px, py, nuevo[0], nuevo[1])


def datos_de_ficha(ficha: dict) -> dict:
    """Extrae los callouts de la ficha (multimedia.galeria_tomas.callouts).

    Solo entran las partes que traen 'point': sin posicion no se puede dibujar
    la linea guia, y una posicion JAMAS se inventa. Si ninguna la trae, la toma
    queda vacia y no se genera (degradacion limpia, no error)."""
    tomas = (ficha.get("multimedia") or {}).get("galeria_tomas") or {}
    callouts = [c for c in (tomas.get("callouts") or [])
                if c.get("label") and c.get("point")]
    return {"callouts": callouts}


def generar_callouts(recorte_path: Path, datos: dict, salida: Path,
                     lado: int = LADO) -> Image.Image:
    """Compone la toma de partes senaladas y la guarda como WebP."""
    lienzo = Image.new("RGBA", (lado, lado), BLANCO)
    recorte = Image.open(recorte_path).convert("RGBA")
    escalado, (px, py, pw, ph) = _colocar_recorte(recorte, lado)
    lienzo.alpha_composite(escalado, (px, py))

    dibujo = ImageDraw.Draw(lienzo)
    callouts = datos.get("callouts", [])

    # Columna de etiquetas a la izquierda, repartidas verticalmente.
    x_box, box_w = _px(28), int(lado * 0.34)
    pad, f = _px(14), _fuente(23)
    margen_v = _px(36)
    disponible = lado - 2 * margen_v
    slot = disponible / max(1, len(callouts))
    ancho_texto = box_w - 2 * pad

    for i, c in enumerate(callouts):
        lineas = _envolver(c["label"], f, ancho_texto)
        alto_linea = f.getbbox("Áygp")[3]
        box_h = len(lineas) * alto_linea + 2 * pad
        cy = int(margen_v + slot * i + slot / 2)
        box_top = cy - box_h // 2

        # Punto de la parte, relativo a la caja del producto colocado.
        rx, ry = c["point"]
        pxp, pyp = int(px + rx * pw), int(py + ry * ph)

        # Linea guia + punto.
        dibujo.line([(x_box + box_w, cy), (pxp, pyp)], fill=NARANJA, width=_px(3))
        r_dot = _px(7)
        dibujo.ellipse([pxp - r_dot, pyp - r_dot, pxp + r_dot, pyp + r_dot],
                       fill=NARANJA, outline=BLANCO, width=_px(2))

        # Caja redondeada con el texto.
        dibujo.rounded_rectangle([x_box, box_top, x_box + box_w, box_top + box_h],
                                 radius=_px(12), fill=NARANJA)
        ty = box_top + pad
        for linea in lineas:
            dibujo.text((x_box + pad, ty), linea, font=f, fill=BLANCO)
            ty += alto_linea

    lienzo.convert("RGB").save(salida, "WEBP", quality=90)
    return lienzo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera la toma de partes senaladas (callouts) de un producto.")
    parser.add_argument("recorte", help="PNG del recorte limpio del producto")
    parser.add_argument("--ficha", help="Ficha del producto (multimedia.galeria_tomas)")
    parser.add_argument("--datos", help="JSON suelto con los callouts (alternativa)")
    parser.add_argument("--salida", required=True, help="WebP de salida")
    parser.add_argument("--preview", default=None, help="PNG de preview (RGB)")
    args = parser.parse_args()

    if args.ficha:
        ficha = json.loads(Path(args.ficha).read_text(encoding="utf-8-sig"))
        datos = datos_de_ficha(ficha)
    elif args.datos:
        datos = json.loads(Path(args.datos).read_text(encoding="utf-8"))
    else:
        parser.error("hace falta --ficha o --datos")

    if not datos.get("callouts"):
        print("SIN CALLOUTS con posicion en la ficha — no se genera la toma.")
        return

    img = generar_callouts(Path(args.recorte), datos, Path(args.salida))
    print("CALLOUTS:", args.salida)
    if args.preview:
        img.convert("RGB").save(args.preview, "PNG")
        print("PREVIEW:", args.preview)


if __name__ == "__main__":
    main()
