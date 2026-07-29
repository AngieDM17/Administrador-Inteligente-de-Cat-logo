"""Contrato de la ficha Ekipon v1.4 expresado como modelos pydantic.

Este modulo define QUE debe cumplir una ficha para considerarse valida.
La herramienta de linea de comandos que lo usa es validar_ficha.py.

Reglas de negocio FIJAS (errores, bloquean):
- producto.nombre_propuesto: no vacio y completamente en MAYUSCULAS.
- producto.sku: debe comenzar con el literal AUTOMATICO (WooCommerce asigna el real).
- precios.precio: entero en COP (se rechazan decimales y textos). Puede ser
  null o 0 SOLO si precio_origen indica PENDIENTE_ANGIE (el precio siempre
  lo define Angie manualmente).
- producto.garantia: debe expresar 1 año (politica fija de la tienda).
- Todo campo de origen debe contener uno de los valores permitidos
  (ver ORIGENES_PERMITIDOS). Dato sin origen = dato inventado = error.

Decisiones de tolerancia (deliberadas, ver comentario en cada campo):
- Todas las secciones aceptan claves extra (extra="allow") porque las fichas
  reales agregan campos legitimos (p. ej. accesorios_incluidos, fecha_revision).
  Las claves desconocidas NO se aceptan en silencio: validar_ficha.py las
  reporta como advertencias.
- Los campos de origen se validan por CONTENIDO, no por igualdad exacta,
  porque las fichas reales escriben el origen con contexto, p. ej.
  "confirmado_por_angie (15-jul-2026). ...". Basta con que el texto contenga
  uno de los valores permitidos como palabra completa.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

# Version del contrato que estos modelos representan.
VERSION_CONTRATO = "1.4"

# Valores de origen permitidos por la plantilla v1.4 (campo _uso).
ORIGENES_PERMITIDOS = (
    "verificado",
    "encontrado_web",
    "generado_ia",
    "generado_ia_sin_verificar",
    "confirmado_por_angie",
    "PENDIENTE_ANGIE",
)

# Patron que busca cualquiera de los origenes como palabra completa
# (los limites evitan falsos positivos como "confirmada_por_angie",
# que NO es un valor permitido).
_PATRON_ORIGEN = re.compile(
    "|".join(
        rf"(?<!\w){re.escape(origen)}(?!\w)"
        for origen in sorted(ORIGENES_PERMITIDOS, key=len, reverse=True)
    )
)


def tiene_origen_permitido(texto: Optional[str]) -> bool:
    """Indica si el texto contiene al menos un valor de origen permitido."""
    return bool(texto) and _PATRON_ORIGEN.search(texto) is not None


# La marca de precio pendiente se busca con los mismos limites de palabra
# que el resto de los origenes, y reutiliza el valor de ORIGENES_PERMITIDOS.
_MARCA_PENDIENTE = ORIGENES_PERMITIDOS[-1]  # "PENDIENTE_ANGIE"
_PATRON_PENDIENTE = re.compile(rf"(?<!\w){re.escape(_MARCA_PENDIENTE)}(?!\w)")


def precio_esta_pendiente(texto: Optional[str]) -> bool:
    """Indica si el origen del precio lleva la marca PENDIENTE_ANGIE completa."""
    return bool(texto) and _PATRON_PENDIENTE.search(texto) is not None


_ESPERADO_ORIGEN = (
    "Esperado: texto que contenga uno de los origenes permitidos: "
    + " | ".join(ORIGENES_PERMITIDOS)
)


def _exigir_origen(valor: Optional[str]) -> Optional[str]:
    """Validador compartido para campos que declaran el origen de un dato."""
    if valor is None or not valor.strip():
        raise ValueError("el origen esta vacio; dato sin origen = dato inventado. " + _ESPERADO_ORIGEN)
    if not tiene_origen_permitido(valor):
        raise ValueError(
            f"'{valor[:80]}' no contiene ningun origen permitido. " + _ESPERADO_ORIGEN
        )
    return valor


class ModeloBase(BaseModel):
    """Base comun: acepta claves extra (las reporta validar_ficha.py) y
    permite poblar campos por alias (_version_ficha, _origen_global, etc.)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class EntradaOriginal(ModeloBase):
    """Lo que entrego Angie al inicio de la investigacion."""

    # Tolerancia: los tres campos son opcionales porque la ficha NBC250 (v1.3)
    # no trae codigo_proveedor y la plantilla los trae vacios.
    nombre_dado: Optional[str] = None
    codigo_proveedor: Optional[str] = None
    foto_referencia: Optional[str] = None
    # Camino preferido del modelo de dos caminos (24-jul-2026): el link exacto
    # del producto. Si viene, la identificacion se hace por extraccion de la
    # fuente (identidad mas fuerte que nombre+foto). Opcional: las fichas de
    # respaldo (solo nombre+foto) entran sin link.
    link_producto: Optional[str] = None


