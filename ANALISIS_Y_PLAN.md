# ANÁLISIS Y PLAN — Administrador Inteligente de Catálogo Ekipon
**Fecha:** 15-jul-2026 · **Autor:** Claude (arquitecto/mentor) · Basado en `HANDOFF_Ekipon_VSCode.md` + `ESTADO_PROYECTO.md` y la revisión del material real en `Desktop\EKIPON.TIENDA`.

> Este documento NO reemplaza al HANDOFF (ese sigue siendo el punto de partida). Es mi lectura crítica y el plan afinado para arrancar el Publicador. Si algo choca con la tienda o el catálogo del proveedor, gana la realidad.

---

## 1. Qué entendí (en una frase)
Construir una plataforma con IA que investigue, redacte, ilustre y publique productos en la tienda WooCommerce de Ekipon como **borradores**, con dos frenos humanos innegociables (**precio** y **publicación**), usando una **ficha JSON estándar** como contrato entre módulos, y diseñada para escalar de ~5.000 a **100.000+** productos.

## 2. Lo que está sólido (no lo toco)
- El enfoque de **ficha JSON como contrato** entre módulos, con **origen por campo**. Es la decisión correcta y es lo que hará el catálogo auditable.
- Los **dos controles humanos** (precio manual, publicación manual sobre borrador).
- La secuencia del roadmap: **Publicador primero**, porque la infraestructura (API REST + app password + plantillas Elementor) ya está probada.
- El stack propuesto (Python, Pillow, pydantic, .env). De acuerdo.

## 3. Riesgos y mejoras que propongo (como mentor)

### A. Higiene ANTES de escribir código (bloqueante)
1. **Una sola carpeta = fuente de verdad.** Hoy hay dos: la de trabajo en VS Code (`Documents\Administrador Inteligente de Catálogo`, casi vacía) y la real (`Desktop\EKIPON.TIENDA`). Trabajar con dos copias garantiza que se desincronicen. Hay que consolidar en una e inicializarla como **repositorio git** (control de versiones = "historial con deshacer" del proyecto).
2. **Credenciales.** `claves_pruebas.txt` tiene en texto plano las claves de la API, el candado del sitio y la contraseña de WordPress. Antes de `git init`: crear `.gitignore`, mover secretos a un `.env`, y nunca commitearlo. (Un `.env` es un archivo privado aparte donde viven las contraseñas, para que no queden escritas dentro del código ni suban al repositorio.)

### B. Decisiones de arquitectura a fijar ahora (baratas ahora, caras después)
3. **Estado en SQLite desde el día 1, no en archivos sueltos.** El HANDOFF propone "empezar con archivos y crecer a una cola". De acuerdo con la cola, pero el *estado* de cada producto (en qué fase va, qué falló) conviene guardarlo desde ya en una base de datos ligera (SQLite = una base de datos que es un solo archivo, sin servidor). Migrar el estado más tarde duele más que hacerlo bien ahora. La ficha JSON sigue siendo el contrato; SQLite solo lleva la cuenta.
4. **Validar la ficha con un esquema (pydantic).** Ya noté una diferencia entre la plantilla v1.4 y las fichas reales (p. ej. `producto.accesorios_incluidos` aparece en el piloto pero no en la plantilla). Un esquema detecta estas derivas automáticamente y evita que el Publicador reciba una ficha malformada.
5. **Publicación idempotente.** El motor reintenta lo que falla; si el Publicador corre dos veces sobre el mismo 4212 no debe crear productos duplicados. Hay que buscar el producto por `codigo_proveedor` antes de crear, y actualizar si ya existe. (Idempotente = "correrlo otra vez no hace daño ni duplica".)
6. **Plantilla Elementor: dinámica, no una copia por producto.** El ESTADO ya lo intuye. Para 100k productos, duplicar la plantilla por producto es insostenible. Tarea de investigación temprana: confirmar cómo guarda Elementor los datos (50198/50201) y si podemos usar UNA plantilla con campos dinámicos.

### C. Realidad de la escala (para conversar, no para hoy)
7. **Video ~1 min por producto a 100k** es enorme en tiempo y almacenamiento. Sugiero reservar el video para los productos top y no como requisito universal. Es una decisión de negocio tuya; solo lo dejo señalado.

## 4. Plan afinado para el Publicador (Fase 2)
Orden que reduce riesgo (cada paso valida al siguiente):

1. **Higiene:** consolidar carpeta → `git init` + `.gitignore` → mover claves a `.env`.
2. **Cliente WooCommerce mínimo + prueba de humo:** un módulo que solo se autentique y **lea el árbol de categorías EN VIVO** de pruebas.ekipon.co. Si esto funciona, la "plomería" está confirmada antes de escribir el publicador completo.
3. **Esquema de la ficha (pydantic):** validar `ficha_revisada_4212.json` contra el contrato.
4. **Publicador:** crear el 4212 como BORRADOR — título, descripción corta (= descripción principal), categoría (resuelta contra el árbol en vivo), etiquetas, precio, galería (subida con app password, ALT con el código), pestaña Descripción con Elementor 50198/50201. Idempotente.
5. **Hook de aprobación:** el proceso deja el producto en borrador y se detiene esperando a Angie.
6. **Verificar en la tienda de pruebas** y solo entonces pensar en encadenar con el Orquestador.

## 5. Preguntas abiertas
- ¿Consolidamos en la carpeta de trabajo (`Documents\...`) o prefieres que el proyecto viva en `Desktop\EKIPON.TIENDA`?
- La ficha del 4212 tiene una inconsistencia menor de negocio ("3 PIEZAS" en el nombre vs. 4 componentes). El Publicador publicará exactamente lo confirmado por Angie; ¿lo dejamos así o ajustas el nombre antes?
