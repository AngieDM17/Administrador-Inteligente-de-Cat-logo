# Auditoría "Abogado del Diablo" + Hoja de ruta

**Fecha:** 2026-07-21
**Contexto:** El pipeline (Investigador → Inspector → Publicador → plantillas Elementor dinámicas)
corre de punta a punta y elimina la carga manual **para un producto** (4212 / ID interno 50238).
Se corrió una revisión crítica adversarial (skill `abogado-del-diablo`) sobre la apuesta de escala
(1 producto → 100.000) y la migración a producción. Este documento fija los hallazgos y los
próximos pasos para no perderlos.

---

## Dónde estamos, sin adornos

- **Cerrada:** la fase de *viabilidad técnica*. El pipeline completo funciona y mató la carga
  manual **para un producto revisado a mano**. Terreno ganado real.
- **No empezada:** la fase de *escala y producción*. "Funciona en 1" y "escala a 100k" son
  afirmaciones distintas; solo está demostrada la primera.
- **Ubicación:** bisagra entre "probé que se puede" y "lo hago aguantar de verdad".

---

## Hallazgos priorizados (grietas)

| # | Grieta | Por qué es letal | Estado |
|---|--------|------------------|--------|
| 1 | **La prueba de escala no existe.** Solo se validó 1 producto, revisado a mano. Regla "borrador siempre" + precio manual = el humano sigue siendo filtro obligatorio. | Si el Investigador falla el 5-10%, a 100k son miles de fichas a corregir a mano. La tesis "mínima intervención humana" se cae. | ⬜ Abierta |
| 2 | **Credenciales en texto plano** y allowlist `TIENDAS_PERMITIDAS` pendiente, justo antes de apuntar a la tienda real. | Una API key de WooCommerce filtrada = acceso de escritura al catálogo real (precios, borrado). | ⬜ Abierta |
| 3 | **El recorte de imagen sigue manual (Canva).** `rembg` marcado "opcional". | La velocidad del sistema = la de su paso más lento. A 100k, un humano recortando fondos es el techo real. | 🟡 Parcial (22-jul): `recortar_producto.py` automatiza el recorte con `rembg`. **Falta medir su tasa de acierto sobre un lote** y fijar el umbral de caída a revisión manual. |
| 4 | **Riesgo centralizado en la dinamización.** Todo depende de Elementor Pro + Woodmart + Code Snippets + meta `ekipon_*`. Una plantilla única. | Una actualización de Woodmart/Elementor puede romper los 100k productos a la vez. Sin staging ni rollback. | ⬜ Abierta |
| 5 | **Bus factor = 1**, y esa persona no programa. Mantenimiento con Claude en el loop. | Un incidente en producción sin dev disponible = paro total hasta la próxima sesión. | ⬜ Abierta |
| 6 | **Contenido templado a escala = riesgo SEO.** Google añadió "scaled content abuse" como spam explícito (2025), con desindexación masiva de sitios. | Si el catálogo masivo se marca como contenido de bajo valor, se puede perder el dominio, no un producto. | ⬜ Abierta |

**La que más mata:** la #1. Todo el proyecto se justifica con "elimina 60-90 min por producto",
y eso está probado sobre exactamente un producto revisado a mano.

**Calibración honesta:** el diagnóstico es correcto; el pronóstico del abogado del diablo está
inflado. Esto **no** es una startup quemando capital con runway contado — es un negocio que ya
factura, mejorando su operación con costo marginal casi cero (quien construye es Claude). Eso le
quita filo a los ángulos de "¿cierra la economía?" y "¿mejor comprar un PIM?". El riesgo SEO es
real pero es del capítulo producción, no de esta semana.

---

## Próximos pasos — dejar cada parte del flujo pulida y funcional

Filosofía: cada etapa del pipeline se cierra con una **definición de terminado** verificable antes
de pasar a la siguiente. No se avanza a producción con etapas a medias.

### Prioridad A — esta semana (barato y decisivo)

1. **Prueba de lote real (grieta #1).**
   Correr el pipeline sobre 100-200 productos reales *sin revisar* y medir la tasa de error de la
   ficha del Investigador.
   *Terminado cuando:* hay un número de tasa de error medido. Umbral de decisión: si >5% sale mal,
   no es automatización, es asistente con niñera → primero se mejora el Investigador.

2. **Endurecer seguridad (grieta #2).**
   Rotar las credenciales de WooCommerce/WordPress, confirmar que `.env` está fuera del repo
   (`.gitignore`), y dejar el allowlist `TIENDAS_PERMITIDAS` listo para el cambio a producción.
   *Terminado cuando:* llaves nuevas en uso, llaves viejas revocadas, `.env` no rastreado por git.

### Prioridad B — antes de producción (capítulo escala)

3. **Automatizar el recorte de imagen (grieta #3).** — *integración hecha el 22-jul.*
   `rembg` ya está en el pipeline (`recortar_producto.py`). Queda medir su tasa de acierto sobre
   un lote real y conectar la galería generada al Publicador (hoy sube galería **solo al crear**).
   *Terminado cuando:* la tasa de acierto está medida, se define el umbral bajo el cual una imagen
   cae a revisión manual, y existe un camino de "refrescar galería" para productos ya creados.

   *Actualización 23-jul:* el recorte corrió limpio sobre foto real 1080 y se generaron partes+medidas.
   Además se destapó el paso previo (**sourcing**): el Chrome logueado de Angie pasa el CAPTCHA de
   Alibaba, pero **bajar fotos por URL a ciegas trae OTROS productos** — el techo de escala aquí no es
   solo `rembg`, es que el sourcing automático exige un **gate de verificación visual**. Detalle en
   `ETAPA_IMAGENES.md`.

4. **Blindar la capa de presentación (grieta #4).**
   Fijar versiones de Elementor/Woodmart, montar un entorno de staging y un plan de rollback antes
   de que la plantilla dinámica única sea punto único de falla.
   *Terminado cuando:* existe staging, las versiones están fijadas, y hay un procedimiento de
   rollback escrito.

5. **Runbook de incidentes en lenguaje no técnico (grieta #5).**
   Documento "qué revisar primero cuando X se rompe" (ej. las fichas dejan de renderizar).
   *Terminado cuando:* Angie puede seguir el runbook sin leer código.

### Prioridad C — capítulo producción / crecimiento

6. **Diferenciación de contenido (grieta #6).**
   Que cada ficha aporte algo que la tabla de specs del proveedor no da (uso real, criterio,
   comparación) — o aceptar explícitamente que el catálogo masivo no rankeará orgánico y no
   depender de SEO para esos productos.
   *Terminado cuando:* hay una decisión tomada y documentada sobre la estrategia de contenido.

7. **Nivel 2 de automatización:** auto-aplicar la plantilla a cada producto sin "Insertar" manual
   (Elementor Theme Builder → Single Product con condición). Último eslabón para 100% automático.

---

## Lo que ya está sólido (no reinventar)

- Pipeline completo verificado en vivo end-to-end sobre el 4212/50238.
- Dinamización por shortcodes probada: la carga manual de datos por producto está muerta.
- De-duplicación resuelta (`description=""`; el template renderiza desde la meta).
- Idempotencia del Publicador (`--actualizar`), banner generado+subido, meta `ekipon_*` guardada.
- Suite de tests: **136 en verde** al 22-jul-2026 (Publicador, Inspector, banner y etapa Imágenes).
- Etapa Imágenes: motor propio determinista (recorte `rembg`, dimensiones, callouts, hero) con su
  contrato de ficha `multimedia.galeria_tomas` validado por el esquema.
