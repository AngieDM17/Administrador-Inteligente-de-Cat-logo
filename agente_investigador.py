"""Agente Investigador headless (Fase 2a).

Reemplaza, para links NO-Alibaba, que YO (Claude, en un chat de Claude Code
sincrono) siga a mano `investigador_v0.3/investigador-ekipon/SKILL.md`. Corre
como parte del servicio local (`app.py`): recibe un link, investiga el
producto con tools de navegador propias (`herramientas_navegador.py`) y
devuelve una ficha v1.4 valida contra `esquema_ficha.FichaEkipon`, lista para
que `orquestador.ejecutar_pipeline()` la consuma tal cual.

Fase 2a = SOLO links NO-Alibaba (extraccion web directa, "sin trabas": sin
sesion logueada, sin CAPTCHA). Alibaba es Fase 2b: perfil propio y
persistente de Playwright + pausa real de CAPTCHA via SSE -- QUEDA DISEÑADA
en el plan, NO IMPLEMENTADA aca. `investigar_producto()` detecta un link de
Alibaba y lo rechaza con un motivo claro en vez de intentarlo a ciegas (la
extraccion automatica de Alibaba esta bloqueada de fabrica, ver
reglas_negocio.md regla 5).

Modelo del agente: ver MODELO_AGENTE mas abajo -- el de mejor razonamiento/
vision disponible, a proposito NO el economico de redactor_ia.py
(claude-haiku-4-5): aca el trabajo es el mismo tipo de juicio fino
("rasgos estructurales, nunca color"; anti-contaminacion de fuentes sucias)
que genero los bugs reales que SKILL.md existe para prevenir.

--- Hallazgo real de esta sesion (verificado corriendo el paquete instalado
de PyPI, NO de la documentacion, que la investigacion previa pudo haber
resumido de forma incompleta) ---

`claude_agent_sdk` NO habla con la API de Anthropic directo: internamente
lanza el binario nativo del CLI de Claude Code (`claude`) como subproceso
(ver `claude_agent_sdk/_internal/transport/subprocess_cli.py`) y le pasa
`ANTHROPIC_API_KEY` por variable de entorno para que el CLI use auth por
clave de API en vez de login OAuth. Osea que "standalone, sin necesitar
Claude Code activo" es correcto en el sentido de "sin sesion de Claude Code
logueada / sin suscripcion" -- pero SI hace falta tener el CLI de Claude
Code INSTALADO Y FUNCIONAL en la maquina (`npm install -g
@anthropic-ai/claude-code`, con su postinstall del binario nativo corrido
bien), ademas del paquete de PyPI `claude-agent-sdk`. En la maquina de esta
sesion el binario esta presente en el PATH pero roto (postinstall no
completo): no bloquea esta tarea (no hay ANTHROPIC_API_KEY todavia para
probar igual), pero es un requisito real de infraestructura que el plan
original no dejaba tan explicito. Ver el reporte final de la sesion.

--- Verificacion ---

NO se prueba con la API real en unit tests (llamada de red paga que ademas
requiere el CLI de Claude Code instalado y funcional): ver
test_agente_investigador.py, que cubre solo la logica pura -- deteccion
link-vs-ruta-de-archivo, deteccion de dominio Alibaba, armado del
system_prompt (incluye el contenido real de SKILL.md leido del disco) y la
degradacion cuando falta la clave. Se verifica a mano/CLI con un link real
de una fuente no-Alibaba, cuando Angie de de alta su ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from cliente_tienda import cargar_env
from esquema_ficha import FichaEkipon

Notificador = Callable[[str], None]

CARPETA_PROYECTO = Path(__file__).parent
RUTA_ENV_DEFECTO = CARPETA_PROYECTO / ".env"
RUTA_SKILL = (
    CARPETA_PROYECTO / "investigador_v0.3" / "investigador-ekipon" / "SKILL.md"
)

# Modelo del agente investigador: el de mejor razonamiento/vision de la
# familia Claude actual (verificado 10-ago-2026 leyendo la lista de modelos
# que reconoce el paquete `anthropic` instalado en esta maquina --
# `claude-opus-5` es el Opus mas reciente de esa lista, no `claude-opus-4-5`
# que es una generacion anterior). A proposito NO es `claude-haiku-4-5` (el
# que usa redactor_ia.py: ahi la tarea es copywriting corto, aca es juicio
# de identificacion visual/anti-contaminacion).
MODELO_AGENTE = "claude-opus-5"

# Dominios de Alibaba/afines: Fase 2a los rechaza explicitamente. El Camino A
# del SKILL.md exige, para estos, sesion logueada + resolver un CAPTCHA a
# mano (Fase 2b, disenada en el plan, no construida todavia).
_DOMINIOS_ALIBABA = ("alibaba.com", "1688.com", "aliexpress.com")

_PATRON_URL = re.compile(r"^https?://", re.IGNORECASE)


class ErrorInvestigacion(Exception):
    """La investigacion no pudo completarse (SDK/CLI ausente, el agente
    termino con error, no devolvio ficha estructurada, etc). Mensaje ya en
    espanol, listo para publicar_notificacion / mostrar a Angie."""


def es_url(texto: str) -> bool:
    """True si `texto` parece un link (http/https) en vez de una ruta de
    archivo local. Logica pura, sin red: la usa app.py para decidir si
    corre este agente antes de orquestador.ejecutar_pipeline, o si va
    directo con la ruta de una ficha ya investigada (comportamiento de
    Fase 1, sin cambios)."""
    return bool(_PATRON_URL.match(texto.strip()))


def es_alibaba(url: str) -> bool:
    """True si el host de `url` es Alibaba/1688/AliExpress. Logica pura,
    sin red: compara el hostname (nunca la URL cruda, para no confundirse
    con un dominio que solo CONTENGA 'alibaba' en el path o la query)."""
    from urllib.parse import urlparse

    host = (urlparse(url.strip()).hostname or "").lower()
    return any(
        host == dominio or host.endswith("." + dominio)
        for dominio in _DOMINIOS_ALIBABA
    )


def _leer_skill() -> str:
    """Lee SKILL.md del disco tal cual -- nunca copiado a mano -- para que
    si el SKILL.md cambia algun dia, este agente no quede desincronizado.
    Lanza ErrorInvestigacion si no se encuentra: sin el no hay reglas de
    negocio que seguir, no tiene sentido investigar igual."""
    if not RUTA_SKILL.is_file():
        raise ErrorInvestigacion(
            f"No encuentro el SKILL.md del Investigador en '{RUTA_SKILL}': "
            "no hay reglas de negocio que seguir, no se puede investigar."
        )
    return RUTA_SKILL.read_text(encoding="utf-8")


# Apendice que traduce el modo SINCRONO del SKILL.md (escrito para un chat
# donde Angie contesta en el momento) al modo HEADLESS de este agente (nadie
# va a leer un mensaje y contestar). No reescribe ninguna regla de negocio
# de SKILL.md: solo cambia COMO se resuelve el "detente y confirma".
_APENDICE_MODO_HEADLESS = """

