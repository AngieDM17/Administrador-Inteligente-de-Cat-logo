---
name: investigador-ekipon
description: Agente Investigador v0.3 del catálogo Ekipon (WooCommerce). Investiga un producto en internet a partir de un nombre/código de proveedor y una foto de referencia, y produce la ficha estándar JSON v1.4 más una pantalla de revisión HTML. Usar SIEMPRE que Angie pida investigar un producto, crear una ficha, "montar" o preparar un producto nuevo para la tienda, identificar un equipo a partir de una foto, o mencione un código de proveedor (ej. "investiga el 9060C"), aunque no diga la palabra "investigar".
---

# Investigador Ekipon v0.3

Convierte una entrada mínima (nombre dado + foto de referencia + código de proveedor si existe) en una **ficha estándar v1.4** lista para revisión humana. Este procedimiento nació del piloto NBC 250 (jul-2026); cada regla existe porque un error real la hizo necesaria.

Antes de empezar, lee `references/reglas_negocio.md` (reglas fijas de la tienda y lecciones del piloto). La plantilla de salida está en `assets/plantilla_ficha_v1.4.json`.

## Fase 0 — Entrada

Hay **dos maneras de entrar**, y una es preferida:

- **CON LINK (preferido).** Angie da el **link exacto** del producto. Es la identidad más fuerte: la ficha sale por extracción de la fuente, completa y verificable. Guárdalo en `entrada_original.link_producto`.
- **SIN LINK (respaldo).** Solo **nombre dado + foto de referencia**. La foto no es opcional: sin ella no hay verificación visual posible y el piloto demostró que identificar por nombre solo es poco confiable. Si falta la foto, pídela antes de investigar.

**Política: siempre intenta conseguir el link.** Aunque Angie entre con nombre+foto, el primer trabajo de la Fase 1 es producir un link antes de caer a la inferencia. El camino de respaldo es la **red de seguridad**, no el plan.

Registra en `entrada_original` el nombre exacto que dio Angie, el código de proveedor tal cual (con sufijos), el link si lo hay, y una descripción escrita de los rasgos visibles en la foto (esa descripción servirá de criterio cuando la foto no esté a mano).

**Si Angie no dio código de antemano (entrada solo con link — el caso normal del lote de varios links), el código lo asignás vos.** Nunca dejes `entrada_original.codigo_proveedor` vacío ni en `null`: el resto del sistema lo usa como identificador único para nombrar archivos (video, banner, carpeta del producto) y para armar el link final en la tienda — sin él, la ficha no se puede publicar y toda la corrida se corta ahí. En la Fase 1, en cuanto identifiques la página del producto, sacá el número de modelo o SKU que declare el fabricante/importador y escribilo en `entrada_original.codigo_proveedor` (13-ago-2026: un caso real mostró que el modelo SÍ se encontraba y se usaba para nombrar las fotos, pero nunca se copiaba a este campo — quedaba `null` y la publicación fallaba igual). Si la fuente genuinamente no publica ningún código reconocible, armá uno corto y estable a partir de la página (por ejemplo, el identificador numérico que trae la URL del listing) — la regla dura es que este campo **nunca** quede vacío al terminar.

## Fase 1 — Identificación (dos caminos)

Objetivo: encontrar la **página del producto exacto** en el importador o fabricante. Termina SIEMPRE marcando **cómo** lo lograste en `identificacion_del_producto.origen_identificacion` (`link` | `busqueda_imagen` | `inferencia`): esa etiqueta le dice a Angie cuánto confiar en la revisión.

### Camino A — con link (dado, o ya conseguido por el puente)

Extrae directo de la fuente. Marca `origen_identificacion: link`.

