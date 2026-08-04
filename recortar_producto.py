"""Automated product cutout (etapa Imagenes).

Removes the background from a product photo with rembg (isnet-general-use) and returns a
transparent RGBA cutout, optionally trimmed to the product's bounding box so the
result drops cleanly into the banner and gallery generators. This replaces the
manual Canva step in the pipeline.

Uso:  python recortar_producto.py <entrada.png> [--salida recorte.png]
                                   [--preview preview.png] [--margen 0.04]

Codigos de salida: 0 = recorte generado; 2 = archivo de entrada no encontrado.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


_NOMBRE_MODELO = "isnet-general-use"
_sesion_rembg = None


def quitar_fondo(imagen: Image.Image) -> Image.Image:
    """Devuelve la imagen con el fondo eliminado (RGBA transparente).

    Modelo: isnet-general-use, no el u2net por defecto de rembg. Angie detecto
    (4-ago-2026) que u2net deja parches de fondo SOLIDOS atrapados dentro de la
    silueta (ej. bajo el asiento de una maquina de gimnasio, reflejo de piso
    entre partes) -- no es un halo de borde (eso ya lo resuelve limpiar_halo),
    es una zona interior que el modelo no segmenta. Verificado corriendo los
    dos modelos sobre la misma foto de origen (leg press U3003B): u2net deja el
    parche, isnet-general-use no. Sesion cacheada: cargar el modelo (~180 MB)
    de nuevo por cada llamada seria carisimo en un lote grande."""
    # Import diferido: cargar rembg (y su modelo) solo cuando se usa de verdad.
    global _sesion_rembg
    from rembg import new_session, remove

    if _sesion_rembg is None:
        _sesion_rembg = new_session(_NOMBRE_MODELO)
    return remove(imagen.convert("RGBA"), session=_sesion_rembg)


def recortar_a_contenido(imagen: Image.Image, margen: float = 0.04) -> Image.Image:
    """Recorta la imagen RGBA a la caja del contenido no transparente, dejando
    un margen proporcional (0..1) alrededor para que no quede pegado al borde."""
    alpha = imagen.getchannel("A")
    caja = alpha.getbbox()
    if caja is None:
        return imagen  # todo transparente: nada que recortar
    izq, arr, der, aba = caja
    ancho, alto = der - izq, aba - arr
    pad_x = int(ancho * margen)
    pad_y = int(alto * margen)
    izq = max(0, izq - pad_x)
    arr = max(0, arr - pad_y)
    der = min(imagen.width, der + pad_x)
    aba = min(imagen.height, aba + pad_y)
    return imagen.crop((izq, arr, der, aba))


def limpiar_halo(imagen: Image.Image, umbral_claro: int = 170) -> Image.Image:
    """Quita el halo claro del borde. rembg deja el borde anti-aliased con alfa
    PARCIAL y color del fondo (claro) filtrado; sobre un banner oscuro se ve como
    un glow. Esos pixeles (alfa parcial + color claro) se vuelven transparentes.

    NO toca el producto: solo mira pixeles de alfa PARCIAL (el relleno solido,
    alfa 255, queda intacto -> el marco plateado no se erosiona), y solo los
    CLAROS, asi que un cable fino oscuro (color, no claro) no se pierde.

    Historia del umbral: arranco en 210 (casi-blanco) tras el banner del vertical
    press; Angie vio que en maquinas PLATEADAS (dip/chin) seguia el glow, porque
    su fringe cae en 170-210 (plateado), no en blanco. Bajado a 170 (30-jul-2026).
    Solo toca alfa parcial, asi que bajar el umbral no come el marco solido."""
    a = np.array(imagen.convert("RGBA"))
    alpha = a[:, :, 3]
    rgb_min = a[:, :, :3].min(axis=2)
    halo = (alpha > 0) & (alpha < 250) & (rgb_min > umbral_claro)
    a[halo, 3] = 0
    return Image.fromarray(a, "RGBA")


def generar_recorte(ruta_entrada: Path, ruta_salida: Path,
                    margen: float = 0.04) -> Image.Image:
    """Compone el recorte transparente y lo guarda como PNG. Devuelve la imagen."""
    original = Image.open(ruta_entrada)
    sin_fondo = quitar_fondo(original)
    sin_halo = limpiar_halo(sin_fondo)
    recorte = recortar_a_contenido(sin_halo, margen)
    recorte.save(ruta_salida, "PNG")
    return recorte


def _sobre_fondo(imagen: Image.Image, color: tuple) -> Image.Image:
    """Aplana una RGBA sobre un color solido (para previsualizar)."""
    fondo = Image.new("RGBA", imagen.size, color)
    return Image.alpha_composite(fondo, imagen).convert("RGB")


def generar_preview(original: Image.Image, recorte: Image.Image,
                    ruta_preview: Path) -> Path:
    """Preview lado a lado: original | recorte sobre blanco. Para revisar a ojo."""
    alto = 500
    def escalar(img: Image.Image) -> Image.Image:
        r = alto / img.height
        return img.resize((int(img.width * r), alto), Image.LANCZOS)

    izq = escalar(original.convert("RGB"))
    der = escalar(_sobre_fondo(recorte, (255, 255, 255, 255)))
    sep = 20
    lienzo = Image.new("RGB", (izq.width + der.width + sep, alto), (245, 245, 245))
    lienzo.paste(izq, (0, 0))
    lienzo.paste(der, (izq.width + sep, 0))
    lienzo.save(ruta_preview, "PNG")
    return ruta_preview


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recorta el fondo de una foto de producto con rembg.")
    parser.add_argument("entrada", help="Foto del producto (png/jpg/webp)")
    parser.add_argument("--salida", default=None,
                        help="PNG del recorte (default: <entrada>_recorte.png)")
    parser.add_argument("--preview", default=None,
                        help="PNG de preview lado a lado (opcional)")
    parser.add_argument("--margen", type=float, default=0.04,
                        help="Margen proporcional alrededor del producto (0..1)")
    args = parser.parse_args()

    ruta_entrada = Path(args.entrada)
    if not ruta_entrada.exists():
        print(f"ENTRADA NO ENCONTRADA: {ruta_entrada}")
        sys.exit(2)

    ruta_salida = Path(args.salida) if args.salida else \
        ruta_entrada.with_name(ruta_entrada.stem + "_recorte.png")

    recorte = generar_recorte(ruta_entrada, ruta_salida, args.margen)
    print(f"RECORTE: {ruta_salida}")

    if args.preview:
        original = Image.open(ruta_entrada)
        generar_preview(original, recorte, Path(args.preview))
        print(f"PREVIEW: {args.preview}")


if __name__ == "__main__":
    main()
