# PUNTO DE PARTIDA — Administrador Inteligente de Catálogo Ekipon
### Documento de traspaso para empezar el desarrollo en Claude Code / VS Code
**Fecha:** 15-jul-2026 · **Autora del proyecto:** Angie · **Estado:** fin de sesión 5 (Cowork)

> **Cómo usar este archivo.** Es el primer documento que debe leerse al abrir el proyecto en VS Code. Contiene TODO lo importante: objetivo, negocio, flujo de trabajo, arquitectura, reglas, lo aprendido y el primer paso técnico. En un repo de Claude Code puedes renombrarlo `CLAUDE.md` para que Claude lo lea automáticamente. Si algo aquí choca con la realidad, gana lo que veas en la tienda y en el catálogo del proveedor.

---

## 0. Contexto humano (leer primero, no saltar)
- **Angie no es programadora.** Es diseñadora gráfica y administra la tienda WooCommerce de la empresa. Está aprendiendo IA y desarrollo.
- **Claude actúa como arquitecto de software senior, desarrollador principal y MENTOR.** Cada término técnico (API, backend, ORM, cola, contenedor, hook, etc.) se explica en palabras simples, con ejemplo de la vida real, antes de usarlo.
- **Trabajo en equipo, no obediencia ciega.** Angie es la dueña del producto (conoce el negocio); Claude cuestiona las ideas, propone mejores soluciones y advierte riesgos ANTES de implementar. Se prefiere una contradicción con argumentos a una mala solución.
- **Calidad sobre velocidad.** Se construye bien aunque tome meses; la meta es una plataforma profesional que en el futuro pueda venderse a otras empresas.

---

## 1. Objetivo del proyecto
Construir un **Administrador Inteligente de Catálogo para WooCommerce, impulsado por IA**, que automatice la creación y administración de productos de la tienda **ekipon.co** con la mínima intervención humana.

- **Hoy:** ~5.000 productos, proceso 100% manual (60–90 min por producto).
- **Meta:** escalar a 100.000+ productos sin rehacer la arquitectura.
- **No** es "un subidor de productos": es una plataforma que administra todo el catálogo.

---

## 2. El flujo de trabajo (pipeline por producto, de inicio a fin)
El 100% de los productos entra por **investigación web** a partir de una entrada mínima. El artefacto que viaja entre todas las etapas es **la ficha estándar en JSON**.

```
Entrada: nombre del proveedor + código + foto de referencia (+ catálogo del proveedor)
   │
   ▼
1. INVESTIGADOR (IA)  → identifica el producto exacto, cruza foto vs catálogo/importador,
                        consolida la ficha JSON con ORIGEN por cada dato. Precio = null.
   │
   ▼
2. REVISIÓN HUMANA #1 (Angie) → corrige en pantalla (nunca edita el JSON a mano).
                        Aquí pone el PRECIO (manual, siempre) y confirma categoría.
   │
   ▼
3. REDACTOR (IA)      → nombre final, descripción, características, SEO (estilo Ekipon).
   │
   ▼
4. IMÁGENES (mixto)   → 8 imágenes WebP 700x700, texto ALT con el código. Foto real > recorte > IA.
   │
   ▼
5. BANNER (Canva)     → plantilla con foto real + título + sellos (envío gratis / contraentrega).
   │
   ▼
6. VIDEO (mixto, última fase) → guion IA + cortes/subtítulos/voz/música/logo; sube a YouTube.
   │
   ▼
7. PUBLICADOR (código) → crea el producto como BORRADOR en WooCommerce vía API REST,
                        sube fotos, rellena plantillas Elementor. SKU automático.
   │
   ▼
8. REVISIÓN HUMANA #2 (Angie) → revisa el borrador en la tienda y PUBLICA ella.
```

**Los dos puntos de control humano innegociables:**
1. **Precio: SIEMPRE manual** (etapa 2). El sistema solo aporta referencias de mercado.
2. **Publicación: SIEMPRE la hace Angie** sobre un borrador (etapa 8). Nada sale automático.

**Orquestador (transversal):** pasa la ficha entre etapas, registra el estado de cada producto y reintenta lo que falle. Es lo que convierte el pipeline en algo que corre en lote con mínima intervención.

---

