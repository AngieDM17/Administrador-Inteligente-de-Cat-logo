# ESTADO DEL PROYECTO — Administrador Inteligente de Catálogo Ekipon

**Última actualización:** 30-jul-2026.
**Para retomar en un chat nuevo:** pídele a Claude que lea PRIMERO este archivo, luego
`AUDITORIA_ABOGADO_DEL_DIABLO.md` y `ETAPA_IMAGENES.md`.
**Regla de oro:** ante cualquier discrepancia entre este documento y el código, **gana el código**.
Verificar antes de afirmar.

---

## 🔵 ACTUALIZACIÓN 30-jul-2026 (leer esto primero)

**Primer producto de GIMNASIO montado de punta a punta hasta la tienda, y primer VERDE del colador.**
Todo verificado ejecutando. Producto: Máquina Leg Press (SKU U3003B) de Fitness Market Colombia.

**1. Primer VERDE del colador.** Hasta ayer el colador marcaba el 100% para revisar. El leg press
—fuente seria, datos limpios, sin motor (`es_motorizado: false`)— salió **LISTO** (cero motivos).
Confirma que el colador sabe dejar pasar lo bueno, no solo frenar lo malo, y que el cuello de
botella real es la CALIDAD DE FUENTE (tienda fitness colombiana = limpio; Alibaba = sucio).

**2. Cadena completa hasta la tienda, sobre una categoría NUEVA (gimnasio):**
link → Investigador → colador (verde) → recorte transparente (rembg) → galería + banner →
Publicador → **BORRADOR id 50295 en `pruebas.ekipon.co`**. Leído de vuelta de la tienda:
status=draft, categoría=Gimnasio, precio vacío (lo pone Angie), 2 imágenes, descripción con tabla
de ficha técnica + banner. **Sin una línea de código especial para gimnasio** — el molde es
uniforme, como sostuvo Angie.

**3. Se creó la categoría "Gimnasio" (id 465) en la tienda de pruebas.** La tienda no tenía rama de
gimnasio; Angie autorizó crearla. (El árbol en vivo se lee siempre; Claude no crea/modifica
categorías sin su ok.)

**Límites honestos:** galería mínima (2 imgs) porque la fuente publica UNA foto; tienda REAL sigue
apagada (candado a `pruebas.ekipon.co`); el precio lo define Angie; falta su revisión visual del
borrador. **DNS de `pruebas.ekipon.co` viene intermitente** (resuelve a ratos); se sorteó con
warm-up + reintentos, pero el Publicador NO tiene reintentos internos — agregarlos si se automatiza.

**4. Primer LOTE end-to-end (muestra de 6 de la colección Fitness Market marca-propia, de 35).**
Todos a borrador en Gimnasio. **Colador: 3 VERDES** (leg curl 50300, Smith 50304, banco 50308) /
**3 REVISAR** (squat rack 50313 sin dimensiones, barra 50317 sin peso, set 50321 combo sin specs) —
50/50, todos los amarillos por dato faltante REAL, ninguno por bug. Findings de escala: (a) **el DNS
intermitente era el cuello operativo** — cada producto tardaba ~35s por warm-up manual. **RESUELTO
(30-jul):** `cliente_tienda._solicitar` ahora reintenta la conexión con espera creciente (el
Publicador lo hereda); un fallo de DNS se reintenta aun en POST porque ocurre antes de enviar el
pedido; un corte no-DNS solo se reintenta en lecturas (para no duplicar). 6 tests nuevos, verificado
en vivo sin warm-up manual. Ya se puede correr un lote de corrido; (b)
el gate visual atrapó que el "set de 8 piezas" mezcla agarres + un rack en sus fotos; (c) la
validación frenó una ficha malformada antes de la tienda. **El pipeline es sólido (6/6 llegaron); los
cuellos para 35 son operativos (DNS) + tu revisión sobre el ~50%, no el sistema.**

**5. Enriquecimiento del contenido (feedback de Angie: "todo se ve corto salvo el banner").** Se
subió el estándar de salida, sin cruzar a inventar. Automático para todos: **descripción COMPLETA**
traída en vivo de la fuente (subió de ~150 a 300-560 chars), **tarjeta de medidas** (solo con ≥2
ejes reales — una barra no la lleva, su largo va en la ficha técnica) y **recorte limpio** de
portada. Con revisión por producto (solo en máquinas multi-parte): **partes señaladas** (callouts;
los puntos se ubican a ojo y se revisa la pieza — `validar_puntos` solo confirma que caiga SOBRE el
producto, no que sea la parte correcta). El leg press 50295 tiene el tratamiento COMPLETO (4 imgs,
incluye callouts); los 6 del lote quedaron con el enriquecimiento automático. La ficha técnica NO se
infla: la fuente publica ~5 datos y no se inventan specs. Generador: `scratchpad/gen_fichas_lote.py`
(pendiente hornear `prosa_de_fuente` + `_plan_galeria` en el pipeline real).

