"""Generador automatico de banners de producto Ekipon (etapa Imagenes).

Compone, sobre la plantilla FIJA de Canva (exportada una vez como PNG), los
tres unicos datos que cambian por producto: titulo, descripcion corta e
imagen del producto (recorte transparente). Asi el banner que hoy se hace a
mano en Canva se genera solo, a partir de la ficha del Investigador.

Uso:  python generador_banner.py <ficha.json> <recorte.png> \
          [--plantilla chrome.png] [--salida banner.png]

El recorte debe ser un PNG con fondo transparente (Angie lo recorta en Canva).
El layout (posiciones, tamanos, colores) vive en CONFIG_BANNER como FRACCIONES
del lienzo (0..1), asi se adapta a cualquier tamano de plantilla y se afina sin
tocar el codigo.

Codigos de salida: 0 = banner generado; 1 = ficha invalida (no cumple el
contrato); 2 = problema con un archivo (falta, no es imagen valida, fuente
ilegible o JSON invalido).
"""

import argparse
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from esquema_ficha import FichaEkipon  # noqa: F401  (valida al cargar la ficha)
from publicador import limpiar_valor_publico
from validar_ficha import cargar_json, describir_error


class ErrorRecurso(Exception):
    """No se pudo leer un recurso del banner (plantilla, recorte o fuente).
    Se traduce a un mensaje claro y salida 2, no a un traceback."""

# Fuente del banner: Open Sans Bold (la que usa Angie en Canva), incluida en el
# repo para que el banner sea reproducible sin depender de fuentes del sistema.
RUTA_FUENTE = str(Path(__file__).parent / "fonts" / "OpenSans-Bold.ttf")

# Separadores donde se corta el nombre largo para el titulo del banner.
_SEPARADORES_TITULO = ("–", "—", "|", "+", " - ")

# Layout del banner en FRACCIONES del lienzo (x0, y0, x1, y1), 0..1.
# Valores iniciales para un lienzo cuadrado; se afinan contra la plantilla real.
#   alineacion del texto: "left" | "center" | "justify"
#   anclaje de la imagen:  "center" | "bottom"
CONFIG_BANNER = {
    "fuente_titulo": RUTA_FUENTE,
    "fuente_descripcion": RUTA_FUENTE,
    "titulo": {
        "caja": (0.06, 0.06, 0.62, 0.30),
        "color": "#FF4E03",
        "mayusculas": True,
        "tam_max_frac": 0.090,   # fraccion de la ALTURA del lienzo
        "tam_min_frac": 0.045,
        "max_lineas": 3,
        "interlineado": 1.04,
        "alineacion": "left",
    },
    "descripcion": {
        "caja": (0.06, 0.32, 0.60, 0.64),
        "color": "#FFFFFF",
        "mayusculas": False,
        "tam_max_frac": 0.038,
        "tam_min_frac": 0.024,
        "max_lineas": 8,
        "interlineado": 1.18,
        "alineacion": "justify",
        "cerrar_frases": True,   # nunca cortar a mitad de oracion
    },
    "imagen": {
        "caja": (0.46, 0.26, 0.98, 0.82),
        "anclaje": "center",     # centro de la caja
    },
}


# ----------------------------------------------------------------------
# Texto: derivacion, medicion, envoltura y auto-ajuste (funciones puras).
# ----------------------------------------------------------------------

def titulo_banner(datos: dict) -> str:
    """Titulo corto para el banner: el nombre completo suele ser larguisimo
    (ej. el 4212), asi que se toma el primer segmento antes de un separador."""
    nombre = (datos.get("producto") or {}).get("nombre_propuesto") or ""
    corte = len(nombre)
    for sep in _SEPARADORES_TITULO:
        pos = nombre.find(sep)
        if pos != -1:
            corte = min(corte, pos)
    corto = nombre[:corte].strip() or nombre.strip()
    # Nunca mostrar marcas internas de origen en el banner publico.
    return limpiar_valor_publico(corto)


