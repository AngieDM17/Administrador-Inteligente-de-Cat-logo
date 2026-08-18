"""Agente Investigador headless (Fase 2a).

Reemplaza, para links NO-Alibaba, que YO (Claude, en un chat de Claude Code
sincrono) siga a mano `investigador_v0.3/investigador-ekipon/SKILL.md`. Corre
como parte del servicio local (`app.py`): recibe un link, investiga el
producto con tools de navegador propias (`herramientas_navegador.py`) y
devuelve una ficha v1.4 valida contra `esquema_ficha.FichaEkipon`, lista para
que `orquestador.ejecutar_pipeline()` la consuma tal cual.

Fase 2a = links NO-Alibaba (extraccion web directa, "sin trabas": sin
sesion logueada, sin CAPTCHA). Fase 2b (10-ago-2026, ver mas abajo) suma
Alibaba, con una ventana de Chrome VISIBLE y una pausa real para que Angie
resuelva login/CAPTCHA a mano.

Modelo del agente: ver MODELO_AGENTE mas abajo -- el de mejor razonamiento/
vision disponible, a proposito NO el economico de redactor_ia.py
(claude-haiku-4-5): aca el trabajo es el mismo tipo de juicio fino
("rasgos estructurales, nunca color"; anti-contaminacion de fuentes sucias)
que genero los bugs reales que SKILL.md existe para prevenir.

--- Autenticacion: suscripcion de Claude Code, NO clave de API (10-ago-2026) ---

Este agente corre `claude_agent_sdk.query()` SIN pasar
`env={"ANTHROPIC_API_KEY": ...}` a ClaudeAgentOptions -- a proposito. Sin esa
variable, el CLI de Claude Code que el SDK lanza por debajo (verificado
leyendo `claude_agent_sdk/_internal/transport/subprocess_cli.py`: el
subproceso hereda el entorno del proceso padre y SOLO agrega lo que venga en
`options.env`) usa la sesion YA LOGUEADA en esta maquina -- la misma cuenta
con la que Angie habla en el chat -- en vez de facturar por token de una
clave de API aparte. Confirmado corriendo exactamente esto en esta maquina:

    opciones = ClaudeAgentOptions(model='claude-opus-5',
                                   permission_mode='bypassPermissions')
    async for msg in query(prompt='responde solo con la palabra OK',
                            options=opciones):
        ...
    # resultado: is_error=False, result='OK' -- funciono, con Opus 5, en un
    # plan Pro (NO hace falta Max).

Sigue haciendo falta el CLI de Claude Code INSTALADO y con sesion iniciada
(`claude login`) -- eso NO cambio, solo dejo de exigir la clave de API. Si
el CLI falta o no hay sesion iniciada, `query()` falla con una excepcion del
SDK: `investigar_producto()` la atrapa y devuelve un mensaje claro en
espanol en vez de un traceback crudo (ver `_mensaje_claro_para_error_sdk`).

OJO -- cupo compartido, no facturacion por uso: el limite pasa a ser la
ventana de 5 horas que Angie ya usa hablando con Claude Code normalmente
(`RateLimitEvent.rate_limit_type == 'five_hour'`, verificado en esta misma
corrida). Si este agente investiga un producto MIENTRAS Angie usa el chat,
se pisan el mismo cupo -- no hay una cuenta de facturacion separada que lo
aisle.

--- Video (10-ago-2026) ---

Ademas de las 3 tools de imagen, este agente trae 2 tools de video sobre
herramientas_navegador.extraer_video/descargar_video, mismo patron exacto:
`extraer_video` detecta si la pagina publica un archivo real y descargable
(mp4/webm/...) o un embed de YouTube/Vimeo; `descargar_video` baja el
archivo real (nunca el embed) a la carpeta del producto. Si la fuente es
.mp4 real, el apendice de modo headless (mas abajo) le exige al agente
guardarlo con el nombre EXACTO '<codigo>_clip_original.mp4' -- ese es el
contrato literal que orquestador.py busca (`_ruta_clip_original`) antes de
poder armar el video final del producto. Scraping de YouTube/Vimeo queda
deliberadamente FUERA de alcance (zona gris de terminos de servicio): un
embed se anota en `multimedia.video_nota` para que Angie lo revise a mano,
nunca se descarga.

--- Alibaba / Fase 2b (10-ago-2026) ---

Ya NO se rechaza un link de Alibaba/1688/AliExpress. `_correr_agente`
detecta `es_alibaba(link)` y arma el MISMO set de 5 tools (mismos nombres,
mismo esquema -- el modelo no necesita saber la diferencia) sobre una
instancia de `navegador_alibaba.SesionAlibaba` en vez de las funciones
stateless de `herramientas_navegador.py`. Esa sesion abre una ventana de
Chromium VISIBLE (perfil propio y persistente en `navegador_perfil_alibaba/`,
gitignored -- nunca el Chrome real de Angie) y se detiene en la PRIMERA
pagina que abre en la corrida para que Angie resuelva a mano el login o el
CAPTCHA -- sin heuristica de deteccion, pausa siempre, una vez por corrida
(ver navegador_alibaba.py para el detalle completo del mecanismo).

El `threading.Event` que hace posible esa pausa/reanudacion vive en `app.py`
(uno por job, `_Job.evento_continuar`) y viaja hacia aca por el parametro
nuevo `evento_continuar` de `investigar_producto()` -- si no se pasa (ej.
tests, o quien llame sin necesitar Alibaba), se crea uno propio que nunca
se setea desde afuera; eso no afecta a un link no-Alibaba porque solo la
tool de Alibaba llega a esperarlo.

--- Verificacion ---

NO se prueba con la API real en unit tests (corrida real que gastaria cupo
de la suscripcion de Angie, y ademas requiere el CLI de Claude Code
instalado y con sesion iniciada): ver test_agente_investigador.py, que cubre
solo la logica pura -- deteccion link-vs-ruta-de-archivo, deteccion de
dominio Alibaba, armado del system_prompt (incluye el contenido real de
SKILL.md leido del disco) y la traduccion de errores del SDK/CLI a mensajes
en espanol. Se verifica a mano/CLI con un link real de una fuente
no-Alibaba. La ventana visible de Alibaba (Fase 2b) se prueba a mano, con
Angie presente frente a su computador -- no hay forma de probarla de punta
a punta en este entorno (ver navegador_alibaba.py y test_navegador_alibaba.py).
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from esquema_ficha import FichaEkipon

Notificador = Callable[[str], None]

CARPETA_PROYECTO = Path(__file__).parent
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

Para VIDEO (novedad 10-ago-2026) tenes dos herramientas mas: `extraer_video`
busca en la pagina un archivo real y descargable, o si no hay, un embed de
YouTube/Vimeo; `descargar_video` baja el archivo real a un archivo dentro de
la carpeta del producto. Igual que con las imagenes: nunca generes ni
inventes un video, solo bajas lo que YA existe real en la fuente. Reglas
exactas segun lo que devuelva `extraer_video`:

- `{"tipo": "archivo", "url": ...}` y la URL termina en `.mp4`: descargalo
  con `descargar_video` y guardalo con el nombre EXACTO
  `<codigo>_clip_original.mp4` (el mismo `codigo` que usas para el nombre
  de las fotos) -- ese nombre literal, sin sufijos ni cambios de extension,
  es lo que orquestador.py busca despues para armar el video final. Es la
  UNICA forma en la que el resto del pipeline encuentra el clip solo.
- `{"tipo": "archivo", "url": ...}` pero la URL NO termina en `.mp4` (ej.
  `.webm`, `.mov`): podes descargarlo igual, pero guardalo con su extension
  REAL (nunca renombres el contenido a `.mp4`: no es lo que dice ser) y
  anota en `multimedia.video_nota` que hay un video real ya descargado pero
  en otro formato, que hace falta convertirlo a mp4 a mano antes de que el
  orquestador lo encuentre -- no lo cuentes como resuelto.
- `{"tipo": "embed", "url": ...}` (YouTube/Vimeo): NO lo descargues bajo
  ninguna circunstancia -- scraping de esas plataformas queda fuera de
  alcance de este agente (zona gris de terminos de servicio, decision
  explicita, no la relajes "para que funcione mejor"). Anota la URL en
  `multimedia.video_nota` (ej. "La pagina tiene un video embebido de
  YouTube: <url> -- no se descarga automatico, revisar a mano si sirve").
- `null` (no hay ningun video, el caso mas comun): seguis reportandolo en
  `video_nota` tal como ya haces, sin inventar nada.

Si el link es de Alibaba/1688/AliExpress (novedad Fase 2b): las mismas 5
herramientas siguen funcionando igual, pero por debajo abren una ventana de
Chrome VISIBLE con sesion persistente. La PRIMERA llamada a `navegar` en una
corrida de Alibaba puede demorar varios MINUTOS -- esta esperando que Angie
resuelva a mano el login o un CAPTCHA desde esa ventana. Esto es NORMAL, no
es un error ni un timeout ni algo que reintentar o abortar: segui esperando
esa misma llamada, y cuando Angie confirme vas a recibir el texto de la
pagina como con cualquier otra fuente y seguis investigando igual.

Tres campos de `producto` tienen un FORMATO LITERAL fijo que el validador
del contrato v1.4 (esquema_ficha.py) exige exacto -- si no calzan asi, la
ficha entera se rechaza y no se guarda (verificado 10-ago-2026: una primera
corrida real fallo por esto exacto, no lo repitas):
- `sku`: el SKU real lo asigna WooCommerce, nunca vos. El valor tiene que
  EMPEZAR con el literal `AUTOMATICO` (podes agregar texto aclaratorio
  despues, ej. "AUTOMATICO — lo asigna el sistema al crear el producto").
  Nunca pongas ahi el codigo de proveedor ni el modelo.
- `garantia`: es politica FIJA de la tienda, no un dato de la fuente ni algo
  pendiente de Angie -- el texto tiene que CONTENER literal "1 año" (ej.
  "1 año de garantia del fabricante").
- `categoria_confianza`: es un campo de ORIGEN (como `nombre_origen`), no una
  etiqueta libre de confianza. Tiene que CONTENER uno de estos textos exactos:
  verificado | encontrado_web | generado_ia | generado_ia_sin_verificar |
  confirmado_por_angie | PENDIENTE_ANGIE. Si la categoria te la dio el arbol
  real de WooCommerce, es "verificado" o "encontrado_web"; si la inferiste
  vos del rubro del producto sin confirmarla contra la tienda, es
  "generado_ia_sin_verificar".
"""


