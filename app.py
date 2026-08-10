"""Servidor local FastAPI del orquestador Ekipon (Fase 1 + Fase 2a).

Pagina minima para que Angie (duenia de negocio, diseñadora grafica, NO
programadora) dispare el pipeline completo pegando la ruta de una ficha ya
investigada -- O, desde la Fase 2a, un LINK de producto (no-Alibaba): colador
de calidad -> galeria -> guion/musica (IA) -> video -> publicacion como
borrador con el video adjunto.

Si lo que se pega en el campo es un link (http/https), el endpoint /generar
corre primero agente_investigador.investigar_producto() (Fase 2a) para
producir la ficha, y SOLO si eso da una ficha valida encadena hacia
orquestador.ejecutar_pipeline() con esa ficha -- un solo flujo continuo para
quien lo mira desde la pagina, notificando por el mismo mecanismo SSE que ya
existia (ver agente_investigador.py: si el link es de Alibaba o la
investigacion falla, el resultado final trae 'estado': 'error' con el
motivo, mismo formato que ya usa orquestador.py). Si es una ruta de archivo,
el comportamiento es EXACTAMENTE el de la Fase 1, sin cambios.

Un solo job a la vez alcanza para esta v1 (no hace falta una cola
sofisticada de jobs concurrentes), pero el pipeline en si corre en un HILO
aparte (threading, no async/await): los modulos internos que orquesta
orquestador.py (y, desde Fase 2a, agente_investigador.py) son sincronos y
hacen I/O pesado de disco/red (ffmpeg, ElevenLabs, Anthropic, WooCommerce,
Playwright) — correrlos directo en el loop de asyncio bloquearia el servidor
entero, incluida la propia pagina de progreso.

Uso:  uvicorn app:app --reload
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agente_investigador
from orquestador import ejecutar_pipeline

CARPETA_PROYECTO = Path(__file__).parent
RUTA_INDEX = CARPETA_PROYECTO / "static" / "index.html"
RUTA_ASSETS = CARPETA_PROYECTO / "static" / "assets"
# Carpeta donde el agente investigador (Fase 2a) guarda la ficha + fotos
# reales de cada link investigado. Una subcarpeta por job_id: evita
# colisiones entre corridas y no depende de conocer el codigo de proveedor
# ANTES de investigar (se sabe recien cuando el agente termina).
CARPETA_INVESTIGACIONES = CARPETA_PROYECTO / "investigaciones"

# Cuanto espera cada vuelta del generador SSE cuando no hay mensajes nuevos
# (poll corto, no busy-loop agresivo; el trabajo real vive en el hilo del
# pipeline, esto solo drena lo que ese hilo va dejando).
_ESPERA_POLL_SEGUNDOS = 0.25


class _Job:
    """Estado de una corrida: la lista de mensajes de progreso (en orden) mas
    el resultado final, si ya termino. Un lock chico protege la lista porque
    el hilo del pipeline escribe y el/los hilo(s) de las peticiones SSE leen
    al mismo tiempo.

    Guardar el HISTORIAL completo (no solo una cola de un solo consumo) es a
    proposito: permite que la pagina reabra /eventos/{job_id} — por ejemplo
    tras recargar la pestaña — y reciba TODO el progreso ya emitido antes de
    seguir en vivo, en vez de quedarse esperando para siempre un mensaje que
    ya paso."""

    def __init__(self) -> None:
        self.mensajes: list[dict] = []
        self.terminado = False
        self.lock = threading.Lock()

    def agregar(self, item: dict) -> None:
        with self.lock:
            self.mensajes.append(item)

    def marcar_terminado(self) -> None:
        with self.lock:
            self.terminado = True

    def desde(self, indice: int) -> tuple[list[dict], int, bool]:
        with self.lock:
            return list(self.mensajes[indice:]), len(self.mensajes), self.terminado


_JOBS: dict[str, _Job] = {}
_JOBS_LOCK = threading.Lock()


class PeticionGenerar(BaseModel):
    ruta_ficha: str


app = FastAPI(
    title="Administrador Inteligente de Catalogo — Ekipon",
    description="Orquestador del pipeline de video + publicacion (Fase 1).",
)

# Logo recortado y las dos tipografias de marca (Montserrat/Anton, ya usadas
# en subtitulos.py/generador_banner.py) para que la pagina se vea con la
# misma identidad visual que el resto de las piezas de Ekipon, no generica.
app.mount("/assets", StaticFiles(directory=RUTA_ASSETS), name="assets")


def _correr_pipeline(job_id: str, entrada: str) -> None:
    """Corre el flujo completo para `entrada`: si es un link, primero
    investiga (Fase 2a) y SOLO si produce una ficha valida encadena hacia
    el pipeline de Fase 1; si es una ruta de archivo, va directo al
    pipeline como siempre. `entrada` es un str (no Path) porque puede ser
    una URL, que Path() no representa bien."""
    job = _JOBS[job_id]

    def notificar(mensaje: str) -> None:
        job.agregar({"tipo": "progreso", "mensaje": mensaje})

    try:
        if agente_investigador.es_url(entrada):
            carpeta_destino = CARPETA_INVESTIGACIONES / job_id
            resultado_investigacion = agente_investigador.investigar_producto(
                entrada, carpeta_destino, notificar,
            )
            if resultado_investigacion["estado"] != "ficha_lista":
                # Mismo formato de resultado que ejecutar_pipeline(): la
                # pagina ya sabe mostrar 'error' sin cambios.
                resultado = {
                    "estado": "error",
                    "motivo": resultado_investigacion.get(
                        "motivo", "La investigacion no produjo una ficha.",
                    ),
                }
                job.agregar({"tipo": "final", "resultado": resultado})
                job.marcar_terminado()
                return
            ruta_ficha = Path(resultado_investigacion["ruta_ficha"])
        else:
            ruta_ficha = Path(entrada)

        resultado = ejecutar_pipeline(ruta_ficha, notificar)
    except Exception as error:
        # Ultima red de seguridad: ni ejecutar_pipeline() ni
        # investigar_producto() deberian lanzar nunca (todo se traduce a
        # estado "error" adentro), pero si algo se escapa igual no se cae
        # el hilo en silencio, ni la pagina se queda esperando un final que
        # nunca llega.
        resultado = {
            "estado": "error",
            "motivo": f"Error inesperado del servidor: {error}",
        }
    job.agregar({"tipo": "final", "resultado": resultado})
    job.marcar_terminado()


@app.post("/generar")
def generar(peticion: PeticionGenerar) -> dict:
    """Recibe un link de producto O la ruta de una ficha ya investigada,
    arranca el flujo correspondiente en un hilo aparte y devuelve un job_id
    para seguir el progreso en /eventos/{job_id}.

    Si `ruta_ficha` es una URL (http/https), NO se valida como archivo --
    se investiga primero (Fase 2a), dentro del hilo. Si es una ruta local,
    se valida que exista ANTES de crear el job, igual que en Fase 1."""
    entrada = peticion.ruta_ficha.strip()
    if not entrada:
        raise HTTPException(
            status_code=400,
            detail="Pega un link de producto o la ruta de una ficha.",
        )

    if agente_investigador.es_url(entrada):
        entrada_normalizada = entrada
    else:
        ruta_ficha = Path(entrada).expanduser()
        if not ruta_ficha.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"No encuentro el archivo de la ficha: {ruta_ficha}",
            )
        entrada_normalizada = str(ruta_ficha.resolve())

    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = _Job()

    hilo = threading.Thread(
        target=_correr_pipeline, args=(job_id, entrada_normalizada),
        daemon=True,
    )
    hilo.start()
    return {"job_id": job_id}


@app.get("/eventos/{job_id}")
def eventos(job_id: str) -> StreamingResponse:
    """Server-Sent Events del progreso de un job. Cada evento es una linea
    'data: <json>\\n\\n'; el ultimo trae {"tipo": "final", "resultado": {...}}
    con el resultado de ejecutar_pipeline (estado listo/revisar/error)."""
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_id desconocido")

    def generador():
        indice = 0
        while True:
            pendientes, indice, terminado = job.desde(indice)
            for item in pendientes:
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            if terminado:
                break
            time.sleep(_ESPERA_POLL_SEGUNDOS)

    return StreamingResponse(generador(), media_type="text/event-stream")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(RUTA_INDEX)
