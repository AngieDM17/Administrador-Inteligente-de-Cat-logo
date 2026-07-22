# ESTADO DEL PROYECTO — Administrador Inteligente de Catálogo Ekipon

**Última actualización:** 22-jul-2026.
**Para retomar en un chat nuevo:** pídele a Claude que lea PRIMERO este archivo, luego
`AUDITORIA_ABOGADO_DEL_DIABLO.md` y `ETAPA_IMAGENES.md`.
**Regla de oro:** ante cualquier discrepancia entre este documento y el código, **gana el código**.
Verificar antes de afirmar.

---

## 🟢 DÓNDE ESTAMOS

**Fase de VIABILIDAD TÉCNICA: cerrada.** El pipeline corre de punta a punta y eliminó la carga
manual (60-90 min) **para un producto revisado a mano**: el 4212, publicado como borrador en
`pruebas.ekipon.co` con ID interno **50238**.

**Fase de ESCALA Y PRODUCCIÓN: no empezada.** "Funciona en 1" y "escala a 100.000" son
afirmaciones distintas; solo está demostrada la primera. Las grietas están listadas en
`AUDITORIA_ABOGADO_DEL_DIABLO.md`.

Estamos exactamente en la bisagra entre "probé que se puede" y "lo hago aguantar de verdad".

---

## El pipeline hoy

| Etapa | Implementación | Estado |
|---|---|---|
| **Investigador v0.3** | Skill de Claude (`investigador_v0.3/`), no código | ✅ probado en NBC 250 y 4212 |
| **Inspector / validación** | `esquema_ficha.py` + `validar_ficha.py` (contrato v1.4) | ✅ |
| **Publicador** | `publicador.py` — crea BORRADOR vía API REST, idempotente (`--actualizar`) | ✅ 4212 = ID 50238 |
| **Dinamización Elementor** | `snippets/shortcodes_ekipon.php` vía Code Snippets | ✅ la plantilla se llena sola desde la meta `ekipon_*` |
| **Imágenes (galería)** | Motor propio Pillow — ver `ETAPA_IMAGENES.md` | ✅ construido, ⬜ sin conectar al Publicador |
| **Banner** | `generador_banner.py` (motor propio, ya no Canva) | ✅ integrado al Publicador |
| **Video** | — | ⬜ última fase, no empezada |
| **Orquestador** | — | ⬜ no empezado |

**Tests:** 136, todos en verde (`python -m unittest discover -p "test_*.py"`).

**Estado en git:** el repo es `AngieDM17/Administrador-Inteligente-de-Cat-logo`, rama `main`.
⚠️ **Al 22-jul la etapa Imágenes completa está SIN COMMITEAR** (los 4 generadores, sus 5 archivos
de tests, `ETAPA_IMAGENES.md`, `AUDITORIA_ABOGADO_DEL_DIABLO.md` y `molino_imagenes/`). Último
commit: `78e3d4c`. Trabajo real fuera de git = trabajo que se puede perder.

---

## ▶️ PRÓXIMO PASO (Prioridad A)

1. **Commitear la etapa Imágenes.** Sacar el trabajo del limbo antes de seguir.
2. **Prueba de lote real** — correr el pipeline sobre 100-200 productos *sin revisar* y medir la
   tasa de error del Investigador.
   *Terminado cuando:* hay un número medido. Umbral: **>5% = todavía no es automatización**,
   primero se mejora el Investigador.
3. **Endurecer seguridad** — rotar claves de WooCommerce/WordPress, `.env` fuera del repo,
   allowlist `TIENDAS_PERMITIDAS` lista antes de apuntar a la tienda real.
   *Terminado cuando:* llaves nuevas en uso, viejas revocadas, `.env` no rastreado por git.

Prioridades B y C (staging, rollback, runbook de incidentes, SEO) están detalladas en la auditoría.

**Filosofía de avance:** cada etapa se cierra con una *definición de terminado* verificable. No se
avanza a producción con etapas a medias.

---

## Qué es el proyecto