**6. Los 28 restantes de Fitness Market: preparados + medidos (aún NO publicados).** Se construyó un
**extractor automático** (`scratchpad/gen_fichas_auto.py`) que trae cada producto, parsea specs por
regex y arma la ficha enriquecida (descripción completa + galería recorte/foto/medidas). Medición
del colador: **20 VERDES / 8 REVISAR** (~71% limpio; los 8 por dato faltante real: torre con 2 dims,
accesorios sin specs, 4 multifuerza sin peso). **Lección de escala:** el extractor auto es tan bueno
como su parser — la 1ª regex era angosta (exigía "mm", sin guiones ni cm) y producía falsos
"contenido corto"; se cazó **verificando la medición contra la fuente**, no aceptando el número.
FALTA: gate visual de las 28 portadas (obligatorio) → recorte → publicar, **en oleadas de ~7** (no
las 28 a ciegas). Este commit es un CHECKPOINT: fichas + fotos preparadas, nada publicado aún.

**7. Oleada 1 publicada (7 máquinas serie U, 50347-50377) + arreglo del HALO del recorte.** Angie
detectó a ojo (su dominio) un **halo blanco** en el banner del vertical press: rembg deja el borde
anti-aliased con color casi-blanco (fondo filtrado) que, sobre el banner oscuro, se ve como glow.
Fix: `recortar_producto.limpiar_halo` vuelve transparentes los píxeles de alfa PARCIAL + casi-blancos,
sin tocar el producto sólido (marco plateado intacto) ni los cables finos oscuros. 3 tests nuevos
(suite **264**). Se re-limpiaron y re-publicaron los **14** productos ya en la tienda con el banner
limpio. **Van 14 gym publicados; faltan 21** (oleadas siguientes).

**Detalle:** memorias de Engram `end-to-end-completo-de-un-producto-de-gimnasio`,
`primer-verde-del-colador`, `la-tienda-de-pruebas-no-tiene-categor-a-de-gimnasio`, `lote-de-muestra-gym`,
`demo-de-enriquecimiento-del-leg-press`, `enriquecimiento-aplicado-al-lote-de-6`, `los-28-restantes-de-fitness-market`,
`primera-oleada-publicada`.

**8. COLECCIÓN COMPLETA de Fitness Market marca-propia publicada (30-jul).** Oleada 3 (6 máquinas,
50438-50463) cerró los 20 verdes; luego se subieron los **8 REVISAR** restantes (50467-50502) como
borrador — el colador los marca porque les falta un dato real (specs/peso/dimensiones) que Angie
debe completar antes de publicar en vivo. **Bug encontrado y arreglado:** 2 fotos (multifuerza serie
1 y 2) venían de la fuente a 2613×2613 px en vez de 1080×1080; el Publicador tardaba más del timeout
de 30s al subirlas y fallaba (timeout de LECTURA, no DNS — el reintento no actuó solo, correctamente:
un POST que expira en la lectura pudo haberse aplicado, reintentar a ciegas duplicaría). Se
redimensionaron a 1080×1080 antes de subir; el Publicador es idempotente así que reintentar el
comando fue seguro. **Total: 29 productos de gimnasio en `pruebas.ekipon.co`, categoría Gimnasio.**

---

## 🔵 ACTUALIZACIÓN 29-jul-2026

Se cerró el círculo end-to-end del colador y se arregló su primer sesgo, todo verificado ejecutando.
**Suite: 251 → 255 tests en verde** (+4).

**1. Círculo end-to-end del colador: CERRADO en vivo.** Hasta ahora el colador solo se había
probado contra fichas ya existentes. Se hizo la pasada VIVA de un solo tiro: un link real →
el Investigador arma la ficha → el colador la revisa.
- **Mezcladora HY-200** (Alibaba, uno de los "limpios" del lote 2): al extraerla campo por campo
  aparecieron DOS contradicciones que el skim rápido de la medición no vio (potencia 4kW vs 15kW;
  motor "diésel" vs eléctrico). El colador marcó REVISAR por esos dos motivos reales. Hallazgo:
  **el "3/10 limpio" del lote 2 está inflado** — una extracción a fondo destapa autofills de
  Alibaba que el vistazo no ve. La revisión humana queda aún más confirmada.

