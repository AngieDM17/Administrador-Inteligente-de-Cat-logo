# Etapa Imágenes — motor de galería

**Última actualización:** 2026-07-22

Genera las piezas de la galería de forma determinista: el mismo producto sale siempre
igual, sin definir reglas a mano.

---

## ⚠️ Estado del flujo (22-jul-2026): la etapa NO cierra

Las piezas funcionan. **La cadena no.** De seis eslabones funcionan dos:

| # | Eslabón | Estado |
|---|---------|--------|
| 1 | Foto del proveedor → recorte (`recortar_producto.py`) | ✅ |
| 2 | El Investigador emite `plan_galeria` y `galeria_tomas` | ❌ `SKILL.md` no los menciona |
| 3 | Ubicar los puntos de los callouts sobre la foto | ❌ manual; el paso de visión no existe |
| 4 | El motor arma las piezas (`motor_galeria.py`) | ✅ |
| 5 | Subir las piezas a la tienda | ❌ nadie conecta el motor con la tienda |
| 6 | El Publicador las asigna al producto | ❌ sube galería **solo al crear** |

**Qué significa en la práctica:** si hoy se investiga un producto nuevo, su ficha sale sin
plan y el motor no tiene qué leer. La ficha del molino con la que se probó todo esto
(`molino_imagenes/ficha_molino_tomas.json`) **está escrita a mano** — es un fixture, no una
corrida real. Ver la regla 2 de "Rigor exigido" en `.claude/CLAUDE.md`.

**Orden para cerrar la etapa:** (1) enseñarle los contratos al Investigador en `SKILL.md`
—desbloquea todo lo de arriba—; (2) cerrar la salida: subir la galería y asignarla, con un
camino de "refrescar galería"; (3) resolver los puntos: construir el paso de visión o
declarar explícitamente que es asistido; (4) recién después, los slots que faltan.

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

**Regla que manda sobre el número:** la cuota fija de 8 está muerta. Se llenan los slots que el
material real permita llenar con honestidad. Rellenar hasta 8 con recortes del mismo objeto es
exactamente lo que produjo la galería "cortada y toda igual" del 4212.

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
- **Publicación:** el Publicador sube la galería **solo al crear** el producto (regla
  fija para no borrar la galería viva). Para refrescar la galería de un producto ya
  creado hace falta un producto de prueba desechable o un camino explícito de
  "refrescar galería".
