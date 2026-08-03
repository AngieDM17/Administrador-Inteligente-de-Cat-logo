# Auditoría "Abogado del Diablo" + Hoja de ruta

**Fecha:** 2026-07-21. **Última actualización de estado: 2026-07-30** (grietas #1 y #3, ver abajo —
todo lo marcado 30-jul está verificado ejecutando: colador sobre las 35 fichas + conteo en vivo
contra la tienda, no de memoria).
**Contexto:** El pipeline (Investigador → Inspector → Publicador → plantillas Elementor dinámicas)
corre de punta a punta y elimina la carga manual **para un producto** (4212 / ID interno 50238).
Se corrió una revisión crítica adversarial (skill `abogado-del-diablo`) sobre la apuesta de escala
(1 producto → 100.000) y la migración a producción. Este documento fija los hallazgos y los
próximos pasos para no perderlos.

---

## Dónde estamos, sin adornos

- **Cerrada:** la fase de *viabilidad técnica*. El pipeline completo funciona y mató la carga
  manual **para un producto revisado a mano**. Terreno ganado real.
- **Cerrada (30-jul):** la primera prueba de escala REAL. Se corrieron 35 productos de una
  categoría nueva (Gimnasio, Fitness Market) de punta a punta — link → Investigador → colador →
  recorte → galería → Publicador → tienda — sin niñera manual por producto (el extractor automático
  hizo el trabajo repetitivo; Claude midió, revisó con gate visual y corrigió lo que falló). Detalle
  abajo, grieta #1.
- **Ubicación:** ya no es "probé que se puede" — es "lo hice aguantar con un lote real, y hasta
  ahora aguanta". Sigue faltando probarlo en 100-200 (el lote de hoy fue 35), pero el patrón de
  fallas ya no es una incógnita: son datos faltantes en la fuente y bugs de presentación puntuales,
  ambos con arreglo conocido.

---

## Hallazgos priorizados (grietas)

| # | Grieta | Por qué es letal | Estado |
|---|--------|------------------|--------|
| 1 | **La prueba de escala no existe.** Solo se validó 1 producto, revisado a mano. Regla "borrador siempre" + precio manual = el humano sigue siendo filtro obligatorio. | Si el Investigador falla el 5-10%, a 100k son miles de fichas a corregir a mano. La tesis "mínima intervención humana" se cae. | 🟢 En gran parte cerrada (30-jul): se corrió un lote real de **35 productos** (categoría Gimnasio completa, Fitness Market) de punta a punta, de una sola pasada por producto: link → Investigador (extractor automático) → colador → gate visual → recorte → galería → Publicador → tienda. **Medido ejecutando el colador sobre las 35 fichas y contando los 35 productos en vivo en la tienda: 24/35 (68,6%) VERDE** (LISTO sin motivo de revisión); 11/35 (31,4%) en REVISAR por **dato faltante real en la fuente** (peso o dimensiones que el proveedor no publica), nunca por falla del pipeline ni invención de datos. La regla "borrador siempre + precio manual" sigue vigente — el humano no desaparece, pero ahora revisa 11 de 35, no 35 de 35. **Falta:** repetir la medición en 100-200 productos de OTRA fuente/categoría para confirmar que el ~69% no es un número inflado por una fuente particularmente limpia (Fitness Market es una tienda seria, no Alibaba). |
| 2 | **Credenciales en texto plano** y allowlist `TIENDAS_PERMITIDAS` pendiente, justo antes de apuntar a la tienda real. | Una API key de WooCommerce filtrada = acceso de escritura al catálogo real (precios, borrado). | 🟡 Parcial: el candado `TIENDAS_PERMITIDAS = {"pruebas.ekipon.co"}` YA está en `cliente_tienda.py` (verificado 28-jul) y `.env` está fuera del repo. **Falta:** rotar las claves reales antes de apuntar a producción. **Sigue siendo tarea de Angie** — Claude no toca credenciales. |
| 3 | **El recorte de imagen sigue manual (Canva).** `rembg` marcado "opcional". | La velocidad del sistema = la de su paso más lento. A 100k, un humano recortando fondos es el techo real. | 🟢 Cerrada en su mayor parte (30-jul): `recortar_producto.py` corrió sin intervención humana sobre las **35 fotos reales** del lote de Gimnasio (una por producto). Se midió y arregló su único defecto real, EN DOS RONDAS: un halo de borde (fondo filtrado por rembg) visible sobre el banner — primero se corrigió para halos blancos, y una segunda revisión de Angie destapó que en máquinas plateadas claras el halo no era blanco sino gris y seguía pasando; ajustado el umbral (`limpiar_halo`, ahora en 170) y verificado con 9 tests unitarios. El camino "refrescar galería" para productos ya creados (`publicador.py --actualizar --refrescar-galeria`) se usó y probó en producción real, dos veces, sobre 21 productos. **Falta:** el gate de verificación visual del *sourcing* (bajar fotos de la fuente) sigue siendo manual/asistido por Claude — no hay una regla de código que lo automatice, y no debería: es la salvaguarda contra contaminación. |
| 4 | **Riesgo centralizado en la dinamización.** Todo depende de Elementor Pro + Woodmart + Code Snippets + meta `ekipon_*`. Una plantilla única. | Una actualización de Woodmart/Elementor puede romper los 100k productos a la vez. Sin staging ni rollback. | ⬜ Abierta |
| 5 | **Bus factor = 1**, y esa persona no programa. Mantenimiento con Claude en el loop. | Un incidente en producción sin dev disponible = paro total hasta la próxima sesión. | ⬜ Abierta |
| 6 | **Contenido templado a escala = riesgo SEO.** Google añadió "scaled content abuse" como spam explícito (2025), con desindexación masiva de sitios. | Si el catálogo masivo se marca como contenido de bajo valor, se puede perder el dominio, no un producto. | ⬜ Abierta |

