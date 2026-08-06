"""Generador automatico de la PORTADA/miniatura de video de producto Ekipon.

Es la miniatura de YouTube del video del producto (una imagen estatica, no el
video en si). A diferencia del banner de fotos (`generador_banner.py`, que
lleva titulo + descripcion + imagen), la portada solo agrega DOS cosas sobre
la plantilla fija de la categoria: el titulo del producto y su recorte
transparente. La plantilla ya trae integrado el fondo fotografico, el logo
EKIPON.CO, los sellos de "Pago Contra Entrega/Envios Gratis" y el grafico del
camion — no se dibuja nada de eso aqui.

Cada categoria tiene su propia plantilla PNG en `plantillas_portada/`; si la
categoria de la ficha no tiene plantilla propia, se usa la GENERICA de
respaldo (nunca se bloquea ni se falla por falta de plantilla especifica).

Reutiliza a proposito la caja de herramientas de texto/imagen de
`generador_banner.py` (auto-ajuste de fuente, envoltura, pegado del recorte)
en vez de duplicarla: este modulo solo aporta su propio layout (sin caja de
descripcion) y la tabla categoria -> plantilla.

Uso:  python generador_portada.py <ficha.json> <recorte.png> \
          [--plantilla otra.png] [--salida portada.png]

Codigos de salida: 0 = portada generada; 1 = ficha invalida (no cumple el
contrato); 2 = problema con un archivo (falta, no es imagen valida, fuente
ilegible o JSON invalido).
"""

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path

from PIL import ImageDraw

from generador_banner import (
    _TAM_REFERENCIA,
    ErrorRecurso,
    _abrir_imagen,
    _ancho_ref,
    _caja_px,
    ajustar_texto,
    cargar_ficha_validada,
    cerrar_en_frases,
    pegar_recorte,
    titulo_banner,
)
from recortar_producto import limpiar_halo

# Fuente del titulo de la portada: Anton (condensada, mayusculas gruesas),
# distinta de la Open Sans Bold que usa el banner de fotos — pedido de Angie
# (4-ago) para que la miniatura de video se lea mas "grito" a tamano chico.
RUTA_FUENTE_TITULO_PORTADA = str(Path(__file__).parent / "fonts" / "Anton-Regular.ttf")

# Bicolor del titulo (pedido de Angie, 4-ago): la PRIMERA palabra del titulo en
# naranja de marca (el mismo que usa generador_banner.py), el resto en negro.
# Reemplaza el ajuste previo que pintaba el titulo entero de naranja.
COLOR_PRIMERA_PALABRA_TITULO = "#FF4E03"

# ----------------------------------------------------------------------
# Layout de la portada en FRACCIONES del lienzo (x0, y0, x1, y1), 0..1.
# Valores iniciales calibrados contra las plantillas 1920x1080 entregadas
# (panel blanco arriba-izquierda para el titulo, zona de foto a la derecha);
# se afinan a mano sin tocar el codigo si Angie ajusta el diseno.
# ----------------------------------------------------------------------
CONFIG_PORTADA = {
    "fuente_titulo": RUTA_FUENTE_TITULO_PORTADA,
    "titulo": {
        "caja": (0.04, 0.14, 0.46, 0.62),
        "color": "#000000",       # color del resto del titulo (todo menos la 1ra palabra)
        "mayusculas": True,
        "tam_max_frac": 0.100,   # fraccion de la ALTURA del lienzo (Anton es mas ancha/pesada que Open Sans: se bajo de 0.110)
        "tam_min_frac": 0.040,
        "max_lineas": 3,
        "interlineado": 1.10,
        "alineacion": "center",
    },
    "recorte": {
        "caja": (0.56, 0.20, 0.98, 0.95),
        "anclaje": "center",
    },
}


# ----------------------------------------------------------------------
# Categoria -> plantilla. Tabla explicita de alias, sin fuzzy matching ni
# IA: predecible y facil de extender a mano cuando llegue una plantilla
# nueva. Lo que no matchea ninguna clave conocida cae al generico.
# ----------------------------------------------------------------------
CARPETA_PLANTILLAS = Path(__file__).parent / "plantillas_portada"
CATEGORIA_GENERICA = "generico"

PLANTILLAS_POR_CATEGORIA = {
    "agro": CARPETA_PLANTILLAS / "agro.png",
    "construccion": CARPETA_PLANTILLAS / "construccion.png",
    "industria": CARPETA_PLANTILLAS / "industria.png",
    "sillas_escritorios": CARPETA_PLANTILLAS / "sillas_escritorios.png",
    "gimnasio": CARPETA_PLANTILLAS / "gimnasio.png",
    "movilidad": CARPETA_PLANTILLAS / "movilidad.png",
    CATEGORIA_GENERICA: CARPETA_PLANTILLAS / "generico.png",
}