**2. Bug del colador (ceguera de categoría) ENCONTRADO y ARREGLADO.** Con una fuente seria
(importador colombiano IO Company, escalera 5525) la ficha salió limpísima, pero el colador dio un
**falso positivo**: "falta la potencia del motor"… en una ESCALERA. El colador exigía potencia a
TODO producto. El catálogo trae categorías sin motor (gimnasio, sillas, escaleras, herramienta
manual).
- **Fix:** campo nuevo `producto.es_motorizado` (sí/no) que llena el Investigador. El colador exige
  potencia SALVO que la ficha diga explícitamente que no lleva motor. Sesgo conservado "ante duda,
  marca": si el campo falta, se asume motorizado (las 7 fichas viejas, todas máquinas, siguen igual).
- **Tocó 4 piezas:** `revisor_publicacion.py` (guarda + helper `_es_no_motorizado`), `esquema_ficha.py`
  (campo en el contrato), `test_revisor_publicacion.py` (+4 tests), y el skill del Investigador
  (`SKILL.md` + `plantilla_ficha_v1.4.json`).
- **Verificado:** la escalera 5525 con `es_motorizado:false` pasó de 2 motivos (uno falso) a 1
  legítimo (la fuente no publica capacidad de carga ni peso). Falso positivo eliminado.

**3. Deploy del skill: las 3 copias durables al día.** El repo NO refresca la copia instalada que
corre. Se copió `SKILL.md` + plantilla al target instalado (diff final vacío) y se reempacó el
artefacto `.skill`. La próxima corrida del Investigador en vivo llenará `es_motorizado` sola.

**Sigue sin verse un VERDE limpio (LISTO):** la escalera queda REVISAR por un dato real que la fuente
no trae (capacidad de carga). Para un verde hace falta una fuente sin contradicciones y con potencia
(si aplica) + dimensiones + capacidad. Puede ser raro con listings crudos.

**PRÓXIMO PASO:** decidir si "sin dimensiones/capacidad" bloquea o solo avisa; y producción tienda
real = decisión de encender (candado a `ekipon.co` + credenciales reales de Angie).

**Detalle:** memorias de Engram `cerrado-el-c-rculo-end-to-end-del-colador-hy-200`,
`arreglado-el-falso-positivo-sin-potencia-del-colador`, `deploy-cerrado-es-motorizado`.

---

## 🔵 ACTUALIZACIÓN 28-jul-2026

Empezó la fase de ESCALA. Lo verificado, ejecutando:

