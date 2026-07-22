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

Uso:  python motor_galeria.py <recorte.png> --ficha ficha.json --destino galeria/
"""

from __future__ import annotations

import argparse
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


def _guardar(imagen: Image.Image, salida: Path) -> None:
    salida.parent.mkdir(parents=True, exist_ok=True)
    imagen.convert("RGB").save(salida, "WEBP", quality=90)


def _origen_de_galeria_tomas(ficha: dict, clave: str) -> str | None:
    tomas = (ficha.get("multimedia") or {}).get("galeria_tomas") or {}
    return tomas.get(clave)


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

        if slot.tipo == "producto_limpio":
            _guardar(generador_galeria.hero_producto(recorte), salida)
            informe["producidos"].append({
                "indice": i, "tipo": slot.tipo, "archivo": str(salida),
                "origen": slot.origen or plan.imagen_base_origen,
            })

        elif slot.tipo == "medidas":
            datos = generador_dimensiones.datos_de_ficha(ficha)
            if not datos:
                informe["omitidos"].append({
                    "tipo": slot.tipo,
                    "motivo": "la ficha no trae medidas verificadas; se omite, no se estima",
                })
                continue
            generador_dimensiones.generar_dimensiones(recorte_path, datos, salida)
            informe["producidos"].append({
                "indice": i, "tipo": slot.tipo, "archivo": str(salida),
                "origen": slot.origen or _origen_de_galeria_tomas(ficha, "dimensiones_origen"),
            })

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
            generador_callouts.generar_callouts(
                recorte_path, {"callouts": revisados["aceptados"]}, salida)
            informe["producidos"].append({
                "indice": i, "tipo": slot.tipo, "archivo": str(salida),
                "origen": slot.origen or _origen_de_galeria_tomas(ficha, "callouts_origen"),
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
    for a in informe["avisos"]:
        print(f"  !   {a}")
    print(f"\n{len(informe['producidos'])} piezas producidas, "
          f"{len(informe['omitidos'])} omitidas.")

    if args.guardar_ficha:
        aplicar_informe(ficha, informe)
        Path(args.guardar_ficha).write_text(
            json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Ficha actualizada en {args.guardar_ficha}")


if __name__ == "__main__":
    main()