Sistema que automatiza la creación y administración de productos de la tienda WooCommerce
ekipon.co (hoy ~5.000 productos, meta 100.000+). Angie es la dueña del producto (diseñadora
gráfica, no programadora — Claude debe explicar todo término técnico). Claude es arquitecto,
desarrollador y mentor.

**Flujo real (decidido 10-jul-2026):** el 100% de los productos entra como nombre + foto de
referencia → investigación web (Alibaba, fabricantes, distribuidores) → ficha técnica consolidada
→ galería → banner → video ~1 min → BORRADOR en WooCommerce con plantilla Elementor → Angie revisa
y publica. El extractor de `.docx` (`extractor_fichas.py` v0.2) quedó como entrada secundaria.

**El contrato que une todo es la ficha JSON estándar v1.4.** Viaja entre todas las etapas.

---

## Reglas de negocio confirmadas por Angie

Fuente única y vigente: `investigador_v0.3/investigador-ekipon/references/reglas_negocio.md`.
Resumen:

1. **Precio: SIEMPRE manual.** Nunca se automatiza. Suele incluir ~$100.000 de envío; se publica
   "Envío GRATIS a todo el país" + pago contra entrega. Moneda COP.
2. **Garantía: siempre 1 año.**
3. **SKU:** lo asigna WooCommerce automáticamente. No se muestra al público.
4. **Sin marcas y sin precio de oferta.**
5. **Nombres:** MAYÚSCULAS, formato "PRODUCTO CARACTERÍSTICA – DETALLE".
6. **Descripción corta WooCommerce** = `descripcion_principal`. La pestaña Descripción la arma la
   plantilla Elementor desde la meta (por eso el Publicador manda `description=""`).
7. **Todo se publica como BORRADOR.** Angie revisa siempre.
8. **Imágenes:** WebP 1080×1080 con ALT que incluya el código.
9. **Angie no define reglas por producto** — eso es trabajo del sistema. Su rol se limita a:
   identidad inicial del producto, confirmación final y precio.

---

## Infraestructura de publicación (verificada desde Fase 0)

- **Tienda de pruebas `pruebas.ekipon.co`** clonada, con candado (contraseña de directorio en
  cPanel), invisible para Google y sin píxeles.
- **Claves de WooCommerce (API REST)** y **contraseña de aplicación de WordPress** creadas y
  verificadas. ⚠️ Siguen en texto plano en `claves_pruebas.txt` — pendiente de la Prioridad A.
- **Autenticación de dos puertas:** candado del directorio + claves de API. El Publicador contempla
  la excepción del candado.
- **Plantillas Elementor por ID:** `50198` = ficha técnica · `50201` = características y video.
- Vía de publicación decidida: **API REST de WooCommerce** (no manual, no conector de terceros).
- **Árbol de categorías EN VIVO** desde WooCommerce, nunca copia estática.

---

## Historia y lecciones aprendidas

Cada lección vino de un error real. No se repiten por gusto: son el criterio del sistema.

### Identificación e investigación

1. **Código de proveedor EXACTO, sufijos incluidos.** 9060C ≠ 9060: eran dos máquinas distintas
   del mismo importador y confundirlas contaminó una ficha completa.
2. **Verificación visual por rasgos estructurales, nunca por color.** Un soldador rojo con perillas
   análogas era OTRO producto (WTSM-250).
3. **Origen por campo obligatorio.** Sin trazabilidad no hay forma de saber qué corregir.
4. **Kits y sets: verificar la COMPOSICIÓN contra el catálogo del proveedor ANTES de confiar en la
   foto.** El 4212 parecía un tanque; solo el catálogo (p.89) reveló que era un set de 4 piezas.
   Una sola foto engaña en ambos sentidos: rechaza piezas válidas o da por bueno otro producto.
5. **Specs "contaminadas" pueden ser legítimas de otra pieza** del mismo set. No descartarlas sin
   entender la composición.
6. **Alibaba bloquea la extracción** y sus listados mueren. No es fuente automática confiable.
   Google Lens / búsqueda por imagen es herramienta central. Autonomía total a escala exigiría un
   scraper headless (Playwright) o una API de datos.