**1. Se midió la tasa de error del Investigador — DOS lotes de links de Alibaba (Prioridad A #2, HECHA).**
- Lote 1 (10 links agro, 27-jul): **50% necesita corrección**.
- Lote 2 (10 links MIXTOS —agro, construcción, bombeo, izaje, movilidad—, 28-jul): **30% limpio /
  70% corrección**. Método: navegar cada link + extraer specs + juzgar calidad de ficha; NO se
  publicó ninguno.
- **Hallazgo clave:** el pipeline NO se rompió en ninguno (10/10 extraídos, sin CAPTCHA en el
  navegador interno). El "error" es **calidad de la fuente**, no del Investigador: campos "Tipo"
  autollenados que contradicen el nombre, listings que son familias configurables (varios
  motores/combustibles) y specs delgadas. **Conclusión medida: la revisión humana es obligatoria,
  no opcional.** Con listings crudos de Alibaba, "cero intervención humana" no es alcanzable.

**2. Construido el COLADOR de listo-para-publicar (`revisor_publicacion.py`, commit `1d171c6`).**
- Separa fichas que pueden fluir solas (**LISTO**) de las que necesitan los ojos de Angie
  (**REVISAR**). No re-hace el juicio del Investigador: **lee las notas que este ya deja en la
  ficha** (`identificacion_del_producto.advertencias`, `campos_por_confirmar`) y les suma chequeos
  mecánicos (falta potencia, faltan dimensiones, estado "usado"). Sesgo: ante duda, MARCA.
- **14 tests nuevos; suite total 251 en verde.**
- Corrido sobre las 7 fichas reales existentes: **7 rojas, 0 verdes** — porque todas tienen ≥1 cosa
  real por confirmar. Hoy NO recorta el número que Angie revisa; cambia el CÓMO (cada ficha llega
  pre-etiquetada con qué mirar). El verde —el ahorro real— aparece cuando entren fichas más limpias.
- **Límite honesto:** el colador es tan fino como las notas del Investigador. Un problema que el
  Investigador no anote solo se atrapa si cae en un chequeo mecánico. Es colador, no muro.

**PRÓXIMO PASO (Prioridad A restante):** (a) cerrar el círculo end-to-end del colador —tomar 1 de
los 10 links, que el Investigador arme la ficha y el colador la revise de una sola pasada (aún no
hecho: el colador se probó contra fichas ya existentes)—; (b) decisión de Angie: ¿"sin dimensiones"
manda a revisión o es solo un aviso?; (c) producción tienda real = decisión de encender (candado a
`ekipon.co` + credenciales reales de Angie).

**Detalle:** memorias de Engram `medici-n-lote-2` y `construido-revisor-publicacion`.

---

## 🔵 ACTUALIZACIÓN 27-jul-2026

Día grande. Cambió la arquitectura de PRESENTACIÓN y se probó el pipeline COMPLETO en varios
productos. Lo verificado, ejecutando:

**1. Investigador de DOS CAMINOS: implementado, desplegado y MEDIDO.**
- Contrato extendido (`link_producto`, `origen_identificacion` link|busqueda_imagen|inferencia).
  Skill instalada en el target de AppData. Ver memoria `implementado-investigador-de-dos-caminos`.
- **Medición del lote (Prioridad A #2):** 10 links agro (Camino A) → **50% salió limpio, 50%
  necesita corrección**. El pipeline NO se rompió en ninguno; el "error" es la CALIDAD DE DATOS
  DEL PROVEEDOR (títulos que contradicen el campo "Tipo", estado "Usado", specs faltantes, números
  implausibles). **Conclusión: la revisión humana es obligatoria, no opcional.** Con link la ficha
  sale rica; sin link (Camino B) sale corta.

**2. La ficha ahora sale en el producto por DESCRIPCIÓN HTML NATIVA (no por Elementor).**
- El intento de inyectar la plantilla Elementor por código NO renderizaba (el 4212 renderiza por
  otra vía, no desde la meta del producto). Se reemplazó: `publicador.generar_descripcion_html()`
  arma ficha técnica + banner (2 columnas: ficha+video izq, banner+características der) como HTML
  con estilos inline en el campo `description`. WooCommerce lo dibuja SIN Elementor, snippet ni
  trabajo manual. Cada producto sale completo solo → Angie solo revisa y publica. Commit 307f7bb.
- Se corrigió el banner (el texto ya no pisa el producto) y el layout 2x2 (commit ad4813c).

**3. Bug de colisión de portadas ARREGLADO.** `subir_imagen` deduplica por título y el motor nombra
las piezas genéricas (`01-producto_limpio.webp`) → un producto reutilizaba la portada de otro (el
taladro tomó la de la picadora). Fix: el título de la imagen lleva el código adelante. Commit aa70d74.

**4. Pipeline completo corrido en 4 productos (borradores en `pruebas.ekipon.co`):**
picadora **50264** (Camino A), taladro **50268** (Camino B, ficha corta), estibadora **50283**
(Camino A, 17 filas), tubo **50290** (Camino A). Falta la mezcladora (sin link aún).

**5. Seguridad (Prioridad A #3) casi cumplida:** `.env` fuera del repo (verificado), y el candado
`TIENDAS_PERMITIDAS = {"pruebas.ekipon.co"}` impide publicar por error en la tienda real.

**PRÓXIMO PASO: producción (tienda real).** Es una decisión de encender, no una tarea: (a) ampliar
el candado a `ekipon.co` (código), (b) credenciales reales de la tienda (tarea de Angie — Claude no
toca credenciales). Se hace cuando Angie diga "ahora sí".

**Detalle completo de la jornada:** memorias de Engram del 24 y 27-jul (buscar "descripción HTML",
"medición de lote", "colisión de portada").

---

## 🟢 DÓNDE ESTAMOS (histórico previo — 23-jul; ver actualización de arriba)

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
| **Colador (listo-para-publicar)** | `revisor_publicacion.py` — marca cada ficha LISTO/REVISAR | ✅ **NUEVO (28-jul)**, 14 tests |
| **Publicador** | `publicador.py` — crea BORRADOR vía API REST, idempotente (`--actualizar`) | ✅ 4212 = ID 50238 + 4 borradores más |
| **Presentación de la ficha** | Descripción HTML nativa (`publicador.generar_descripcion_html`) | ✅ **27-jul**: ficha+banner salen solos, sin Elementor ni trabajo manual |
| **Imágenes (galería)** | Motor propio Pillow — ver `ETAPA_IMAGENES.md` | ✅ **CERRADA end-to-end** (23-jul: borrador 50255 con galería de 8). Mejoras pendientes: generadores escala/escena/otro-ángulo |
| **Banner** | `generador_banner.py` (motor propio, ya no Canva) | ✅ integrado al Publicador |
| **Video** | — | ⬜ última fase, no empezada |
| **Orquestador** | — | ⬜ no empezado |

**Tests:** 251, todos en verde (`python -m pytest`, corrido el 28-jul).

**Estado en git:** el repo es `AngieDM17/Administrador-Inteligente-de-Cat-logo`, rama `main`.
Último commit (HEAD) al 28-jul: `1d171c6` (feat: colador listo-para-publicar). **Árbol limpio** —
todo el trabajo de imágenes, dos caminos, descripción HTML, los 4 borradores y el colador está
commiteado y pusheado a GitHub.

---

## ▶️ PRÓXIMO PASO (Prioridad A)

1. **Etapa de Imágenes: CERRADA end-to-end el 23-jul.** Un producto real (molino) recorrió toda la
   cadena hasta el borrador **50255** con su galería de 8 en la tienda de pruebas. Quedan **mejoras,
   no el cierre**: generadores no construidos (escala/escena/otro-ángulo), automatizar el handoff
   del sourcing (el "buzón") + su gate de verificación visual, y confirmar dims reales del molino
   (hoy `medidas` usa provisionales de Alibaba). Con imágenes cerrada, **el próximo paso de
   Prioridad A pasa a ser el #2: medir la tasa de error del Investigador.** Detalle en `ETAPA_IMAGENES.md`.

2. **Medir la tasa de error del Investigador — con un lote CHICO primero.**
   *RESULTADO 23-jul (lote de 5):* identificación de TIPO por visión **5/5**; la búsqueda de TEXTO
   **contamina** (1/5 claro: picadora → cocina) y casi nunca pincha el modelo exacto sin código.
   **DECISIÓN tomada:** rediseñar el Investigador con **dos caminos de entrada — LINK (preferido:
   extracción completa y verificada, probado) + nombre+foto de respaldo** (inferencia con
   visión-primero + gate visual). Política: siempre intentar conseguir el link. Alibaba pide 1
   CAPTCHA por **sesión**, no por producto; links no-Alibaba = cero. Dos añadidos confirmados:
   **puente foto→link** (buscar un link vía imagen antes de caer a inferencia) y **etiqueta de
   método** por ficha (`origen_identificacion`). Detalle en la memoria
   `decision-investigador-dos-caminos` y en Engram.
   ⚠️ Ojo: el Investigador es una **skill, no código**, así que 100-200 productos no se pueden
   correr sin niñera. Empezar con 20-30 a mano: es el experimento más barato capaz de
   invalidar la apuesta. Si la tasa es mala, se evitó construir un motor de lotes para algo
   roto; si es buena, recién ahí se justifica hacerlo ejecutable.
   *Terminado cuando:* hay un número medido. Umbral: **>5% = todavía no es automatización**.

3. **Endurecer seguridad** — rotar claves de WooCommerce/WordPress, `.env` fuera del repo,
   allowlist `TIENDAS_PERMITIDAS` lista antes de apuntar a la tienda real.
   *Terminado cuando:* llaves nuevas en uso, viejas revocadas, `.env` no rastreado por git.
   *Verificado el 22-jul:* `claves_pruebas.txt` y `.env` nunca entraron al historial de git;
   las claves están en texto plano solo en la máquina local.

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

**Sourcing y verificación (23-jul-2026):**
- **Slots ENCONTRADOS vs CREADOS.** Los encontrados (foto real, accesorios) los limita cuántas
  fotos reales existan; los creados (hero, medidas, partes, escala, escena, otro-ángulo) se
  fabrican desde UNA foto real + la ficha y NO dependen del número de fotos. La "cuota muerta"
  prohíbe una sola cosa: rellenar con recortes repetidos, no fabricar tomas creadas.
- **Todo sourcing automático DEBE pasar por un gate de verificación visual.** Verificado en vivo:
  bajar fotos de proveedor por URL a ciegas trajo OTROS productos (una lancha, motores) en vez del
  molino; solo se atrapó mirándolas. El `criterio_verificacion_visual` no es teoría: es lo que
  evita publicar una lancha en la ficha de un molino.
- **El Chrome logueado de Angie pasa el CAPTCHA de Alibaba** (el navegador limpio no). Conducir ese
  navegador es un camino más liviano que un scraper headless (matiza la lección 6).

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