def descripcion_banner(datos: dict) -> str:
    """Texto del banner: usa 'descripcion_banner' (gancho corto) si la ficha la
    trae; si no, cae a la descripcion principal (que luego se cierra por frases
    para no cortar a mitad de oracion)."""
    corta = datos.get("descripcion_banner")
    if isinstance(corta, str) and corta.strip():
        texto = corta
    else:
        texto = datos.get("descripcion_principal") or ""
    # Limpiar marcas internas de origen antes de mostrarlo en el banner publico.
    return limpiar_valor_publico(" ".join(texto.split()))


def partir_en_frases(texto: str) -> list[str]:
    """Parte el texto en frases completas (cada una termina en . ! o ?)."""
    frases = re.findall(r".*?[.!?](?=\s|$)", texto, flags=re.S)
    return [f.strip() for f in frases if f.strip()] or [texto.strip()]


def _caja_px(caja_frac, ancho: int, alto: int) -> tuple[int, int, int, int]:
    """Convierte una caja en fracciones (0..1) a pixeles del lienzo."""
    x0, y0, x1, y1 = caja_frac
    return (round(x0 * ancho), round(y0 * alto), round(x1 * ancho), round(y1 * alto))


# Tamano de referencia para medir palabras UNA sola vez. Las metricas de una
# fuente escalan linealmente con el tamano, asi que el ancho a cualquier tamano
# se obtiene por proporcion — sin volver a medir (medir es caro sin Raqm).
_TAM_REFERENCIA = 64
_FUENTES: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
# Medir texto en este Pillow tiene un costo fijo alto por llamada (~25 ms, sin
# Raqm). Cacheamos el ancho de cada palabra a tamano de referencia para medir
# cada palabra UNA sola vez en todo el proceso; los demas tamanos se derivan
# por proporcion (las metricas escalan linealmente).
_ANCHOS_REF: dict[tuple[str, str], float] = {}
_METRICAS_FUENTE: dict[str, tuple[float, float]] = {}


def _fuente(fuente_path: str, tam: int) -> ImageFont.FreeTypeFont:
    """Devuelve la fuente al tamano pedido, cacheada (cargarla cuesta)."""
    clave = (fuente_path, tam)
    if clave not in _FUENTES:
        try:
            _FUENTES[clave] = ImageFont.truetype(fuente_path, tam)
        except OSError as error:
            raise ErrorRecurso(
                f"no se pudo leer la fuente '{fuente_path}': {error}."
            ) from error
    return _FUENTES[clave]


def _abrir_imagen(ruta: Path, que: str) -> Image.Image:
    """Abre y decodifica una imagen; error claro si falta o esta corrupta."""
    try:
        imagen = Image.open(ruta)
        imagen.load()  # fuerza la decodificacion para detectar archivos truncados
        return imagen
    except (OSError, UnidentifiedImageError) as error:
        raise ErrorRecurso(
            f"no se pudo abrir {que} '{ruta}': no es una imagen valida ({error})."
        ) from error


def _ancho_ref(fuente_path: str, palabra: str) -> float:
    """Ancho de una palabra a tamano de referencia, medido una sola vez."""
    clave = (fuente_path, palabra)
    if clave not in _ANCHOS_REF:
        _ANCHOS_REF[clave] = _fuente(fuente_path, _TAM_REFERENCIA).getlength(palabra)
    return _ANCHOS_REF[clave]


def _metricas(fuente_path: str, texto: str):
    """Devuelve (palabras, anchos_por_palabra, ancho_espacio, alto_linea) a
    tamano de referencia, reutilizando el cache para no volver a medir."""
    palabras = texto.split()
    anchos = {p: _ancho_ref(fuente_path, p) for p in set(palabras)}
    if fuente_path not in _METRICAS_FUENTE:
        fuente = _fuente(fuente_path, _TAM_REFERENCIA)
        _METRICAS_FUENTE[fuente_path] = (fuente.getlength(" "), fuente.getbbox("ÁygpQ")[3])
    espacio, alto = _METRICAS_FUENTE[fuente_path]
    return palabras, anchos, espacio, alto