def _armar_system_prompt() -> str:
    """SKILL.md (leido del disco) + el apendice de arriba. Funcion propia
    -- no inline en _correr_agente -- para poder probarla con unit tests sin
    tocar la red ni el SDK: cualquier cambio que rompa la lectura del
    SKILL.md o pierda el apendice se detecta ahi."""
    return _leer_skill() + _APENDICE_MODO_HEADLESS


def _mensaje_claro_para_error_sdk(error: Exception) -> str:
    """Traduce una excepcion cruda de claude_agent_sdk/CLI de Claude Code
    (CLI no instalado, sin sesion iniciada, cupo agotado, red caida, etc.)
    a un mensaje en espanol que Angie pueda leer y accionar -- nunca un
    traceback crudo. Compara por NOMBRE de tipo (`type(error).__name__`) en
    vez de importar claude_agent_sdk._errors a nivel de modulo: asi el
    camino de Alibaba (rechazo temprano, sin tocar el SDK) no paga el costo
    de ese import solo para poder reconocer sus excepciones."""
    tipo = type(error).__name__
    if tipo == "CLINotFoundError":
        return (
            "No encuentro el CLI de Claude Code instalado en esta maquina "
            "-- hace falta para que el agente investigador corra con tu "
            "suscripcion. Instalalo (`npm install -g @anthropic-ai/"
            "claude-code`) y confirma que `claude --version` funciona en "
            "una terminal."
        )
    return (
        "El agente investigador no pudo correr -- lo mas probable es que "
        "falte iniciar sesion del CLI de Claude Code en esta maquina. Corre "
        "`claude login` en una terminal y volve a intentar. (Detalle "
        f"tecnico: {tipo}: {error})"
    )


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
                          evento_continuar: threading.Event,
                          sesion_alibaba=None) -> dict | None:
    """Corre claude_agent_sdk.query() con las tools de navegador propias y
    el output_format del contrato v1.4. Import diferido de
    claude_agent_sdk/herramientas_navegador: asi quien solo usa el camino
    de Fase 1 (ficha ya investigada, sin agente) no paga el costo de
    importarlos, y si faltan, el error queda acotado a este agente.

    Si `es_alibaba(link)`, las 5 tools se arman sobre una instancia de
    `navegador_alibaba.SesionAlibaba` (ventana visible, pausa de
    login/CAPTCHA) en vez de las funciones stateless de
    `herramientas_navegador.py` -- mismos nombres de tool, misma firma:
    `fuente` es indistintamente el modulo o la sesion, el resto del codigo
    de abajo no necesita saber cual de los dos es.

    `sesion_alibaba`, si se pasa, es una instancia YA ABIERTA de
    `navegador_alibaba.SesionAlibaba` para REUSAR entre varias llamadas
    (lote_masivo.py: una sola sesion para todo el lote nocturno, asi el
    CAPTCHA/login de Alibaba se resuelve UNA vez, no una vez por producto
    -- ver SesionAlibaba._primera_navegacion, que solo pausa en la primera
    navegacion real de la instancia). En ese caso esta funcion NO la cierra
    al terminar -- la cierra quien la creo, al final del lote. Si no se
    pasa (comportamiento de siempre para un solo link), y el link es de
    Alibaba, se crea una sesion PROPIA que esta funcion SI cierra en su
    `finally`, igual que antes de este parametro."""
    from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query, tool

    import herramientas_navegador as nav

    _sesion_propia = None
    if es_alibaba(link):
        if sesion_alibaba is not None:
            fuente = sesion_alibaba
        else:
            import navegador_alibaba

            _sesion_propia = navegador_alibaba.SesionAlibaba(
                publicar_notificacion, evento_continuar,
            )
            fuente = _sesion_propia
    else:
        fuente = nav

    @tool(
        "navegar",
        "Abre una URL de producto y devuelve el texto visible de la pagina "
        "(sin marcado HTML), para leer specs/descripcion/precio.",
        {"url": str},
    )
    async def _tool_navegar(args: dict) -> dict:
        try:
            texto = await asyncio.to_thread(fuente.navegar, args["url"])
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
            urls = await asyncio.to_thread(fuente.extraer_imagenes, args["url"])
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
        "y SIN extension o con cualquiera (ej. '9060C_foto_1') -- la "
        "herramienta siempre la guarda como .webp de verdad, sin importar "
        "que formato tenia la fuente. Usa el nombre que devuelve el "
        "resultado (no el que pediste) para anotarla en la ficha.",
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
            # descargar_imagen() SIEMPRE devuelve .webp real (convierte el
            # contenido, no solo renombra) -- ver su docstring, bug real
            # 14-ago-2026 de un .jpg que en realidad era PNG. La ruta final
            # puede diferir de `destino` si nombre_archivo no terminaba en
            # .webp; se reporta la real para que el agente la use en la ficha.
            ruta_final = await asyncio.to_thread(
                fuente.descargar_imagen, args["url_imagen"], destino
            )
        except nav.ErrorRecurso as error:
            return {
                "content": [{"type": "text", "text": f"ERROR: {error}"}],
                "is_error": True,
            }
        return {"content": [{"type": "text", "text": f"Guardada como {ruta_final.name}"}]}

    @tool(
        "extraer_video",
        "Busca el video de una pagina de producto: primero un archivo real "
        "y descargable (mp4/webm/...), si no hay, un embed de YouTube/"
        "Vimeo. Devuelve {\"tipo\": \"archivo\"|\"embed\", \"url\": ...} o "
        "null si no hay ningun video.",
        {"url": str},
    )
    async def _tool_extraer_video(args: dict) -> dict:
        try:
            resultado = await asyncio.to_thread(fuente.extraer_video, args["url"])
        except nav.ErrorRecurso as error:
            return {
                "content": [{"type": "text", "text": f"ERROR: {error}"}],
                "is_error": True,
            }
        return {
            "content": [
                {"type": "text", "text": json.dumps(resultado, ensure_ascii=False)}
            ]
        }

    @tool(
        "descargar_video",
        "Descarga un video real (por su URL) a un archivo dentro de la "
        "carpeta del producto. NUNCA la uses con un embed de YouTube/Vimeo "
        "(eso no se descarga, se anota en video_nota). nombre_archivo va "
        "SIN ruta, solo el nombre -- para el clip principal del producto, "
        "si la fuente es .mp4, usa EXACTO '<codigo>_clip_original.mp4' "
        "(ver apendice).",
        {"url_video": str, "nombre_archivo": str},
    )
    async def _tool_descargar_video(args: dict) -> dict:
        # Path(...).name descarta cualquier componente de ruta que venga en
        # nombre_archivo: la descarga nunca puede salir de carpeta_destino
        # (mismo resguardo que _tool_descargar_imagen).
        nombre = Path(args["nombre_archivo"]).name
        if not nombre:
            return {
                "content": [{"type": "text", "text": "ERROR: nombre_archivo vacio."}],
                "is_error": True,
            }
        destino = carpeta_destino / nombre
        try:
            await asyncio.to_thread(fuente.descargar_video, args["url_video"], destino)
        except nav.ErrorRecurso as error:
            return {
                "content": [{"type": "text", "text": f"ERROR: {error}"}],
                "is_error": True,
            }
        return {"content": [{"type": "text", "text": f"Guardado como {destino.name}"}]}

    servidor = create_sdk_mcp_server(
        name="navegador_ekipon",
        tools=[
            _tool_navegar,
            _tool_extraer_imagenes,
            _tool_descargar_imagen,
            _tool_extraer_video,
            _tool_descargar_video,
        ],
    )
    nombres_tools = [
        "mcp__navegador_ekipon__navegar",
        "mcp__navegador_ekipon__extraer_imagenes",
        "mcp__navegador_ekipon__descargar_imagen",
        "mcp__navegador_ekipon__extraer_video",
        "mcp__navegador_ekipon__descargar_video",
    ]

    # El system prompt (SKILL.md completo + apendice, ~18KB) se escribe a un
    # archivo y se pasa por RUTA, no como string: verificado en esta sesion
    # que claude_agent_sdk pasa system_prompt Y el JSON schema de
    # output_format enteros como argumentos de linea de comando
    # (subprocess_cli.py: --system-prompt / --json-schema). En Windows, la
    # combinacion de ambos (system_prompt largo + schema de FichaEkipon,
    # ~13KB) supera el limite practico de linea de comando y el spawn del
    # CLI falla con "Claude Code not found" -- un mensaje enganoso que en
    # realidad es un fallo de creacion del proceso, no que falte el binario
    # (se confirmo ejecutando el mismo .exe a mano, sin problema). El SDK
    # SI soporta system_prompt={"type": "file", "path": ...} para este caso
    # exacto; el schema no tiene un equivalente por archivo, pero por si
    # solo (13KB) no rompe el limite -- solo la suma de los dos lo hacia.
    ruta_prompt = carpeta_destino / "_system_prompt.md"
    ruta_prompt.write_text(_armar_system_prompt(), encoding="utf-8")

    opciones = ClaudeAgentOptions(
        system_prompt={"type": "file", "path": str(ruta_prompt)},
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
        # SIN env={"ANTHROPIC_API_KEY": ...} a proposito: el CLI hereda el
        # entorno del proceso padre y usa la sesion de Claude Code YA
        # LOGUEADA en esta maquina (suscripcion de Angie), no una clave de
        # API facturada aparte -- ver el docstring del modulo. El cupo es
        # la ventana compartida de 5 horas: si esto corre mientras Angie
        # usa el chat, se pisan el mismo cupo.
        output_format={
            "type": "json_schema",
            "schema": FichaEkipon.model_json_schema(),
        },
    )

    publicar_notificacion(f"Investigando el producto: {link}")
    resultado_estructurado: dict | None = None
    ultimo_mensaje_error: str | None = None
    llego_resultado = False

    try:
        # Verificado en esta sesion: claude_agent_sdk (0.2.134, todavia en
        # 0.x) a veces emite, DESPUES de un ResultMessage real y exitoso,
        # un mensaje de control espurio {"type": "error", "error":
        # "success"} durante el cierre del stream -- query.py lo traduce a
        # una excepcion generica que, sin este manejo, tira a la basura una
        # investigacion que en realidad SI termino bien (y ya gasto el
        # consumo real de la API). Por eso: (1) se corta el loop apenas
        # llega el ResultMessage real, en vez de seguir consumiendo el
        # generador de mas; (2) si igual algo revienta DESPUES de tener ya
        # un resultado, se ignora ese error espurio -- solo se relanza si
        # la excepcion llego ANTES de ver un ResultMessage real.
        try:
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
                    llego_resultado = True
                    resultado_estructurado = getattr(mensaje, "structured_output", None)
                    if getattr(mensaje, "is_error", False):
                        ultimo_mensaje_error = str(
                            getattr(mensaje, "result", None) or "sin detalle"
                        )
                    break
        except Exception as error:
            if not llego_resultado:
                raise
            publicar_notificacion(
                f"(aviso interno, sin impacto: el SDK cerro con un mensaje "
                f"espurio despues del resultado real: {error})"
            )
    finally:
        # La sesion de Alibaba PROPIA (ventana visible + perfil persistente)
        # se cierra siempre al terminar esta corrida -- exito, error, o
        # excepcion -- para no dejar un Chromium huerfano abierto. El
        # user_data_dir en disco NO se borra: las cookies quedan para la
        # proxima corrida (ver navegador_alibaba.SesionAlibaba.cerrar). Si
        # la sesion vino REUSADA desde afuera (lote_masivo.py), NO se cierra
        # aca -- la cierra quien la creo, al final del lote completo.
        if _sesion_propia is not None:
            await asyncio.to_thread(_sesion_propia.cerrar)

    if ultimo_mensaje_error is not None:
        raise ErrorInvestigacion(
            f"El agente investigador termino con error: {ultimo_mensaje_error}"
        )
    return resultado_estructurado


