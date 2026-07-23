# Etapa Imágenes — motor de galería

**Última actualización:** 2026-07-23

Genera las piezas de la galería de forma determinista: el mismo producto sale siempre
igual, sin definir reglas a mano.

---

## Estado del flujo (23-jul-2026): la generación corre sobre foto real; falta el paso a la tienda

**Novedad del 23-jul:** por primera vez la mitad de **generación** corrió de punta a punta sobre
material REAL y verificado (foto de proveedor de 1080), produciendo **partes** y **medidas**. El
bloqueo de resolución que congelaba la etapa **está resuelto**. Lo que falta ahora es distinto:
subir la galería a la tienda (nunca se hizo) y construir los generadores que aún no existen.

| # | Eslabón | Estado |
|---|---------|--------|
| 1 | Sourcing de fotos reales | 🟡 asistido — ver "Sourcing" abajo |
| 2 | Foto → recorte (`recortar_producto.py`) | ✅ probado sobre foto 1080 |
| 3 | El Investigador emite `plan_galeria` y `galeria_tomas` | ✅ contrato; skill *sin instalar* (reserva abajo) |
| 4 | Ubicar los puntos de los callouts | ✅ paso del procedimiento (agente + `validar_puntos.py`) |
| 5 | El motor arma las piezas (`motor_galeria.py`) | ✅ 3 tipos creados: hero, medidas, partes |
| 6 | Del plan al campo que lee el Publicador | ✅ `imagenes_confirmadas_del_plan` |
| 7 | El Publicador sube al borrador | ✅ `--refrescar-galeria` (opt-in) — **nunca corrido de verdad** |

**Eslabón 2 — la reserva que queda.** La Fase 4 de `SKILL.md` enseña los contratos, y un agente
que la ejecutó a ciegas produjo una ficha válida al primer intento. La reserva es que el
Investigador **no está instalado como skill en ningún lado** — no aparece ni en
`~/.claude/skills/` ni en `.claude/skills/` —, así que hoy se ejecuta leyéndole el `SKILL.md`
a mano. Decir "el Investigador es una skill" es optimista: es una skill *sin instalar*, y eso
conviene tenerlo presente antes de la prueba de lote.