## 3. Arquitectura por módulos/agentes
| Módulo | Tipo | Qué hace | Estado |
|---|---|---|---|
| **Investigador** | IA (skill) | Identifica producto, consolida ficha con origen por campo | ✅ v0.3 construida y probada (NBC 250 + 4212) |
| **Redactor** | IA | Nombre, descripción, características, SEO con estilo consistente | ⬜ por construir (hoy se hace dentro del Investigador) |
| **Imágenes** | Mixto | 8 WebP 700x700; real/recorte/IA; ALT con código | 🟡 se hace a mano; falta módulo |
| **Publicador** | Código | Borrador WooCommerce + Elementor vía API REST | 🟡 infraestructura probada; falta el módulo/código |
| **Banner** | Canva (API) | Montaje con plantilla | 🟡 manual (piloto hecho) |
| **Video** | Mixto | Guion IA + edición por código | ⬜ última fase |
| **Orquestador** | Código | Coordina etapas, estados, reintentos | ⬜ por construir (clave para escalar) |

**La ficha estándar JSON** (ver §6) es el corazón: todos los módulos la leen, agregan su parte y la pasan al siguiente.

---

## 4. Reglas de negocio (fijas — no se preguntan, no se cambian)
1. **Precio: SIEMPRE manual.** Lo define Angie. Suele incluir ~$100.000 de envío y se publica "Envío GRATIS a todo el país" + pago contra entrega.
2. **Garantía: siempre 1 año.**
3. **SKU:** lo asigna la tienda automáticamente; no se muestra al público.
4. **Sin marcas y sin precio de oferta.**
5. **Nombres:** MAYÚSCULAS, formato "PRODUCTO CARACTERÍSTICA – DETALLE".
6. **Descripción corta de WooCommerce** = descripción principal de la ficha. Pestaña Descripción = ficha técnica + plantilla Elementor (banner, texto, video).
7. **Todo se publica como BORRADOR.** Angie revisa siempre antes de publicar.
8. **Multimedia por producto:** 8 imágenes de galería + 1 banner Canva + video ~1 min (a YouTube; el enlace va en la plantilla Elementor).
9. **Imágenes:** WebP 700x700, con ALT que incluya el código.

---

## 5. El Investigador v0.3 (la skill ya construida)
Es un **procedimiento formal de 7 fases** que Claude ejecuta (no código todavía; será la especificación del módulo cuando se codifique). Vive en la carpeta de skills (`investigador-ekipon/`): `SKILL.md`, `assets/plantilla_ficha_v1.4.json`, `assets/plantilla_revision.html`, `references/reglas_negocio.md`.

**Las 7 fases:** 0) entrada mínima (nombre + foto obligatoria) → 1) identificación del producto exacto → 2) criterio de verificación visual (par SÍ/NO) → 3) consolidación de la ficha con origen por campo → 4) multimedia (8 imágenes) → 5) SEO → 6) salidas (ficha JSON + pantalla de revisión HTML).

**Salidas:** `ficha_investigada_<código>.json` + `revision_<código>.html`. La pantalla de revisión tiene campos editables y un botón "Descargar ficha corregida" que devuelve el JSON en estado `revisada` (Angie **nunca** edita el JSON a mano — se rompe).

---

## 6. La ficha estándar JSON (v1.4) — el artefacto central
Estructura (claves principales): `entrada_original`, `identificacion_del_producto` (con `advertencias`), `producto` (nombre, categoría, etiquetas, garantía), `precios` (precio + `referencias_mercado`), `descripcion_principal`, `caracteristicas`, `ficha_tecnica`, `criterio_verificacion_visual`, `multimedia` (galería + briefs), `seo`, `campos_por_confirmar`, `fuentes_consultadas`.

**Regla de oro — ORIGEN por campo.** Todo dato lleva su procedencia: `verificado` | `encontrado_web` | `generado_ia` | `generado_ia_sin_verificar` | `confirmado_por_angie` | `PENDIENTE_ANGIE`. Un dato sin origen es un dato inventado. Esto es lo que hace la ficha auditable y es el requisito #1 del motor.

---

## 7. Infraestructura que YA EXISTE (verificada, Fase 0)
- **Tienda de pruebas `pruebas.ekipon.co`** clonada, protegida con contraseña, invisible a Google, sin píxeles.
- **API REST de WooCommerce** con claves creadas y verificadas → permite CREAR productos por API.
- **Contraseña de aplicación de WordPress** creada y probada → subir fotos y leer/escribir plantillas.
- **Dos productos ya creados por API** en la tienda de pruebas (prueba de que funciona).
- **Plantillas Elementor identificadas por ID:** `50198` = ficha técnica · `50201` = características + video YouTube.
- **Vía de publicación DECIDIDA:** API REST de WooCommerce (no manual, no conector de terceros; no existe conector WooCommerce listo).
- ⚠️ **Seguridad pendiente:** las credenciales están en `claves_pruebas.txt` en **texto plano** → mover a variables de entorno / archivo `.env` fuera del control de versiones. Primera tarea de higiene en VS Code.

