"""Redactor con IA del guion de voz en off y del prompt de musica de fondo
(etapa Video, orquestador Fase 1).

Dos funciones puras de cara afuera, ambas con la misma regla de degradacion:
si falta la clave de Anthropic o la llamada falla por CUALQUIER motivo (red,
limite de uso, clave invalida, SDK no instalado), devuelven None y NUNCA
lanzan. El orquestador (orquestador.py) cae entonces al camino automatico ya
existente: `cuerpo_manual=None` en voz_en_off.generar_a_archivo (recorte de la
ficha) y PROMPT_MUSICA_GENERICO para la musica.

Regla fija del negocio (reglas_negocio.md): la ficha tecnica nunca se infla.
`redactar_guion_voz` solo puede citar datos que YA estan en la ficha
(descripcion_principal, caracteristicas, ficha_tecnica) — el prompt se lo
prohibe explicitamente y la funcion no le pasa ningun otro campo interno
(advertencias, origenes) que pudiera filtrarse a un guion publico.

Modelo: claude-haiku-4-5 (el Haiku mas barato disponible) — tarea corta de
redaccion, no ameritaba un modelo mayor.

Lectura de la clave: mismo patron que voz_en_off._clave_api() /
musica._clave_api() (cargar_env de cliente_tienda.py sobre el .env del
proyecto), para no inventar un mecanismo nuevo de leer el .env.
"""

from __future__ import annotations

from pathlib import Path

import voz_en_off
from cliente_tienda import cargar_env

CARPETA_PROYECTO = Path(__file__).parent
RUTA_ENV_DEFECTO = CARPETA_PROYECTO / ".env"

MODELO = "claude-haiku-4-5"

# Presupuesto real del CUERPO del guion: el total que arma voz_en_off.
# armar_guion() menos las DOS apariciones de FRASE_FIJA (abre y cierra) y los
# dos espacios de union del join final — es el mismo calculo que hace
# armar_guion() puertas adentro cuando arma el guion automatico, no una
# aproximacion de "menos una FRASE_FIJA".
_OVERHEAD_FRASE_FIJA = 2 * len(voz_en_off.FRASE_FIJA) + 2
PRESUPUESTO_CUERPO_GUION = max(
    0, voz_en_off.PRESUPUESTO_CARACTERES_DEFECTO - _OVERHEAD_FRASE_FIJA
)

# Prompt de respaldo cuando no hay clave, la llamada falla, o la ficha no
# trae categoria: generico pero nunca vacio (musica.py exige un prompt).
PROMPT_MUSICA_GENERICO = (
    "energetic upbeat corporate background music, motivational, no vocals"
)

# Estilo musical por categoria: (fragmento en minusculas de la categoria, el
# tono que sugiere). Sirve de EJEMPLO al modelo, no de resultado final: la
# categoria real de la ficha puede no calzar exacto con ninguna fila, y ahi es
# donde el modelo adapta el tono en vez de un match rigido de substring.
_ESTILOS_POR_CATEGORIA = (
    ("gimnasio", "energetic powerful gym workout music, motivational, no vocals"),
    ("fitness", "energetic powerful gym workout music, motivational, no vocals"),
    ("construccion", "serious industrial construction background music, steady, no vocals"),
    ("obra", "serious industrial construction background music, steady, no vocals"),
    ("agro", "upbeat rural agricultural background music, warm, no vocals"),
    ("agricola", "upbeat rural agricultural background music, warm, no vocals"),
    ("industria", "driving industrial corporate background music, no vocals"),
    ("movilidad", "modern upbeat electric mobility background music, no vocals"),
    ("silla", "calm professional office background music, no vocals"),
    ("escritorio", "calm professional office background music, no vocals"),
)


def _clave_api() -> str | None:
    """Lee ANTHROPIC_API_KEY del .env del proyecto. Devuelve None si falta o
    esta vacia — NUNCA lanza: es la senal que usan ambas funciones publicas
    para degradar al camino automatico sin IA."""
    env = cargar_env(RUTA_ENV_DEFECTO)
    clave = env.get("ANTHROPIC_API_KEY", "").strip()
    return clave or None


def _datos_seguros_para_guion(ficha: dict) -> dict:
    """Extrae SOLO los campos con datos reales que el guion puede citar.

    A proposito no se le pasa la ficha completa al modelo: asi no puede
    citar (ni "inspirarse" en) campos internos como advertencias, origenes o
    campos_por_confirmar, que no son para el publico. Las claves de
    ficha_tecnica que empiezan con '_' (metadatos: _origen_global, _nota) se
    excluyen por el mismo motivo que texto_publico.limpiar_valor_publico las
    trata como no publicas."""
    producto = ficha.get("producto") or {}
    ficha_tecnica = ficha.get("ficha_tecnica") or {}
    return {
        "nombre": producto.get("nombre_propuesto") or "",
        "descripcion_principal": ficha.get("descripcion_principal") or "",
        "caracteristicas": [
            c for c in (ficha.get("caracteristicas") or []) if isinstance(c, str)
        ],
        "ficha_tecnica": {
            clave: valor
            for clave, valor in ficha_tecnica.items()
            if isinstance(clave, str) and not clave.startswith("_")
        },
    }