- Links **NO-Alibaba** (importador / fabricante / retail serio): se leen solos con extracción web, sin trabas.
- Links de **Alibaba**: la extracción automática a ciegas está **bloqueada** (devuelve vacío). Se leen desde el navegador con la sesión de Angie, que pide **un CAPTCHA por sesión, no por producto** (resuelto una vez, varias fichas de Alibaba cargan en fila). Alibaba es fuente de datos válida cuando el link es el del producto exacto; lo que no sirve es el grab ciego.

### Camino B — sin link

**B1 — Puente foto→link (intentar SIEMPRE primero).** Antes de inferir, intenta **producir un link** por búsqueda por imagen: pega la foto de referencia en Alibaba Lens (en el Chrome de Angie), entra a los proveedores que devuelve y verifica cada candidato contra los rasgos estructurales de la foto. Si uno coincide, **ya tienes link → vuelve al Camino A** y marca `origen_identificacion: busqueda_imagen`.

**B2 — Inferencia (solo si el puente no dio link).** Arma la búsqueda **desde la visión primero** (los rasgos que ves en la foto guían las palabras, no al revés) y pasa cada resultado por el **gate visual** (compáralo con la foto antes de creerle). La ficha que sale es **nivel-familia** y va marcada de **menor confianza**: `origen_identificacion: inferencia`. Esta es la red de seguridad, no el objetivo.

### Reglas que valen en los dos caminos

1. El **código de proveedor** debe coincidir **EXACTAMENTE, sufijos incluidos**: 9060C ≠ 9060 — en el piloto eran dos máquinas distintas y el error contaminó la ficha entera. Trata cualquier diferencia de código como producto distinto.
2. Prioriza fuentes: página del importador colombiano → fabricante/OEM → distribuidores serios. **MercadoLibre** solo sirve como referencia de mercado, nunca como fuente de especificaciones (suele ser otra variante del producto).
3. Cuidado con denominaciones genéricas chinas (tipo "NBC-250"): varios fabricantes las usan con especificaciones distintas. Solo valen datos de la página del producto con el código exacto.
4. Compara la página encontrada contra la foto de referencia por **rasgos estructurales** (panel, displays, perillas, conectores, disposición) — nunca por color. Si algo no cuadra, marca `resultado: IDENTIFICACION_DUDOSA`, presenta a Angie la evidencia (foto de referencia vs. foto encontrada, señalando los rasgos) y **detente hasta que confirme**. Es más barato preguntar que rehacer una ficha contaminada.

## Fase 2 — Criterio de verificación visual

Con la identificación confirmada, define junto con Angie el par SÍ/NO: qué rasgos confirman que una imagen ES este producto y qué producto parecido debe rechazarse. Escríbelo en `criterio_verificacion_visual`. Este criterio lo heredarán el módulo de imágenes y el agente de video, así que sé concreto ("panel con doble display digital y dos perillas rojas", no "se ve similar").

## Fase 3 — Consolidación de la ficha

Copia `assets/plantilla_ficha_v1.4.json` como `ficha_investigada_<CODIGO>.json` y llénala. Reglas de oro:

