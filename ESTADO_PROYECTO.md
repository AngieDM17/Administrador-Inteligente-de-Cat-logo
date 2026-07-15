# ESTADO DEL PROYECTO — Administrador Inteligente de Catálogo Ekipon
**Última actualización:** 15-jul-2026 (sesión 5). **Para retomar en un chat nuevo:** pídele a Claude que lea PRIMERO este archivo. Si hay discrepancia sobre el piloto 4212, manda `revision_4212.html`.

## 🟢 DÓNDE QUEDAMOS (sesión 5 — lo más reciente)
**El Investigador v0.3 se estrenó con un producto NUEVO de principio a fin (código 4212, IO Company) y PASÓ la prueba.** Primera corrida real de la skill con algo distinto al NBC 250.
- **Resultado:** ficha completa + 8 imágenes WebP 700x700. Archivos: `ficha_revisada_4212.json`, `revision_4212.html`, carpeta `4212_imagenes/` (01–08 + preview).
- **Qué cazó la skill (su valor):** el proveedor titulaba "COMPRESOR" algo cuya foto era un tanque; el producto NO era un equipo sino un SET de 4 componentes (compresor + tanque pulmón 600 L + secador refrigerado + filtro); y fotos que casi se rechazan eran piezas legítimas del set. Solo se destrabó cruzando la foto con el CATÁLOGO OFICIAL (p.89), no con una sola imagen.
- **Confirmado por Angie:** nombre "SISTEMA DE AIRE COMPRIMIDO 3 PIEZAS – TANQUE PULMÓN 600 L + SECADOR REFRIGERADO + FILTRO"; precio $16.434.999 (incluye ~$100.000 envío); categoría Industria; incluye compresor.
- **Pendientes menores del 4212:** specs del compresor (HP/caudal, opcional) y el nombre dice "3 PIEZAS" aunque son 4 componentes (ajustable en revisión).
- **Lo siguiente:** montar el 4212 como BORRADOR en WooCommerce = arranque del Publicador. OJO: publicar necesita acceso de red a la tienda (API REST de pruebas.ekipon.co), que el entorno de Cowork tiene restringido → disparador para construir el Publicador/Orquestador en Claude Code (extensión de VS Code), decisión de sesión 5.


## 🟢 DÓNDE QUEDAMOS (resumen de arranque)
El **piloto NBC 250 está COMPLETO**: ficha + 8 imágenes WebP + banner Canva. Todos sus pendientes cerrados.
**CORRECCIÓN CLAVE (sesión 4):** la infraestructura de publicación en WooCommerce **YA EXISTE y está probada** desde la Fase 0 (ver sección propia abajo). El método NO está "por definir": es la **API REST de WooCommerce**, con claves y contraseña de aplicación creadas y verificadas, dos productos ya creados en la tienda de pruebas y las plantillas Elementor identificadas.
**Lo siguiente (elige al retomar):**
1. **Estrenar el Investigador v0.3 con un producto NUEVO** de principio a fin — RECOMENDADO. Es el único eslabón aún sin probar (la skill solo se corrió con el NBC 250 y con mucha corrección humana). Publicar enseña poco nuevo porque la plomería ya está probada.
2. **Montar el NBC 250 como BORRADOR en WooCommerce** (Fase 2, Publicador) — cierre rápido y de bajo riesgo (~20-30 min) porque la API ya está lista; útil si prefieres ver el ciclo completo una vez y tener un producto real arriba.
Archivos clave del piloto: `ficha_investigada_NBC250.json`, `revision_NBC250.html`, carpeta `NBC250_imagenes/` (01–08 + preview), banner en Canva (links abajo).
Estilos aprobados por Angie ya guardados en `investigador_v0.3/investigador-ekipon/references/reglas_negocio.md` (descripción de producto + banner).

