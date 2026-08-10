"""Cliente compartido de la tienda de PRUEBAS Ekipon.

Aplica las mismas reglas de conexion que estreno prueba_humo.py (cada modulo
mantiene su propia copia de estas reglas basicas; unificarlas en un modulo
compartido queda como mejora pendiente):
- Candado de seguridad: solo corre contra la tienda de pruebas, solo HTTPS.
- Rechazo de redirecciones: las credenciales nunca viajan a otro destino.
- Dos puertas de autenticacion segun el tipo de endpoint:
  1. wc/v3 (WooCommerce): candado del sitio en la cabecera Authorization
     (si esta configurado) + claves API como parametros en la URL.
  2. wp/v2 (WordPress: medios): contraseña de aplicacion (WP_USER +
     WP_APP_PASSWORD) en la cabecera Authorization.
     NOTA: wp/v2 requiere la excepcion del candado del hosting (Fase 0);
     queda pendiente de verificacion en vivo.

Este cliente NO tiene metodos para borrar ni para publicar/cambiar estado:
todo producto se crea SIEMPRE como borrador y la revision final es humana.
Solo puede actualizar productos que SIGAN en borrador (actualizar_borrador
verifica el estado en la tienda antes de enviar nada).
"""

import base64
import json
import socket
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

# Candado de seguridad: unica tienda contra la que este cliente acepta correr.
# La tienda real (ekipon.co) NO esta en la lista a proposito.
TIENDAS_PERMITIDAS = {"pruebas.ekipon.co"}

TIMEOUT_SEGUNDOS = 30

# El DNS de la tienda de pruebas resuelve de forma intermitente (getaddrinfo
# falla y resuelve a ratos). Se reintenta la conexion con espera creciente para
# que un lote no se caiga por un hipo de DNS. Ver test_cliente_tienda.py.
INTENTOS_CONEXION = 5
_ESPERA_BASE_SEG = 1.5

# Tipo de contenido para subir imagenes; el estandar de la tienda es WebP.
_TIPOS_IMAGEN = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# Tipo de contenido para subir el video de producto (siempre mp4: es lo que
# entrega ensamblar_video_producto.generar_a_archivo()).
_TIPOS_VIDEO = {".mp4": "video/mp4"}


class ErrorTienda(Exception):
    """Fallo al hablar con la tienda, con mensaje ya redactado en español."""

    def __init__(self, mensaje: str, codigo_http: int | None = None):
        super().__init__(mensaje)
        self.codigo_http = codigo_http


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Rechaza redirecciones: nunca reenviamos credenciales a otro destino."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code,
            f"redireccion hacia '{newurl}' rechazada por el candado de seguridad",
            headers, fp,
        )


_ABRIDOR = urllib.request.build_opener(_SinRedirecciones)


def cargar_env(ruta: Path) -> dict:
    """Lee el archivo .env (CLAVE=valor) sin depender de librerias externas."""
    if not ruta.is_file():
        sys.exit(f"ERROR: no encuentro {ruta}. Crea el .env (ver .env.example).")
    valores = {}
    # utf-8-sig: tolera el BOM que agregan algunos editores de Windows
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def verificar_candado(url_tienda: str) -> str:
    """Se niega a correr contra cualquier tienda que no sea la de pruebas."""
    partes = urlparse(url_tienda)
    if partes.scheme != "https":
        sys.exit(
            "CANDADO DE SEGURIDAD: WC_STORE_URL debe empezar con https:// "
            "(las claves nunca viajan sin cifrar). No se hizo ninguna conexion."
        )
    host = partes.hostname or ""
    if host not in TIENDAS_PERMITIDAS:
        sys.exit(
            "CANDADO DE SEGURIDAD: este cliente solo corre contra "
            f"{sorted(TIENDAS_PERMITIDAS)} y el .env apunta a '{host}'. "
            "No se hizo ninguna conexion."
        )
    return url_tienda.rstrip("/")


def forzar_borrador(payload: dict) -> dict:
    """Devuelve una copia del payload con status='draft', SIEMPRE.

    Regla fija del negocio: todo producto se crea como borrador y Angie lo
    revisa antes de publicar. Si quien llama trae otro estado explicito,
    se considera un error de programacion y se falla en voz alta.
    """
    estado = payload.get("status")
    if estado is not None and estado != "draft":
        raise ValueError(
            f"crear_producto recibio status='{estado}', pero la regla fija de "
            "la tienda es crear SIEMPRE como borrador ('draft'). No se envio nada."
        )
    seguro = dict(payload)
    seguro["status"] = "draft"
    return seguro