*El paquete `investigador_v0.3/investigador-ekipon.skill` **se reempaquetó el 22-jul-2026**
desde la carpeta viva. Durante ocho días estuvo desincronizado: traía la cuota muerta ("Meta:
8 imágenes de galería") y su `reglas_negocio.md` no tenía las reglas 9b/9c, así que instalarlo
habría instalado el antipatrón. **Es un artefacto derivado: cada vez que se toque `SKILL.md`,
la plantilla o `reglas_negocio.md`, hay que volver a empaquetarlo**, o vuelve a mentir.*

**Eslabón 3 — qué significa "resuelto".** No hay paso de visión automático y se decidió que
por ahora no lo haya: el agente ubica los puntos mirando el recorte y `validar_puntos.py`
controla que caigan sobre el producto. El procedimiento completo, con sus cinco pasos y sus
razones, está más abajo en este mismo archivo.

### Sourcing de fotos reales (probado el 23-jul-2026)

El sourcing hoy lo hace Angie a mano (Alibaba Lens: pega la foto de referencia, entra a los
proveedores, captura las imágenes). Lo probado esta sesión, con el navegador:

- **El muro de Alibaba es de identidad, no de bots.** El navegador limpio choca con un CAPTCHA;
  el **Chrome real y logueado de Angie entra sin CAPTCHA** y "Buscar con imagen" funciona.
  Conducir *ese* navegador es un camino más liviano que un scraper headless — actualiza la
  lección 6 de `ESTADO_PROYECTO.md`.
- **El handoff de la foto local al navegador está trancado** por un candado de seguridad
  (`file_upload` rechaza rutas del repo; navegar a `file://` / `localhost` está bloqueado). Ese
  es el **"buzón"** que hay que diseñar para automatizar; hoy Angie sube la foto a mano.
- **Descargar** fotos de proveedor SÍ funciona (curl desde Bash llega a `s.alicdn.com`).
- **⚠️ El grab de URLs a ciegas es una fábrica de contaminación.** Extraer imágenes por orden del
  DOM trajo los OTROS productos del proveedor (una lancha, motores, un generador), no el molino.
  Solo se atrapó **mirándolas**. **Regla dura: todo sourcing automático DEBE pasar por un gate de
  verificación visual** (match contra las anclas del `criterio_verificacion_visual`). Ese criterio
  dejó de ser teoría; es el candado que evita publicar una lancha en la ficha de un molino.
- Resultado: **6 fotos reales del molino**, variadas y verificadas, en `Imagenes/` (varias 1080+).

### La generación, probada sobre foto real (23-jul-2026)

Corrida real sobre `Imagenes/molino_blanco_harina.jpg` (1042 px): recorte limpio → 6 puntos
ubicados (**6/6 aceptados** por `validar_puntos.py`) → **partes** y **medidas** generadas en
`Imagenes/galeria/`. El pipeline de piezas **creadas** funciona sobre material real.

- **Medidas** salió con dimensiones **provisionales** (las del listado de Alibaba, variante 900W:
  76×34×33 cm, 17,5 kg), marcadas `encontrado_web` en una ficha de trabajo aparte
  (`molino_imagenes/ficha_molino_corrida.json`, **NO** la canónica). El "Alto 33 cm" contradice
  la proporción visible (son sin la base) → hay que reemplazarlo por las medidas **reales** en la
  revisión. Es el caso "traer el dato y corregir en la revisión" que pidió Angie, hecho visible.
- **Partes** salió bien; pega menor de layout (las etiquetas se apilan a la izquierda y las líneas
  guía cruzan la imagen para llegar a las partes de la derecha).

### Lo que falta para declararla cerrada

- **El paso a la tienda nunca se corrió.** Falta que el Publicador `--refrescar-galeria` deje la
  galería en un borrador de `pruebas.ekipon.co`. **Eso es lo que cierra la etapa.**
- **Generadores no construidos** (tipos *creados* que faltan): `persona_escala` (escala; además
  necesita la altura real del producto), `escena_funcionamiento` (IA + red + aprobación de Angie),
  `otro_angulo_ia` (modelo de imagen + red + aprobación), `portada_variantes` (y solo si el
  producto tiene variantes de motor).
- **Dimensiones reales del molino** sin confirmar (para que `medidas` deje de ser provisional).

**Definición de terminado que falta cumplir:** un producto real recorrido entero hasta un borrador
**con galería en la tienda de pruebas**. La generación ya llega; el subir-a-tienda no se probó.

---

## Principios (no negociables)

1. **El producto nunca se crea de la nada; sí puede re-renderizarse desde una foto real.**
   Hay tres niveles y no valen lo mismo:
   - **Texto → imagen: PROHIBIDO.** No hay nada real de donde anclarse. Comprobado: Canva
     generó un molino con una marca inventada ("SHENGKEY").
   - **Imagen → imagen (otro ángulo del MISMO equipo): PERMITIDO Y ACOTADO.** Es fiel cuando
     transforma una vista que la foto ya contiene; **inventa las caras que ninguna foto muestra**
     (trasera, superior) — eso se comprobó en el NBC 250. Se marca `generado_ia_sin_verificar`,
     lleva sufijo `_IA` y pasa por revisión humana.
   - **Escena / fondo / persona con el producto real encima: PERMITIDO.** El producto es su
     recorte real; lo generado es el entorno.

   *Corrección (22-jul-2026): una versión anterior de este documento prohibía toda generación con
   IA sobre el producto. Esa regla generalizaba de más — extendía un fallo de texto→imagen a
   imagen→imagen, que es otra cosa — y contradecía la regla 6 de `reglas_negocio.md` y el proceso
   manual real de Angie. Manda esta versión.*
2. **Galería = visual; ficha = texto.** La galería demuestra, la ficha lista specs.
   No se duplica. Nada de tarjetas de texto de relleno.
3. **Si no está verificado, se omite.** Ningún dato se inventa y ningún dato faltante
   frena el pipeline.
4. **Se estandarizan los TIPOS de toma, no el contenido.** Las etiquetas y medidas
   vienen SIEMPRE de la ficha del producto; nunca hardcodeadas.

---

## Plantilla de galería — el proceso manual real

**Fuente: el proceso que Angie ejecuta hoy a mano** (descrito por ella el 22-jul-2026). Estas son
las órdenes que recibió y el procedimiento que sigue producto por producto. La etapa de imágenes
NO inventa un método nuevo: automatiza ESTE.

**Entrada real:** llega **1 sola foto** con el nombre del producto. El primer trabajo es buscar en
internet la mayor cantidad de fotos reales disponibles. Con lo que aparece se llenan los slots.

**Dos tipos de slot, y no se llenan igual.** Antes de mirar el número, hay que separarlos:
- **Encontrados** (slots 5 y 8 — foto de Alibaba, accesorios): son **fotos reales**. Los limita
  cuántas fotos reales existan; una sola foto rinde pocos de estos.
- **Creados** (slots 1, 2, 3, 4, 6, 7 — persona, partes, portada de variantes, escena, medidas,
  otro ángulo): se **fabrican** desde la foto real + los datos de la ficha. **No** los limita
  cuántas fotos haya: una sola foto real alcanza para varias tomas creadas distintas.

Esta distinción es la que evita el error de creer que "una foto = galería corta": la foto limita
los encontrados, no los creados.

| # | Slot | Origen | Automatizable | Estado |
|---|------|--------|---------------|--------|
| 1 | **Persona al lado** (idea de escala) | Escena IA + recorte real | Alta — plantilla fija | ⬜ requiere red |
| 2 | **Partes señaladas** | Callouts sobre foto completa | Alta — falta ubicar puntos | ✅ `generador_callouts.py` |
| 3 | **Portada con variantes de motor** (diésel / gasolina / eléctrico) | Composición de variantes reales | Alta — composición determinista | ⬜ no construido |
| 4 | **Escena de funcionamiento** | Escena IA + producto real | Media — la escena varía por producto | ⬜ |
| 5 | **Foto de Alibaba** (completa o partes) | Foto REAL | Es sourcing, no generación | ⬜ vía carpeta |
| 6 | **Medidas sobre la máquina** | Diagrama desde la ficha | Alta — datos de la ficha | ✅ `generador_dimensiones.py` |
| 7 | **Otro ángulo con IA** | Imagen→imagen del mismo equipo | Media — riesgo de caras no fotografiadas | ⬜ ver principio 1 |
| 8 | **Accesorios incluidos** | Foto REAL | Es sourcing | ⬜ vía carpeta |

**Slots condicionales:** el 3 aplica solo si el producto tiene variantes de motor (tres, dos o
ninguna); el 8 solo si viene con accesorios. Lo que no aplica **no se rellena con otra cosa**.

**Regla que manda sobre el número (corregida).** No hay cuota fija de 8. La regla de la "cuota
muerta" prohíbe **una sola cosa**: rellenar con **recortes repetidos** de la misma foto (el 4212
"cortado y todo igual"). **No** prohíbe fabricar las tomas creadas — hacer la de medidas o la de
partes señaladas es lo contrario del relleno. La regla real: se produce **cada tipo que aplica** y
se puede hacer con honestidad (encontrado real, o creado desde material real); se saltan solo los
que **no aplican** (sin variantes → sin slot 3; sin accesorios → sin slot 8) o los que
**fabricarían mentira** (producto desde texto = imposible; `otro_angulo_ia` va anclado a la foto
real, con sufijo `_IA` y revisión humana). Nunca recortes repetidos.

