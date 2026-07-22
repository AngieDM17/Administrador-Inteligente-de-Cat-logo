"""Generador de galeria de producto Ekipon (etapa Imagenes).

Resuelve el problema de VARIEDAD cuando hay pocas fotos reales: en vez de
rellenar la galeria con recortes redundantes de la misma foto, combina la(s)
foto(s) real(es) limpia(s) con TARJETAS INFORMATIVAS generadas desde datos
seguros de la ficha. Las tarjetas NO son fotos y no inventan el producto: son
graficos de marca que le aclaran al cliente como es y que hace el equipo.

Formato de salida: WebP 1080x1080 (estandar de la tienda) + un contact-sheet PNG
de preview para revisar a ojo antes de publicar.

Uso:  python generador_galeria.py <recorte.png> --datos <datos.json>
                                  --salida-dir <carpeta> [--preview preview.png]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RUTA_FUENTE = str(Path(__file__).parent / "fonts" / "OpenSans-Bold.ttf")

# Paleta de marca (misma que el banner).
NARANJA = "#FF4E03"
BLANCO = "#FFFFFF"
OSCURO = "#1A1A1A"
GRIS_FONDO = "#F4F4F4"

LADO = 1080  # lado del cuadrado de la tienda
# Constantes de layout afinadas a 700 px; se escalan al lado real.
_ESCALA = LADO / 700.0


def _px(valor: float) -> int:
    return int(round(valor * _ESCALA))


def _fuente(tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(RUTA_FUENTE, _px(tam))


def _envolver(texto: str, fuente: ImageFont.FreeTypeFont, ancho_max: int) -> list[str]:
    """Parte un texto en lineas que caben en ancho_max px."""
    palabras = texto.split()
    lineas: list[str] = []
    actual = ""
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


def hero_producto(recorte: Image.Image, lado: int = LADO,
                  fondo: str = BLANCO, margen: float = 0.10) -> Image.Image:
    """Foto real limpia como imagen principal: el recorte centrado sobre fondo
    uniforme, escalado para llenar el cuadrado con un margen proporcional."""
    lienzo = Image.new("RGBA", (lado, lado), fondo)
    recorte = recorte.convert("RGBA")
    caja = int(lado * (1 - 2 * margen))
    ratio = min(caja / recorte.width, caja / recorte.height)
    nuevo = (max(1, int(recorte.width * ratio)), max(1, int(recorte.height * ratio)))
    escalado = recorte.resize(nuevo, Image.LANCZOS)
    pos = ((lado - nuevo[0]) // 2, (lado - nuevo[1]) // 2)
    lienzo.alpha_composite(escalado, pos)
    return lienzo


def _plan_vinetas(items: list[str], tam: int, ancho_max: int,
                  interlinea: int, gap: int) -> tuple[list[list[str]], int, int]:
    """Para un tamano de fuente, devuelve (lineas por item, alto de linea, alto
    total) — sirve para elegir el tamano mas grande que entra sin cortarse."""
    fuente = _fuente(tam)
    alto_linea = fuente.getbbox("Áyg")[3]
    por_item = [_envolver(item, fuente, ancho_max) for item in items]
    total = 0
    for lineas in por_item:
        total += len(lineas) * (alto_linea + interlinea) + gap
    return por_item, alto_linea, total


def tarjeta_info(titulo: str, items: list[str], lado: int = LADO) -> Image.Image:
    """Tarjeta de marca: banda naranja con titulo + lista de vinetas oscuras.

    El cuerpo se AUTO-AJUSTA: elige el mayor tamano de fuente (dentro de un
    rango) cuyo contenido entra completo sin chocar con el acento inferior."""
    lienzo = Image.new("RGBA", (lado, lado), BLANCO)
    dibujo = ImageDraw.Draw(lienzo)

    # Banda de titulo.
    banda_alto = _px(150)
    dibujo.rectangle([0, 0, lado, banda_alto], fill=NARANJA)
    f_titulo = _fuente(46)
    caja_t = dibujo.textbbox((0, 0), titulo, font=f_titulo)
    ty = (banda_alto - (caja_t[3] - caja_t[1])) // 2 - caja_t[1]
    dibujo.text((_px(50), ty), titulo, font=f_titulo, fill=BLANCO)

    # Area util del cuerpo (entre la banda y el acento inferior).
    x_punto, x_texto = _px(55), _px(100)
    ancho_max = lado - x_texto - _px(50)
    acento = _px(16)
    y_inicio = banda_alto + _px(45)
    alto_disponible = (lado - acento - _px(30)) - y_inicio

    # Elegir el mayor tamano que entra (de grande a chico); si nada entra, el min.
    interlinea, gap = _px(12), _px(20)
    for tam in range(38, 25, -2):
        por_item, alto_linea, total = _plan_vinetas(
            items, tam, ancho_max, interlinea, gap)
        if total <= alto_disponible:
            break

    # Dibujar las vinetas ya planificadas.
    y = y_inicio
    r_dot = _px(9)
    for lineas in por_item:
        dibujo.ellipse([x_punto, y + alto_linea * 0.30,
                        x_punto + r_dot * 2, y + alto_linea * 0.30 + r_dot * 2],
                       fill=NARANJA)
        f_item = _fuente(tam)
        for linea in lineas:
            dibujo.text((x_texto, y), linea, font=f_item, fill=OSCURO)
            y += alto_linea + interlinea
        y += gap

    # Acento inferior.
    dibujo.rectangle([0, lado - acento, lado, lado], fill=NARANJA)
    return lienzo


def construir_galeria(recorte_path: Path, datos: dict,
                      salida_dir: Path) -> list[Path]:
    """Genera la galeria (hero + tarjetas) como WebP 1080x1080. Devuelve rutas."""
    salida_dir.mkdir(parents=True, exist_ok=True)
    recorte = Image.open(recorte_path)

    piezas: list[tuple[str, Image.Image]] = [
        ("01-producto", hero_producto(recorte)),
    ]
    for i, tarjeta in enumerate(datos.get("tarjetas", []), start=2):
        img = tarjeta_info(tarjeta["titulo"], tarjeta["items"])
        piezas.append((f"{i:02d}-{tarjeta['slug']}", img))

    rutas: list[Path] = []
    for nombre, img in piezas:
        ruta = salida_dir / f"{nombre}.webp"
        img.convert("RGB").save(ruta, "WEBP", quality=90)
        rutas.append(ruta)
    return rutas


def contact_sheet(rutas: list[Path], salida: Path, cols: int = 4) -> Path:
    """Preview en cuadricula de todas las imagenes generadas, con su nombre."""
    thumb = 300
    pad, etiqueta = 16, 28
    filas = (len(rutas) + cols - 1) // cols
    ancho = cols * thumb + (cols + 1) * pad
    alto = filas * (thumb + etiqueta) + (filas + 1) * pad
    hoja = Image.new("RGB", (ancho, alto), GRIS_FONDO)
    dibujo = ImageDraw.Draw(hoja)
    f = ImageFont.truetype(RUTA_FUENTE, 20)
    for idx, ruta in enumerate(rutas):
        r, c = divmod(idx, cols)
        x = pad + c * (thumb + pad)
        y = pad + r * (thumb + etiqueta + pad)
        with Image.open(ruta) as im:
            img = im.convert("RGB").resize((thumb, thumb), Image.LANCZOS)
        hoja.paste(img, (x, y))
        dibujo.text((x, y + thumb + 4), ruta.stem, font=f, fill=OSCURO)
    hoja.save(salida, "PNG")
    return salida


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera la galeria de un producto (foto real + tarjetas info).")
    parser.add_argument("recorte", help="PNG del recorte limpio del producto")
    parser.add_argument("--datos", required=True, help="JSON con las tarjetas")
    parser.add_argument("--salida-dir", required=True, help="Carpeta de salida")
    parser.add_argument("--preview", default=None, help="PNG de contact-sheet")
    args = parser.parse_args()

    datos = json.loads(Path(args.datos).read_text(encoding="utf-8"))
    rutas = construir_galeria(Path(args.recorte), datos, Path(args.salida_dir))
    for r in rutas:
        print("IMG:", r)
    if args.preview:
        contact_sheet(rutas, Path(args.preview))
        print("PREVIEW:", args.preview)


if __name__ == "__main__":
    main()