class IdentificacionDelProducto(ModeloBase):
    """Resultado de identificar el producto contra la fuente principal."""

    resultado: str
    detalle: Optional[str] = None
    fuente_principal: Optional[str] = None
    # Tolerancia: NBC250 (v1.3) no trae advertencias ni estado_en_proveedor
    # (usa estado_en_importador, que quedara reportado como clave extra).
    advertencias: Optional[list] = None
    estado_en_proveedor: Optional[str] = None
    # Etiqueta de metodo del modelo de dos caminos (24-jul-2026): COMO se
    # identifico el producto, para saber cuanto confiar en la ficha durante la
    # revision. Lista cerrada: 'link' (extraido de la fuente exacta),
    # 'busqueda_imagen' (link conseguido por reverse-image antes de inferir),
    # 'inferencia' (solo nombre+foto; ficha nivel-familia, menor confianza).
    origen_identificacion: Optional[str] = None

    @field_validator("resultado")
    @classmethod
    def _resultado_conocido(cls, valor: str) -> str:
        # Se valida por PREFIJO porque las fichas reales agregan contexto,
        # p. ej. "IDENTIFICADO — producto exacto del importador".
        permitidos = ("IDENTIFICADO", "IDENTIFICACION_DUDOSA", "NO_IDENTIFICADO")
        if not any(valor.startswith(p) for p in permitidos):
            raise ValueError(
                f"'{valor[:60]}' no es un resultado reconocido. "
                "Esperado: texto que comience con IDENTIFICADO, "
                "IDENTIFICACION_DUDOSA o NO_IDENTIFICADO."
            )
        return valor

    @field_validator("origen_identificacion")
    @classmethod
    def _origen_identificacion_conocido(cls, valor):
        # Opcional por tolerancia: las fichas v1.3/v1.4 previas no lo traen.
        # Si viene, debe ser uno de los tres metodos del modelo de dos caminos.
        # Se normaliza (espacios/mayusculas) para no invalidar una ficha entera
        # por un ' Link' descuidado, en linea con la tolerancia del resto del
        # contrato, y se devuelve el token canonico en minusculas.
        if valor in (None, ""):
            return valor
        normalizado = valor.strip().lower() if isinstance(valor, str) else valor
        permitidos = ("link", "busqueda_imagen", "inferencia")
        if normalizado not in permitidos:
            raise ValueError(
                f"origen_identificacion '{str(valor)[:40]}' no es un metodo valido. "
                f"Esperado uno de: {', '.join(permitidos)}."
            )
        return normalizado