def investigar_producto(link: str, carpeta_destino: Path,
                         publicar_notificacion: Notificador,
                         evento_continuar: threading.Event | None = None,
                         sesion_alibaba=None) -> dict:
    """Punto de entrada sincrono (mismo criterio que el resto del pipeline:
    orquestador.py y sus pasos son funciones sincronas, llamadas desde el
    hilo de fondo de app.py -- ver _correr_pipeline). Investiga `link` con
    el agente headless, valida el resultado contra FichaEkipon, y si es
    valido guarda la ficha (+ las fotos reales que el agente haya
    descargado) en `carpeta_destino`.

    `evento_continuar` es el `threading.Event` que hace posible la pausa de
    login/CAPTCHA de Alibaba (Fase 2b, ver navegador_alibaba.py): quien
    llama con Alibaba en mente (app.py, uno por job en `_Job.evento_continuar`)
    lo pasa para que la tool de Alibaba pueda esperarlo y quien lo controla
    desde afuera (el endpoint POST /continuar/{job_id}) pueda despertarla.
    Si no se pasa (ej. tests, o un link no-Alibaba que nunca llega a
    necesitarlo), se crea uno propio que nunca se setea desde afuera -- no
    hay problema, porque solo la tool de Alibaba llega a esperarlo.

    `sesion_alibaba`, si se pasa, es una `navegador_alibaba.SesionAlibaba`
    YA ABIERTA para reusar en vez de abrir una ventana nueva (lote_masivo.py:
    una sola sesion para todo el lote nocturno). Viaja intacta hacia
    `_correr_agente`, que decide si la usa (link de Alibaba) o la ignora
    (cualquier otro link). Ver el docstring de `_correr_agente` para el
    detalle de quien la cierra en cada caso.

    Devuelve SIEMPRE uno de estos dos dicts, nunca lanza:

      {"estado": "ficha_lista", "ruta_ficha": Path}  -> exito
      {"estado": "error", "motivo": str}               -> fallo (SDK/CLI
                                                           ausente o sin
                                                           sesion iniciada,
                                                           ficha invalida,
                                                           error real del
                                                           agente)

    Quien llama (app.py) decide que hacer con 'ficha_lista': encadenar hacia
    orquestador.ejecutar_pipeline(ruta_ficha, ...)."""
    link = link.strip()
    carpeta_destino = Path(carpeta_destino)

    if evento_continuar is None:
        evento_continuar = threading.Event()

    carpeta_destino.mkdir(parents=True, exist_ok=True)

    try:
        ficha = asyncio.run(
            _correr_agente(
                link, carpeta_destino, publicar_notificacion, evento_continuar,
                sesion_alibaba=sesion_alibaba,
            )
        )
    except ErrorInvestigacion as error:
        publicar_notificacion(f"ERROR: {error}")
        return {"estado": "error", "motivo": str(error)}
    except ImportError as error:
        motivo = (
            "Falta el paquete claude-agent-sdk instalado (`pip install "
            f"claude-agent-sdk`): {error}"
        )
        publicar_notificacion(motivo)
        return {"estado": "error", "motivo": motivo}
    except Exception as error:  # ultima red de seguridad: nunca se escapa
        # un traceback crudo hacia el hilo del servidor -- CLI ausente, sin
        # sesion iniciada, cupo agotado, red caida, etc.
        motivo = _mensaje_claro_para_error_sdk(error)
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