# Alias conocidos (ya normalizados: minusculas, sin tildes, "_" en vez de
# espacio) hacia las claves de PLANTILLAS_POR_CATEGORIA de arriba.
ALIAS_CATEGORIA = {
    "agro": "agro",
    "agricola": "agro",
    "agropecuario": "agro",
    "agropecuaria": "agro",
    "agroindustria": "agro",
    "agricultura": "agro",
    "construccion": "construccion",
    "obra": "construccion",
    "obras_civiles": "construccion",
    "industria": "industria",
    "industrial": "industria",
    "sillas_y_escritorios": "sillas_escritorios",
    "sillas_escritorios": "sillas_escritorios",
    "sillas": "sillas_escritorios",
    "escritorios": "sillas_escritorios",
    "gimnasio": "gimnasio",
    "gimnacio": "gimnasio",  # por si el typo original se cuela en algun dato
    "fitness": "gimnasio",
    "movilidad": "movilidad",
    "movilidad_electrica": "movilidad",
}


def _normalizar_categoria(texto: str) -> str:
    """Normaliza una categoria libre para buscarla en ALIAS_CATEGORIA: toma
    el primer tramo de una ruta tipo 'Industria > Equipos de Soldadura'
    (las categorias reales del Investigador llegan asi de seguido), le saca
    tildes y la pasa a minusculas con guion bajo en vez de espacio."""
    if not texto:
        return ""
    primer_tramo = re.split(r"[>/]", texto)[0]
    sin_tildes = unicodedata.normalize("NFKD", primer_tramo)
    sin_tildes = sin_tildes.encode("ascii", "ignore").decode("ascii")
    return "_".join(sin_tildes.strip().lower().split())


def plantilla_portada(datos: dict) -> Path:
    """Ruta de la plantilla que corresponde a la categoria de la ficha, o la
    generica si la categoria esta vacia o no tiene plantilla propia."""
    categoria = (datos.get("producto") or {}).get("categoria_propuesta") or ""
    clave = ALIAS_CATEGORIA.get(_normalizar_categoria(categoria), CATEGORIA_GENERICA)
    return PLANTILLAS_POR_CATEGORIA[clave]


# ----------------------------------------------------------------------
# Dibujo del titulo bicolor (propio de la portada: no toca dibujar_bloque en
# generador_banner.py, que el banner de fotos sigue usando con un solo color).
# ----------------------------------------------------------------------

def dibujar_titulo_portada(lienzo, texto: str, caja_px, cfg: dict) -> None:
    """Dibuja el titulo de la portada igual que dibujar_bloque() (mismo
    auto-ajuste de tamano y misma envoltura en lineas, reutilizando las
    funciones de bajo nivel de generador_banner.py) pero en DOS colores: la
    PRIMERA palabra del titulo completo (la primera palabra de la primera
    linea) en cfg["color_primera_palabra"], y todas las demas palabras (en
    cualquier linea) en cfg["color"]. Respeta la alineacion center/justify
    tal como la calcula dibujar_bloque."""
    if not texto:
        return
    if cfg.get("mayusculas"):
        texto = texto.upper()
    x0, y0, x1, y1 = caja_px
    alto = lienzo.height
    tam_max = round(cfg["tam_max_frac"] * alto)
    tam_min = round(cfg["tam_min_frac"] * alto)
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
    color_resto = cfg["color"]
    color_primera = cfg.get("color_primera_palabra", color_resto)
    es_primera_palabra_global = True  # solo la 1ra palabra de TODO el titulo
    y = y0
    for indice, linea in enumerate(lineas):
        palabras = linea.split(" ")
        es_ultima = indice == len(lineas) - 1
        if cfg["alineacion"] == "justify" and len(palabras) > 1 and not es_ultima:
            anchos = [_ancho_ref(ruta_fuente, p) * ratio for p in palabras]
            hueco = ((x1 - x0) - sum(anchos)) / (len(palabras) - 1)
            x = x0
            for palabra, ancho in zip(palabras, anchos):
                color = color_primera if es_primera_palabra_global else color_resto
                dibujo.text((x, y), palabra, font=fuente, fill=color)
                es_primera_palabra_global = False
                x += ancho + hueco
        else:
            if cfg["alineacion"] == "center":
                x = x0 + ((x1 - x0) - fuente.getlength(linea)) // 2
            else:
                x = x0
            espacio = fuente.getlength(" ")
            for palabra in palabras:
                color = color_primera if es_primera_palabra_global else color_resto
                dibujo.text((x, y), palabra, font=fuente, fill=color)
                es_primera_palabra_global = False
                x += fuente.getlength(palabra) + espacio
        y += alto_linea