## Infraestructura de publicación — YA EXISTE (Fase 0, verificado sesión 4)
Recuperado de la sesión "Ekipon intelligent product management system" (Fase 0). Esto corrige la idea de que "falta definir cómo se publica":
- **Tienda de pruebas `pruebas.ekipon.co`** clonada, con candado (protegida con contraseña de directorio en cPanel), invisible para Google y sin píxeles.
- **Claves de WooCommerce (API REST)** creadas y verificadas — permiten CREAR productos por API. Guardadas en `claves_pruebas.txt`.
- **Contraseña de aplicación de WordPress** creada y probada — sirve para subir fotos y leer/escribir plantillas. Guardada en `claves_pruebas.txt`.
- **Dos productos ya creados por el sistema** en la tienda de pruebas (prueba de que la creación por API funciona).
- **Plantillas Elementor identificadas por ID:** `50198` = ficha técnica · `50201` = características y video YouTube. El sistema puede leerlas y replicarlas llenándolas con los datos de cada producto.
- Vía técnica de publicación DECIDIDA: **API REST de WooCommerce** (no manual, no conector de terceros — no existe conector WooCommerce listo en el registro; WordPress.com no aplica a un WooCommerce propio).
- Pendiente de seguridad (repetido abajo): `claves_pruebas.txt` sigue en texto plano.

## Qué es el proyecto
Sistema que automatiza la creación y administración de productos de la tienda WooCommerce ekipon.co (hoy ~5.000 productos, meta 100.000+). Angie es la dueña del producto (diseñadora gráfica, no programadora — Claude debe explicar todo término técnico). Claude es arquitecto, desarrollador y mentor.

## Decisión clave (10-jul-2026): el flujo real es investigación web
El 100% de los productos entra así: nombre + foto de referencia → investigar en internet (Alibaba, fabricantes, distribuidores) → ficha técnica consolidada → ~8 imágenes → banner (plantilla Canva) → video ~1 min (miniatura Canva al inicio, cortes, música, voz en off comercial, subtítulos, logo) → publicar BORRADOR en WooCommerce con la plantilla Elementor → Angie revisa y publica.
Tiempo manual actual: 60–90 min por producto. El extractor de .docx (extractor_fichas.py v0.2) quedó como entrada secundaria.

## Arquitectura acordada (pendiente documentar como v1.2)
- **Agente Investigador** (IA): identifica producto, navega fuentes, consolida ficha con origen por campo. ← PRIMERO A CONSTRUIR (v0.3)
- **Agente Redactor** (IA): nombre, descripción, características, SEO con estilo Ekipon consistente.
- **Módulo Imágenes** (mixto): selección/verificación con IA; fondo, WebP 700x700, ALT con código.
- **Módulo Publicador** (código): borrador WooCommerce + plantilla Elementor (evaluar plantilla dinámica con campos, no copias por producto).
- **Agente Video** (mixto): guion y selección IA; corte, subtítulos, exportación con código. ÚLTIMA FASE.
- **Orquestador**: pasa la ficha entre etapas, registra estados, reintenta fallos.
- La **ficha estándar JSON** es el documento que viaja entre todos.

## Roadmap
Fase 1 Investigador → Fase 2 Publicador → Fase 3 Imágenes → Fase 4 Banner/miniatura (API Canva) → Fase 5 Video.

## Reglas de negocio confirmadas por Angie
1. **Precio: SIEMPRE manual.** Nunca se automatiza (varía por muchos factores). El sistema solo muestra referencias de mercado. Suele incluir ~$100.000 de envío y se publica "Envío GRATIS a todo el país" + pago contra entrega.
2. **Garantía: siempre 1 año.** No se pregunta.
3. **SKU:** lo asigna el sistema de la tienda automáticamente. No se muestra al público.
4. **Sin marcas, sin precio de oferta.**
5. **Nombres:** MAYÚSCULAS, formato "PRODUCTO CARACTERÍSTICA – DETALLE".
6. **Descripción corta WooCommerce** = descripción principal de la ficha. Pestaña Descripción = ficha técnica + plantilla Elementor (banner, texto, video).
7. **Todo se publica como BORRADOR**; Angie revisa siempre antes de publicar.
8. **Meta multimedia por producto:** 8 imágenes galería + 1 banner Canva + video ~1 min (formato YouTube; se sube a YouTube y el enlace va en la plantilla).

