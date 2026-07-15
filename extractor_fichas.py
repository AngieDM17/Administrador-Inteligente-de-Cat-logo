# -*- coding: utf-8 -*-
"""
EXTRACTOR DE FICHAS v0.2 — Proyecto Ekipon, Fase 1
===================================================
Qué hace: lee un documento Word (.docx) con la ficha de un producto
y produce dos cosas:
  1. Un archivo JSON con todo el contenido organizado (la "ficha estándar")
  2. Una carpeta con todas las imágenes extraídas en calidad original

Cómo se usa (desde una terminal):
  python extractor_fichas.py "Soldadura.prubeas .docx"

NOTA PARA ANGIE: este script es la etapa "mecánica" del extractor.
No usa inteligencia artificial: solo abre el documento y saca lo que hay.
La etapa de interpretación (nombre comercial, categoría, etc.) la hace
Claude después, leyendo el JSON que este script genera.

Un .docx es en realidad un archivo ZIP (comprimido) que contiene:
  - word/document.xml  -> todo el texto y las tablas
  - word/media/        -> todas las imágenes
Por eso no necesitamos programas especiales para abrirlo.

Cambios v0.2 (tras la primera prueba con la soldadura):
  - Las características que vienen pegadas en un solo párrafo separadas
    por chulitos (✅) ahora se parten correctamente en piezas.
  - La fila de encabezado de la tabla ("Especificación / Detalle") ya no
    se cuela aunque llegue con el texto cortado.
"""

import sys
import os
import re
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

# "Namespace" de Word: es el prefijo técnico que usan las etiquetas
# internas del documento (párrafos, tablas, filas...).
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extraer_texto_de(elemento):
    """Junta todo el texto que hay dentro de un elemento del documento."""
    return "".join(t.text or "" for t in elemento.iter(W + "t")).strip()


def extraer(ruta_docx):
    if not os.path.exists(ruta_docx):
        print(f"ERROR: no encuentro el archivo: {ruta_docx}")
        sys.exit(1)

    nombre_base = os.path.splitext(os.path.basename(ruta_docx))[0].strip()
    carpeta_salida = f"extraido_{nombre_base}"
    carpeta_imagenes = os.path.join(carpeta_salida, "imagenes")
    os.makedirs(carpeta_imagenes, exist_ok=True)

    z = zipfile.ZipFile(ruta_docx)

    # ---------- 1. IMÁGENES ----------
    imagenes = []
    for nombre in z.namelist():
        if nombre.startswith("word/media/"):
            datos = z.read(nombre)
            destino = os.path.join(carpeta_imagenes, os.path.basename(nombre))
            with open(destino, "wb") as f:
                f.write(datos)
            imagenes.append({
                "archivo": os.path.basename(nombre),
                "tamano_kb": round(len(datos) / 1024, 1)
            })
    print(f"[OK] {len(imagenes)} imágenes extraídas en {carpeta_imagenes}")

    # ---------- 2. TEXTO Y TABLAS ----------
    raiz = ET.fromstring(z.read("word/document.xml"))
    cuerpo = raiz.find(W + "body")

    parrafos = []          # texto suelto, en orden
    tablas = []            # cada tabla como lista de filas [clave, valor]

    for hijo in cuerpo:
        if hijo.tag == W + "p":                      # párrafo
            texto = extraer_texto_de(hijo)
            if texto:
                parrafos.append(texto)
        elif hijo.tag == W + "tbl":                  # tabla
            filas = []
            for fila in hijo.iter(W + "tr"):
                celdas = [extraer_texto_de(c) for c in fila.iter(W + "tc")]
                if any(celdas):
                    filas.append(celdas)
            tablas.append(filas)

    print(f"[OK] {len(parrafos)} párrafos y {len(tablas)} tablas encontradas")

    # ---------- 3. DATOS CON PATRÓN FIJO (precio, YouTube) ----------
    todo_el_texto = "\n".join(parrafos)

    precio = None
    m = re.search(r"Precio\s*Normal\s*:?\s*\$?\s*([\d.,]+)", todo_el_texto, re.IGNORECASE)
    if m:
        # "260.000" -> 260000 (quitamos puntos de miles)
        precio = int(m.group(1).replace(".", "").replace(",", ""))

    video = None
    m = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+", todo_el_texto)
    if m:
        video = m.group(0)

    # ---------- 4. FICHA TÉCNICA (tabla clave -> valor) ----------
    ficha_tecnica = {}
    for tabla in tablas:
        for fila in tabla:
            if len(fila) >= 2 and fila[0] and fila[1]:
                clave = fila[0].strip()
                valor = fila[1].strip()
                # Saltamos filas de encabezado tipo "Especificación / Detalle"
                # (usamos "pecificaci" porque a veces el texto llega cortado)
                if "pecificaci" in clave.lower() or valor.lower() == "detalle":
                    continue
                ficha_tecnica[clave] = valor

    # ---------- 5. SEPARAR DESCRIPCIÓN Y CARACTERÍSTICAS ----------
    descripcion, caracteristicas = [], []
    modo = "descripcion"
    for p in parrafos:
        limpio = p.strip()
        bajo = limpio.lower()
        if bajo.startswith("caracteristicas") or bajo.startswith("características"):
            modo = "caracteristicas"
            continue
        if bajo.startswith("ficha técnica") or bajo.startswith("ficha tecnica"):
            modo = "otro"
            continue
        if bajo.startswith("descripcion") or bajo.startswith("descripción"):
            continue
        if bajo.startswith("precio") or "youtube" in bajo:
            continue
        if modo == "descripcion":
            descripcion.append(limpio)
        elif modo == "caracteristicas":
            # A veces varias características vienen en un mismo párrafo,
            # separadas por chulitos (✅). Las partimos en piezas.
            piezas = re.split(r"[✅✔☑•▪]", limpio)
            for pieza in piezas:
                pieza = pieza.strip().lstrip("-– ").rstrip(".").strip()
                if pieza:
                    caracteristicas.append(pieza)

    # ---------- 6. ARMAR LA FICHA ESTÁNDAR ----------
    ficha = {
        "archivo_origen": os.path.basename(ruta_docx),
        "fecha_extraccion": date.today().isoformat(),
        "estado": "extraido_pendiente_ia",
        "producto": {
            "nombre_propuesto": None,        # lo genera Claude en la etapa 2
            "modelo": ficha_tecnica.get("Modelo") or ficha_tecnica.get("MODELO"),
            "sku": None,                     # lo genera el sistema al crear el producto
            "categoria_propuesta": None,     # la asigna Claude (etapa 2)
            "garantia": "1 año"              # política fija de la tienda
        },
        "precios": {"precio": precio, "moneda": "COP"},
        "descripcion_principal": " ".join(descripcion),
        "caracteristicas": caracteristicas,
        "ficha_tecnica": ficha_tecnica,
        "multimedia": {
            "imagenes": imagenes,
            "video_youtube": video
        }
    }

    ruta_json = os.path.join(carpeta_salida, "ficha_extraida.json")
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(ficha, f, ensure_ascii=False, indent=2)

    print(f"[OK] Ficha estándar guardada en {ruta_json}")
    print("\nResumen:")
    print(f"  Modelo: {ficha['producto']['modelo']}")
    print(f"  Precio: {precio} COP")
    print(f"  Especificaciones: {len(ficha_tecnica)}")
    print(f"  Características: {len(caracteristicas)}")
    print(f"  Imágenes: {len(imagenes)}")
    print(f"  Video: {video}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Uso: python extractor_fichas.py "nombre_del_archivo.docx"')
        sys.exit(1)
    extraer(sys.argv[1])