## Apendice — modo headless (Fase 2a, agente sin Angie en vivo)

Corres SIN Angie presente en tiempo real: nadie va a leer un mensaje tuyo y
contestarte en el momento. Donde el SKILL.md de arriba dice "detente hasta
que confirme" o pide definir algo CONVERSANDO con Angie (identificacion
dudosa, el par SI/NO de `criterio_verificacion_visual`, cualquier dato
incierto): en vez de detenerte, ANOTA la duda honestamente en
`identificacion_del_producto.advertencias` o en `campos_por_confirmar` de la
ficha final, con el mismo detalle que le hubieras dado en la conversacion, y
SEGUI investigando el resto. El revisor de listo-para-publicar
(`revisor_publicacion.py`) ya lee exactamente esos dos campos: CUALQUIER
entrada real ahi deja la ficha marcada REVISAR antes de publicarse -- anotar
la duda ES el mecanismo de "parar y preguntar" en este modo, no hace falta
que inventes otro.

Nunca inventes un dato con tal de completar un campo. Lo que no encuentres
se omite o va a campos_por_confirmar -- nunca se completa a ciegas ni con
un valor generico "tipico" del rubro.

La UNICA excepcion real es si la pagina exige iniciar sesion o resolver un
CAPTCHA: ahi no hay nada que puedas hacer en este modo (no tenes sesion
guardada ni manos para resolverlo). No lo intentes forzar, no inventes una
ficha igual: reporta el problema tal cual (la herramienta de navegar va a
devolver un error) y termina sin producir una ficha para ese link.