# ----------------------------------------------------------------------
# Composicion completa.
# ----------------------------------------------------------------------

def componer_portada(ruta_plantilla: Path, datos: dict, ruta_recorte: Path,
                     config: dict = None) -> "Image.Image":
    """Devuelve la portada compuesta (RGBA) del tamano de la plantilla."""
    config = config or CONFIG_PORTADA
    lienzo = _abrir_imagen(ruta_plantilla, "la plantilla").convert("RGBA")
    ancho, alto = lienzo.width, lienzo.height

    recorte = limpiar_halo(_abrir_imagen(ruta_recorte, "el recorte"))
    pegar_recorte(lienzo, recorte, _caja_px(config["recorte"]["caja"], ancho, alto),
                  config["recorte"].get("anclaje", "center"))

    cfg_titulo = dict(config["titulo"], _fuente_path=config["fuente_titulo"],
                      color_primera_palabra=COLOR_PRIMERA_PALABRA_TITULO)
    dibujar_titulo_portada(lienzo, titulo_banner(datos),
                           _caja_px(config["titulo"]["caja"], ancho, alto), cfg_titulo)
    return lienzo


def generar_a_archivo(datos: dict, ruta_recorte: Path, ruta_salida: Path,
                      ruta_plantilla: Path = None) -> Path:
    """Compone la portada y la guarda como PNG. Devuelve la ruta de salida.
    Pensada para que el Publicador la use sin pasar por el CLI. Si no se pasa
    plantilla, se elige sola por la categoria de la ficha (con respaldo
    generico). Lanza ErrorRecurso si la plantilla o el recorte no se pueden
    leer."""
    ruta_plantilla = ruta_plantilla or plantilla_portada(datos)
    portada = componer_portada(ruta_plantilla, datos, ruta_recorte)
    # Guardado atomico (mismo patron que main()): si el proceso muere a mitad
    # de guardado, no queda un PNG corrupto pisando uno previo valido. Esta es
    # la funcion que usa el Publicador en produccion, asi que el resguardo
    # tiene que vivir aca y no solo en el CLI.
    temporal = Path(str(ruta_salida) + ".tmp")
    portada.convert("RGB").save(temporal, "PNG")
    os.replace(temporal, ruta_salida)
    return ruta_salida


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Genera la portada/miniatura de video de un producto a "
        "partir de su ficha, la plantilla de su categoria y el recorte del "
        "producto."
    )
    parser.add_argument("ruta_ficha", help="ruta al .json de la ficha")
    parser.add_argument("ruta_recorte", help="PNG transparente del producto")
    parser.add_argument("--plantilla", default=None,
                        help="PNG de plantilla a usar (default: la de la "
                        "categoria de la ficha, o la generica si no matchea)")
    parser.add_argument("--salida", default=None,
                        help="PNG de salida (default: <codigo>_portada.png)")
    args = parser.parse_args()

    ruta_ficha = Path(args.ruta_ficha).resolve()
    ruta_recorte = Path(args.ruta_recorte).resolve()
    if not ruta_recorte.is_file():
        print(f"ERROR DE ARCHIVO: no existe el recorte: {ruta_recorte}")
        sys.exit(2)

    datos = cargar_ficha_validada(ruta_ficha)

    ruta_plantilla = Path(args.plantilla).resolve() if args.plantilla else plantilla_portada(datos)
    if not ruta_plantilla.is_file():
        print(f"ERROR DE ARCHIVO: no existe la plantilla: {ruta_plantilla}")
        sys.exit(2)

    print(f"Titulo de la portada: {titulo_banner(datos)}")
    print(f"Plantilla usada: {ruta_plantilla.name}")
    salida = Path(args.salida).resolve() if args.salida else ruta_ficha.with_name(
        f"{ruta_ficha.stem}_portada.png"
    )
    # Guardado atomico: se escribe a un temporal y se renombra al final, para
    # no dejar un PNG a medias si algo falla (no se pisa una portada previa
    # valida).
    temporal = salida.with_name(salida.name + ".tmp")
    try:
        portada = componer_portada(ruta_plantilla, datos, ruta_recorte)
        portada.convert("RGB").save(temporal, "PNG")
        os.replace(temporal, salida)
    except ErrorRecurso as error:
        print(f"ERROR DE ARCHIVO: {error}")
        sys.exit(2)
    except OSError as error:
        temporal.unlink(missing_ok=True)
        print(f"ERROR DE ARCHIVO: no se pudo guardar la portada en '{salida}': {error}")
        sys.exit(2)
    print(f"Portada generada: {salida}  ({portada.width}x{portada.height})")


if __name__ == "__main__":
    main()