# ----------------------------------------------------------------------
# Carpeta legible (10-ago-2026, lote nocturno)
# ----------------------------------------------------------------------
#
# investigar_producto() SIGUE trabajando en una carpeta temporal (uuid):
# el nombre legible recien se puede armar cuando la ficha YA tiene
# producto.nombre_propuesto / entrada_original.codigo_proveedor, y eso solo
# se sabe cuando esta funcion ya termino. Por eso el renombre es un paso
# APARTE que corre quien llama (app.py para el camino de un solo link,
# lote_masivo.py para el lote) justo despues de recibir 'ficha_lista' --
# una sola funcion compartida, para no duplicar la logica de slug/colision
# entre los dos caminos.

def _slug_legible(ficha: dict) -> str:
    """'<codigo>_<nombre-en-slug>' para nombrar la carpeta de un producto de
    forma que Angie pueda leerla a simple vista (en vez del uuid opaco de
    la carpeta temporal). Reusa `publicador.generar_slug` (ya limpia
    acentos/simbolos y pasa a minusculas) para la parte del nombre, y
    `_slug_codigo` (ya usado para el nombre del archivo de la ficha) para
    la parte del codigo -- no se duplica ninguna de las dos logicas.

    Import de publicador diferido (mismo criterio que orquestador.py: evita
    el costo de importarlo para quien no llega a necesitar el renombre)."""
    slug_codigo = _slug_codigo(ficha)
    producto = ficha.get("producto") or {}
    nombre = str(producto.get("nombre_propuesto") or "").strip()
    if not nombre:
        return slug_codigo

    import publicador

    try:
        slug_nombre = publicador.generar_slug("", nombre)
    except ValueError:
        return slug_codigo
    if not slug_nombre:
        return slug_codigo
    return f"{slug_codigo}_{slug_nombre}"


