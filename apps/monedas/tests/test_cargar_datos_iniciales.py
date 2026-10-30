import os
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.cajas.models import (
    Caja,
    DenominacionBillete,
    InventarioBilleteCaja,
    SaldoCaja,
    Sucursal,
)
from apps.clientes.models import Cliente
from apps.comisiones.models import ComisionCategoria
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


DATOS_PRODUCCION = {
    "INITIAL_USD_PYG_BUY_RATE": "7100.00",
    "INITIAL_USD_PYG_SELL_RATE": "7200.00",
    "INITIAL_COMMISSION_MINORISTA": "2.50",
    "INITIAL_COMMISSION_CORPORATIVO": "2.00",
    "INITIAL_COMMISSION_VIP": "1.50",
}


class CargarDatosInicialesTests(TestCase):
    def test_perfil_demo_es_completo_e_idempotente(self):
        call_command("cargar_datos_iniciales", profile="demo")

        self.assertEqual(Moneda.objects.count(), 7)
        self.assertEqual(TasaCambio.objects.filter(activo=True).count(), 6)
        self.assertEqual(ComisionCategoria.objects.count(), 3)
        self.assertEqual(Group.objects.filter(
            name__in=("administrador", "analista_cambiario", "usuario_cliente", "cajero")
        ).count(), 4)
        self.assertEqual(Cliente.objects.count(), 3)
        self.assertEqual(Sucursal.objects.count(), 1)
        self.assertEqual(Caja.objects.count(), 1)
        self.assertEqual(SaldoCaja.objects.count(), 2)
        self.assertEqual(DenominacionBillete.objects.count(), 11)
        self.assertEqual(InventarioBilleteCaja.objects.count(), 11)
        self.assertFalse(InventarioBilleteCaja.objects.exclude(cantidad=0).exists())
        self.assertFalse(SaldoCaja.objects.exclude(saldo=Decimal("0.00")).exists())

        tasa = TasaCambio.objects.get(
            moneda_origen__codigo="USD",
            moneda_destino__codigo="PYG",
            activo=True,
        )
        tasa.tasa_compra = Decimal("7000.00")
        tasa.save(update_fields=["tasa_compra"])
        comision = ComisionCategoria.objects.get(categoria="VIP")
        comision.porcentaje = Decimal("1.25")
        comision.save(update_fields=["porcentaje"])

        call_command("cargar_datos_iniciales", profile="demo")

        self.assertEqual(Moneda.objects.count(), 7)
        self.assertEqual(TasaCambio.objects.count(), 6)
        self.assertEqual(Cliente.objects.count(), 3)
        self.assertEqual(Caja.objects.count(), 1)
        tasa.refresh_from_db()
        comision.refresh_from_db()
        self.assertEqual(tasa.tasa_compra, Decimal("7000.00"))
        self.assertEqual(comision.porcentaje, Decimal("1.25"))

    def test_perfil_minimal_solo_carga_catalogos_de_produccion(self):
        with patch.dict(os.environ, DATOS_PRODUCCION):
            call_command("cargar_datos_iniciales", profile="minimal")
            call_command("cargar_datos_iniciales", profile="minimal")

        self.assertEqual(
            set(Moneda.objects.values_list("codigo", flat=True)),
            {"USD", "PYG"},
        )
        self.assertEqual(TasaCambio.objects.count(), 1)
        self.assertEqual(ComisionCategoria.objects.count(), 3)
        self.assertEqual(Group.objects.filter(
            name__in=("administrador", "analista_cambiario", "usuario_cliente", "cajero")
        ).count(), 4)
        self.assertFalse(Cliente.objects.exists())
        # La migración de cajas crea la sucursal/caja única del sistema;
        # el perfil minimal no agrega clientes ni inventario demo.
        self.assertEqual(Sucursal.objects.count(), 1)
        self.assertEqual(Caja.objects.count(), 1)
        self.assertFalse(SaldoCaja.objects.exists())
        self.assertFalse(InventarioBilleteCaja.objects.exists())

    def test_perfil_minimal_exige_valores_financieros_sin_cargar_datos_parciales(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesMessage(CommandError, "INITIAL_COMMISSION_MINORISTA"):
                call_command("cargar_datos_iniciales", profile="minimal")

        self.assertFalse(Moneda.objects.exists())
        self.assertFalse(ComisionCategoria.objects.exists())
        self.assertFalse(TasaCambio.objects.exists())
