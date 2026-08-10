"""Redactor con IA del guion de voz en off y del prompt de musica de fondo
(etapa Video, orquestador Fase 1).

Dos funciones puras de cara afuera, ambas con la misma regla de degradacion:
si la llamada falla por CUALQUIER motivo (CLI de Claude Code ausente, sin
sesion iniciada, cupo agotado, red caida), devuelven None y NUNCA lanzan. El
orquestador (orquestador.py) cae entonces al camino automatico ya existente:
`cuerpo_manual=None` en voz_en_off.generar_a_archivo (recorte de la ficha) y
PROMPT_MUSICA_GENERICO para la musica.

Regla fija del negocio (reglas_negocio.md): la ficha tecnica nunca se infla.
`redactar_guion_voz` solo puede citar datos que YA estan en la ficha
(descripcion_principal, caracteristicas, ficha_tecnica) — el prompt se lo
prohibe explicitamente y la funcion no le pasa ningun otro campo interno
(advertencias, origenes) que pudiera filtrarse a un guion publico.

Modelo: claude-haiku-4-5 (el Haiku mas barato disponible) — tarea corta de
redaccion, no ameritaba un modelo mayor. Ademas, al ser el modelo mas rapido/
liviano, pisa MENOS la ventana de 5 horas compartida (ver mas abajo) que si
esto corriera con Opus.

--- Autenticacion: suscripcion de Claude Code, NO clave de API dedicada ---

Igual que agente_investigador.py: corre `claude_agent_sdk.query()` SIN pasar
`env={"ANTHROPIC_API_KEY": ...}`, asi el CLI de Claude Code que el SDK lanza
por debajo hereda el entorno del proceso padre y usa la sesion YA LOGUEADA en
esta maquina (la misma cuenta con la que Angie habla en el chat) en vez de
facturar por token de una clave de API aparte. El requisito real que sigue
en pie es tener el CLI instalado y con sesion iniciada (`claude login`) —
si falta, `_consultar_ia_sincrono` degrada a None como cualquier otro fallo.

OJO -- cupo compartido, no facturacion por uso: el limite es la ventana de
5 horas que Angie ya usa hablando con Claude Code normalmente
(`RateLimitEvent.rate_limit_type == 'five_hour'`). Si esto corre pesado
MIENTRAS Angie usa el chat, se pisan el mismo cupo — por eso el modelo mas
liviano (Haiku) y `max_turns=1` (una sola vuelta, sin loop agentico).
"""

from __future__ import annotations

import asyncio

import voz_en_off

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

# Prompt de respaldo cuando la llamada a la IA falla o la ficha no trae
# categoria: generico pero nunca vacio (musica.py exige un prompt).
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


async def _consultar_ia(prompt: str) -> str | None:
    """Corre claude_agent_sdk.query() con MODELO y devuelve el texto plano
    final (ResultMessage.result), o None si el SDK/CLI no esta disponible,
    no hay sesion iniciada, se agoto el cupo compartido, o cualquier otro
    fallo. NUNCA lanza -- funcion async interna, compartida por
    redactar_guion_voz y redactar_prompt_musica via _consultar_ia_sincrono.

    Sin system_prompt ni output_format: ambos prompts piden texto plano
    corto, no hace falta ninguno de los dos (a diferencia de
    agente_investigador.py, que si necesita el contrato de ficha v1.4).
    tools=[] + permission_mode='bypassPermissions': esto es copywriting de
    una sola vuelta, nunca debe poder tocar el filesystem ni colgarse
    esperando una aprobacion que nadie va a dar en modo headless."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except Exception:
        return None

    opciones = ClaudeAgentOptions(
        model=MODELO,
        permission_mode="bypassPermissions",
        tools=[],
        max_turns=1,
    )

    texto: str | None = None
    llego_resultado = False
    try:
        async for mensaje in query(prompt=prompt, options=opciones):
            if type(mensaje).__name__ == "ResultMessage":
                llego_resultado = True
                if not getattr(mensaje, "is_error", False):
                    texto = (str(getattr(mensaje, "result", None) or "")).strip() or None
                break
    except Exception:
        # Mismo mensaje de control espurio que agente_investigador.
        # _correr_agente atrapa tras un ResultMessage real (ver su
        # docstring): si ya se vio el resultado, se ignora; si revento
        # ANTES de ver ninguno (CLI ausente, sin sesion, cupo agotado, red
        # caida), degrada a None como cualquier otro fallo.
        if not llego_resultado:
            return None
    return texto


def _consultar_ia_sincrono(prompt: str) -> str | None:
    """Envoltorio sincrono de _consultar_ia -- mismo patron que
    agente_investigador.investigar_producto() envolviendo _correr_agente:
    redactar_guion_voz/redactar_prompt_musica son funciones sincronas (asi
    las llama orquestador.py), asyncio.run() cierra la brecha en un solo
    lugar en vez de en cada funcion publica. Cualquier excepcion que se
    escape igual degrada a None -- ninguna funcion publica de este modulo
    lanza nunca."""
    try:
        return asyncio.run(_consultar_ia(prompt))
    except Exception:
        return None


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

    Devuelve None si la ficha no trae nada real que citar, o la llamada
    falla por cualquier motivo (CLI de Claude Code ausente, sin sesion
    iniciada, cupo agotado, red caida). NUNCA lanza. Quien llama pasa el
    resultado como `cuerpo_manual` a voz_en_off.generar_a_archivo(); con
    None, ese modulo cae solo a su recorte automatico de la ficha
    (comportamiento ya existente, sin cambios)."""
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

    return _consultar_ia_sincrono(prompt)


def redactar_prompt_musica(ficha: dict) -> str | None:
    """Redacta el prompt de musica de fondo (en INGLES: lo exige
    cliente.music.compose() de ElevenLabs, ver musica.py) adaptado a la
    categoria del producto.

    Devuelve None si la ficha no trae categoria, o la llamada falla por
    cualquier motivo. Quien llama cae entonces a PROMPT_MUSICA_GENERICO."""
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

    return _consultar_ia_sincrono(prompt)