def _nombre_archivo_ascii(nombre: str) -> str:
    """Convierte el nombre de archivo a ASCII seguro para la cabecera HTTP."""
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    limpio = "".join(c if (c.isalnum() or c in "._-") else "-" for c in plano)
    limpio = limpio.strip("-.")
    return limpio or "imagen"


class ClienteTienda:
    """Conexion autenticada a la tienda de pruebas. Solo crea borradores."""

    def __init__(self, env: dict):
        for requerida in ("WC_STORE_URL", "WC_CONSUMER_KEY", "WC_CONSUMER_SECRET"):
            if not env.get(requerida):
                sys.exit(f"ERROR: falta {requerida} en el .env.")
        self.base = verificar_candado(env["WC_STORE_URL"])
        self._env = env

    @classmethod
    def desde_env(cls, ruta_env: Path | None = None) -> "ClienteTienda":
        """Construye el cliente leyendo el .env en TIEMPO DE EJECUCION."""
        env = cargar_env(ruta_env or Path(__file__).parent / ".env")
        return cls(env)

    # ------------------------------------------------------------------
    # Autenticacion: dos puertas segun el tipo de endpoint.
    # ------------------------------------------------------------------

    def _autenticar_wc(self, url: str) -> tuple[str, dict]:
        """wc/v3: candado del sitio en cabecera + claves API en la URL
        (valido porque el candado de seguridad exige HTTPS)."""
        separador = "&" if "?" in url else "?"
        url_final = (
            f"{url}{separador}consumer_key={quote(self._env['WC_CONSUMER_KEY'])}"
            f"&consumer_secret={quote(self._env['WC_CONSUMER_SECRET'])}"
        )
        cabeceras = {}
        if self._env.get("SITE_LOCK_USER") and self._env.get("SITE_LOCK_PASS"):
            credencial = base64.b64encode(
                f"{self._env['SITE_LOCK_USER']}:{self._env['SITE_LOCK_PASS']}".encode()
            ).decode()
            cabeceras["Authorization"] = f"Basic {credencial}"
        return url_final, cabeceras

    def _autenticar_wp(self, url: str) -> tuple[str, dict]:
        """wp/v2: contraseña de aplicacion de WordPress en la cabecera.

        NOTA (Fase 0): estos endpoints necesitan la excepcion del candado del
        hosting para el usuario de aplicacion; pendiente de verificar en vivo.
        """
        for requerida in ("WP_USER", "WP_APP_PASSWORD"):
            if not self._env.get(requerida):
                raise ErrorTienda(
                    f"falta {requerida} en el .env: los endpoints wp/v2 (subida "
                    "de imagenes) usan la contraseña de aplicacion de WordPress."
                )
        credencial = base64.b64encode(
            f"{self._env['WP_USER']}:{self._env['WP_APP_PASSWORD']}".encode()
        ).decode()
        return url, {"Authorization": f"Basic {credencial}"}

    def _preparar(self, ruta: str) -> tuple[str, dict]:
        url = f"{self.base}{ruta}"
        if "/wp-json/wc/v3/" in url:
            return self._autenticar_wc(url)
        if "/wp-json/wp/v2/" in url:
            return self._autenticar_wp(url)
        raise ErrorTienda(
            f"ruta no reconocida: '{ruta}'. Este cliente solo habla con "
            "/wp-json/wc/v3/ (WooCommerce) y /wp-json/wp/v2/ (medios)."
        )

    # ------------------------------------------------------------------
    # Transporte con errores en español (mismos mensajes que prueba_humo).
    # ------------------------------------------------------------------

    def _solicitar(self, ruta: str, datos: bytes | None = None,
                   cabeceras_extra: dict | None = None,
                   metodo: str | None = None):
        # metodo=None deja el comportamiento clasico de urllib:
        # GET sin datos, POST con datos. Solo actualizar_borrador pasa "PUT".
        url_final, cabeceras = self._preparar(ruta)
        cabeceras.update(cabeceras_extra or {})
        peticion = urllib.request.Request(
            url_final, data=datos, headers=cabeceras, method=metodo
        )
        # Un GET no tiene efectos; un POST/PUT si. Importa para decidir que es
        # seguro reintentar cuando la conexion falla a mitad de camino.
        es_lectura = datos is None and metodo is None
        for intento in range(1, INTENTOS_CONEXION + 1):
            try:
                with _ABRIDOR.open(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:
                    return json.loads(respuesta.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                # Una respuesta HTTP real (auth, 404, etc.) NUNCA se reintenta:
                # el servidor contesto, el problema no es transitorio.
                if error.code == 401:
                    raise ErrorTienda(
                        "FALLO (401): la tienda rechazo el acceso. Revisar en el .env "
                        "el candado (SITE_LOCK_USER/PASS), las claves API "
                        "(WC_CONSUMER_KEY/SECRET) o la contraseña de aplicacion "
                        "(WP_USER/WP_APP_PASSWORD) segun el endpoint.",
                        codigo_http=401,
                    ) from error
                if error.code == 403:
                    raise ErrorTienda(
                        "FALLO (403): acceso prohibido. Puede ser el candado del "
                        "sitio o permisos de la clave API.",
                        codigo_http=403,
                    ) from error
                if error.code in (301, 302, 303, 307, 308):
                    raise ErrorTienda(
                        f"FALLO: {error.reason}. No se reenviaron credenciales.",
                        codigo_http=error.code,
                    ) from error
                raise ErrorTienda(
                    f"FALLO (HTTP {error.code}): {error.reason}",
                    codigo_http=error.code,
                ) from error
            except (urllib.error.URLError, TimeoutError) as error:
                # TimeoutError puede saltar durante respuesta.read() (no solo al
                # abrir la conexion); ambos casos se informan igual, en español.
                razon = getattr(error, "reason", error)
                # Un fallo de DNS (getaddrinfo) ocurre ANTES de enviar el pedido:
                # el servidor no vio nada, asi que reintentar es seguro aunque sea
                # un POST. Otros cortes de conexion solo se reintentan en lecturas:
                # un POST/PUT pudo haberse aplicado en el servidor aunque falle la
                # respuesta, y reintentarlo duplicaria.
                es_dns = isinstance(razon, socket.gaierror)
                if (es_dns or es_lectura) and intento < INTENTOS_CONEXION:
                    time.sleep(_ESPERA_BASE_SEG * intento)
                    continue
                raise ErrorTienda(
                    f"FALLO de conexion tras {intento} intento(s): {razon}. "
                    "Revisar internet o el dominio en WC_STORE_URL."
                ) from error

    # ------------------------------------------------------------------
    # Operaciones permitidas. NO hay borrar, NO hay publicar: a proposito.
    # ------------------------------------------------------------------

    def obtener(self, ruta: str):
        """GET autenticado que devuelve el JSON ya decodificado."""
        return self._solicitar(ruta)

    def obtener_paginado(self, ruta: str) -> list:
        """GET de listas largas, pagina por pagina (per_page=100)."""
        elementos, pagina = [], 1
        separador = "&" if "?" in ruta else "?"
        while True:
            datos = self._solicitar(f"{ruta}{separador}per_page=100&page={pagina}")
            if not datos:
                break
            elementos.extend(datos)
            if len(datos) < 100:
                break
            pagina += 1
        return elementos

    def crear_producto(self, payload: dict) -> dict:
        """POST /wp-json/wc/v3/products. SIEMPRE como borrador ('draft')."""
        seguro = forzar_borrador(payload)
        cuerpo = json.dumps(seguro, ensure_ascii=False).encode("utf-8")
        return self._solicitar(
            "/wp-json/wc/v3/products",
            datos=cuerpo,
            cabeceras_extra={"Content-Type": "application/json; charset=utf-8"},
        )

    def actualizar_borrador(self, product_id: int, payload: dict) -> dict:
        """PUT /wp-json/wc/v3/products/{id} — SOLO si sigue siendo borrador.

        Regla fija del negocio: un producto publicado (o privado) ya paso la
        revision humana y este cliente NUNCA lo toca. Antes de enviar nada se
        consulta el estado actual en la tienda; si no es 'draft', se falla en
        voz alta sin modificar nada.
        """
        actual = self.obtener(f"/wp-json/wc/v3/products/{product_id}")
        estado = (actual or {}).get("status")
        if estado != "draft":
            raise ErrorTienda(
                f"el producto {product_id} esta en estado '{estado}', no en "
                "borrador ('draft'). Los productos publicados o privados no se "
                "tocan por regla fija: cualquier cambio se hace a mano en la "
                "tienda. No se envio nada."
            )
        seguro = forzar_borrador(payload)
        cuerpo = json.dumps(seguro, ensure_ascii=False).encode("utf-8")
        return self._solicitar(
            f"/wp-json/wc/v3/products/{product_id}",
            datos=cuerpo,
            cabeceras_extra={"Content-Type": "application/json; charset=utf-8"},
            metodo="PUT",
        )

    def subir_imagen(self, ruta_archivo: Path, alt_text: str, titulo: str,
                     slug_medio: str | None = None) -> dict:
        """Sube una imagen a la mediateca (wp/v2) y le fija el texto alt.

        IDEMPOTENTE: reutiliza un medio ya subido en vez de duplicarlo. La
        busqueda es por TITULO, no por slug: WordPress fija el titulo del medio
        con el nombre del archivo YA en la primera llamada (la subida), asi que
        un reintento reconoce la imagen aunque la segunda llamada (alt/slug)
        haya fallado antes. (Asume nombres de archivo unicos por caso, que es
        como los entrega el Investigador: 4212-sistema-01-conjunto.webp, etc.)

        1. Busca un medio existente cuyo titulo sea igual al de esta imagen.
        2. Si no existe: POST /wp-json/wp/v2/media con el binario crudo.
        3. POST /wp-json/wp/v2/media/{id} para fijar alt_text, titulo y slug.
        """
        previos = self.obtener(f"/wp-json/wp/v2/media?search={quote(titulo)}")
        if isinstance(previos, list):
            for medio in previos:
                titulo_medio = (medio.get("title") or {}).get("rendered", "")
                if titulo_medio.strip() == titulo.strip():
                    return medio

        ruta_archivo = Path(ruta_archivo)
        if not ruta_archivo.is_file():
            raise ErrorTienda(f"no existe el archivo de imagen: {ruta_archivo}")
        binario = ruta_archivo.read_bytes()
        tipo = _TIPOS_IMAGEN.get(ruta_archivo.suffix.lower(), "image/webp")
        nombre = _nombre_archivo_ascii(ruta_archivo.name)
        medio = self._solicitar(
            "/wp-json/wp/v2/media",
            datos=binario,
            cabeceras_extra={
                "Content-Type": tipo,
                "Content-Disposition": f'attachment; filename="{nombre}"',
            },
        )
        cuerpo_detalle = {"alt_text": alt_text, "title": titulo}
        if slug_medio:
            cuerpo_detalle["slug"] = slug_medio
        detalle = json.dumps(cuerpo_detalle, ensure_ascii=False).encode("utf-8")
        return self._solicitar(
            f"/wp-json/wp/v2/media/{medio['id']}",
            datos=detalle,
            cabeceras_extra={"Content-Type": "application/json; charset=utf-8"},
        )

    def subir_video(self, ruta_archivo: Path, product_id: int, titulo: str) -> dict:
        """Sube el video de producto a la mediateca (wp/v2), asociado
        DIRECTAMENTE al producto via el parametro 'post' (asi la tienda lo
        deja adjunto al producto sin un paso aparte). Devuelve el medio.

        Mismo patron que subir_imagen: IDEMPOTENTE por titulo (busca un medio
        existente con ese titulo exacto antes de subir, para que un reintento
        tras un fallo no duplique el video en la mediateca).
        """
        previos = self.obtener(f"/wp-json/wp/v2/media?search={quote(titulo)}")
        if isinstance(previos, list):
            for medio in previos:
                titulo_medio = (medio.get("title") or {}).get("rendered", "")
                if titulo_medio.strip() == titulo.strip():
                    return medio

        ruta_archivo = Path(ruta_archivo)
        if not ruta_archivo.is_file():
            raise ErrorTienda(f"no existe el archivo de video: {ruta_archivo}")
        binario = ruta_archivo.read_bytes()
        tipo = _TIPOS_VIDEO.get(ruta_archivo.suffix.lower(), "video/mp4")
        nombre = _nombre_archivo_ascii(ruta_archivo.name)
        medio = self._solicitar(
            f"/wp-json/wp/v2/media?post={product_id}",
            datos=binario,
            cabeceras_extra={
                "Content-Type": tipo,
                "Content-Disposition": f'attachment; filename="{nombre}"',
            },
        )
        detalle = json.dumps({"title": titulo}, ensure_ascii=False).encode("utf-8")
        return self._solicitar(
            f"/wp-json/wp/v2/media/{medio['id']}",
            datos=detalle,
            cabeceras_extra={"Content-Type": "application/json; charset=utf-8"},
        )