## Reglas de sistema aprendidas en el piloto NBC 250 (casos reales)
1. **Código de proveedor EXACTO, sufijos incluidos:** 9060C ≠ 9060 (fueron dos máquinas distintas; el error contaminó una ficha entera).
2. **Verificación visual contra foto de referencia:** el criterio lo definen rasgos (panel con doble display vs perillas), NO el color. Angie valida siempre.
3. **Origen por campo:** cada dato se marca verificado / encontrado_web / generado_ia_sin_verificar.
4. **Árbol de categorías EN VIVO desde WooCommerce**, nunca copia estática (la copia estaba desactualizada: existe "Industria > Equipos de Soldadura").
5. **Alibaba no es fuente confiable automática** (bloquea extracción y los listados mueren). Google Lens / búsqueda por imagen es herramienta central.
6. **Imágenes IA:** solo para completar, con las reales como referencia; prohibido inventar textos/etiquetas/conectores; sufijo _IA en el archivo; revisión humana.
7. La revisión de fichas debe ser una **pantalla con campos**, no un JSON editable a mano (Angie rompió el JSON al editarlo — el formato es frágil).

## Piloto NBC 250 (caso de prueba, casi cerrado)
- Archivo: `ficha_investigada_NBC250.json` (v1.3) + `galeria_NBC250.html`.
- Producto: 9060C SOLDADOR MIG MULTIFUNCION NBC 250, IO Company ($2.354.703, sin existencias). Precio Ekipon: $2.454.703. Categoría: Industria > Equipos de Soldadura. 4 fotos reales confirmadas + 4 briefs de generación IA listos en el JSON.
- Pendiente: accesorios incluidos (preguntar a proveedor / revisar caja) y ejecutar los briefs de IA.

## Investigador v0.3 — CONSTRUIDO (14-jul-2026)
Decisión: v0.3 es una **skill de Claude** (procedimiento formal que Claude ejecuta), no código Python — la infraestructura de código llega en fases posteriores y esta skill será su especificación. Carpeta `investigador_v0.3/`:
- `investigador-ekipon.skill` — paquete instalable (Angie: clic en "Save skill" en el chat, o Ajustes > Capacidades). Instalada, basta decir "investiga el [código] [nombre]" + foto.
- `investigador-ekipon/SKILL.md` — procedimiento en 7 fases (entrada→identificación→criterio visual→consolidación→multimedia→SEO→salidas) con todas las lecciones del piloto.
- `assets/plantilla_ficha_v1.4.json` — ficha estándar v1.4 (limpia, con origen por campo obligatorio).
- `assets/plantilla_revision.html` — pantalla de revisión con campos; botón "Descargar ficha corregida" devuelve el JSON en estado `revisada` (cumple regla 7: Angie nunca edita JSON).
- `references/reglas_negocio.md` — reglas fijas + lecciones NBC 250.
Además se generó `revision_NBC250.html` (pantalla real del piloto, probada: 11 secciones, 39 campos, galería y briefs).

## Avances sesión 2 (14-jul-2026, parte 2)
- **Accesorios NBC 250:** verificado que la página del 9060C NO los publica (ficha técnica revisada completa). Queda preguntar por WhatsApp a IO Company (+57 310 745 4644, Alejandra) o revisar la caja. Nueva regla en la skill: revisar SIEMPRE la ficha técnica del proveedor antes de dar accesorios por pendientes.
- **Imágenes faltantes — cambio de plan:** tomas 5 y 7 (zooms) se hacen por RECORTE de fotos reales (más fiel que IA, no inventa nada); solo tomas 6 y 8 van por IA. Nueva regla en la skill. Para los recortes: Angie guarda las 4 fotos originales en `NBC250_imagenes/originales/` (carpeta ya creada) y Claude las recorta a WebP 700x700. Para las IA: se necesita autorizar el conector Canva o Adobe (Ajustes > Conectores) o usar la herramienta de Angie con los 2 briefs.
- Nota técnica: el entorno de Claude no puede descargar imágenes de internet directamente (bloqueo de red); las fotos debe aportarlas Angie en la carpeta.