- **Cada campo lleva origen**: `verificado`, `encontrado_web`, `generado_ia`, `generado_ia_sin_verificar`, `confirmado_por_angie` o `PENDIENTE_ANGIE`. Un dato sin origen es un dato inventado.
- **Precio: jamás lo decidas.** Deja `precio: null`, origen `PENDIENTE_ANGIE`, y llena `referencias_mercado` con lo encontrado (fuente, precio, fecha, existencias).
- **Categoría**: si hay conexión a WooCommerce, lee el árbol EN VIVO y propone una rama real. Si no hay conexión, propón la categoría y déjala explícitamente como no confirmada. Nunca uses un árbol copiado de fichas anteriores.
- Datos estimados (peso, dimensiones) siempre con "aprox." y marcados `[generado_ia_sin_verificar]` dentro del valor.
- El nombre propuesto va en MAYÚSCULAS con formato "PRODUCTO CARACTERÍSTICA – DETALLE". Sin marcas. **TODO el texto en mayúsculas de verdad, sin ninguna excepción** — incluida la "x" que separa medidas (ej. "90 X 37,5 CM", no "90 x 37,5 cm" ni "90 x 37,5 CM"): una sola letra minúscula en cualquier parte del nombre (así sea una "x" de "por") hace que la ficha entera se rechace. Caso real, 19-ago-2026: "BANDA 90 x 37,5 CM" con la "x" en minúscula tumbó la ficha.
- **`producto.es_motorizado` (SIEMPRE):** `true` si el producto lleva motor (maquinaria eléctrica/combustión), `false` si no (escalera, silla, gimnasio, herramienta manual). El revisor de listo-para-publicar exige "potencia del motor" solo a los motorizados; si lo dejas sin definir, asume que sí lleva motor y lo pedirá. Un producto sin motor sin este campo en `false` genera un falso "falta la potencia".
- **Accesorios incluidos**: antes de darlos por pendientes, revisa la ficha técnica y la descripción completa del proveedor — algunos SÍ publican qué incluye la caja (antorcha, pinza tierra, portaelectrodo). Registra el resultado aunque sea negativo ("verificado: la página no los menciona, fecha") para que nadie repita la búsqueda. Solo entonces va a `campos_por_confirmar`.
- Todo lo demás que quede sin resolver va a `campos_por_confirmar`.
- Registra TODAS las fuentes en `fuentes_consultadas`, incluidas las descartadas y por qué — las fuentes descartadas del piloto evitaron repetir el mismo error en la corrección.

## Fase 4 — Multimedia: el plan de la galería

Llenas **dos** contratos de la sección `multimedia`, y no se superponen:

| Contrato | Qué responde |
|---|---|
| `plan_galeria` | **QUÉ** lleva la galería y **de qué foto real** sale cada pieza |
| `galeria_tomas` | Los **DATOS** con los que el motor dibuja las piezas generadas (etiquetas, medidas) |

Lo que **NO** llenas: el campo `archivo` de los slots que **produce el motor** (lo escribe él al
generar la pieza) ni `imagenes_galeria_confirmadas` (se arma solo a partir del plan, después). Tú
planificas; la máquina produce.

**Excepción — los slots de material real SÍ llevan `archivo`.** En `foto_real` y `accesorios` la
imagen ya existe: el motor no genera nada para ellos y los omite diciendo que son "material real,
entra por la carpeta del producto". Si dejas su `archivo` vacío, ese slot no apunta a ninguna imagen
y queda inservible: nunca llega a la galería. Regla práctica:

| El material del slot… | `archivo` |
|---|---|
| ya existe (`foto_real`, `accesorios`) | **lo escribes tú**, con la ruta de la foto real dentro de la carpeta del producto |
| lo dibuja el motor (`producto_limpio`, `medidas`, `partes_senaladas`, …) | lo dejas ausente; lo escribe el motor |

### 4.1 Reunir el material real

Normalmente llega **una sola foto**. El primer trabajo es buscar en internet la mayor cantidad de
fotos reales del producto exacto, y verificar cada una contra el criterio de la Fase 2.

**Antes de eso, descarta las imágenes que no son del producto.** Las páginas de proveedor mezclan
fotos reales con material de "credibilidad de la empresa": certificados de calidad, capturas de
entrevistas o TV, fotos de fábrica/bodega, banners de marketing genéricos. Ninguna de estas es
candidata a la galería — se reconocen de un vistazo, sin necesidad del criterio visual (regla fija,
ver `reglas_negocio.md`).

**No hay meta de 8 imágenes. La cuota fija está muerta.** Se llenan los slots que el material real
permita llenar con honestidad, y nada más. Rellenar hasta un número con recortes redundantes del
mismo objeto es lo que produjo la galería "cortada y toda igual" del piloto 4212: mejor 3 tomas
honestas que 8 con relleno. Un slot que no aplica **no se sustituye por otra cosa**: se omite.

