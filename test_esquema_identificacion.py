"""Pruebas del modelo de dos caminos en el contrato de la ficha.

El Investigador tiene dos caminos de entrada (link preferido, nombre+foto de
respaldo). Eso agrego dos casillas al contrato, y aqui se verifica que sean
datos de PRIMERA CLASE, no huerfanos:

1. `entrada_original.link_producto` existe y es opcional (respaldo sin link).
2. `identificacion_del_producto.origen_identificacion` acepta solo la lista
   cerrada link | busqueda_imagen | inferencia (y None por tolerancia).
3. Ambas casillas son "conocidas" para el detector de drift (validar_ficha),
   asi que no se reportan como clave desconocida.
"""

import unittest

from pydantic import ValidationError

from esquema_ficha import (
    EntradaOriginal,
    IdentificacionDelProducto,
    claves_conocidas,
)


class PruebasLinkProducto(unittest.TestCase):
    """El link es el camino preferido, pero opcional (hay respaldo sin link)."""

    def test_entrada_acepta_link(self):
        e = EntradaOriginal.model_validate({
            "nombre_dado": "Molino de martillos",
            "link_producto": "https://importador.example/producto/400",
        })
        self.assertEqual(e.link_producto, "https://importador.example/producto/400")

    def test_entrada_sin_link_es_valida(self):
        # Camino de respaldo: solo nombre + foto, sin link.
        e = EntradaOriginal.model_validate({"nombre_dado": "Molino"})
        self.assertIsNone(e.link_producto)


class PruebasOrigenIdentificacion(unittest.TestCase):
    """La etiqueta de metodo dice cuanto confiar en la ficha."""

    def _identificacion(self, **extra):
        base = {"resultado": "IDENTIFICADO"}
        base.update(extra)
        return base

    def test_acepta_los_tres_metodos(self):
        for metodo in ("link", "busqueda_imagen", "inferencia"):
            with self.subTest(metodo=metodo):
                i = IdentificacionDelProducto.model_validate(
                    self._identificacion(origen_identificacion=metodo)
                )
                self.assertEqual(i.origen_identificacion, metodo)

    def test_metodo_se_normaliza(self):
        # Tolerancia como el resto del contrato: espacios y mayusculas no
        # invalidan la ficha; se guarda el token canonico en minusculas.
        i = IdentificacionDelProducto.model_validate(
            self._identificacion(origen_identificacion="  Link ")
        )
        self.assertEqual(i.origen_identificacion, "link")

    def test_metodo_ausente_es_valido(self):
        # Tolerancia: las fichas v1.3/v1.4 previas no traen la etiqueta.
        i = IdentificacionDelProducto.model_validate(self._identificacion())
        self.assertIsNone(i.origen_identificacion)

    def test_metodo_desconocido_se_rechaza(self):
        with self.assertRaises(ValidationError) as ctx:
            IdentificacionDelProducto.model_validate(
                self._identificacion(origen_identificacion="adivinado")
            )
        self.assertIn("origen_identificacion", str(ctx.exception))


class PruebasNoSonHuerfanos(unittest.TestCase):
    """Las casillas nuevas son conocidas para el detector de drift."""

    def test_link_producto_es_conocido(self):
        self.assertIn("link_producto", claves_conocidas(EntradaOriginal))

    def test_origen_identificacion_es_conocido(self):
        self.assertIn(
            "origen_identificacion", claves_conocidas(IdentificacionDelProducto)
        )


if __name__ == "__main__":
    unittest.main()
