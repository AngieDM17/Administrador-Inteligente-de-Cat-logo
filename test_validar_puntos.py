"""Pruebas de la validacion de puntos contra la silueta del producto.

Es el control determinista que hace seguro el paso de vision: un modelo puede
ubicar mal una etiqueta, pero el canal alfa del recorte no opina — dice si hay
producto o no lo hay.
"""

import unittest

from PIL import Image

from validar_puntos import (
    filtrar_callouts,
    punto_sobre_producto,
)


def _recorte(lado: int = 200) -> Image.Image:
    """Recorte sintetico: cuadrado opaco centrado sobre fondo transparente.

    El producto ocupa del 25% al 75% del lienzo en ambos ejes.
    """
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    cuerpo = Image.new("RGBA", (lado // 2, lado // 2), (255, 78, 3, 255))
    img.paste(cuerpo, (lado // 4, lado // 4))
    return img


class PruebasPuntoSobreProducto(unittest.TestCase):
    def test_centro_del_producto_es_valido(self):
        self.assertTrue(punto_sobre_producto(_recorte(), [0.5, 0.5]))

    def test_esquina_transparente_se_rechaza(self):
        self.assertFalse(punto_sobre_producto(_recorte(), [0.02, 0.02]))

    def test_punto_lejos_del_producto_se_rechaza(self):
        self.assertFalse(punto_sobre_producto(_recorte(), [0.95, 0.95]))

    def test_filo_del_producto_se_acepta_por_tolerancia(self):
        # Justo afuera del borde izquierdo: una etiqueta apuntada al filo es
        # legitima y no debe rechazarse por 2 pixeles.
        self.assertTrue(punto_sobre_producto(_recorte(), [0.24, 0.5]))

    def test_parte_delgada_a_3_por_ciento_se_acepta(self):
        # El caso real del molino: 'Soporte robusto' y 'Puerto de descarga'
        # caian a 3,0% y 3,6% del producto — etiquetas CORRECTAS apuntadas a
        # una pata y a un puerto hundido. Con la tolerancia vieja (1,5%) se
        # descartaban por error.
        self.assertTrue(punto_sobre_producto(_recorte(), [0.22, 0.5]))

    def test_punto_a_20_por_ciento_sigue_rechazandose(self):
        # El limite del otro lado: lejos del producto se rechaza igual.
        self.assertFalse(punto_sobre_producto(_recorte(), [0.05, 0.5]))

    def test_parte_fina_no_se_escapa_entre_los_vecinos(self):
        # Una barra vertical de 2px: un anillo de 8 vecinos podria saltearla.
        # La ventana completa la encuentra.
        img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        img.paste(Image.new("RGBA", (2, 120), (255, 78, 3, 255)), (100, 40))
        self.assertTrue(punto_sobre_producto(img, [0.47, 0.5]))

    def test_punto_fuera_de_rango_se_rechaza(self):
        self.assertFalse(punto_sobre_producto(_recorte(), [1.5, 0.5]))
        self.assertFalse(punto_sobre_producto(_recorte(), [-0.1, 0.5]))

    def test_punto_vacio_o_incompleto_se_rechaza(self):
        self.assertFalse(punto_sobre_producto(_recorte(), None))
        self.assertFalse(punto_sobre_producto(_recorte(), []))
        self.assertFalse(punto_sobre_producto(_recorte(), [0.5]))

    def test_tolerancia_cero_es_estricta(self):
        # Sin tolerancia, el filo de afuera ya no pasa.
        self.assertFalse(punto_sobre_producto(_recorte(), [0.24, 0.5], tolerancia=0))


class PruebasFiltrarCallouts(unittest.TestCase):
    def test_separa_los_tres_grupos(self):
        r = filtrar_callouts(_recorte(), [
            {"label": "Motor", "point": [0.5, 0.5]},        # sobre el producto
            {"label": "Tolva", "point": [0.95, 0.95]},      # en el aire
            {"label": "Chasis"},                            # sin punto
        ])
        self.assertEqual([c["label"] for c in r["aceptados"]], ["Motor"])
        self.assertEqual([d["label"] for d in r["descartados"]], ["Tolva"])
        self.assertEqual(r["sin_punto"], ["Chasis"])

    def test_el_descartado_explica_el_motivo(self):
        r = filtrar_callouts(_recorte(), [{"label": "Tolva", "point": [0.95, 0.95]}])
        self.assertIn("no cae sobre el producto", r["descartados"][0]["motivo"])

    def test_callout_sin_label_se_ignora(self):
        r = filtrar_callouts(_recorte(), [{"label": "  ", "point": [0.5, 0.5]}])
        self.assertEqual(r["aceptados"], [])
        self.assertEqual(r["descartados"], [])
        self.assertEqual(r["sin_punto"], [])

    def test_lista_vacia_no_rompe(self):
        r = filtrar_callouts(_recorte(), [])
        self.assertEqual(r["aceptados"], [])

    def test_none_no_rompe(self):
        self.assertEqual(filtrar_callouts(_recorte(), None)["aceptados"], [])

    def test_no_muta_los_callouts_aceptados(self):
        original = {"label": "Motor", "point": [0.5, 0.5]}
        r = filtrar_callouts(_recorte(), [original])
        self.assertIs(r["aceptados"][0], original)


if __name__ == "__main__":
    unittest.main()