def _envolver(palabras: list[str], anchos: dict, espacio: float, ancho_max: float) -> list[str]:
    """Envuelve por palabra usando anchos ya calculados (sin medir de nuevo)."""
    lineas, actual, ancho_actual = [], [], 0.0
    for palabra in palabras:
        extra = (espacio if actual else 0) + anchos[palabra]
        if actual and ancho_actual + extra > ancho_max:
            lineas.append(" ".join(actual))
            actual, ancho_actual = [palabra], anchos[palabra]
        else:
            actual.append(palabra)
            ancho_actual += extra
    if actual:
        lineas.append(" ".join(actual))
    return lineas


def _ajuste_a_tam(palabras, anchos_ref, espacio_ref, alto_ref, tam,
                  ancho_max, alto_max, max_lineas, interlineado):
    """Envuelve a ese tamano (por proporcion) y dice si entra en la caja.
    Devuelve (lineas, cabe). Unica formula de ajuste, usada por _entra y
    ajustar_texto para que no se dupliquen."""
    r = tam / _TAM_REFERENCIA
    anchos = {p: w * r for p, w in anchos_ref.items()}
    lineas = _envolver(palabras, anchos, espacio_ref * r, ancho_max)
    cabe = len(lineas) <= max_lineas and alto_ref * r * interlineado * len(lineas) <= alto_max
    return lineas, cabe


def _entra(texto: str, ancho_max: float, alto_max: float, fuente_path: str,
           tam: int, max_lineas: int, interlineado: float) -> bool:
    """¿El texto entra en la caja a ese tamano (dentro de max_lineas)?"""
    palabras, anchos_ref, espacio_ref, alto_ref = _metricas(fuente_path, texto)
    _, cabe = _ajuste_a_tam(palabras, anchos_ref, espacio_ref, alto_ref, tam,
                            ancho_max, alto_max, max_lineas, interlineado)
    return cabe


def cerrar_en_frases(texto: str, caja_px, fuente_path: str, tam_min: int,
                     max_lineas: int, interlineado: float) -> str:
    """Devuelve la mayor cantidad de frases COMPLETAS del inicio que entran en
    la caja (al tamano minimo). Evita cortar a mitad de oracion."""
    ancho_max, alto_max = caja_px[2] - caja_px[0], caja_px[3] - caja_px[1]
    frases = partir_en_frases(texto)
    for cantidad in range(len(frases), 0, -1):
        candidato = " ".join(frases[:cantidad])
        if _entra(candidato, ancho_max, alto_max, fuente_path, tam_min, max_lineas, interlineado):
            return candidato
    return texto  # ni una frase entra; ajustar_texto la recorta con elipsis


def ajustar_texto(texto: str, caja_px, fuente_path: str, tam_max: int,
                  tam_min: int, max_lineas: int, interlineado: float):
    """Encuentra la fuente mas grande (entre tam_min y tam_max) con la que el
    texto entra en la caja respetando max_lineas. Devuelve (fuente, lineas).

    Mide las palabras una sola vez (a tamano de referencia) y prueba cada
    tamano por proporcion — rapido aunque medir sea caro. Si ni con el minimo
    entra, recorta la ultima linea con elipsis.
    """
    x0, y0, x1, y1 = caja_px
    ancho_max, alto_max = x1 - x0, y1 - y0
    tam_min = max(1, tam_min)  # la fuente no admite tamano 0
    tam_max = max(tam_max, tam_min)  # el rango nunca queda vacio
    palabras, anchos_ref, espacio_ref, alto_ref = _metricas(fuente_path, texto)

    mejor = None
    for tam in range(tam_max, tam_min - 1, -1):
        lineas, cabe = _ajuste_a_tam(palabras, anchos_ref, espacio_ref, alto_ref,
                                     tam, ancho_max, alto_max, max_lineas, interlineado)
        if cabe:
            return _fuente(fuente_path, tam), lineas
        mejor = (tam, lineas)

    # No entro ni con el minimo: recortar a max_lineas con elipsis.
    tam, lineas = mejor
    fuente = _fuente(fuente_path, tam)
    lineas = lineas[:max_lineas]
    while lineas[-1] and fuente.getlength(lineas[-1] + "…") > ancho_max:
        ultima = lineas[-1]
        lineas[-1] = ultima.rsplit(" ", 1)[0] if " " in ultima else ultima[:-1]
    lineas[-1] = lineas[-1] + "…"
    return fuente, lineas


