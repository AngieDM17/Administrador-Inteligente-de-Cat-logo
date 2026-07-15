# Prompts para ChatGPT — Galería NBC 250 (código 9060C)
**Técnica: imagen → imagen.** En cada punto: adjunta la(s) foto(s) real(es) indicada(s) y pega el texto en ChatGPT. Fondo blanco, formato cuadrado. Al final se exportan a WebP 700x700.

> Regla de oro (recuérdasela a ChatGPT y revísalo tú): **no inventar** textos, rótulos, perillas, conectores ni rejillas que no se vean en la foto real. Si ChatGPT agrega algo que no está en la referencia, se descarta.
>
> Panel real confirmado: **doble display digital (A y V), TRES perillas rojas + un botón rojo**, rótulo "NBC-250 INVERTER IGBT". Cuerpo rojo, base con ruedas y asa negra.

---

## SEGURAS (salen de transformar tus fotos reales)

### Imagen 1 — Foto real izquierda, fondo limpio  → adjunta FOTO 1 (125421)
```
Toma esta foto del equipo tal cual y recórtala sobre fondo blanco puro (#FFFFFF), estilo fotografía de producto para e-commerce. Iluminación de estudio suave, sombra sutil bajo el equipo. NO cambies el equipo: mantén idénticos el panel de control, las perillas, los displays, el rótulo, la antorcha, el carrete y las ruedas. No agregues texto ni logos nuevos. Salida cuadrada 1:1, alta resolución.
```

### Imagen 2 — Foto real derecha (con logo), fondo limpio → adjunta FOTO 2 (125450)
```
Toma esta foto del equipo tal cual y recórtala sobre fondo blanco puro (#FFFFFF), estilo fotografía de producto para e-commerce. Iluminación de estudio suave, sombra sutil. NO modifiques el equipo: conserva el panel, las perillas rojas y el botón, el logo "I.O. Tools / www.iocompanysas.com" del costado y la rejilla lateral exactamente como están. No inventes textos ni etiquetas. Salida cuadrada 1:1, alta resolución.
```

### Imagen 3 — Vista frontal (~0°) derivada → adjunta FOTO 1 y FOTO 2 juntas
```
Usando estas dos fotos del MISMO equipo como referencia estricta, genera una vista FRONTAL directa (de frente, 0°) del equipo completo sobre fondo blanco puro. El frente debe mostrar exactamente lo que aparece en las fotos: panel con doble display digital (A y V), tres perillas rojas y un botón rojo, rótulo "NBC-250 INVERTER IGBT", conector de antorcha, cuerpo rojo con base de ruedas y asa negra arriba. No inventes controles, textos ni conectores que no estén en las referencias. Fotografía de producto, iluminación de estudio, salida cuadrada 1:1.
```

### Imagen 4 — Vista lateral derecha derivada → adjunta FOTO 2 (125450)
```
Usando esta foto como referencia estricta, genera una vista LATERAL DERECHA completa del equipo (el costado rojo con la rejilla de ventilación y el logo "I.O. Tools" tal como aparecen en la foto), sobre fondo blanco puro. No agregues etiquetas, rejillas ni conectores que no estén en la referencia. Fotografía de producto, iluminación de estudio, salida cuadrada 1:1.
```

---

## ACCESORIOS (ya son fotos reales — solo limpiar fondo)

### Imagen 5 — Antorcha MIG → adjunta FOTO 3 (125510)
```
Recorta esta antorcha sobre fondo blanco puro (#FFFFFF), estilo foto de producto, sombra sutil. No cambies la antorcha ni su cable. Salida cuadrada 1:1.
```

### Imagen 6 — Kit de accesorios → adjunta FOTO 4 (125533)
```
Recorta este kit (careta, pinza de tierra, portaelectrodo, cable y cepillo) sobre fondo blanco puro (#FFFFFF), estilo foto de producto. No cambies los objetos. Salida cuadrada 1:1.
```

---

## NO generar por ahora (no hay foto real de esas caras → ChatGPT las inventaría)
- **Vista trasera** del equipo — no fue fotografiada.
- **Vista superior / picado** de la tapa del carrete — no fue fotografiada.

Si quieres esas dos vistas, la vía fiel es conseguir la foto real: pedírsela a IO Company o fotografiar la máquina. Con IA saldría inventada y rompe la regla.

## Resultado esperado
Galería de **6 imágenes fieles** (2 reales de la máquina + 2 derivadas seguras + 2 de accesorios) en vez de 8 forzadas con caras inventadas. Cuando tengas los 6 archivos, guárdalos en `NBC250_imagenes/` y te los convierto a WebP 700x700 con el nombre estándar.
