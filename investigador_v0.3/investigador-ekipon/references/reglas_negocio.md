# Reglas de negocio Ekipon (confirmadas por Angie) y lecciones del piloto NBC 250

## Reglas fijas de la tienda — no se preguntan, no se cambian

1. **Precio: SIEMPRE manual.** Lo define Angie; varía por múltiples factores y NO se automatiza. El sistema solo aporta referencias de mercado. El precio suele incluir ~$100.000 de envío y se publica como "Envío GRATIS a todo el país" con pago contra entrega.
2. **Garantía: siempre 1 año.**
3. **SKU:** lo asigna automáticamente el sistema de la tienda. No se muestra al público.
4. **Sin marcas y sin precio de oferta.**
5. **Nombres:** MAYÚSCULAS, formato "PRODUCTO CARACTERÍSTICA – DETALLE".
6. **Descripción corta de WooCommerce** = `descripcion_principal` de la ficha. La pestaña Descripción = ficha técnica + plantilla Elementor (banner, texto, video).
7. **Todo se publica como BORRADOR.** Angie revisa siempre antes de publicar.
8. **Meta multimedia por producto:** galería + 1 banner + video ~1 min (formato YouTube; se sube a YouTube y el enlace va en la plantilla Elementor).
   - **El banner lo genera el motor propio** (`generador_banner.py`), no Canva. El Publicador lo crea y lo sube solo.
   - **La galería la define la plantilla de su CATEGORÍA**, no un número fijo global (ver `ETAPA_IMAGENES.md`). La meta histórica de 8 imágenes se abandonó: rellenar para llegar a una cuota produjo tomas redundantes en el 4212. Vale más una galería corta y honesta que una larga con relleno.
9. **Formato de imágenes de la tienda:** WebP 1080×1080, con texto ALT que incluya el código.
9b. **Datos de las tomas generadas (`multimedia.galeria_tomas`):** el motor de imágenes dibuja solo las tomas de *partes señaladas* y *dimensiones*, pero necesita sus datos. Llenar siempre que la fuente los dé:
   - `callouts`: lista de partes REALES y visibles del producto (`label`). El `point` (posición sobre la foto) se deja en `null` — el Investigador sabe QUÉ partes hay, no DÓNDE caen en la foto; sin `point` esa parte no se dibuja y **nunca se inventa una posición**.
   - `dimensiones`: `alto`, `ancho`, `fondo`, `peso` tal como los publica la fuente. Lo que no esté explícito se deja en `null` — se omite, no se estima.
   - Ambos exigen su `*_origen` (regla de origen por campo). Sin origen = dato inventado.
9c. **Plan de galería (`multimedia.plan_galeria`):** declara QUÉ lleva la galería, de qué foto sale cada pieza y quién responde por ella. Dos reglas duras, ambas verificadas por el esquema:
   - **Todo lo que no sea `foto_real` debe anclarse a una imagen real** (`imagen_base` del plan o `deriva_de` del slot). Generar el producto desde texto no se puede expresar en el contrato: no existe.
   - **`fuente` y `origen` son ejes distintos y no se contradicen.** `fuente` dice cómo se hizo la imagen; `origen` dice quién responde por ella. Una imagen de IA nunca puede declarar `verificado` ni `encontrado_web`, y una foto real nunca puede declarar `generado_ia`. Las de IA llevan sufijo `_IA` en el archivo.
   - `imagen_base` es la foto canónica del producto: garantiza que todas las piezas se vean como la MISMA máquina.
9d. **Descartar imágenes de "credibilidad de proveedor", nunca del producto.** Las páginas de Alibaba y de fabricantes mezclan fotos reales del producto con material promocional de la EMPRESA: certificados de calidad (CE, ISO, informes de prueba tipo "PARTIAL CERTIFICATION"), capturas de entrevistas o apariciones en TV ("TV STATION INTERVIEW"), fotos de la fábrica o bodega, banners genéricos ("Fast Delivery", "Modern Factory"). Ninguna de estas muestra el producto — se descartan siempre al reunir el material real (Fase 4.1 del SKILL), sin necesidad de pasar por el criterio de verificación visual: se reconocen de un vistazo, no hace falta compararlas contra la foto de referencia. (Regla agregada 13-ago-2026, pedido de Angie.)

## Lecciones del piloto NBC 250 (cada una viene de un error real)