# ----------------------------------------------------------------------
# Dibujo sobre el lienzo.
# ----------------------------------------------------------------------

def dibujar_bloque(lienzo: Image.Image, texto: str, caja_px, cfg: dict) -> None:
    """Dibuja un bloque de texto (titulo o descripcion) con auto-ajuste."""
    if not texto:
        return
    if cfg.get("mayusculas"):
        texto = texto.upper()
    x0, y0, x1, y1 = caja_px
    alto = lienzo.height
    tam_max = round(cfg["tam_max_frac"] * alto)
    tam_min = round(cfg["tam_min_frac"] * alto)
    # Cerrar en frases completas antes de ajustar (nada de cortes a mitad).
    if cfg.get("cerrar_frases"):
        texto = cerrar_en_frases(texto, caja_px, cfg["_fuente_path"], tam_min,
                                 cfg["max_lineas"], cfg["interlineado"])
    fuente, lineas = ajustar_texto(
        texto, caja_px, cfg["_fuente_path"], tam_max, tam_min,
        cfg["max_lineas"], cfg["interlineado"],
    )
    dibujo = ImageDraw.Draw(lienzo)
    alto_linea = fuente.getbbox("ÁygpQ")[3] * cfg["interlineado"]
    ratio = fuente.size / _TAM_REFERENCIA
    ruta_fuente = cfg["_fuente_path"]
    y = y0
    for indice, linea in enumerate(lineas):
        palabras = linea.split(" ")
        es_ultima = indice == len(lineas) - 1
        # Justificado: repartir el sobrante entre las palabras (menos la ultima
        # linea, que se deja natural para que no quede rala).
        if cfg["alineacion"] == "justify" and len(palabras) > 1 and not es_ultima:
            anchos = [_ancho_ref(ruta_fuente, p) * ratio for p in palabras]
            hueco = ((x1 - x0) - sum(anchos)) / (len(palabras) - 1)
            x = x0
            for palabra, ancho in zip(palabras, anchos):
                dibujo.text((x, y), palabra, font=fuente, fill=cfg["color"])
                x += ancho + hueco
        else:
            if cfg["alineacion"] == "center":
                x = x0 + ((x1 - x0) - fuente.getlength(linea)) // 2
            else:
                x = x0
            dibujo.text((x, y), linea, font=fuente, fill=cfg["color"])
        y += alto_linea


def pegar_recorte(lienzo: Image.Image, recorte: Image.Image, caja_px, anclaje: str) -> None:
    """Escala el recorte para entrar en la caja (sin deformar) y lo pega
    respetando la transparencia."""
    x0, y0, x1, y1 = caja_px
    ancho_caja, alto_caja = x1 - x0, y1 - y0
    recorte = recorte.convert("RGBA")
    # Recortar los margenes transparentes: el producto suele venir centrado en
    # un lienzo grande, y sin esto quedaria chico con mucho aire alrededor.
    contenido = recorte.getbbox()
    if contenido:
        recorte = recorte.crop(contenido)
    escala = min(ancho_caja / recorte.width, alto_caja / recorte.height)
    nuevo = (max(1, round(recorte.width * escala)), max(1, round(recorte.height * escala)))
    recorte = recorte.resize(nuevo, Image.LANCZOS)
    if anclaje == "center":
        px = x0 + (ancho_caja - recorte.width) // 2
        py = y0 + (alto_caja - recorte.height) // 2
    else:  # bottom
        px = x0 + (ancho_caja - recorte.width) // 2
        py = y1 - recorte.height
    lienzo.alpha_composite(recorte, (px, py))


