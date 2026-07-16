"""Prueba de humo del Publicador Ekipon.

Se conecta a la tienda de PRUEBAS y lee el arbol de categorias en vivo.
Solo LECTURA: no crea, no modifica y no borra nada.

Uso:  python prueba_humo.py
Requiere: archivo .env en esta misma carpeta (ver .env.example).
"""

import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# Candado de seguridad: unica tienda contra la que este script acepta correr.
# La tienda real (ekipon.co) NO esta en la lista a proposito.
TIENDAS_PERMITIDAS = {"pruebas.ekipon.co"}

TIMEOUT_SEGUNDOS = 30


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
            "CANDADO DE SEGURIDAD: este script solo corre contra "
            f"{sorted(TIENDAS_PERMITIDAS)} y el .env apunta a '{host}'. "
            "No se hizo ninguna conexion."
        )
    return url_tienda.rstrip("/")


def pedir_json(url: str, env: dict):
    """GET autenticado.

    La tienda de pruebas tiene DOS puertas:
    1. El candado del sitio (SITE_LOCK_*, si esta configurado): autenticacion
       basica en la cabecera Authorization.
    2. Las claves API de WooCommerce: siempre como parametros en la URL
       (valido porque el candado de seguridad exige HTTPS).
    """
    from urllib.parse import quote

    separador = "&" if "?" in url else "?"
    url_final = (
        f"{url}{separador}consumer_key={quote(env['WC_CONSUMER_KEY'])}"
        f"&consumer_secret={quote(env['WC_CONSUMER_SECRET'])}"
    )
    cabeceras = {}
    if env.get("SITE_LOCK_USER") and env.get("SITE_LOCK_PASS"):
        credencial = base64.b64encode(
            f"{env['SITE_LOCK_USER']}:{env['SITE_LOCK_PASS']}".encode()
        ).decode()
        cabeceras["Authorization"] = f"Basic {credencial}"

    peticion = urllib.request.Request(url_final, headers=cabeceras)
    with _ABRIDOR.open(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:
        return json.loads(respuesta.read().decode("utf-8")), dict(respuesta.headers)


def leer_categorias(base: str, env: dict) -> list:
    """Lee TODAS las categorias de producto, pagina por pagina."""
    categorias, pagina = [], 1
    while True:
        url = (
            f"{base}/wp-json/wc/v3/products/categories"
            f"?per_page=100&page={pagina}&orderby=name"
        )
        datos, _ = pedir_json(url, env)
        if not datos:
            break
        categorias.extend(datos)
        if len(datos) < 100:
            break
        pagina += 1
    return categorias


def imprimir_arbol(categorias: list) -> None:
    """Muestra las categorias como arbol, con la cantidad de productos de cada una."""
    hijos_de = {}
    for cat in categorias:
        hijos_de.setdefault(cat["parent"], []).append(cat)
    for lista in hijos_de.values():
        lista.sort(key=lambda c: c["name"].lower())

    vistos = set()  # evita recursion infinita si los datos traen un ciclo

    def rama(id_padre: int, nivel: int) -> None:
        for cat in hijos_de.get(id_padre, []):
            sangria = "    " * nivel
            if cat["id"] in vistos:
                print(f"{sangria}! categoria {cat['id']} con parentesco ciclico — se omite")
                continue
            vistos.add(cat["id"])
            print(f"{sangria}- {cat['name']}  (id {cat['id']}, {cat['count']} productos)")
            rama(cat["id"], nivel + 1)

    rama(0, 0)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    env = cargar_env(Path(__file__).parent / ".env")
    for requerida in ("WC_STORE_URL", "WC_CONSUMER_KEY", "WC_CONSUMER_SECRET"):
        if not env.get(requerida):
            sys.exit(f"ERROR: falta {requerida} en el .env.")

    base = verificar_candado(env["WC_STORE_URL"])
    print(f"Tienda: {base}  [candado OK: es la tienda de pruebas]")
    print("Conectando y leyendo categorias en vivo...\n")

    try:
        categorias = leer_categorias(base, env)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            sys.exit(
                "FALLO (401): la tienda rechazo el acceso. Revisar en el .env el candado "
                "(SITE_LOCK_USER/PASS) y las claves API (WC_CONSUMER_KEY/SECRET)."
            )
        if error.code == 403:
            sys.exit("FALLO (403): acceso prohibido. Puede ser el candado del sitio o permisos de la clave API.")
        sys.exit(f"FALLO (HTTP {error.code}): {error.reason}")
    except urllib.error.URLError as error:
        sys.exit(f"FALLO de conexion: {error.reason}. Revisar internet o el dominio en WC_STORE_URL.")

    print(f"PRUEBA DE HUMO OK — autenticacion aceptada, {len(categorias)} categorias leidas:\n")
    imprimir_arbol(categorias)


if __name__ == "__main__":
    main()