---

## 8. Decisión de plataforma (sesión 5)
- **El motor automatizado (multiagente, en lote, con hooks de aprobación) se construye y corre en Claude Code vía la extensión de VS Code.** Da la potencia de subagentes/hooks sin usar la terminal; Angie lo maneja desde un panel de chat.
- **Cowork** queda como **cabina de revisión humana** (etapas de aprobación, tareas creativas con conectores).
- **Regla:** no automatizar en serie hasta que el Investigador sea confiable. Ya se probó una vez (4212); conviene correr 1–2 productos nuevos más antes de migrar del todo.
- **Por qué no todo en Cowork:** es por sesión y mantiene a la persona en el bucle; no corre en lote desatendido. **Por qué no solo terminal:** Angie no programa — la extensión resuelve eso.

---

## 9. Roadmap
**Fase 1 Investigador** (✅ hecho como skill) → **Fase 2 Publicador** (siguiente, primer objetivo en VS Code) → **Fase 3 Imágenes** (módulo) → **Fase 4 Banner** (API Canva) → **Fase 5 Video**. El **Orquestador** se va construyendo a medida que hay ≥2 módulos que coordinar.

---

## 10. Lecciones aprendidas (cada una viene de un error real — son requisitos del motor)
**Del piloto NBC 250:**
1. **Código de proveedor EXACTO, con sufijos.** `9060C ≠ 9060`: eran máquinas distintas; el error contaminó una ficha entera.
2. **Verificación visual por rasgos estructurales, NUNCA por color.**
3. **Origen por campo obligatorio** (sin trazabilidad no se sabe qué corregir).
4. **Árbol de categorías EN VIVO desde WooCommerce**, nunca una copia estática (queda desactualizada).
5. **Alibaba no es fuente automática** (bloquea extracción); búsqueda por imagen es central.
6. **Imágenes IA solo para completar**, con las reales como referencia estricta; prohibido inventar textos/etiquetas/conectores; sufijo `_IA`; revisión humana.
7. **Angie no edita JSON a mano** → revisión siempre por pantalla con campos.
8. **Accesorios/qué incluye: revisar SIEMPRE la ficha técnica del proveedor** antes de darlo por pendiente.

**Del piloto 4212 (sesión 5) — las más importantes para el motor:**
9. **Kits/sets: verificar la COMPOSICIÓN contra el CATÁLOGO del proveedor antes de confiar en una sola foto.** El 4212 se titulaba "compresor", la foto parecía un tanque, y en realidad era un **set de 4 componentes** (compresor + tanque + secador + filtro). Solo el catálogo oficial (p.89) lo reveló. Una foto engaña en ambos sentidos: rechazar piezas válidas o dar por bueno el producto equivocado.
10. **Specs "contaminadas" pueden ser legítimas de otra pieza** del set. No descartar specs sin entender la composición.
11. **Galería de 8 sin IA:** con un set de varias piezas se llegó a 8 con material real (4 fotos + 1 montaje del conjunto + 3 recortes). Patrón: priorizar montaje + recortes de foto real antes que IA.
12. **Canva no recrea productos:** genera imagen desde texto (no fiel). Para ángulos nuevos fieles sirven ChatGPT/Adobe imagen→imagen. Canva = banner y composición (montaje/hero), no recreación.

---

## 11. Gotchas técnicos del entorno (relevantes para el build)
- **Desincronización de archivos herramienta ↔ shell:** un archivo escrito por una vía puede verse truncado por la otra. **Fix:** escribir/validar el archivo entero desde una sola vía (en Cowork: desde el shell con Python + `json.loads`).
- **Permisos de borrado:** `rm` de archivos ya sincronizados da "Operation not permitted"; archivos venidos de "subidos" llegan solo-lectura. **Fix:** habilitar borrado / `chmod u+w`. (En VS Code con acceso normal al disco esto desaparece.)
- **El entorno de Cowork no descarga imágenes/PDF de internet ni tiene red abierta a la tienda.** Por eso la publicación real necesita correr donde SÍ hay acceso (VS Code / servidor). Este es el motivo técnico de migrar el Publicador.

---

## 12. Estado actual y primer objetivo en VS Code
**Hecho:** Investigador v0.3 (skill) · piloto NBC 250 completo · piloto 4212 completo (ficha + 8 imágenes) · infraestructura de publicación probada.
**Falta construir como código:** Publicador, módulo de Imágenes, Redactor, Video, Orquestador.