def renombrar_carpeta_investigacion(carpeta_actual: Path, ficha: dict,
                                     publicar_notificacion: Notificador) -> Path:
    """Renombra `carpeta_actual` (la carpeta temporal por uuid donde
    investigar_producto trabajo) a un nombre legible '<codigo>_<nombre-en-
    slug>' -- se llama DESPUES de que la ficha ya existe, con la ficha en
    memoria. Si ya existe una carpeta con ese nombre (otro producto previo
    con el mismo codigo/nombre), agrega un sufijo numerico -2, -3... para
    no pisarla nunca.

    Devuelve la carpeta FINAL: la renombrada si todo salio bien, o
    `carpeta_actual` sin tocar si no se pudo (sin nombre/codigo utilizable,
    la carpeta no existe, o el renombre en disco fallo). Quien llama tiene
    que seguir trabajando SIEMPRE con la ruta devuelta, nunca con la
    original -- si el renombre paso, la vieja ya no existe."""
    carpeta_actual = Path(carpeta_actual)
    if not carpeta_actual.is_dir():
        return carpeta_actual

    base = _slug_legible(ficha)
    if not base:
        return carpeta_actual

    carpeta_padre = carpeta_actual.parent
    destino = carpeta_padre / base
    sufijo = 2
    while destino.exists() and destino.resolve() != carpeta_actual.resolve():
        destino = carpeta_padre / f"{base}-{sufijo}"
        sufijo += 1

    if destino.resolve() == carpeta_actual.resolve():
        return carpeta_actual

    try:
        carpeta_actual.rename(destino)
    except OSError as error:
        publicar_notificacion(
            f"No se pudo renombrar la carpeta de trabajo a '{destino.name}' "
            f"({error}); se sigue con el nombre temporal."
        )
        return carpeta_actual

    return destino