def redactar_guion_voz(ficha: dict) -> str | None:
    """Redacta el CUERPO del guion de voz en off (sin las FRASE_FIJA de
    apertura/cierre: esas las agrega voz_en_off.armar_guion aparte, y
    duplicarlas aca alargaria el guion mas alla del presupuesto medido).

    Usa SOLO datos reales de la ficha (descripcion_principal,
    caracteristicas, ficha_tecnica) — el prompt prohibe explicitamente
    inventar specs, en linea con la regla fija del negocio.

    Devuelve None si falta la clave, la ficha no trae nada real que citar, o
    la llamada falla por cualquier motivo (red, limite de uso, SDK ausente).
    NUNCA lanza. Quien llama pasa el resultado como `cuerpo_manual` a
    voz_en_off.generar_a_archivo(); con None, ese modulo cae solo a su
    recorte automatico de la ficha (comportamiento ya existente, sin cambios)."""
    clave = _clave_api()
    if clave is None:
        return None

    datos = _datos_seguros_para_guion(ficha)
    if not (datos["descripcion_principal"] or datos["caracteristicas"]):
        return None  # nada real de la ficha que el guion pueda citar

    prompt = (
        "Redacta el CUERPO de un guion de voz en off publicitario, en "
        "espanol colombiano neutro, para un video de producto de la tienda "
        "Ekipon. Presupuesto estricto: como maximo "
        f"{PRESUPUESTO_CUERPO_GUION} caracteres (contando espacios). Devuelve "
        "SOLO el texto del guion, sin comillas, sin titulo, sin "
        "explicaciones.\n\n"
        "REGLA FIJA E INQUEBRANTABLE: no inventes ninguna especificacion "
        "tecnica, medida, material, marca ni caracteristica que no este en "
        "los datos de abajo. Si los datos no alcanzan para llenar el "
        "presupuesto, escribe un guion mas corto: nunca rellenes con datos "
        "inventados ni genericos.\n\n"
        f"Producto: {datos['nombre']}\n"
        f"Descripcion: {datos['descripcion_principal']}\n"
        f"Caracteristicas: {' | '.join(datos['caracteristicas'])}\n"
        f"Ficha tecnica: {datos['ficha_tecnica']}\n"
    )

    try:
        from anthropic import Anthropic

        cliente = Anthropic(api_key=clave)
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = next(
            (bloque.text for bloque in respuesta.content if bloque.type == "text"),
            "",
        ).strip()
        return texto or None
    except Exception:
        # Cualquier fallo (red, limite de uso, clave invalida, SDK no
        # instalado) degrada a None: el camino automatico de voz_en_off
        # sigue funcionando sin este redactor.
        return None


def redactar_prompt_musica(ficha: dict) -> str | None:
    """Redacta el prompt de musica de fondo (en INGLES: lo exige
    cliente.music.compose() de ElevenLabs, ver musica.py) adaptado a la
    categoria del producto.

    Devuelve None si falta la clave, la ficha no trae categoria, o la
    llamada falla por cualquier motivo. Quien llama cae entonces a
    PROMPT_MUSICA_GENERICO."""
    clave = _clave_api()
    if clave is None:
        return None

    categoria = ((ficha.get("producto") or {}).get("categoria_propuesta") or "").strip()
    if not categoria:
        return None

    ejemplos = "\n".join(
        f"- {cat}: {estilo}" for cat, estilo in _ESTILOS_POR_CATEGORIA
    )
    prompt = (
        "Redacta un prompt de musica de fondo (en INGLES) para un video de "
        f"producto de la categoria '{categoria}' de una tienda de maquinaria "
        "y equipos industriales. El prompt es para un generador de musica "
        "por IA: describe genero, energia y animo, SIN letra/vocals. Una "
        "sola linea de texto, sin comillas, sin explicaciones.\n\n"
        "Ejemplos de tono por categoria (guia de referencia, no copiar "
        "literal si la categoria pedida es distinta):\n"
        f"{ejemplos}\n"
    )

    try:
        from anthropic import Anthropic

        cliente = Anthropic(api_key=clave)
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = next(
            (bloque.text for bloque in respuesta.content if bloque.type == "text"),
            "",
        ).strip()
        return texto or None
    except Exception:
        return None