1. **Código de proveedor EXACTO, sufijos incluidos.** 9060C ≠ 9060: eran dos máquinas distintas del mismo importador y confundirlas contaminó una ficha completa (specs, fabricante, precio — todo del producto equivocado).
2. **Verificación visual por rasgos estructurales, nunca por color.** El criterio del NBC 250: panel con doble display digital + dos perillas rojas + carrete expuesto arriba + frente corrugado negro. Un soldador rojo con perillas análogas era OTRO producto (WTSM-250).
3. **Origen por campo obligatorio.** Sin trazabilidad no hay forma de saber qué corregir cuando algo sale mal.
4. **Árbol de categorías EN VIVO desde WooCommerce.** La copia estática estaba desactualizada: no incluía "Industria > Equipos de Soldadura", que sí existe.
5. **Alibaba bloquea la extracción y sus listados mueren.** No es fuente automática confiable. Google Lens / búsqueda por imagen es herramienta central.
6. **Imágenes IA solo para completar la galería**, con las reales como referencia estricta. Prohibido inventar textos, etiquetas o conectores. Sufijo `_IA`. Revisión humana siempre.
7. **Angie no edita JSON a mano** (se rompió en el piloto). La revisión es siempre por pantalla con campos (`revision_<CODIGO>.html`).
8. **Accesorios incluidos: revisar SIEMPRE primero la ficha técnica del proveedor** — algunos sí publican qué trae la caja. Si no aparecen (caso NBC 250: verificado 14-jul-2026, la página no los menciona), va a `campos_por_confirmar` con la nota de verificación, y se pregunta al proveedor o se revisa la caja.
9. **Para zooms de partes, recorte de foto real antes que IA** — un recorte no puede inventar conectores ni etiquetas. La IA queda solo para ángulos que ninguna foto real cubre.
10. **Peso y dimensiones estimados se aceptan** (transporte propio, no requieren precisión), pero siempre con "aprox." y marcados `[generado_ia_sin_verificar]`.
11. **Tres niveles de IA sobre la imagen, y no valen lo mismo** (precisa la regla 6):
   - **Texto → imagen: PROHIBIDO.** Nada real de donde anclarse; Canva inventó un molino con marca falsa ("SHENGKEY").
   - **Imagen → imagen del MISMO equipo: permitido y acotado.** Fiel al transformar una vista que la foto ya contiene; inventa las caras que ninguna foto muestra (trasera, superior — comprobado en el NBC 250). Marcar `generado_ia_sin_verificar`, sufijo `_IA`, revisión humana.
   - **Escena, fondo o persona con el recorte real encima: permitido.** El producto es real; lo generado es el entorno.

## Contexto del sistema mayor

El Investigador es la primera etapa del pipeline Ekipon. La ficha JSON v1.4 que produce es el
contrato que consumen todas las etapas siguientes: el Inspector la valida (`esquema_ficha.py`), el
motor de imágenes lee `multimedia.galeria_tomas` para dibujar sus tomas, y el Publicador la
convierte en un borrador de WooCommerce con su meta `ekipon_*`, desde la cual la plantilla
Elementor se llena sola.

Consecuencia práctica: **un dato mal puesto acá se propaga a todo el catálogo**. Por eso la regla
de origen por campo no es burocracia — es el único mecanismo para saber qué corregir cuando algo
sale mal a escala. Estado general del proyecto en `ESTADO_PROYECTO.md`.
## Estilo de descripción del producto (aprobado por Angie, 14-jul-2026)
La descripción principal debe tener DOS partes:
1. **Intro técnica**: qué es y qué hace el equipo (procesos, voltaje, amperaje, capacidad).
2. **Párrafo de cierre comercial** con esta fórmula fija:
   > "Gracias a su [atributo clave 1] y [atributo clave 2], el [NOMBRE DEL PRODUCTO] es una excelente opción para [audiencia 1], [audiencia 2], [audiencia 3] y [uso/trabajo profesional] que requieren [beneficio 1], [beneficio 2] y [beneficio 3]."

Ejemplo real (NBC 250):
> "Gracias a su diseño multifunción y construcción de alta calidad, el SOLDADOR MIG MULTIFUNCIÓN NBC 250 es una excelente opción para talleres metalmecánicos, empresas de fabricación, mantenimiento industrial y trabajos profesionales que requieren soldaduras limpias, resistentes y de excelente acabado."

Reglas al aplicar la fórmula:
- NUNCA incluir el código de proveedor en el texto público (ej.: quitar "9060C"). El código va solo en campos internos.
- Adaptar audiencias y beneficios al tipo de producto (no todo es soldadura).
- Mantener el nombre del producto en el mismo formato del campo `nombre_propuesto`.

## Estilo del banner (aprobado por Angie 14-jul-2026; lo produce `generador_banner.py`)

El estilo que sigue es el que Angie aprobó y **no cambia**. Lo que cambió es la herramienta: el diseño nació en Canva, pero hoy el banner de cada producto lo dibuja el motor propio `generador_banner.py`, y el Publicador lo genera y lo sube solo (regla 8). Nadie abre Canva por producto.

- Composición: cuadrado 1080x1080 de Ekipon (título arriba, descripción a la izquierda, foto del producto a la derecha, sellos "ENVÍOS A TODO EL PAÍS" y "PAGO CONTRAENTREGA" abajo).
- Descripción del banner = párrafo REDACTADO de **largo medio** (ni muy largo ni solo specs; ~40-50 palabras), estilo del ejemplo de la Peletizadora: "El [producto] reúne/está diseñado para [función]… Ideal para [audiencias] que requieren [beneficios]."
- Lo único que aporta el Investigador es ese texto y la foto del producto; la composición la pone el motor y no se retoca a mano por producto. Si el estilo tiene que cambiar, se cambia en `generador_banner.py` —una vez, para todo el catálogo—, nunca copiando y editando una pieza suelta.