**Límite de HOY (no confundir con la regla).** El motor solo construye 3 tipos creados —
`producto_limpio`, `medidas`, `partes_senaladas` (`motor_galeria.py`, `TIPOS_SOPORTADOS`)—;
persona, escena y otro-ángulo todavía **no** están construidos. Así que hoy la galería se apoya en
las **fotos reales sourced** + esos **3 creados**, no en una generación completa. Que un producto
quede en pocas tomas puede ser **falla río arriba** (identificación sin specs → sin medidas) o
generadores faltantes — **no** necesariamente "galería honesta y corta".

### Qué de esto ya está construido

Dos de los ocho slots (2 y 6) ya salen solos del motor. El 3 es la misma clase de pieza
determinista y es el próximo candidato natural. El 1 y el 4 son escenas: producto real compuesto
sobre entorno generado. El 5 y el 8 no son generación sino **sourcing** — se resuelven con la
carpeta de producto, no con código de imagen.

---

## Módulos

| Archivo | Qué hace |
|---------|----------|
| **`motor_galeria.py`** | **Lee el plan de la ficha y produce toda la galería. Un comando por producto.** |
| `validar_puntos.py` | Verifica que los puntos de los callouts caigan sobre la silueta del producto. |
| `recortar_producto.py` | Quita el fondo (rembg) y recorta al contenido. Reemplaza el paso manual de Canva. |
| `generador_galeria.py` | Hero del producto + contact-sheet de preview. |
| `generador_dimensiones.py` | Toma de tamaño: líneas de medida + sellos de peso/fondo. |
| `generador_callouts.py` | Toma de partes señaladas con líneas guía. |
| `generador_banner.py` | Banner de marca del producto. |