Sobre los recortes: solo sirven con originales de alta resolución. En el NBC 250 se rechazaron
porque venían de capturas de ~500 px ampliadas. **Un recorte nunca sustituye un ángulo nuevo.**

### 4.2 `plan_galeria`

- `imagen_base` — la **foto canónica** del producto: la que define su identidad visual. Toda pieza
  derivada sale de ella, y por eso las piezas se ven como la MISMA máquina y no derivan hacia otro
  equipo. Lleva su `imagen_base_origen`.
- `slots` — la lista, **en el orden en que se verá la galería**. Cada slot declara:

| Campo | Qué es |
|---|---|
| `tipo` | qué muestra la toma (lista cerrada, abajo) |
| `fuente` | **CÓMO** se hizo la imagen (lista cerrada, abajo) |
| `origen` | **QUIÉN responde** por ella (los mismos orígenes de la Fase 3). **Condicional:** ver abajo |
| `deriva_de` | de qué foto real salió, si no es la `imagen_base` |
| `nota` | descripción breve de la toma; termina siendo el texto ALT de SEO |

**`tipo`** — uno de: `producto_limpio`, `partes_senaladas`, `foto_real`, `medidas`, `accesorios`.

**Fuera de alcance por ahora (decisión de Angie, 30-jul-2026):** `persona_escala`,
`portada_variantes`, `escena_funcionamiento`, `otro_angulo_ia`. Esas tomas se van a generar
aparte y se suben a la galería a mano; **no las planifiques** en `plan_galeria` hasta que se
avise que el plan está listo para incorporarlas de nuevo. No es una omisión caso por caso (no
va en `_slots_omitidos_y_por_que`): es un tipo de toma que el proyecto no cubre todavía.

**`fuente`** — uno de: `foto_real` (material real tal cual), `edicion_manual` (foto real editada a
mano), `generado_motor` (pieza determinista del motor propio), `compuesto` (montaje de material
real), `escena_ia` (entorno generado con el producto real encima), `imagen_a_imagen` (re-render del
producto a partir de una foto real).

**`origen` va SOLO si el slot ya tiene `archivo`.** El esquema lo exige exactamente en ese caso y en
ningún otro: un slot planificado y todavía no producido no tiene imagen, y sin imagen no hay de qué
responder. O sea que va junto con la excepción de arriba —los slots de material real llevan los dos,
`archivo` y `origen`— y los que produce el motor no llevan ninguno de los dos: él escribe el archivo
y hereda el origen del dato con que dibujó la pieza. **No inventes un responsable para una imagen
que todavía no existe**, y si la validación te rechaza un slot por origen, mirá primero si le pusiste
`archivo`.

**Slots condicionales:** `accesorios` solo si el producto viene con accesorios. Si no aplica, no va.

#### Un slot que no va se DECLARA: `_slots_omitidos_y_por_que`

Omitir un slot en silencio pierde información. La etapa siguiente no puede distinguir "este producto
no lleva `accesorios`" de "el Investigador se olvidó", y el próximo que abra la ficha rehace el
mismo análisis para llegar a la misma conclusión.

Por eso, cuando dejes fuera un slot que la plantilla de su categoría pedía, escribí el motivo en la
clave **opcional** `_slots_omitidos_y_por_que` dentro de `plan_galeria`: una lista de textos, un
renglón por slot omitido. Si no omitiste ninguno, no pongas la clave.

```json
"plan_galeria": {
  "_slots_omitidos_y_por_que": [
    "accesorios: la fuente no menciona que el producto incluya accesorios"
  ],
  "imagen_base": "…"
}
```

Va con guion bajo a propósito: las claves `_` son ayuda para humanos y el motor las descarta antes
de validar, así que documentar la omisión no cambia en nada lo que se produce.

#### Las dos reglas que el esquema hace cumplir