Recorda ademas, siempre (regla fija, no se relaja en este modo):
- El precio NUNCA se decide: precios.precio en null, precios.precio_origen
  con la marca PENDIENTE_ANGIE.
- El codigo de proveedor se compara con igualdad EXACTA de string
  (9060C != 9060: son productos distintos).
- MercadoLibre nunca es fuente de especificaciones tecnicas -- solo
  referencia de precio si aparece, y eso va a precios.referencias_mercado.
- No tenes ninguna herramienta para generar una imagen desde texto ni para
  editar una foto: solo para navegar una pagina, listar las imagenes reales
  que trae, y descargar una puntual. Toda imagen de la galeria que planifiques
  tiene que anclarse a una foto real descargada (regla del contrato de
  multimedia.plan_galeria).
"""


def _armar_system_prompt() -> str:
    """SKILL.md (leido del disco) + el apendice de arriba. Funcion propia
    -- no inline en _correr_agente -- para poder probarla con unit tests sin
    tocar la red ni el SDK: cualquier cambio que rompa la lectura del
    SKILL.md o pierda el apendice se detecta ahi."""
    return _leer_skill() + _APENDICE_MODO_HEADLESS


def _clave_api() -> str | None:
    """Mismo patron que redactor_ia._clave_api() / voz_en_off._clave_api():
    lee ANTHROPIC_API_KEY del .env del proyecto via cargar_env() de
    cliente_tienda.py (nunca os.environ directo). None si falta o esta
    vacia -- la senal que usa investigar_producto() para no intentar
    correr el agente sin clave."""
    env = cargar_env(RUTA_ENV_DEFECTO)
    clave = env.get("ANTHROPIC_API_KEY", "").strip()
    return clave or None


def _slug_codigo(ficha: dict) -> str:
    """codigo_proveedor de la ficha recien producida, saneado para nombre
    de archivo (letras/numeros/guion/guion bajo; el resto se descarta).
    Cae a 'producto' si la ficha no trae codigo -- nunca deja el nombre de
    archivo vacio. Logica pura."""
    entrada = ficha.get("entrada_original") or {}
    codigo = str(entrada.get("codigo_proveedor") or "").strip()
    limpio = re.sub(r"[^A-Za-z0-9_-]+", "_", codigo).strip("_")
    return limpio or "producto"


async def _correr_agente(link: str, carpeta_destino: Path,
                          publicar_notificacion: Notificador,
                          clave: str) -> dict | None:
    """Corre claude_agent_sdk.query() con las tools de navegador propias y
    el output_format del contrato v1.4. Import diferido de
    claude_agent_sdk/herramientas_navegador: asi quien solo usa el camino
    de Fase 1 (ficha ya investigada, sin agente) no paga el costo de
    importarlos, y si faltan, el error queda acotado a este agente."""
    from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query, tool

    import herramientas_navegador as nav

    @tool(
        "navegar",
        "Abre una URL de producto y devuelve el texto visible de la pagina "
        "(sin marcado HTML), para leer specs/descripcion/precio.",
        {"url": str},
    )
    async def _tool_navegar(args: dict) -> dict:
        try:
            texto = await asyncio.to_thread(nav.navegar, args["url"])
        except nav.ErrorRecurso as error:
            return {
                "content": [{"type": "text", "text": f"ERROR: {error}"}],
                "is_error": True,
            }
        return {"content": [{"type": "text", "text": texto}]}

    @tool(
        "extraer_imagenes",
        "Devuelve la lista de URLs de imagenes REALES encontradas en una "
        "pagina de producto (para elegir cuales descargar).",
        {"url": str},
    )
    async def _tool_extraer_imagenes(args: dict) -> dict:
        try:
            urls = await asyncio.to_thread(nav.extraer_imagenes, args["url"])
        except nav.ErrorRecurso as error:
            return {
                "content": [{"type": "text", "text": f"ERROR: {error}"}],
                "is_error": True,
            }
        return {"content": [{"type": "text", "text": json.dumps(urls, ensure_ascii=False)}]}

    @tool(
        "descargar_imagen",
        "Descarga una imagen real (por su URL) a un archivo dentro de la "
        "carpeta del producto. nombre_archivo va SIN ruta, solo el nombre "
        "(ej. '9060C_foto_1.jpg').",
        {"url_imagen": str, "nombre_archivo": str},
    )
    async def _tool_descargar_imagen(args: dict) -> dict:
        # Path(...).name descarta cualquier componente de ruta que venga en
        # nombre_archivo: la descarga nunca puede salir de carpeta_destino.
        nombre = Path(args["nombre_archivo"]).name
        if not nombre:
            return {
                "content": [{"type": "text", "text": "ERROR: nombre_archivo vacio."}],
                "is_error": True,
            }
        destino = carpeta_destino / nombre
        try:
            await asyncio.to_thread(nav.descargar_imagen, args["url_imagen"], destino)
        except nav.ErrorRecurso as error:
            return {
                "content": [{"type": "text", "text": f"ERROR: {error}"}],
                "is_error": True,
            }
        return {"content": [{"type": "text", "text": f"Guardada como {destino.name}"}]}

    servidor = create_sdk_mcp_server(
        name="navegador_ekipon",
        tools=[_tool_navegar, _tool_extraer_imagenes, _tool_descargar_imagen],
    )
    nombres_tools = [
        "mcp__navegador_ekipon__navegar",
        "mcp__navegador_ekipon__extraer_imagenes",
        "mcp__navegador_ekipon__descargar_imagen",
    ]

    opciones = ClaudeAgentOptions(
        system_prompt=_armar_system_prompt(),
        mcp_servers={"navegador_ekipon": servidor},
        # tools=[] apaga el set de herramientas por defecto de Claude Code
        # (Bash, Read, Write, Edit, WebSearch, etc: --tools ""). Este agente
        # SOLO navega y descarga fotos reales -- nunca debe poder tocar el
        # filesystem de Angie ni correr comandos por su cuenta.
        tools=[],
        allowed_tools=nombres_tools,
        # bypassPermissions: en modo headless no hay nadie que apruebe un
        # prompt de permiso (se colgaria esperando para siempre). El riesgo
        # que eso normalmente cubre ya esta acotado arriba: tools=[] + solo
        # 3 tools propias, de solo-lectura salvo escribir DENTRO de
        # carpeta_destino.
        permission_mode="bypassPermissions",
        model=MODELO_AGENTE,
        env={"ANTHROPIC_API_KEY": clave},
        output_format={
            "type": "json_schema",
            "schema": FichaEkipon.model_json_schema(),
        },
    )

    publicar_notificacion(f"Investigando el producto: {link}")
    resultado_estructurado: dict | None = None
    ultimo_mensaje_error: str | None = None

    async for mensaje in query(
        prompt=(
            "Investiga este producto siguiendo el SKILL.md y el apendice de "
            "arriba, y arma su ficha v1.4 completa. Camino A (con link): "
            "extrae directo de la fuente. Link del producto:\n\n"
            f"{link}\n\n"
            "Guarda este mismo link en entrada_original.link_producto."
        ),
        options=opciones,
    ):
        tipo = type(mensaje).__name__
        if tipo == "ResultMessage":
            resultado_estructurado = getattr(mensaje, "structured_output", None)
            if getattr(mensaje, "is_error", False):
                ultimo_mensaje_error = str(
                    getattr(mensaje, "result", None) or "sin detalle"
                )

    if ultimo_mensaje_error is not None:
        raise ErrorInvestigacion(
            f"El agente investigador termino con error: {ultimo_mensaje_error}"
        )
    return resultado_estructurado


def investigar_producto(link: str, carpeta_destino: Path,
                         publicar_notificacion: Notificador) -> dict:
    """Punto de entrada sincrono (mismo criterio que el resto del pipeline:
    orquestador.py y sus pasos son funciones sincronas, llamadas desde el
    hilo de fondo de app.py -- ver _correr_pipeline). Investiga `link` con
    el agente headless, valida el resultado contra FichaEkipon, y si es
    valido guarda la ficha (+ las fotos reales que el agente haya
    descargado) en `carpeta_destino`.

    Devuelve SIEMPRE uno de estos dos dicts, nunca lanza:

      {"estado": "ficha_lista", "ruta_ficha": Path}  -> exito
      {"estado": "error", "motivo": str}               -> fallo (Alibaba,
                                                           sin clave, SDK/CLI
                                                           ausente, ficha
                                                           invalida, error
                                                           real del agente)

    Quien llama (app.py) decide que hacer con 'ficha_lista': encadenar hacia
    orquestador.ejecutar_pipeline(ruta_ficha, ...)."""
    link = link.strip()
    carpeta_destino = Path(carpeta_destino)

    if es_alibaba(link):
        motivo = (
            "Este link es de Alibaba: la Fase 2a de este agente todavia no "
            "lo soporta (Alibaba exige sesion logueada y resolver un "
            "CAPTCHA a mano -- eso es la Fase 2b, disenada pero no "
            "construida todavia). Investiga este producto a mano, como "
            "hoy."
        )
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}

    clave = _clave_api()
    if clave is None:
        motivo = (
            f"Falta ANTHROPIC_API_KEY en '{RUTA_ENV_DEFECTO}': no se puede "
            "correr el agente investigador. Da de alta la clave, o "
            "investiga este producto a mano como hoy."
        )
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}

    carpeta_destino.mkdir(parents=True, exist_ok=True)

    try:
        ficha = asyncio.run(
            _correr_agente(link, carpeta_destino, publicar_notificacion, clave)
        )
    except ErrorInvestigacion as error:
        publicar_notificacion(f"ERROR: {error}")
        return {"estado": "error", "motivo": str(error)}
    except ImportError as error:
        motivo = (
            "Falta claude-agent-sdk (o el CLI de Claude Code que usa por "
            f"debajo -- ver el modulo agente_investigador.py): {error}"
        )
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}
    except Exception as error:  # ultima red de seguridad: nunca se escapa
        # un traceback crudo hacia el hilo del servidor.
        motivo = f"El agente investigador fallo inesperadamente: {error}"
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}

    if not isinstance(ficha, dict):
        motivo = (
            "El agente investigador no devolvio una ficha estructurada "
            "(structured_output vacio o con un tipo inesperado)."
        )
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}

    publicar_notificacion("Validando la ficha contra el contrato v1.4...")
    try:
        FichaEkipon.model_validate(ficha)
    except ValidationError as error:
        motivo = (
            "La ficha que armo el agente no cumple el contrato v1.4 -- no "
            f"se guarda una ficha invalida: {error}"
        )
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}

    codigo = _slug_codigo(ficha)
    ruta_ficha = carpeta_destino / f"ficha_investigada_{codigo}.json"
    ruta_ficha.write_text(
        json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    publicar_notificacion(f"Ficha investigada guardada: {ruta_ficha.name}")

    return {"estado": "ficha_lista", "ruta_ficha": ruta_ficha}