### El motor: un comando por producto

```bash
python motor_galeria.py <recorte.png> --ficha ficha.json --destino galeria/
```

Recorre `plan_galeria`, produce lo que sabe producir y **declara por qué omitió el
resto**. Dos conductas fijas:

- **Degrada, no falla.** Un slot sin datos se omite con su motivo escrito; nunca se
  inventa nada para llenar el hueco. Un slot que el motor no sabe hacer no impide
  producir los demás.
- **El origen viaja con la imagen.** Cada pieza hereda el origen de los datos con que
  se dibujó. Una imagen es tan confiable como el dato que tiene detrás, y queda anotado.

Corrida real sobre el molino: 3 piezas producidas (producto limpio, medidas, partes
señaladas), 2 omitidas con motivo (`foto_real` entra por la carpeta; `otro_angulo_ia`
necesita red).

### La validación de puntos, y su techo

El recorte deja el fondo transparente, así que **el canal alfa dice dónde hay producto**.
Un punto sobre píxeles transparentes está mal, sin discusión: es un control determinista
sobre una salida de IA.

Se mira una ventana de radio 5% alrededor del punto, no un anillo de vecinos — las partes
finas (una pata, un eje) se escapan entre los puntos de un anillo. **El 5% está calibrado
con datos reales**, no elegido a ojo: en el molino, un punto bien puesto cae a 0,6% del
producto, dos puntos apuntados a partes delgadas caen a 3,0% y 3,6%, y uno en el aire cae
a más del 10%. Con el 1,5% inicial se descartaban etiquetas legítimas.

**El techo, y hay que tenerlo presente:** esto verifica que el punto caiga sobre el
producto, **no que caiga sobre la parte correcta**. La geometría no sabe de semántica. En
el molino, la etiqueta "Puerto de descarga" apuntaba al vacío entre las patas y el control
la dejó pasar, porque había una pata a pocos píxeles — se detectó **mirando la imagen
renderizada, no el log**. Se resolvió poniendo su `point` en `null`: el puerto no se
identifica con certeza en la única foto disponible, así que se omite.

Moraleja para el lote: el control automático atrapa el error grosero; la revisión de la
pieza renderizada sigue haciendo falta.

---

## El paso de visión: quién ubica los puntos (decidido 22-jul-2026)

**El agente mira el recorte y escribe los puntos. La geometría los controla. Es un paso del
procedimiento, no código nuevo.**

### Por qué así y no con un modelo de visión llamado desde el pipeline

Un paso ejecutable que llame a un modelo automatizaría esto de verdad, y **es a donde hay que
llegar**. Hoy no, por tres razones concretas:

1. **Metería la primera llamada a IA dentro del pipeline**: clave de API, costo por producto y
   salida no determinista, justo en un motor cuyo principio declarado es lo contrario —
   determinista y sin red.