**PRIMER OBJETIVO EN VS CODE — el Publicador (Fase 2):**
1. Higiene: mover credenciales de `claves_pruebas.txt` a un `.env`.
2. Script/módulo que, dado una `ficha_revisada_<código>.json` + la carpeta de imágenes, cree el producto como **BORRADOR** en `pruebas.ekipon.co` vía **API REST de WooCommerce**: título, descripción corta (= descripción principal), categoría, etiquetas, precio, galería de imágenes (subidas con la contraseña de aplicación, ALT con código), y la pestaña Descripción con las plantillas Elementor `50198`/`50201`.
3. Caso de prueba real: el **4212** (todo su material está listo en la carpeta).
4. Añadir el **hook de aprobación**: el proceso deja el producto en borrador y espera la revisión/publicación humana.

Con el Publicador funcionando, se corre 1–2 productos nuevos por el Investigador y se empieza a encadenar con el Orquestador.

---

## 13. Recomendaciones de stack (para discutir al arrancar el build)
Propuestas iniciales, a explicar y validar con Angie antes de fijar:
- **Lenguaje:** Python (ecosistema maduro para IA, scraping, imágenes, APIs).
- **Ficha:** el JSON estándar v1.4 como contrato entre módulos (validar con un esquema, p. ej. `pydantic`).
- **Imágenes:** `Pillow` (redimensionar, WebP, recortes, montajes) — ya probado.
- **WooCommerce:** su **API REST** + la **contraseña de aplicación** de WordPress para media/Elementor.
- **Orquestación:** empezar simple (un script que recorre etapas y guarda estado en archivos/DB) y crecer a una **cola de trabajos** cuando el volumen lo pida (para 100k productos). Explicar "cola" y "base de datos" cuando toque.
- **IA:** el Investigador/Redactor como subagentes de Claude Code, con **hooks** que pausan en los puntos humanos (precio, publicación).
- **Secretos:** `.env` + nunca subir credenciales al control de versiones.

---

## 14. Archivos clave en la carpeta del proyecto
- `HANDOFF_Ekipon_VSCode.md` — **este documento** (punto de partida en VS Code).
- `ESTADO_PROYECTO.md` — bitácora viva del proyecto (sesión a sesión).
- `PRD_Sistema_Inteligente_Ekipon.pdf` — visión inicial de Angie.
- `Arquitectura_Ekipon_v1.1.docx` — arquitectura (desactualizada; pendiente v1.2).
- `investigador_v0.3/` — la skill del Investigador (SKILL.md, plantilla ficha v1.4, plantilla revisión, reglas de negocio).
- **Piloto 4212 (caso de prueba para el Publicador):** `ficha_revisada_4212.json`, `revision_4212.html`, `4212_imagenes/` (8 WebP 700x700 + preview).
- **Piloto NBC 250:** `ficha_investigada_NBC250.json`, `revision_NBC250.html`, `NBC250_imagenes/`.
- `claves_pruebas.txt` — ⚠️ credenciales en texto plano (mover a `.env`).

---

## 15. Glosario mínimo (para Angie)
- **API / API REST:** la "puerta de servicio" de un programa para que otro le pida o le mande datos. WooCommerce tiene una: por ahí creamos productos sin usar el panel a mano.
- **Backend / Frontend:** el motor por debajo (backend) vs. la pantalla que ve la persona (frontend).
- **Orquestador:** el "director de orquesta" que hace que cada módulo toque en su turno y reintenta si algo falla.
- **Hook:** un punto de pausa programado. Aquí sirven para frenar en el precio y en la publicación y esperar tu OK.
- **Headless:** que corre "sin pantalla", solo o en lote, sin que nadie esté mirando.
- **Cola de trabajos (queue):** una fila de tareas pendientes; el sistema las va tomando de a una. Sirve para procesar miles de productos ordenadamente.
- **`.env` / variables de entorno:** un archivo aparte y privado donde se guardan las contraseñas, para no dejarlas escritas en el código.
- **WebP:** un formato de imagen liviano y de buena calidad; el estándar de la tienda (700x700).
- **MCP / conector:** una forma estándar de enchufar herramientas externas (Canva, WooCommerce, etc.) a Claude.

---

*Fin del documento. Para retomar: abrir este archivo primero, luego `ESTADO_PROYECTO.md` para el detalle sesión a sesión, y usar el 4212 como primer caso real del Publicador.*
