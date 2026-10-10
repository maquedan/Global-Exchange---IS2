from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.cajas.models import Caja, FondoCajero, MovimientoCaja, SaldoCaja, Sucursal
from apps.monedas.models import Moneda
from apps.cajas.services import MovimientoNoPermitido, registrar_movimiento


class GestionCajasTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(username="admin-cajas", password="test")
        self.analista = user_model.objects.create_user(username="analista-cajas", password="test")
        self.cajero = user_model.objects.create_user(username="cajero-cajas", password="test")
        Group.objects.get_or_create(name="administrador")[0].user_set.add(self.admin)
        Group.objects.get_or_create(name="analista_cambiario")[0].user_set.add(self.analista)
        Group.objects.get_or_create(name="cajero")[0].user_set.add(self.cajero)
        self.moneda = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$")
        self.sucursal = Sucursal.objects.create(
            nombre="Casa Central", direccion="Av. Principal 123"
        )
        self.caja = Caja.objects.create(sucursal=self.sucursal)

    def ingresar_efectivo(self, importe="100.00"):
        return registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.INGRESO,
            moneda_id=self.moneda.pk,
            importe=Decimal(importe),
            realizado_por=self.admin,
        )

    def test_admin_crea_sucursal_y_caja(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("cajas:crear_sucursal"),
            {"nombre": "Sucursal Norte", "direccion": "Calle 1", "activa": "on"},
        )

        self.assertRedirects(respuesta, reverse("cajas:lista"))
        sucursal = Sucursal.objects.get(nombre="Sucursal Norte")
        self.assertTrue(Caja.objects.filter(sucursal=sucursal).exists())

    def test_solo_administrador_puede_gestionar_cajas(self):
        self.client.force_login(self.analista)

        self.assertEqual(self.client.get(reverse("cajas:lista")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("cajas:registrar_movimiento", args=[self.sucursal.pk]),
                {},
            ).status_code,
            403,
        )

    def test_formulario_registra_ingreso_de_efectivo(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("cajas:registrar_movimiento", args=[self.sucursal.pk]),
            {
                "tipo": MovimientoCaja.Tipo.INGRESO,
                "moneda": self.moneda.pk,
                "importe": "125.50",
                "nota": "Fondo inicial",
            },
        )

        self.assertRedirects(
            respuesta, reverse("cajas:detalle", args=[self.sucursal.pk])
        )
        movimiento = MovimientoCaja.objects.get()
        self.assertEqual(movimiento.realizado_por, self.admin)
        self.assertEqual(movimiento.nota, "Fondo inicial")
        self.assertEqual(movimiento.saldo_caja_resultante, Decimal("125.50"))

    def test_solo_usuarios_con_rol_cajero_pueden_recibir_fondos(self):
        self.ingresar_efectivo()

        with self.assertRaises(MovimientoNoPermitido):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.ASIGNACION,
                moneda_id=self.moneda.pk,
                importe=Decimal("10.00"),
                cajero_id=self.analista.pk,
                realizado_por=self.admin,
            )

    def test_se_pueden_devolver_fondos_a_un_usuario_que_dejo_el_rol_cajero(self):
        self.ingresar_efectivo()
        registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.ASIGNACION,
            moneda_id=self.moneda.pk,
            importe=Decimal("20.00"),
            cajero_id=self.cajero.pk,
            realizado_por=self.admin,
        )
        self.cajero.groups.remove(Group.objects.get(name="cajero"))
        self.client.force_login(self.admin)

        detalle = self.client.get(reverse("cajas:detalle", args=[self.sucursal.pk]))
        self.assertIn(
            self.cajero.pk,
            detalle.context["formulario"].fields["cajero"].queryset.values_list(
                "pk", flat=True
            ),
        )

        respuesta = self.client.post(
            reverse("cajas:registrar_movimiento", args=[self.sucursal.pk]),
            {
                "tipo": MovimientoCaja.Tipo.DEVOLUCION,
                "moneda": self.moneda.pk,
                "cajero": self.cajero.pk,
                "importe": "20.00",
            },
        )
        self.assertRedirects(
            respuesta, reverse("cajas:detalle", args=[self.sucursal.pk])
        )

        self.assertEqual(
            FondoCajero.objects.get(
                caja=self.caja, cajero=self.cajero, moneda=self.moneda
            ).saldo,
            Decimal("0.00"),
        )

    def test_historial_pagina_movimientos_anteriores(self):
        for _ in range(51):
            self.ingresar_efectivo("0.01")
        self.client.force_login(self.admin)

        respuesta = self.client.get(
            reverse("cajas:detalle", args=[self.sucursal.pk]), {"page": 2}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["page_obj"].number, 2)
        self.assertEqual(len(respuesta.context["movimientos"]), 1)

    def test_ingreso_asignacion_y_devolucion_actualizan_saldos_e_historial(self):
        self.ingresar_efectivo()

        registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.ASIGNACION,
            moneda_id=self.moneda.pk,
            importe=Decimal("40.00"),
            cajero_id=self.cajero.pk,
            realizado_por=self.admin,
        )
        registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.DEVOLUCION,
            moneda_id=self.moneda.pk,
            importe=Decimal("10.00"),
            cajero_id=self.cajero.pk,
            realizado_por=self.admin,
        )

        self.assertEqual(SaldoCaja.objects.get(caja=self.caja, moneda=self.moneda).saldo, Decimal("70.00"))
        self.assertEqual(
            FondoCajero.objects.get(
                caja=self.caja, cajero=self.cajero, moneda=self.moneda
            ).saldo,
            Decimal("30.00"),
        )
        movimientos = list(MovimientoCaja.objects.order_by("pk"))
        self.assertEqual(len(movimientos), 3)
        self.assertEqual(
            [movimiento.saldo_caja_resultante for movimiento in movimientos],
            [Decimal("100.00"), Decimal("60.00"), Decimal("70.00")],
        )
        self.assertEqual(movimientos[1].saldo_cajero_resultante, Decimal("40.00"))
        self.assertEqual(movimientos[2].saldo_cajero_resultante, Decimal("30.00"))

    def test_no_permite_asignar_mas_efectivo_que_el_disponible(self):
        with self.assertRaises(MovimientoNoPermitido):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.ASIGNACION,
                moneda_id=self.moneda.pk,
                importe=Decimal("1.00"),
                cajero_id=self.cajero.pk,
                realizado_por=self.admin,
            )

        self.assertFalse(SaldoCaja.objects.exists())
        self.assertFalse(FondoCajero.objects.exists())
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_no_permite_devolver_mas_efectivo_que_el_asignado(self):
        self.ingresar_efectivo()

        with self.assertRaises(MovimientoNoPermitido):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.DEVOLUCION,
                moneda_id=self.moneda.pk,
                importe=Decimal("1.00"),
                cajero_id=self.cajero.pk,
                realizado_por=self.admin,
            )

        self.assertEqual(MovimientoCaja.objects.count(), 1)
        self.assertEqual(SaldoCaja.objects.get(caja=self.caja, moneda=self.moneda).saldo, Decimal("100.00"))

    def test_no_permite_retirar_efectivo_asignado_al_cajero(self):
        self.ingresar_efectivo()
        registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.ASIGNACION,
            moneda_id=self.moneda.pk,
            importe=Decimal("70.00"),
            cajero_id=self.cajero.pk,
            realizado_por=self.admin,
        )

        with self.assertRaises(MovimientoNoPermitido):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.RETIRO,
                moneda_id=self.moneda.pk,
                importe=Decimal("31.00"),
                realizado_por=self.admin,
            )

    def test_no_se_puede_desactivar_sucursal_con_fondos_pendientes(self):
        self.ingresar_efectivo()
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("cajas:editar_sucursal", args=[self.sucursal.pk]),
            {
                "nombre": self.sucursal.nombre,
                "direccion": self.sucursal.direccion,
                "activa": "",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("activa", respuesta.context["formulario"].errors)
        self.sucursal.refresh_from_db()
        self.assertTrue(self.sucursal.activa)