7. **Accesorios incluidos: revisar SIEMPRE primero la ficha técnica del proveedor.** Si no
   aparecen, va a `campos_por_confirmar` con la nota de verificación.

### Imágenes

8. **El producto siempre es REAL.** Nunca se genera una foto falsa del producto con IA. Comprobado
   dos veces: ChatGPT imagen→imagen inventa las caras no fotografiadas, y la generación por texto
   de Canva inventó un molino con marca falsa ("SHENGKEY"). La IA sirve para escena/fondo/persona.
9. **Motor propio vs Canva:** motor propio (Pillow) para piezas repetibles que deben verse igual en
   todos los productos (hero, dimensiones, callouts, banner) — determinista y sin red. Canva solo
   para escenas fotorrealistas únicas, porque **reinventa cada vez**.
10. **Rellenar para llegar a una cuota es un antipatrón.** La galería del 4212 salió "cortada y
    toda igual" porque había ~4 fotos reales y se rellenó a 8 con un collage y recortes
    redundantes. Mejor 3 tomas honestas que 8 con relleno.
11. **Los recortes no sustituyen ángulos nuevos.** Rechazados en el NBC 250: venían de capturas de
    ~500px ampliadas. El recorte solo sirve con originales de alta resolución.
12. **Se estandarizan los TIPOS de toma, no el contenido.** Labels y medidas salen SIEMPRE de la
    ficha de cada producto, nunca hardcodeados.

### Proceso y herramientas

13. **Angie no edita JSON a mano** (lo rompió en el piloto). La revisión es siempre por pantalla
    con campos (`revision_<CODIGO>.html`).
14. **Nunca incluir el código de proveedor en el texto público** (ej. quitar "9060C"). El código
    vive solo en campos internos.
15. **GOTCHA — desincronización JSON:** archivos escritos por una vía se ven truncados por la otra.
    Fix: reescribir el archivo entero de una vez y validar; no fiarse de una sola vista.
16. **El entorno local no tiene salida de red directa** (ni a Canva ni a la tienda). Solo las
    herramientas del harness tienen red. Es un límite del entorno, no un callejón sin salida.

### Pilotos

- **NBC 250** (9060C SOLDADOR MIG MULTIFUNCIÓN, IO Company): completo. Ficha + 8 imágenes WebP +
  banner. Precio $2.454.703. Categoría Industria > Equipos de Soldadura. Criterio visual final:
  tres perillas rojas + un botón rojo. Accesorios confirmados (antorcha MIG + kit).
- **4212** (SISTEMA DE AIRE COMPRIMIDO 3 PIEZAS): primera corrida real del Investigador con
  producto nuevo, **pasó**. Precio $16.434.999, categoría Industria. Es el caso que atraviesa todo
  el pipeline hasta el borrador 50238.
- **Molino** (MOLINO PULVERIZADOR DE GRANO SECO Y COCIDO): caso de prueba de la etapa Imágenes.
  1 sola foto real. 150 kg/h · 2 HP (110V) · 2800 rpm · 85×43,5×46,5 cm · 20 kg · $1.159.000.

### Estilos aprobados por Angie (14-jul-2026)

- **Descripción del producto:** intro técnica + párrafo de cierre con la fórmula fija
  "Gracias a su [atributos], el [PRODUCTO] es una excelente opción para [audiencias] que requieren
  [beneficios]."
- **Banner:** párrafo redactado de largo medio (~40-50 palabras), no una lista de specs.

Detalle completo de ambos estilos en `reglas_negocio.md`.

---

## Decisión de plataforma (15-jul-2026)

El motor multiagente (Investigador → Redactor → Imágenes → Publicador → Orquestador, en lote) se
construye y corre en **Claude Code vía la extensión de VS Code**. Cowork queda como cabina de
revisión humana.

**Regla que sigue vigente:** no automatizar en serie hasta que el Investigador sea confiable. Por
eso la prueba de lote es la prioridad número uno.