2. **Apilaría un segundo paso de IA sin haber medido el primero.** La tasa de error del
   Investigador todavía no está medida (es la Prioridad A #2 de `ESTADO_PROYECTO.md`). Construir
   sobre un error desconocido multiplica el error, no lo controla.
3. **No baja el techo de escala.** El Investigador ya es una skill y no código, así que el tope de
   la cadena hoy lo pone él. Ubicar puntos con el agente no empeora ese tope. Cuando el
   Investigador se vuelva ejecutable, este paso migra con él: es la MISMA migración, no otra.

### El procedimiento, por producto

Va **entre el recorte y el motor**, y son cinco pasos:

1. El Investigador deja `point` en `null` en todos los callouts. Sabe QUÉ partes hay, no DÓNDE
   caen. Eso no es una carencia: es la división correcta del trabajo.
2. Con el recorte ya producido, **el agente mira la imagen** y escribe `[x, y]` normalizados (0..1)
   para cada etiqueta que pueda ubicar **con certeza**. La que no pueda ubicar con certeza **se
   queda en `null`** — se omite, nunca se adivina una coordenada.
3. Se corre el control determinista:
   ```bash
   python validar_puntos.py <recorte.png> --ficha <ficha.json>
   ```
   Devuelve tres grupos: **aceptados** (se dibujan), **descartados** (el punto cae fuera del
   producto) y **sin punto** (no se dibujan, y está bien).
4. Todo **descartado** se vuelve a ubicar o se pone en `null`. Un descarte jamás se fuerza: si el
   control lo rechazó, o el punto está mal o la parte no se distingue en esa foto.
5. **Se mira la pieza renderizada antes de publicar.** No es opcional y no es redundante: el
   control es geométrico y no sabe de semántica. En el molino dejó pasar "Puerto de descarga"
   apuntando al vacío entre las patas, y eso se detectó mirando la imagen, no el log.

### El límite que este paso NO resuelve

Sigue siendo posible poner un punto sobre el producto pero sobre la **parte equivocada**. Ningún
control geométrico va a atrapar eso. Por eso el paso 5 existe y por eso todo termina en borrador
con revisión de Angie.

---

**Salida:** WebP **1080×1080** (estándar de la tienda).
**Marca:** naranja `#FF4E03` + `fonts/OpenSans-Bold.ttf`.
Las constantes de layout se afinaron a 700 px y se escalan con `_px()`, así que
cambiar `LADO` mantiene las proporciones (render nativo, no estirado).

---

## Uso

```bash
# 1. Recorte limpio (una vez por producto)
python recortar_producto.py foto.png --salida producto_recorte.png

# 2. Tomas generadas — leen los datos DE LA FICHA
python generador_dimensiones.py producto_recorte.png \
    --ficha ficha_revisada_<codigo>.json --salida galeria/02-dimensiones.webp

python generador_callouts.py producto_recorte.png \
    --ficha ficha_revisada_<codigo>.json --salida galeria/03-partes.webp
```

Ambos aceptan `--preview salida.png` para revisar a ojo antes de publicar.
`--datos <json>` existe como alternativa para iterar sin ficha.

---

## Contrato de ficha: `multimedia.plan_galeria`

El **plan** dice QUÉ lleva la galería y de qué foto sale cada pieza. Es el contrato
donde enchufan los tres mecanismos: el motor propio, la carpeta de producto y el MCP
de imagen. Validado en `esquema_ficha.py`, probado en `test_esquema_plan_galeria.py`.

```json
"plan_galeria": {
  "imagen_base": "molino/01-original.jpg",
  "imagen_base_origen": "encontrado_web",
  "slots": [
    { "tipo": "foto_real", "fuente": "foto_real", "origen": "encontrado_web" },
    { "tipo": "medidas", "fuente": "generado_motor", "origen": "encontrado_web",
      "archivo": "galeria/06-medidas.webp" },
    { "tipo": "otro_angulo_ia", "fuente": "imagen_a_imagen",
      "origen": "generado_ia_sin_verificar", "archivo": "galeria/07-angulo_IA.webp" }
  ]
}
```

### Las dos promesas que el contrato hace cumplir

**1. Ninguna imagen del producto nace sin una foto real detrás.** Toda `fuente`
distinta de `foto_real` está obligada a declarar de dónde salió (`deriva_de` propio o
el `imagen_base` del plan). La consecuencia importa: **texto → imagen es imposible de
expresar en este contrato**. El caso que inventó la marca "SHENGKEY" no se puede
escribir, no porque esté prohibido en un documento, sino porque no hay forma de
representarlo.

**2. Una recreación nunca se disfraza de fotografía.** `fuente` y `origen` son ejes
distintos y el esquema no los deja contradecirse:

| Eje | Qué responde | Ejemplo |
|---|---|---|
| `fuente` | **cómo** se hizo la imagen | `imagen_a_imagen` |
| `origen` | **quién** responde por ella | `confirmado_por_angie` |

Una imagen de IA no puede declarar `verificado` ni `encontrado_web` — eso afirmaría
que es una foto. Sí puede declarar `confirmado_por_angie`: eso significa "Angie la
revisó y responde por ella", que es la revisión humana de la regla 6. El `_IA` en el
nombre del archivo la delata a simple vista.

Esto es lo que hace que usar IA sea **seguro en vez de prohibido**: meses después
seguís pudiendo distinguir qué es foto, qué es recreación y quién la aprobó.

### Por qué sirve desde hoy, sin automatizar nada

La fuente `edicion_manual` describe lo que Angie hace hoy en Canva. O sea: el plan se
puede llenar con el proceso manual tal cual es, y cada slot va migrando a
`generado_motor` a medida que se automatiza. **El contrato es el mapa de la migración**,
no un requisito para empezar.

`imagen_base` es la foto canónica del producto: garantiza que las piezas generadas se
vean como la misma máquina y no deriven hacia otro equipo. Se refuerza con
`criterio_verificacion_visual` de la ficha, que ya declara los rasgos estructurales
que el producto debe mostrar sí o sí.

---

## Contrato de ficha: `multimedia.galeria_tomas`

Lo emite el **Investigador**; los generadores lo leen. Validado en `esquema_ficha.py`.

```json
"galeria_tomas": {
  "callouts": [
    { "label": "Tolva de alimentación extra grande", "point": [0.50, 0.10] }
  ],
  "callouts_origen": "encontrado_web",
  "dimensiones": { "alto": "85 cm", "ancho": "43,5 cm", "fondo": "46,5 cm", "peso": "20 kg" },
  "dimensiones_origen": "encontrado_web"
}
```

Reglas que el esquema **hace cumplir**:

- **Origen obligatorio** si hay datos (dato sin origen = dato inventado).
- `point` es `[x, y]` relativo al producto, entre 0 y 1; fuera de rango se rechaza.
- Todo es **opcional**: las fichas anteriores (4212) siguen siendo válidas.

### Por qué `point` puede venir vacío

El Investigador averigua **qué partes** tiene el producto leyendo la web, pero **no
dónde caen sobre la foto** — eso solo se sabe mirando la imagen. Por eso `point` es
opcional y viene en `null`: **sin punto, esa parte no se dibuja**. Nunca se inventa
una posición. Ubicar los puntos es un paso visual (hoy asistido; automatizable a
futuro con un paso de visión).

---

## Tests

```bash
python -m unittest discover -p "test_*.py"
```

Cubren: recorte, envoltura de texto, auto-ajuste sin desbordes, tamaño y modo de
salida, **determinismo** (misma entrada → mismos bytes), casos borde vacíos y el
contrato `galeria_tomas` (origen obligatorio, puntos inválidos).

---

## Limitaciones conocidas

- **Toma #2 versión "persona al lado":** requiere combinar una escena de Canva con el
  recorte real, lo que exige mover la imagen entre el pipeline y Canva. En entornos
  sin salida de red directa no es posible; en producción el puente funcionaría
  subiendo el recorte a la media de la tienda (`cliente_tienda.subir_imagen`) y
  pasando esa URL a Canva.
- **Toma #4 (detalle en función):** necesita una foto real del proveedor. No se
  genera con IA para no inventar el mecanismo interno.
- **Publicación:** por defecto el Publicador sube la galería **solo al crear** el producto
  (regla fija para no borrar la galería viva). Refrescar la de un producto ya creado exige
  pedirlo a mano con `--refrescar-galeria`, que **reemplaza** la galería de la tienda. Si la
  ficha no trae ninguna imagen preparada, esa corrida se detiene con código distinto de cero
  y no toca nada: "no hay nada que subir" no puede significar "borrá todo".
- **El motor debe correrse con `--destino` DENTRO de la carpeta de la ficha.** El Publicador
  resuelve cada imagen como `carpeta_de_la_ficha / url`, que es una base distinta de aquella
  desde la que se corrió el motor. `relativizar_a_carpeta_de_ficha` reescribe las rutas
  contra esa base, pero un archivo que quede **fuera** de la carpeta de la ficha no se puede
  reescribir: se avisa y esa pieza no llega a la galería (el Publicador rechaza a propósito
  las rutas absolutas y los saltos `..`).
- **El Publicador no verifica quién firma una imagen.** `ImagenGaleria` no tiene campo
  `origen`: al subir solo se comprueba que la ruta sea segura y que el archivo exista. El
  filtro que descarta `generado_ia_sin_verificar` vive **solo** en el puente automático
  (`motor_galeria.imagenes_confirmadas_del_plan`), así que una
  `multimedia.imagenes_galeria_confirmadas` escrita por otra vía —a mano, u otra herramienta—
  lo esquiva. Es un hueco **preexistente**, anotado aquí para que no se descubra dos veces.