1. **Ninguna imagen del producto nace sin una foto real detrás.** Toda `fuente` distinta de
   `foto_real` está obligada a declarar de dónde salió (`deriva_de` propio, o la `imagen_base` del
   plan). Consecuencia buscada: **texto → imagen es imposible de escribir en este contrato**. El
   caso que inventó una marca falsa ("SHENGKEY") no se puede ni representar.
2. **Una recreación jamás se disfraza de fotografía.** `fuente` y `origen` son ejes distintos y el
   esquema no los deja contradecirse: una imagen hecha con `escena_ia` o `imagen_a_imagen` **no
   puede** declarar `verificado` ni `encontrado_web` (eso afirmaría que es una foto). Sí puede
   declarar `generado_ia_sin_verificar`, o `confirmado_por_angie` cuando ella la revisó y responde
   por ella. Además el archivo lleva `_IA` en el nombre, para que se delate a simple vista.

Si intentas escribir una combinación prohibida, la validación la rechaza con el motivo. No la
esquives: significa que la imagen no es lo que dice ser.

### 4.3 `galeria_tomas`

Los datos con los que el motor dibuja las tomas generadas. Todo es opcional y **lo que no esté
verificado se OMITE**: ningún dato faltante frena el pipeline, y ninguno se inventa.

- `callouts` — lista de partes señaladas del producto: `{ "label": "...", "point": null }`.
  Va con `callouts_origen` obligatorio si hay al menos una.
- `dimensiones` — `alto`, `ancho`, `fondo`, `peso`, como texto **con su unidad** ("85 cm", "20 kg").
  Va con `dimensiones_origen` obligatorio si hay al menos una.

#### `point` SIEMPRE va en `null`

Tú averiguas **QUÉ partes** tiene el producto leyendo la web; **no sabes DÓNDE caen sobre la foto**
— eso solo se sabe mirando la imagen. Sin punto, esa parte simplemente no se dibuja. **Nunca
inventes una coordenada.** Ubicar los puntos es un paso visual posterior.

### 4.4 Generación con IA — fuera de alcance por ahora

**Descartada del proyecto por decisión de Angie (30-jul-2026).** `imagen_a_imagen` (otro ángulo
del MISMO equipo) y `escena_ia` (entorno generado con el producto real encima) no se generan
hoy: esas tomas se van a producir aparte y se suben a la galería a mano. No escribas
`briefs_generacion_ia` ni planifiques estos tipos — se retoma cuando el plan de esa parte esté
mejor montado. Se conserva la regla de fondo para cuando se reactive: prohibido que la IA
invente textos, etiquetas, modelos o conectores; imagen → imagen inventa las caras que ninguna
foto muestra (comprobado en el NBC 250), y nada de esto se ejecuta sin que Angie lo apruebe.

## Fase 5 — SEO

Meta título (≤ ~60 caracteres, termina en "| Ekipon"), meta descripción (≤ ~155, cierra con "Envío GRATIS a todo el país y pago contra entrega" cuando quepa), 4–6 palabras clave con intención de compra en Colombia, y `texto_alt_base` que describa el producto por sus rasgos visibles.

## Fase 6 — Salidas

Genera exactamente dos archivos en la carpeta del proyecto:

1. `ficha_investigada_<CODIGO>.json` — la ficha v1.4 completa, `estado: pendiente_revision`.
2. `revision_<CODIGO>.html` — copia `assets/plantilla_revision.html` y reemplaza el marcador `__FICHA_JSON__` por el contenido del JSON. Angie revisa y corrige ahí (nunca editará el JSON a mano: en el piloto el formato se rompió) y el botón "Descargar ficha corregida" le devuelve el JSON actualizado.

Cierra informando: qué se identificó, con qué confianza, cuántas imágenes reales hay, y la lista de `campos_por_confirmar`. Todo termina SIEMPRE en revisión de Angie — el sistema propone, ella decide.