## Estado REAL del piloto NBC 250 (según `revision_NBC250.html`, la fuente correcta)
CORRECCIÓN (sesión 3): la sección anterior de "recortes ejecutados" quedó obsoleta. Lo verdadero:
- **Recortes tomas 5 y 7: RECHAZADOS por Angie.** Motivo: calidad insuficiente (venían de capturas ~500px ampliadas) y ángulo repetido. Lección para el sistema: el recorte solo sirve con originales de alta resolución y NUNCA sustituye ángulos nuevos — no aporta variedad. Los .webp de recorte en `NBC250_imagenes/` quedaron descartados.
- **Plan de imágenes faltantes (decisión de Angie):** las 4 tomas faltantes (5–8) se generan por **IA con ángulos NUEVOS y variados** (no zooms, no recortes), fondo blanco puro, calidad de fotografía de producto profesional. Los 4 briefs ya están escritos dentro de la ficha (`revision_NBC250.html` / `ficha_investigada_NBC250.json`).
- **Precio confirmado por Angie:** $2.454.703 COP. **Categoría confirmada:** Industria > Equipos de Soldadura.
- **Contradicción a zanjar dentro del propio archivo:** el bloque `criterio_verificacion_visual` aún dice "dos perillas rojas", pero los briefs y los pendientes dicen "tres perillas + un botón rojo". Dirección probable de corrección: TRES perillas + botón (es lo que muestran las fotos), PENDIENTE validación visual final de Angie contra la máquina.
- **Accesorios:** el texto de la página del 9060C no los menciona (verificado), pero las fotos de galería muestran antorcha MIG y kit (careta, pinza tierra, portaelectrodo, cepillo). Falta ratificar con IO Company (WhatsApp +57 310 745 4644, Alejandra). Ojo: si las fotos -12 y -13 son accesorios y no la máquina, solo hay 2 fotos de la máquina — recontar la galería.

## Pendientes NBC 250 — TODOS CERRADOS (14-jul, sesión 3)
1. ~~Validar criterio visual~~ ✅ TRES perillas rojas + un botón rojo, `confirmado_por_angie`.
2. ~~Confirmar accesorios~~ ✅ Angie confirma incluidos (antorcha MIG + kit). En `producto.accesorios_incluidos`.
3. ~~Imágenes de galería~~ ✅ **8 imágenes WebP 700x700 generadas** en `NBC250_imagenes/` (`9060C-NBC250-01…08…webp`) + `galeria_NBC250_preview.png`.
   - Decisión de Angie: usar las imágenes de **ChatGPT** (imagen→imagen). Advertencia dada y aceptada: las vistas trasera/lateral/superior son RECREACIONES no verificadas contra foto real; solo el panel frontal (01 y 02) es foto real. Claude borró la etiqueta "AC 220V" (contradecía el doble voltaje 110/220V) y un "EXPORT" inventado.
   - Composición: 01 y 02 fotos reales (panel) · 03–06 recreaciones IA · 07–08 accesorios reales.
   - Regla nueva aprendida: ChatGPT imagen→imagen inventa las caras NO fotografiadas (trasera/superior); fiel solo al transformar vistas existentes. Prompts en `briefs_chatgpt_NBC250.md`.
   - GOTCHA técnico: el JSON de la ficha se desincronizó entre la herramienta de archivos y el shell a mitad de edición (quedó truncado en el shell). Se resolvió reescribiéndolo completo desde el shell y validando con python. Si vuelve a pasar, reescribir el archivo entero de una vez, no por parches.

