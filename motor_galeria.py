"""Motor de galeria: lee el plan de la ficha y produce las piezas, solo.

Hasta ahora los generadores eran comandos sueltos que habia que correr uno por
uno. Esta es la pieza que faltaba: toma la ficha, recorre
`multimedia.plan_galeria` y arma lo que sabe armar, con UN comando por
producto.

Dos reglas de conducta, las mismas de todo el proyecto:

- **Degradar, no fallar.** Un slot sin datos no rompe la corrida: se omite con
  su motivo escrito. Nada se inventa para llenar un hueco.
- **El origen viaja con la imagen.** Cada pieza producida hereda el origen de
  los DATOS con que se dibujo (las medidas de la ficha, los callouts). Una
  imagen es tan confiable como el dato que tiene detras, y eso queda anotado.

Ademas arma el puente hacia el Publicador: lo producido queda en el plan, y
`imagenes_confirmadas_del_plan` lo traduce a
`multimedia.imagenes_galeria_confirmadas`, que es el unico campo que el
Publicador mira. Sin ese paso la galeria se produce y nadie la sube.

Uso:  python motor_galeria.py <recorte.png> --ficha ficha.json --destino galeria/
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from PIL import Image

import generador_callouts
import generador_dimensiones
import generador_galeria
from esquema_ficha import PlanGaleria
from validar_puntos import filtrar_callouts

# Tipos de slot que el motor sabe producir hoy. El resto se omite diciendo
# por que: es mejor un hueco declarado que una imagen inventada.
TIPOS_SOPORTADOS = ("producto_limpio", "medidas", "partes_senaladas")

_MOTIVOS_NO_SOPORTADO = {
    "persona_escala": "todavia no automatizado (necesita la silueta de persona y el alto real)",
    "portada_variantes": "todavia no automatizado (necesita las fotos de cada variante)",
    "escena_funcionamiento": "necesita un generador de escena con red",
    "otro_angulo_ia": "necesita un modelo de imagen con red",
    "foto_real": "no se genera: es material real, entra por la carpeta del producto",
    "accesorios": "no se genera: es material real, entra por la carpeta del producto",
}

# Lado del cuadrado que exige la tienda. No se escribe el numero a mano: lo
# declaran los generadores, y aqui se toma el MAYOR de los tres para que el
# aviso de resolucion no se quede corto si manana uno de ellos sube de tamano.
LADO_SALIDA = max(
    generador_galeria.LADO,
    generador_dimensiones.LADO,
    generador_callouts.LADO,
)

# Origen que significa "nadie firmo esta imagen". Una imagen asi no puede
# llegar sola a la tienda: la revision humana es justamente lo que falta.
# 'confirmado_por_angie' SI pasa, porque es esa revision ya hecha.
ORIGEN_SIN_FIRMA = "generado_ia_sin_verificar"

# Nota por defecto de cada tipo de slot, para cuando el plan no trae una.
# Cuidado al tocar esta tabla: la nota termina siendo el texto ALT de la
# imagen en la tienda (publicador.texto_alt_imagen), o sea texto que leen
# personas y buscadores. Por eso cada nota describe LA TOMA y nada mas:
# decir aqui algo del producto seria inventar un dato sin origen.
NOTAS_POR_TIPO = {
    "producto_limpio": "Vista general del producto sobre fondo limpio",
    "persona_escala": "Comparacion de tamano con una persona",
    "partes_senaladas": "Partes principales senaladas sobre el producto",
    "portada_variantes": "Portada con las variantes disponibles",
    "escena_funcionamiento": "El producto en funcionamiento",
    "foto_real": "Fotografia del producto",
    "medidas": "Medidas del producto",
    "otro_angulo_ia": "Vista del producto desde otro angulo",
    "accesorios": "Accesorios incluidos",
}

# Red de seguridad: si manana se agrega un tipo a TIPOS_SLOT y nadie escribe
# su nota, la galeria no se queda sin texto alt (ImagenGaleria lo exige).
NOTA_GENERICA = "Imagen del producto"


def _guardar(imagen: Image.Image, salida: Path) -> None:
    salida.parent.mkdir(parents=True, exist_ok=True)
    imagen.convert("RGB").save(salida, "WEBP", quality=90)


def _origen_de_galeria_tomas(ficha: dict, clave: str) -> str | None:
    tomas = (ficha.get("multimedia") or {}).get("galeria_tomas") or {}
    return tomas.get(clave)


# De donde hereda su origen cada pieza que el motor produce, cuando el slot no
# lo trae escrito: del dato con que se dibujo. 'producto_limpio' no sale de un
# dato de la ficha sino de la foto base, asi que hereda el origen del plan.
_ORIGEN_DE_RESPALDO = {
    "medidas": "dimensiones_origen",
    "partes_senaladas": "callouts_origen",
}


def _origen_de_slot(slot, plan: PlanGaleria, ficha: dict) -> str | None:
    """Quien responde por la pieza, o None si no se puede determinar."""
    if (slot.origen or "").strip():
        return slot.origen
    clave = _ORIGEN_DE_RESPALDO.get(slot.tipo)
    respaldo = (_origen_de_galeria_tomas(ficha, clave) if clave
                else plan.imagen_base_origen)
    return respaldo if (respaldo or "").strip() else None


def _motivo_sin_origen(tipo: str) -> str:
    """Motivo de omision de una pieza sin origen, con la salida escrita.

    Un motivo que no dice como arreglarlo obliga a leer el codigo. El campo de
    respaldo cambia segun el tipo, asi que se nombra el que corresponde.
    """
    clave = _ORIGEN_DE_RESPALDO.get(tipo)
    respaldo = (f"multimedia.galeria_tomas.{clave}" if clave
                else "multimedia.plan_galeria.imagen_base_origen")
    return (
        "sin origen: nadie responderia por esta imagen, y dato sin origen = "
        "dato inventado. Esperado: declarar 'origen' en el slot, o "
        f"'{respaldo}' en la ficha."
    )


def aviso_de_resolucion(recorte: Image.Image) -> str | None:
    """Aviso si el recorte es mas chico que el cuadrado que exige la tienda.

    Los generadores escalan lo que les den hasta `LADO_SALIDA`, asi que una foto
    pobre no falla: sale ampliada y borrosa, con pinta de pieza terminada. Eso
    es peor que un error, porque nadie lo mira dos veces. La leccion 11 de
    ESTADO_PROYECTO.md ya lo decia ("el recorte solo sirve con originales de
    alta resolucion") y no habia nada en el codigo que lo controlara.

    Avisa, NO bloquea: la conducta declarada del motor es degradar en vez de
    fallar. Devuelve None cuando el recorte alcanza.
    """
    mayor = max(recorte.width, recorte.height)
    if mayor >= LADO_SALIDA:
        return None
    factor = LADO_SALIDA / mayor
    return (
        f"RESOLUCION INSUFICIENTE: el recorte mide {recorte.width}x{recorte.height} px "
        f"y la salida exige {LADO_SALIDA}x{LADO_SALIDA} px. Su lado mayor ({mayor} px) "
        f"se va a ampliar {factor:.1f}x: las piezas salen agrandadas, o sea SIN "
        "calidad de tienda. Conseguir una foto original de mayor resolucion."
    )


def plan_de_ficha(ficha: dict) -> PlanGaleria | None:
    """Plan validado contra el esquema, o None si la ficha no trae plan.

    Se valida aqui a proposito: asi el motor trabaja siempre sobre un plan que
    ya cumple las reglas duras (toda pieza derivada anclada a una foto real).
    """
    crudo = (ficha.get("multimedia") or {}).get("plan_galeria")
    if not crudo:
        return None
    limpio = {k: v for k, v in crudo.items() if not k.startswith("_")}
    return PlanGaleria.model_validate(limpio)


def producir_galeria(ficha: dict, recorte_path: Path, destino: Path) -> dict:
    """Produce las piezas del plan. No modifica la ficha: devuelve el informe.

    Informe: {'producidos': [...], 'omitidos': [...], 'avisos': [...]}
    Cada producido trae indice, tipo, archivo y origen, listo para volcarse al
    plan con `aplicar_informe`.
    """
    informe = {"producidos": [], "omitidos": [], "avisos": []}

    plan = plan_de_ficha(ficha)
    if plan is None or not plan.hay_slots():
        informe["avisos"].append("la ficha no trae multimedia.plan_galeria con slots")
        return informe

    if not recorte_path.exists():
        raise FileNotFoundError(
            f"no existe el recorte {recorte_path}. Corre antes recortar_producto.py."
        )
    recorte = Image.open(recorte_path).convert("RGBA")

    # Se mide ANTES de dibujar nada: si la foto no da el tamano, todas las
    # piezas de esta corrida van a salir ampliadas y hay que decirlo una vez,
    # al principio, no pieza por pieza.
    aviso = aviso_de_resolucion(recorte)
    if aviso:
        informe["avisos"].append(aviso)

    # Los generadores guardan directo con PIL y no crean la carpeta: se crea
    # una sola vez aca, antes de despachar el primer slot.
    destino.mkdir(parents=True, exist_ok=True)

    for i, slot in enumerate(plan.slots, start=1):
        salida = destino / f"{i:02d}-{slot.tipo}.webp"

        if slot.tipo not in TIPOS_SOPORTADOS:
            informe["omitidos"].append({
                "tipo": slot.tipo,
                "motivo": _MOTIVOS_NO_SOPORTADO.get(slot.tipo, "tipo no soportado por el motor"),
            })
            continue

        # Primero los DATOS con que se dibuja la pieza: sin ellos no hay nada
        # que hacer, y ese motivo es mas util que cualquier otro.
        datos = None
        if slot.tipo == "medidas":
            datos = generador_dimensiones.datos_de_ficha(ficha)
            if not datos:
                informe["omitidos"].append({
                    "tipo": slot.tipo,
                    "motivo": "la ficha no trae medidas verificadas; se omite, no se estima",
                })
                continue

        elif slot.tipo == "partes_senaladas":
            crudos = generador_callouts.datos_de_ficha(ficha).get("callouts", [])
            revisados = filtrar_callouts(recorte, crudos)
            for d in revisados["descartados"]:
                informe["avisos"].append(
                    f"callout descartado: '{d['label']}' — {d['motivo']} (point={d['point']})"
                )
            if not revisados["aceptados"]:
                informe["omitidos"].append({
                    "tipo": slot.tipo,
                    "motivo": "ningun callout con punto valido sobre el producto",
                })
                continue
            datos = {"callouts": revisados["aceptados"]}

        # Despues, quien responde por ella. Se controla ANTES de dibujar y para
        # los tres tipos por igual: una pieza sin origen no puede volver al plan
        # (el esquema la rechaza al revalidar), asi que producir el archivo solo
        # dejaria basura en el disco y reventaria la corrida mas adelante.
        origen = _origen_de_slot(slot, plan, ficha)
        if origen is None:
            informe["omitidos"].append({
                "tipo": slot.tipo,
                "motivo": _motivo_sin_origen(slot.tipo),
            })
            continue

        if slot.tipo == "producto_limpio":
            _guardar(generador_galeria.hero_producto(recorte), salida)
        elif slot.tipo == "medidas":
            generador_dimensiones.generar_dimensiones(recorte_path, datos, salida)
        else:
            generador_callouts.generar_callouts(recorte_path, datos, salida)

        informe["producidos"].append({
            "indice": i, "tipo": slot.tipo, "archivo": str(salida),
            "origen": origen,
        })

    return informe


def aplicar_informe(ficha: dict, informe: dict) -> dict:
    """Vuelca al plan de la ficha el archivo y el origen de lo producido.

    Separado de `producir_galeria` a proposito: producir no deberia mutar la
    ficha de nadie por sorpresa. Quien quiera guardar el resultado, lo pide.
    """
    slots = (((ficha.get("multimedia") or {}).get("plan_galeria") or {}).get("slots")) or []
    for p in informe.get("producidos", []):
        idx = p["indice"] - 1
        if 0 <= idx < len(slots):
            slots[idx]["archivo"] = p["archivo"]
            if p.get("origen"):
                slots[idx]["origen"] = p["origen"]
    return ficha


def relativizar_a_carpeta_de_ficha(informe: dict, carpeta_ficha: Path) -> list[str]:
    """Reescribe los archivos producidos como rutas relativas a la CARPETA DE
    LA FICHA, que es la base con la que el Publicador los va a buscar.

    Por que hace falta (comprobado el 22-jul-2026): el motor escribe los
    archivos relativos al directorio desde donde se lo corrio, pero el
    Publicador resuelve cada imagen como `carpeta_de_la_ficha / url`
    (publicador.py, en `preparar_imagenes`). Son dos bases distintas. Con la
    ficha en la raiz del repo coinciden POR CASUALIDAD — que es el unico caso
    probado hasta hoy, el 4212 — y en cuanto la ficha vive en una subcarpeta la
    imagen "existe" para el motor y "falta" para el Publicador. El fallo
    aparece recien al publicar, lejos de su causa.

    Un archivo que quede fuera de la carpeta de la ficha NO se reescribe: se
    avisa. El Publicador rechaza esas rutas a proposito (barrera de seguridad
    contra '..' y rutas absolutas), asi que inventar un salto hacia arriba solo
    cambiaria el error de lugar.
    """
    avisos: list[str] = []
    base = carpeta_ficha.resolve()
    for producido in informe.get("producidos", []):
        try:
            relativa = Path(producido["archivo"]).resolve().relative_to(base)
        except ValueError:
            avisos.append(
                f"'{producido['archivo']}' quedo fuera de la carpeta de la ficha "
                f"({carpeta_ficha}). El Publicador solo acepta rutas relativas "
                "dentro de esa carpeta y la va a rechazar: produci la galeria en "
                "una subcarpeta de la ficha (--destino)."
            )
            continue
        producido["archivo"] = relativa.as_posix()
    return avisos


def nota_de_slot(slot) -> str:
    """Nota descriptiva de un slot: la suya, o la que corresponde a su tipo.

    Nunca devuelve vacio a proposito: `ImagenGaleria` exige nota con
    min_length=1, y esa nota es el texto alt con que la imagen sale publicada.
    """
    if slot.nota and slot.nota.strip():
        return slot.nota.strip()
    return NOTAS_POR_TIPO.get(slot.tipo, NOTA_GENERICA)


def imagenes_confirmadas_del_plan(ficha: dict) -> tuple[list[dict], list[dict]]:
    """Traduce el plan de la galeria a la lista que sabe leer el Publicador.

    Este es el puente que faltaba: el motor deja lo producido en
    `multimedia.plan_galeria.slots[].archivo`, y el Publicador solo mira
    `multimedia.imagenes_galeria_confirmadas`. Aqui se pasa de uno al otro.

    Funcion PURA: no toca la ficha. Devuelve (incluidas, omitidas), donde
    cada incluida es {"url", "nota"} —la forma que exige `ImagenGaleria`— en
    el ORDEN del plan, que es el orden de la galeria en la tienda.

    Se omite, con su motivo escrito:
    - el slot sin `archivo`: esta planificado pero todavia no se produjo, no
      hay nada que subir;
    - el slot cuyo origen dice `generado_ia_sin_verificar`: significa
      literalmente que nadie firmo esa imagen, y una imagen sin responsable
      no llega sola a la vidriera.
    """
    incluidas: list[dict] = []
    omitidas: list[dict] = []

    plan = plan_de_ficha(ficha)
    if plan is None or not plan.hay_slots():
        return incluidas, omitidas

    for i, slot in enumerate(plan.slots, start=1):
        if not (slot.archivo or "").strip():
            omitidas.append({
                "indice": i, "tipo": slot.tipo, "archivo": "",
                "motivo": "sin archivo: el slot esta planificado pero todavia no se produjo",
            })
            continue
        if ORIGEN_SIN_FIRMA in (slot.origen or ""):
            omitidas.append({
                "indice": i, "tipo": slot.tipo, "archivo": slot.archivo,
                "motivo": f"origen '{ORIGEN_SIN_FIRMA}': nadie reviso esta imagen, "
                          "no se sube a la tienda",
            })
            continue
        incluidas.append({"url": slot.archivo, "nota": nota_de_slot(slot)})

    return incluidas, omitidas


def aplicar_confirmadas(ficha: dict, incluidas: list[dict]) -> dict:
    """Escribe en `multimedia.imagenes_galeria_confirmadas` lo que el
    Publicador va a subir.

    Igual que `aplicar_informe`, vive aparte de la funcion que calcula: la
    ficha se muta solo cuando alguien lo pide (--guardar-ficha), nunca por
    sorpresa.
    """
    multimedia = ficha.setdefault("multimedia", {})
    multimedia["imagenes_galeria_confirmadas"] = incluidas
    return ficha


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produce la galeria de un producto leyendo su plan.")
    parser.add_argument("recorte", help="Recorte PNG con fondo transparente")
    parser.add_argument("--ficha", required=True, help="Ficha del producto")
    parser.add_argument("--destino", default="galeria", help="Carpeta de salida")
    parser.add_argument("--guardar-ficha", metavar="RUTA",
                        help="Escribe la ficha con el plan actualizado")
    args = parser.parse_args()

    ruta_ficha = Path(args.ficha)
    ficha = json.loads(ruta_ficha.read_text(encoding="utf-8-sig"))
    informe = producir_galeria(ficha, Path(args.recorte), Path(args.destino))

    for p in informe["producidos"]:
        print(f"  OK  {p['tipo']:22s} -> {p['archivo']}  [{p['origen']}]")
    for o in informe["omitidos"]:
        print(f"  --  {o['tipo']:22s} omitido: {o['motivo']}")
    print(f"\n{len(informe['producidos'])} piezas producidas, "
          f"{len(informe['omitidos'])} omitidas.")

    # Las rutas de arriba son relativas al directorio desde donde se corrio el
    # motor; dentro de la ficha tienen que ser relativas a la CARPETA DE LA
    # FICHA, que es como las busca el Publicador. Se relativizan antes de
    # calcular nada, para que lo que se imprime sea lo que se guarda.
    carpeta_ficha = Path(args.guardar_ficha or args.ficha).parent
    avisos = list(informe["avisos"]) + relativizar_a_carpeta_de_ficha(
        informe, carpeta_ficha)

    # La galeria que veria el Publicador. Se calcula sobre una COPIA para que
    # mirar el resultado no cueste mutar la ficha de nadie; la mutacion real
    # vive mas abajo, en el camino explicito de guardado.
    incluidas, omitidas = imagenes_confirmadas_del_plan(
        aplicar_informe(copy.deepcopy(ficha), informe))

    print(f"\nGaleria para el Publicador ({len(incluidas)} imagenes, en orden):")
    for n, imagen in enumerate(incluidas, start=1):
        print(f"  {n:>2}. {imagen['url']}  ({imagen['nota']})")
    for o in omitidas:
        print(f"  --  slot {o['indice']} {o['tipo']}: {o['motivo']}")

    if args.guardar_ficha:
        aplicar_informe(ficha, informe)
        aplicar_confirmadas(ficha, incluidas)
        Path(args.guardar_ficha).write_text(
            json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nFicha actualizada en {args.guardar_ficha} "
              f"(plan_galeria + imagenes_galeria_confirmadas)")

    # Los avisos van AL FINAL y en bloque, no salpicados entre las piezas: son
    # lo unico de esta salida que exige una decision humana antes de publicar,
    # y en el medio del listado se pasan por alto.
    if avisos:
        raya = "!" * 72
        print(f"\n{raya}")
        print(f"{len(avisos)} AVISO(S) — revisar antes de publicar:")
        for a in avisos:
            print(f"  !   {a}")
        print(raya)


if __name__ == "__main__":
    main()