# ----------------------------------------------------------------------
# Composicion completa.
# ----------------------------------------------------------------------

def componer_banner(ruta_plantilla: Path, datos: dict, ruta_recorte: Path,
                    config: dict = None) -> Image.Image:
    """Devuelve el banner compuesto (RGBA) del tamano de la plantilla."""
    config = config or CONFIG_BANNER
    lienzo = _abrir_imagen(ruta_plantilla, "la plantilla").convert("RGBA")
    ancho, alto = lienzo.width, lienzo.height

    recorte = _abrir_imagen(ruta_recorte, "el recorte")
    pegar_recorte(lienzo, recorte, _caja_px(config["imagen"]["caja"], ancho, alto),
                  config["imagen"].get("anclaje", "center"))

    cfg_titulo = dict(config["titulo"], _fuente_path=config["fuente_titulo"])
    dibujar_bloque(lienzo, titulo_banner(datos),
                   _caja_px(config["titulo"]["caja"], ancho, alto), cfg_titulo)

    cfg_desc = dict(config["descripcion"], _fuente_path=config["fuente_descripcion"])
    dibujar_bloque(lienzo, descripcion_banner(datos),
                   _caja_px(config["descripcion"]["caja"], ancho, alto), cfg_desc)
    return lienzo


def cargar_ficha_validada(ruta_ficha: Path) -> dict:
    """Carga la ficha y la valida contra el contrato v1.4 (mismo inspector)."""
    from pydantic import ValidationError

    datos = cargar_json(ruta_ficha)
    try:
        FichaEkipon.model_validate(datos)
    except ValidationError as error:
        print("FICHA INVALIDA — no se genera el banner:")
        for numero, err in enumerate(error.errors(), start=1):
            print(f"  {numero}. {describir_error(err)}")
        sys.exit(1)
    return datos


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Genera el banner de un producto a partir de su ficha, la "
        "plantilla fija y el recorte del producto."
    )
    parser.add_argument("ruta_ficha", help="ruta al .json de la ficha")
    parser.add_argument("ruta_recorte", help="PNG transparente del producto")
    parser.add_argument("--plantilla", default="plantilla_banner.png",
                        help="PNG del chrome fijo (default: plantilla_banner.png)")
    parser.add_argument("--salida", default=None,
                        help="PNG de salida (default: <codigo>_banner.png)")
    args = parser.parse_args()

    ruta_ficha = Path(args.ruta_ficha).resolve()
    ruta_recorte = Path(args.ruta_recorte).resolve()
    ruta_plantilla = Path(args.plantilla).resolve()
    for ruta, que in ((ruta_recorte, "el recorte"), (ruta_plantilla, "la plantilla")):
        if not ruta.is_file():
            print(f"ERROR DE ARCHIVO: no existe {que}: {ruta}")
            sys.exit(2)

    datos = cargar_ficha_validada(ruta_ficha)
    print(f"Titulo del banner: {titulo_banner(datos)}")
    salida = Path(args.salida).resolve() if args.salida else ruta_ficha.with_name(
        f"{ruta_ficha.stem}_banner.png"
    )
    # Guardado atomico: se escribe a un temporal y se renombra al final, para
    # no dejar un PNG a medias si algo falla (no se pisa un banner previo valido).
    temporal = salida.with_name(salida.name + ".tmp")
    try:
        banner = componer_banner(ruta_plantilla, datos, ruta_recorte)
        banner.convert("RGB").save(temporal, "PNG")
        os.replace(temporal, salida)
    except ErrorRecurso as error:
        print(f"ERROR DE ARCHIVO: {error}")
        sys.exit(2)
    except OSError as error:
        temporal.unlink(missing_ok=True)
        print(f"ERROR DE ARCHIVO: no se pudo guardar el banner en '{salida}': {error}")
        sys.exit(2)
    print(f"Banner generado: {salida}  ({banner.width}x{banner.height})")


if __name__ == "__main__":
    main()
