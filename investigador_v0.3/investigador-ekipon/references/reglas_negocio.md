# Reglas de negocio Ekipon (confirmadas por Angie) y lecciones del piloto NBC 250

## Reglas fijas de la tienda — no se preguntan, no se cambian

1. **Precio: SIEMPRE manual.** Lo define Angie; varía por múltiples factores y NO se automatiza. El sistema solo aporta referencias de mercado. El precio suele incluir ~$100.000 de envío y se publica como "Envío GRATIS a todo el país" con pago contra entrega.
2. **Garantía: siempre 1 año.**
3. **SKU:** lo asigna automáticamente el sistema de la tienda. No se muestra al público.
4. **Sin marcas y sin precio de oferta.**
5. **Nombres:** MAYÚSCULAS, formato "PRODUCTO CARACTERÍSTICA – DETALLE".
6. **Descripción corta de WooCommerce** = `descripcion_principal` de la ficha. La pestaña Descripción = ficha técnica + plantilla Elementor (banner, texto, video).
7. **Todo se publica como BORRADOR.** Angie revisa siempre antes de publicar.
8. **Meta multimedia por producto:** 8 imágenes de galería + 1 banner Canva + video ~1 min (formato YouTube; se sube a YouTube y el enlace va en la plantilla Elementor).
9. **Formato de imágenes de la tienda:** WebP 700×700, con texto ALT que incluya el código.

## Lecciones del piloto NBC 250 (cada una viene de un error real)

1. **Código de proveedor EXACTO, sufijos incluidos.** 9060C ≠ 9060: eran dos máquinas distintas del mismo importador y confundirlas contaminó una ficha completa (specs, fabricante, precio — todo del producto equivocado).
2. **Verificación visual por rasgos estructurales, nunca por color.** El criterio del NBC 250: panel con doble display digital + dos perillas rojas + carrete expuesto arriba + frente corrugado negro. Un soldador rojo con perillas análogas era OTRO producto (WTSM-250).
3. **Origen por campo obligatorio.** Sin trazabilidad no hay forma de saber qué corregir cuando algo sale mal.
4. **Árbol de categorías EN VIVO desde WooCommerce.** La copia estática estaba desactualizada: no incluía "Industria > Equipos de Soldadura", que sí existe.
5. **Alibaba bloquea la extracción y sus listados mueren.** No es fuente automática confiable. Google Lens / búsqueda por imagen es herramienta central.
6. **Imágenes IA solo para completar la galería**, con las reales como referencia estricta. Prohibido inventar textos, etiquetas o conectores. Sufijo `_IA`. Revisión humana siempre.
7. **Angie no edita JSON a mano** (se rompió en el piloto). La revisión es siempre por pantalla con campos (`revision_<CODIGO>.html`).
8. **Accesorios incluidos: revisar SIEMPRE primero la ficha técnica del proveedor** — algunos sí publican qué trae la caja. Si no aparecen (caso NBC 250: verificado 14-jul-2026, la página no los menciona), va a `campos_por_confirmar` con la nota de verificación, y se pregunta al proveedor o se revisa la caja.
10. **Para zooms de partes, recorte de foto real antes que IA** — un recorte no puede inventar conectores ni etiquetas. La IA queda solo para ángulos que ninguna foto real cubre.
9. **Peso y dimensiones estimados se aceptan** (transporte propio, no requieren precisión), pero siempre con "aprox." y marcados `[generado_ia_sin_verificar]`.

## Contexto del sistema mayor

El Investiga
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

## Estilo del banner (Canva, aprobado por Angie 14-jul-2026)
- Plantilla base: post cuadrado 1080x1080 de Ekipon (título arriba, descripción a la izquierda, foto del producto a la derecha, sellos "ENVÍOS A TODO EL PAÍS" y "PAGO CONTRAENTREGA" abajo).
- Descripción del banner = párrafo REDACTADO de **largo medio** (ni muy largo ni solo specs; ~40-50 palabras), estilo del ejemplo de la Peletizadora: "El [producto] reúne/está diseñado para [función]… Ideal para [audiencias] que requieren [beneficios]."
- Siempre trabajar sobre una COPIA de la plantilla, no sobre el original.