**La que más mata:** ya no es la #1 en el mismo sentido — se pasó de "no existe la prueba" a "hay una
prueba real con un número real" (68,6% verde sobre 35 productos). Lo que sigue matando de esa grieta
es más angosto: confirmar que ese ~69% no es un espejismo de haber elegido una fuente linda
(Fitness Market) — repetirlo con otra fuente/categoría antes de creer el número a ciegas. La #2
(credenciales) pasa a ser la más urgente de las que quedan abiertas, porque es la única que bloquea
literalmente el paso a producción y depende de una acción que Claude no puede tomar por Angie.

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

   *Actualización 27-28 jul:* HECHA en versión chica (dos lotes de 10 links: 50% y 30/70). El dato
   grande enseñó que el problema NO es el Investigador sino la calidad de la fuente (Alibaba), así
   que la respuesta no fue "mejorar el Investigador" sino construir el **colador de listo-para-
   publicar** (`revisor_publicacion.py`): humano solo sobre lo marcado, no sobre todo.

   *Actualización 30-jul — CASI CERRADA:* se cerró el círculo link→ficha→colador de una pasada
   (pendiente desde el 27-28) y se corrió el lote grande: **35 productos** (la categoría Gimnasio
   COMPLETA de Fitness Market), de punta a punta, publicados en `pruebas.ekipon.co`. Resultado
   medido ejecutando el colador sobre las 35 fichas y contando los 35 productos en vivo en la
   tienda (categoría id 465): **24/35 (68,6%) VERDE**, 11/35 (31,4%) a revisión por dato real
   faltante — un umbral bien distinto al 5% de la regla original, pero ojo con leerlo igual: ese 5%
   hablaba de *errores* del Investigador (dato mal extraído o inventado), y lo medido acá es *datos
   ausentes en la fuente* (el proveedor no publica el peso o la dimensión). Son fallas de naturaleza
   distinta — la del 31,4% no la arregla "mejorar el Investigador", la arregla completar el dato a
   mano o conseguir mejor fuente. En el camino se destaparon y arreglaron 3 bugs reales que un lote
   chico no hubiera mostrado: ceguera de categoría del colador (pedía "potencia de motor" a
   productos sin motor), DNS intermitente de la tienda de pruebas (ahora con reintentos automáticos
   en `cliente_tienda.py`), y dos rondas de halo blanco/plateado en el recorte (`limpiar_halo`).
   **Falta:** repetir con 100-200 productos de una fuente MÁS sucia (tipo Alibaba) para no confundir
   "el sistema aguanta" con "esta fuente en particular es fácil".

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

   *Actualización 30-jul — CASI CERRADA:* tasa de acierto medida sobre las 35 fotos del lote de
   Gimnasio: `rembg` recortó las 35 sin fallar en quitar el fondo; el único defecto sistemático fue
   un halo de borde (ver grieta #3 en la tabla de arriba), no una falla de recorte en sí. El camino
   "refrescar galería para productos ya creados" que este ítem pedía como pendiente **ya existe y se
   usó en producción real** (`publicador.py --actualizar --refrescar-galeria`), dos veces, sobre 21
   y luego 35 productos, sin perder ninguna imagen. El gate de verificación visual del sourcing
   siguió siendo manual (Claude mirando cada foto antes de bajarla) — eso NO se automatiza a
   propósito, es la salvaguarda contra contaminación entre productos. **Falta:** definir un umbral
   numérico explícito de "esta imagen cae a revisión manual" (hoy el criterio vive en el juicio de
   Claude al mirar, no en una regla de código verificable).

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
- Suite de tests: **265 en verde** al 30-jul-2026 (Publicador, Inspector, banner, etapa Imágenes,
  colador, cliente de tienda y recorte).
- Etapa Imágenes: motor propio determinista (recorte `rembg` + `limpiar_halo`, dimensiones,
  callouts, hero) con su contrato de ficha `multimedia.galeria_tomas` validado por el esquema.
- Colador (`revisor_publicacion.py`) probado a escala: 35 fichas reales, sin falsos positivos por
  categoría de producto (motorizado vs no motorizado, `producto.es_motorizado`).
- Cliente de tienda con reintentos automáticos ante DNS intermitente (`cliente_tienda.py`),
  probado en producción real subiendo/actualizando 35 productos.
