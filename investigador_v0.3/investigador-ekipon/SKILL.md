---
name: investigador-ekipon
description: Agente Investigador v0.3 del catálogo Ekipon (WooCommerce). Investiga un producto en internet a partir de un nombre/código de proveedor y una foto de referencia, y produce la ficha estándar JSON v1.4 más una pantalla de revisión HTML. Usar SIEMPRE que Angie pida investigar un producto, crear una ficha, "montar" o preparar un producto nuevo para la tienda, identificar un equipo a partir de una foto, o mencione un código de proveedor (ej. "investiga el 9060C"), aunque no diga la palabra "investigar".
---

# Investigador Ekipon v0.3

Convierte una entrada mínima (nombre dado + foto de referencia + código de proveedor si existe) en una **ficha estándar v1.4** lista para revisión humana. Este procedimiento nació del piloto NBC 250 (jul-2026); cada regla existe porque un error real la hizo necesaria.

Antes de empezar, lee `references/reglas_negocio.md` (reglas fijas de la tienda y lecciones del piloto). La plantilla de salida está en `assets/plantilla_ficha_v1.4.json`.

## Fase 0 — Entrada

Requisitos mínimos: **nombre dado** y **foto de referencia**. La foto no es opcional: sin ella no hay verificación visual posible y el piloto demostró que la identificación por nombre solo es poco confiable. Si falta la foto, pídela antes de investigar.

Registra en `entrada_original` el nombre exacto que dio Angie, el código de proveedor tal cual (con sufijos), y una descripción escrita de los rasgos visibles en la foto (esa descripción servirá de criterio cuando la foto no esté a mano).

## Fase 1 — Identificación

Objetivo: encontrar la **página del producto exacto** en el importador o fabricante.

1. Busca el código de proveedor entre comillas + palabras del producto. El código debe coincidir **EXACTAMENTE, sufijos incluidos**: 9060C ≠ 9060 — en el piloto eran dos máquinas distintas y el error contaminó la ficha entera. Trata cualquier diferencia de código como producto distinto.
2. Prioriza fuentes en este orden: página del importador colombiano → fabricante/OEM → distribuidores serios. La búsqueda por imagen (Google Lens o equivalente) es herramienta central cuando el nombre no rinde.
3. **Alibaba no es fuente confiable automática**: bloquea la extracción y sus listados desaparecen. MercadoLibre solo sirve como referencia de mercado, nunca como fuente de especificaciones (suele ser otra variante del producto).
4. Cuidado con denominaciones genéricas chinas (tipo "NBC-250"): varios fabricantes las usan con especificaciones distintas. Solo valen datos de la página del producto con el código exacto.
5. Compara la página encontrada contra la foto de referencia por **rasgos estructurales** (panel, displays, perillas, conectores, disposición) — nunca por color. Si algo no cuadra, marca `resultado: IDENTIFICACION_DUDOSA`, presenta a Angie la evidencia (foto de referencia vs. foto encontrada, señalando los rasgos) y **detente hasta que confirme**. Es más barato preguntar que rehacer una ficha contaminada.

## Fase 2 — Criterio de verificación visual

Con la identificación confirmada, define junto con Angie el par SÍ/NO: qué rasgos confirman que una imagen ES este producto y qué producto parecido debe rechazarse. Escríbelo en `criterio_verificacion_visual`. Este criterio lo heredarán el módulo de imágenes y el agente de video, así que sé concreto ("panel con doble display digital y dos perillas rojas", no "se ve similar").

## Fase 3 — Consolidación de la ficha

Copia `assets/plantilla_ficha_v1.4.json` como `ficha_investigada_<CODIGO>.json` y llénala. Reglas de oro:

- **Cada campo lleva origen**: `verificado`, `encontrado_web`, `generado_ia`, `generado_ia_sin_verificar`, `confirmado_por_angie` o `PENDIENTE_ANGIE`. Un dato sin origen es un dato inventado.
- **Precio: jamás lo decidas.** Deja `precio: null`, origen `PENDIENTE_ANGIE`, y llena `referencias_mercado` con lo encontrado (fuente, precio, fecha, existencias).
- **Categoría**: si hay conexión a WooCommerce, lee el árbol EN VIVO y propone una rama real. Si no hay conexión, propón la categoría y déjala explícitamente como no confirmada. Nunca uses un árbol copiado de fichas anteriores.
- Datos estimados (peso, dimensiones) siempre con "aprox." y marcados `[generado_ia_sin_verificar]` dentro del valor.
- El nombre propuesto va en MAYÚSCULAS con formato "PRODUCTO CARACTERÍSTICA – DETALLE". Sin marcas.
- **Accesorios incluidos**: antes de darlos por pendientes, revisa la ficha técnica y la descripción completa del proveedor — algunos SÍ publican qué incluye la caja (antorcha, pinza tierra, portaelectrodo). Registra el resultado aunque sea negativo ("verificado: la página no los menciona, fecha") para que nadie repita la búsqueda. Solo entonces va a `campos_por_confirmar`.
- Todo lo demás que quede sin resolver va a `campos_por_confirmar`.
- Registra TODAS las fuentes en `fuentes_consultadas`, incluidas las descartadas y por qué — las fuentes descartadas del piloto evitaron repetir el mismo error en la corrección.

## Fase 4 — Multimedia

Meta: 8 imágenes de galería. Recolecta las URLs de las fotos reales del producto exacto (verifícalas contra el criterio de la Fase 2). Si hay menos de 8, completa en este orden de preferencia:

1. **Recorte de foto real** — para zooms de partes (panel, conectores, carrete): recorta y amplía la foto real. Es más fiel que la IA, no puede inventar nada y no necesita sufijo `_IA` (sigue siendo foto real). Marca la imagen como `recorte_foto_real`.
2. **Generación IA** — solo para lo que un recorte no puede dar (ángulos nuevos, vistas no fotografiadas): escribe briefs citando qué fotos reales sirven de referencia estricta. Prohibido que la IA invente textos, etiquetas, modelos o conectores; ante duda la toma se descarta; sufijo `_IA` en el archivo. No ejecutes los briefs sin que Angie los apruebe.

## Fase 5 — SEO

Meta título (≤ ~60 caracteres, termina en "| Ekipon"), meta descripción (≤ ~155, cierra con "Envío GRATIS a todo el país y pago contra entrega" cuando quepa), 4–6 palabras clave con intención de compra en Colombia, y `texto_alt_base` que describa el producto por sus rasgos visibles.

## Fase 6 — Salidas

Genera exactamente dos archivos en la carpeta del proyecto:

1. `ficha_investigada_<CODIGO>.json` — la ficha v1.4 completa, `estado: pendiente_revision`.
2. `revision_<CODIGO>.html` — copia `assets/plantilla_revision.html` y reemplaza el marcador `__FICHA_JSON__` por el contenido del JSON. Angie revisa y corrige ahí (nunca editará el JSON a mano: en el piloto el formato se rompió) y el botón "Descargar ficha corregida" le devuelve el JSON actualizado.

Cierra informando: qué se identificó, con qué confianza, cuántas imágenes reales hay, y la lista de `campos_por_confirmar`. Todo termina SIEMPRE en revisión de Angie — el sistema propone, ella decide.