class Producto(ModeloBase):
    """Datos comerciales del producto. Aqui viven varias reglas fijas."""

    nombre_propuesto: str
    nombre_origen: str
    modelo: Optional[str] = None
    sku: str
    categoria_propuesta: Optional[str] = None
    categoria_confianza: str
    etiquetas_propuestas: Optional[list] = None
    garantia: str
    # True si el producto lleva motor (maquinaria electrica/combustion), False si
    # no (escalera, silla, gimnasio, herramienta manual). Opcional por tolerancia
    # con fichas previas; el colador solo salta la exigencia de potencia cuando es
    # explicitamente False (ante ausencia se asume motorizado).
    es_motorizado: Optional[bool] = None

    @field_validator("nombre_propuesto")
    @classmethod
    def _nombre_en_mayusculas(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError(
                "no puede estar vacio. Esperado: nombre comercial en MAYUSCULAS."
            )
        if valor != valor.upper():
            raise ValueError(
                f"'{valor[:80]}' tiene letras minusculas. "
                "Esperado: el nombre completo en MAYUSCULAS (regla fija de la tienda)."
            )
        return valor

    @field_validator("sku")
    @classmethod
    def _sku_automatico(cls, valor: str) -> str:
        # Regla fija: el SKU real lo asigna WooCommerce. La ficha debe decir
        # AUTOMATICO; se permite texto aclaratorio despues (asi lo hace la
        # ficha 4212: "AUTOMATICO — lo asigna el sistema...").
        if not valor.startswith("AUTOMATICO"):
            raise ValueError(
                f"'{valor[:60]}' no es valido. Esperado: el literal AUTOMATICO "
                "(el SKU real lo asigna WooCommerce, nunca se escribe a mano)."
            )
        return valor

    @field_validator("garantia")
    @classmethod
    def _garantia_un_ano(cls, valor: str) -> str:
        if "1 año" not in valor:
            raise ValueError(
                f"'{valor[:60]}' no expresa la garantia fija. "
                "Esperado: texto que contenga '1 año' (politica fija de la tienda)."
            )
        return valor

    # Campos de origen: nombre_origen y categoria_confianza declaran de donde
    # salio el dato, por eso se validan contra los origenes permitidos.
    _v_nombre_origen = field_validator("nombre_origen")(_exigir_origen)
    _v_categoria_confianza = field_validator("categoria_confianza")(_exigir_origen)


class Precios(ModeloBase):
    """Precio y referencias. REGLA FIJA: el precio lo define Angie a mano."""

    # StrictInt rechaza decimales (16434999.0) y textos ("16434999").
    precio: Optional[StrictInt] = None
    precio_origen: str
    # Tolerancia: NBC250 (v1.3) no trae referencias_mercado (usa
    # referencia_encontrada, que quedara reportada como clave extra).
    referencias_mercado: Optional[list] = None
    nota_envio: Optional[str] = None
    moneda: str

    @field_validator("precio")
    @classmethod
    def _precio_no_negativo(cls, valor: Optional[int]) -> Optional[int]:
        if valor is not None and valor < 0:
            raise ValueError(
                f"{valor} es negativo. Esperado: entero en COP mayor o igual a 0."
            )
        return valor

    @field_validator("moneda")
    @classmethod
    def _moneda_cop(cls, valor: str) -> str:
        if valor != "COP":
            raise ValueError(f"'{valor}' no es valido. Esperado: COP (pesos colombianos).")
        return valor

    _v_precio_origen = field_validator("precio_origen")(_exigir_origen)

    @model_validator(mode="after")
    def _precio_pendiente_solo_con_marca(self) -> "Precios":
        # Asi representa la plantilla un precio pendiente: precio null y
        # precio_origen con la marca PENDIENTE_ANGIE. Un precio vacio SIN esa
        # marca es un error (el precio nunca se omite en silencio).
        if self.precio in (None, 0) and not precio_esta_pendiente(self.precio_origen):
            raise ValueError(
                "precios.precio esta vacio (null o 0) pero precios.precio_origen "
                "no dice PENDIENTE_ANGIE. Esperado: precio entero definido por "
                "Angie, o la marca PENDIENTE_ANGIE en precio_origen."
            )
        return self


class FichaTecnica(ModeloBase):
    """Ficha tecnica: claves libres en MAYUSCULAS + metadatos con guion bajo.

    Tolerancia: las claves tecnicas (TANQUE — CAPACIDAD, VOLTAJE, etc.) varian
    por producto, por eso NO se listan aqui; llegan como claves extra y no se
    reportan como desconocidas. El origen se controla a nivel de seccion con
    _origen_global, igual que en las fichas reales.
    """

    origen_global: Optional[str] = Field(None, alias="_origen_global")
    nota: Optional[str] = Field(None, alias="_nota")

    @model_validator(mode="after")
    def _datos_con_origen_global(self) -> "FichaTecnica":
        claves_de_datos = [
            clave for clave in (self.model_extra or {}) if not clave.startswith("_")
        ]
        if claves_de_datos and not tiene_origen_permitido(self.origen_global):
            raise ValueError(
                "ficha_tecnica trae datos pero _origen_global no declara un "
                "origen permitido. Dato sin origen = dato inventado. "
                + _ESPERADO_ORIGEN
            )
        return self


class CriterioVerificacionVisual(ModeloBase):
    """Criterio SI/NO para aceptar o rechazar imagenes."""

    # Tolerancia: todos opcionales porque NBC250 (v1.3) renombra SI_es a
    # SI_es_NBC250_9060C y no trae uso; ese drift se reporta como clave extra.
    definido_por: Optional[str] = None
    SI_es: Optional[str] = None
    NO_es: Optional[str] = None
    rasgo_decisivo: Optional[str] = None
    uso: Optional[str] = None


class ImagenGaleria(ModeloBase):
    """Una imagen confirmada de la galeria: ruta relativa + nota descriptiva."""

    url: str = Field(min_length=1)
    nota: str = Field(min_length=1)


class CalloutParte(ModeloBase):
    """Una parte senalada del producto, para la toma de callouts.

    'point' es OPCIONAL a proposito: el Investigador puede averiguar QUE partes
    tiene el producto (de la web), pero no DONDE caen sobre la foto real. Sin
    punto, la parte no se dibuja — se omite, nunca se inventa una posicion.
    """

    label: str = Field(min_length=1)
    point: Optional[list[float]] = None  # [x, y] relativos al producto, 0..1

    @field_validator("point")
    @classmethod
    def _v_point(cls, valor):
        if valor is None:
            return valor
        if len(valor) != 2 or not all(0.0 <= c <= 1.0 for c in valor):
            raise ValueError("point debe ser [x, y] con valores entre 0 y 1")
        return valor


class DimensionesProducto(ModeloBase):
    """Medidas reales del producto para la toma de tamano. Todas opcionales:
    lo que no este verificado se OMITE, no se inventa ni frena el pipeline."""

    alto: Optional[str] = None
    ancho: Optional[str] = None
    fondo: Optional[str] = None
    peso: Optional[str] = None

    def hay_alguna(self) -> bool:
        return any([self.alto, self.ancho, self.fondo, self.peso])


class GaleriaTomas(ModeloBase):
    """Datos que alimentan las tomas GENERADAS de la galeria (callouts y
    dimensiones). Los emite el Investigador para que la etapa de imagenes salga
    sola, sin JSONs sueltos escritos a mano."""

    callouts: Optional[list[CalloutParte]] = None
    callouts_origen: Optional[str] = None
    dimensiones: Optional[DimensionesProducto] = None
    dimensiones_origen: Optional[str] = None

    @model_validator(mode="after")
    def _exigir_origen_si_hay_datos(self):
        """Regla del proyecto: dato sin origen = dato inventado."""
        if self.callouts:
            _exigir_origen(self.callouts_origen)
        if self.dimensiones is not None and self.dimensiones.hay_alguna():
            _exigir_origen(self.dimensiones_origen)
        return self


# --- Plan de galeria -------------------------------------------------------
# Los slots salen del proceso manual que Angie ejecuta hoy producto por
# producto (descrito por ella el 22-jul-2026). La etapa de imagenes no inventa
# un metodo nuevo: automatiza ESTE. Ver ETAPA_IMAGENES.md.
TIPOS_SLOT = (
    "producto_limpio",        # hero: recorte limpio sobre blanco
    "persona_escala",         # persona al lado para dar idea del tamano
    "partes_senaladas",       # callouts sobre la maquina completa
    "portada_variantes",      # portada con las variantes de motor del producto
    "escena_funcionamiento",  # la maquina en uso
    "foto_real",              # foto del proveedor / web / Alibaba
    "medidas",                # medidas sobre la maquina
    "otro_angulo_ia",         # re-render imagen->imagen del mismo equipo
    "accesorios",             # accesorios incluidos, si vienen
)

# COMO se produjo la imagen. Es un eje distinto del origen: 'fuente' dice con
# que se hizo, 'origen' dice quien responde por ella. Los dos hacen falta para
# saber, meses despues, que imagen es una foto y cual es una recreacion.
FUENTES_SLOT = (
    "foto_real",        # material real tal cual; no deriva de nada
    "edicion_manual",   # foto real editada a mano (lo que Angie hace hoy en Canva)
    "generado_motor",   # pieza determinista del motor propio (Pillow)
    "compuesto",        # montaje de material real
    "escena_ia",        # entorno generado con el producto real encima
    "imagen_a_imagen",  # re-render del producto a partir de una foto real
)

# Fuentes que NO son una fotografia: no pueden declarar un origen que afirme
# que la imagen es real. Regla 6 de reglas_negocio.md.
_FUENTES_IA = ("escena_ia", "imagen_a_imagen")

# Origenes que afirman "esto es una foto del producto".
_ORIGENES_QUE_AFIRMAN_FOTO = ("verificado", "encontrado_web")

# Origenes que afirman "esto lo genero una IA".
_ORIGENES_QUE_AFIRMAN_IA = ("generado_ia", "generado_ia_sin_verificar")


def _patron_de(origenes: tuple[str, ...]) -> re.Pattern:
    """Patron con limites de palabra, igual que _PATRON_ORIGEN.

    Los limites importan: '_' cuenta como caracter de palabra, asi que
    'generado_ia' NO matchea dentro de 'generado_ia_sin_verificar'. Cada
    origen se reconoce solo a si mismo.
    """
    return re.compile(
        "|".join(
            rf"(?<!\w){re.escape(o)}(?!\w)"
            for o in sorted(origenes, key=len, reverse=True)
        )
    )


_PATRON_AFIRMA_FOTO = _patron_de(_ORIGENES_QUE_AFIRMAN_FOTO)
_PATRON_AFIRMA_IA = _patron_de(_ORIGENES_QUE_AFIRMAN_IA)

# Fuentes que obligan a declarar de que imagen REAL salieron. Con esto la
# generacion desde la nada (texto->imagen, la que invento la marca falsa
# "SHENGKEY") queda IMPOSIBLE de expresar en el contrato: toda imagen del
# producto esta anclada a una foto real, o no entra.
_FUENTES_QUE_EXIGEN_BASE = (
    "edicion_manual",
    "generado_motor",
    "compuesto",
    "escena_ia",
    "imagen_a_imagen",
)


class SlotGaleria(ModeloBase):
    """Una posicion de la galeria: que se muestra, como se produjo y quien
    responde por ella.

    'archivo' vacio = slot planificado pero todavia no producido. Por eso el
    origen solo se exige cuando la imagen existe: sin imagen no hay nada que
    declarar.
    """

    tipo: str
    fuente: str
    origen: Optional[str] = None
    archivo: Optional[str] = None
    # De que imagen real salio. Si falta, se usa el imagen_base del plan.
    deriva_de: Optional[str] = None
    nota: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _tipo_conocido(cls, valor: str) -> str:
        if valor not in TIPOS_SLOT:
            raise ValueError(
                f"'{valor[:40]}' no es un tipo de slot valido. "
                "Esperado uno de: " + " | ".join(TIPOS_SLOT)
            )
        return valor

    @field_validator("fuente")
    @classmethod
    def _fuente_conocida(cls, valor: str) -> str:
        if valor not in FUENTES_SLOT:
            raise ValueError(
                f"'{valor[:40]}' no es una fuente valida. "
                "Esperado uno de: " + " | ".join(FUENTES_SLOT)
            )
        return valor

    @model_validator(mode="after")
    def _coherencia_fuente_origen(self) -> "SlotGaleria":
        # Una imagen producida sin origen es una imagen sin responsable.
        if self.archivo is not None and not self.archivo.strip():
            raise ValueError("slot con 'archivo' vacio; omitir la clave o poner la ruta.")
        if self.archivo:
            _exigir_origen(self.origen)

        if self.origen:
            afirma_foto = _PATRON_AFIRMA_FOTO.search(self.origen) is not None
            afirma_ia = _PATRON_AFIRMA_IA.search(self.origen) is not None

            # Una recreacion jamas puede presentarse como fotografia.
            if self.fuente in _FUENTES_IA and afirma_foto:
                raise ValueError(
                    f"el slot '{self.tipo}' se produjo con '{self.fuente}' (la genero una IA) "
                    f"pero su origen dice '{self.origen[:40]}', que afirma que es una foto real. "
                    "Esperado: generado_ia, generado_ia_sin_verificar o confirmado_por_angie."
                )
            # Y una foto real no se marca como generada.
            if self.fuente == "foto_real" and afirma_ia:
                raise ValueError(
                    f"el slot '{self.tipo}' dice ser foto_real pero su origen "
                    f"'{self.origen[:40]}' afirma que la genero una IA. "
                    "Esperado: cambiar la fuente, o declarar un origen de material real."
                )

        # Regla 6: las imagenes de IA se reconocen por el nombre del archivo.
        if self.fuente in _FUENTES_IA and self.archivo and "_IA" not in self.archivo:
            raise ValueError(
                f"'{self.archivo[:60]}' es una imagen generada por IA y su nombre no lleva "
                "el sufijo _IA (regla 6: siempre debe poder reconocerse a simple vista)."
            )
        return self

    def necesita_base(self) -> bool:
        """Si es True, esta imagen debe declarar de que foto real salio."""
        return self.fuente in _FUENTES_QUE_EXIGEN_BASE


class PlanGaleria(ModeloBase):
    """Plan de la galeria de un producto: los slots, y cual es la foto base.

    'imagen_base' es la foto canonica del producto. Sirve para dos cosas:
    que todas las piezas generadas se vean como la MISMA maquina, y que
    ninguna imagen del producto pueda nacer sin una foto real detras.
    """

    imagen_base: Optional[str] = None
    imagen_base_origen: Optional[str] = None
    slots: Optional[list[SlotGaleria]] = None

    def hay_slots(self) -> bool:
        return bool(self.slots)

    @model_validator(mode="after")
    def _reglas_del_plan(self) -> "PlanGaleria":
        if self.imagen_base:
            _exigir_origen(self.imagen_base_origen)

        sin_ancla = [
            s.tipo for s in (self.slots or [])
            if s.necesita_base() and not (s.deriva_de or self.imagen_base)
        ]
        if sin_ancla:
            raise ValueError(
                "estos slots se producen a partir de una imagen pero no declaran cual: "
                + ", ".join(sin_ancla)
                + ". Esperado: 'deriva_de' en el slot, o 'imagen_base' en el plan. "
                "Ninguna imagen del producto puede nacer sin una foto real detras."
            )
        return self


class Multimedia(ModeloBase):
    """Imagenes, briefs y video."""

    # Tolerancia: opcional porque NBC250 (v1.3) usa otra estructura
    # (galeria_final); su ausencia se reporta como advertencia, y la
    # estructura vieja como clave extra.
    imagenes_galeria_confirmadas: Optional[list[ImagenGaleria]] = None
    imagenes_nota: Optional[str] = None
    briefs_generacion_ia: Optional[list] = None
    regla_generacion: Optional[str] = None
    formato_destino: Optional[str] = None
    video_youtube: Optional[str] = None
    video_nota: Optional[str] = None
    # Datos de las tomas generadas (callouts y dimensiones). Opcional: si el
    # Investigador no los trae, esas tomas simplemente no se generan.
    galeria_tomas: Optional[GaleriaTomas] = None
    # Plan de la galeria: QUE slots lleva el producto, de que foto sale cada
    # uno y quien responde por el. No se superpone con galeria_tomas:
    # plan_galeria dice QUE se arma, galeria_tomas trae los DATOS con que se
    # dibujan las piezas generadas (labels, puntos, medidas).
    plan_galeria: Optional[PlanGaleria] = None


class Seo(ModeloBase):
    """Metadatos para buscadores."""

    meta_titulo: Optional[str] = None
    meta_descripcion: Optional[str] = None
    palabras_clave: Optional[list] = None
    texto_alt_base: Optional[str] = None
    origen: str

    _v_origen = field_validator("origen")(_exigir_origen)


class FichaEkipon(ModeloBase):
    """Ficha completa segun el contrato v1.4.

    Las claves de nivel superior que no esten aqui NO se rechazan (las fichas
    reales agregan fecha_revision, _comentario, etc.), pero validar_ficha.py
    las reporta como advertencias para que el drift quede visible.
    """

    version_ficha: Optional[str] = Field(None, alias="_version_ficha")
    uso: Optional[str] = Field(None, alias="_uso")
    modo_entrada: Optional[str] = None
    entrada_original: EntradaOriginal
    fecha_investigacion: Optional[str] = None
    estado: str = Field(min_length=1)
    identificacion_del_producto: IdentificacionDelProducto
    producto: Producto
    precios: Precios
    descripcion_principal: Optional[str] = None
    descripcion_origen: Optional[str] = None
    descripcion_banner: Optional[str] = None
    descripcion_banner_origen: Optional[str] = None
    caracteristicas: Optional[list] = None
    caracteristicas_origen: Optional[str] = None
    ficha_tecnica: FichaTecnica
    criterio_verificacion_visual: Optional[CriterioVerificacionVisual] = None
    multimedia: Multimedia
    seo: Seo
    campos_por_confirmar: Optional[list] = None
    fuentes_consultadas: Optional[list] = None

    @model_validator(mode="after")
    def _contenido_con_origen(self) -> "FichaEkipon":
        # Regla de origen aplicada en pareja: si hay contenido, su campo
        # *_origen debe declarar un origen permitido. Si el contenido esta
        # vacio (como en la plantilla), no se exige nada.
        # Cada tupla es (campo, campo_origen, contenido, origen): si hay
        # contenido, su campo_origen debe declarar un origen permitido.
        # Una sola regla para los tres pares.
        pares = [
            ("descripcion_principal", "descripcion_origen",
             self.descripcion_principal, self.descripcion_origen),
            ("descripcion_banner", "descripcion_banner_origen",
             self.descripcion_banner, self.descripcion_banner_origen),
            ("caracteristicas", "caracteristicas_origen",
             self.caracteristicas, self.caracteristicas_origen),
        ]
        problemas = []
        for campo, campo_origen, contenido, origen in pares:
            hay_contenido = contenido.strip() if isinstance(contenido, str) else contenido
            if hay_contenido and not tiene_origen_permitido(origen):
                problemas.append(
                    f"{campo} tiene contenido pero {campo_origen} "
                    "no declara un origen permitido"
                )
        if problemas:
            raise ValueError("; ".join(problemas) + ". " + _ESPERADO_ORIGEN)
        return self


def claves_conocidas(modelo: type[BaseModel]) -> set[str]:
    """Claves JSON que un modelo reconoce: el nombre del campo Y su alias,
    porque populate_by_name=True acepta ambas formas al validar."""
    return {
        clave
        for nombre, campo in modelo.model_fields.items()
        for clave in (nombre, campo.alias or nombre)
    }


# Secciones cuyo interior se revisa en busca de claves desconocidas.
# ficha_tecnica queda fuera a proposito: sus claves tecnicas son libres.
MODELOS_POR_SECCION: dict[str, type[BaseModel]] = {
    "entrada_original": EntradaOriginal,
    "identificacion_del_producto": IdentificacionDelProducto,
    "producto": Producto,
    "precios": Precios,
    "criterio_verificacion_visual": CriterioVerificacionVisual,
    "multimedia": Multimedia,
    "seo": Seo,
}