## Banner NBC 250 — HECHO y EXPORTADO (sesión 3)
- Plantilla de Angie en Canva ("imagen producto", post IG 1080x1080). Se trabajó sobre una COPIA (design id **DAHPZTFO-Ro**, editar: https://www.canva.com/d/cCTgBbyFGWeq4qC); la plantilla original (DAHPZDbAOA8) quedó intacta.
- Contenido final: título "SOLDADOR MIG NBC 250" · descripción de largo medio redactada ("El Soldador MIG Multifunción NBC 250 reúne cuatro procesos en un solo equipo (MIG, sin gas, MMA y TIG), con doble voltaje 110V/220V y hasta 250A. Ideal para talleres metalmecánicos, fabricación y mantenimiento industrial que requieren soldaduras limpias, resistentes y de excelente acabado.") · foto real del importador a la derecha · sellos envío gratis + contraentrega.
- Exportado a PNG (link temporal, se regenera con `export-design` sobre DAHPZTFO-Ro). Angie lo descarga de Canva a la carpeta (el entorno de Claude no descarga de internet).
- Aprendizajes Canva: el conector "Personalizado" fallaba (pide OAuth Client ID manual) → usar el Canva ESTÁNDAR. Para editar una plantilla, la cuenta conectada debe ser dueña o tener acceso. Subir imagen a Canva requiere URL pública (se usó la del importador).

## Estilos de redacción aprobados por Angie (sesión 3) → en reglas_negocio.md
- **Descripción del producto (WooCommerce):** intro técnica + párrafo de cierre fórmula "Gracias a su [atributos], el [PRODUCTO] es una excelente opción para [audiencias] que requieren [beneficios]". NUNCA incluir código de proveedor (ej. 9060C) en t


## Avances sesión 5 (15-jul-2026): Investigador estrenado con producto nuevo (4212) + decisión de plataforma
- **Prueba de fuego del Investigador v0.3 superada** con el 4212 (ver "DÓNDE QUEDAMOS sesión 5").
- **Decisión de plataforma:** el motor multiagente automatizado (Investigador→Redactor→Imágenes→Publicador→Orquestador, en lote y con mínima intervención) se construirá y correrá en **Claude Code vía la extensión de VS Code** (misma potencia de subagentes/hooks sin usar terminal). Cowork queda como cabina de revisión humana. Regla: no automatizar en serie hasta que el Investigador sea confiable — probado una vez; conviene 1-2 productos más antes de migrar.
- **Galería de 8 sin IA:** para un set con varias piezas se llegó a 8 con material real (4 fotos reales + 1 montaje del conjunto + 3 recortes), sin generación IA. Patrón nuevo: cuando el producto tiene varias piezas/vistas reales, priorizar montaje + recortes antes que IA.
- **Canva no sirve para recrear un producto:** genera imagen desde texto (no fiel). Para ángulos nuevos fieles: ChatGPT/Adobe imagen→imagen. Canva = banner y composición (montaje/hero).

## Lecciones nuevas para el sistema (sesión 5)
1. **Kits/sets: verificar la COMPOSICIÓN contra el catálogo del proveedor ANTES de confiar en la foto de referencia.** El 4212 parecía un tanque (la foto mostraba 1 de 4 componentes); solo el catálogo (p.89) reveló que era un set de 4. Una sola foto engaña en ambos sentidos: rechazar piezas válidas o dar por bueno un producto equivocado.
2. **Specs "contaminadas" pueden ser legítimas de otra pieza.** Las specs de secador en la ficha de "tanque" eran reales (del secador del set). No descartar specs sin entender la composición.
3. **GOTCHA — desincronización JSON herramienta-de-archivos / shell:** archivos escritos por una vía se ven truncados por la otra. Fix: reescribir el archivo entero DESDE EL SHELL con Python y validar; no fiarse de una sola vista.
4. **GOTCHA — permisos:** `rm` de archivos ya sincronizados da "Operation not permitted" → usar la herramienta `allow_cowork_file_delete`. Archivos copiados de `uploads` llegan solo-lectura → `chmod u+w` antes de sobrescribir.
5. **El entorno no descarga imágenes/PDF de internet** — pasarle a Angie las URLs para que baje el material a la carpeta (funcionó con las 4 fotos del 4212).
