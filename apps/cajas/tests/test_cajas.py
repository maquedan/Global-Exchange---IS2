from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.cajas.forms import MovimientoCajaForm
from apps.cajas.models import (
    Caja,
    DenominacionBillete,
    DetalleMovimientoBillete,
    FondoCajero,
    InventarioBilleteCaja,
    InventarioBilleteCajero,
    MovimientoCaja,
    SaldoCaja,
    Sucursal,
)
from apps.monedas.models import Moneda
from apps.cajas.services import (
    MovimientoNoPermitido,
    denominacion_tiene_referencias,
    registrar_conteo_inventario,
    registrar_movimiento,
)


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
        self.centavo = DenominacionBillete.objects.create(
            moneda=self.moneda, valor=Decimal("0.01")
        )
        self.billete_10 = DenominacionBillete.objects.create(
            moneda=self.moneda, valor=Decimal("10.00")
        )
        self.sucursal = Sucursal.objects.create(
            nombre="Casa Central", direccion="Av. Principal 123"
        )
        self.caja = Caja.objects.create(sucursal=self.sucursal)

    def billetes(self, importe, denominacion=None):
        importe = Decimal(importe)
        denominacion = denominacion or self.centavo
        cantidad = int(importe / denominacion.valor)
        assert denominacion.valor * cantidad == importe
        return {denominacion.pk: cantidad}

    def ingresar_efectivo(self, importe="100.00", denominacion=None):
        return registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.INGRESO,
            moneda_id=self.moneda.pk,
            realizado_por=self.admin,
            billetes=self.billetes(importe, denominacion),
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
        for nombre in (
            "cajas:registrar_movimiento",
            "cajas:registrar_denominacion",
            "cajas:registrar_conteo",
        ):
            self.assertEqual(
                self.client.get(reverse(nombre, args=[self.sucursal.pk])).status_code,
                403,
            )

    def test_cada_operacion_de_caja_tiene_su_propia_pagina(self):
        self.client.force_login(self.admin)

        movimiento = self.client.get(
            reverse("cajas:registrar_movimiento", args=[self.sucursal.pk])
        )
        denominacion = self.client.get(
            reverse("cajas:registrar_denominacion", args=[self.sucursal.pk])
        )
        conteo = self.client.get(
            reverse("cajas:registrar_conteo", args=[self.sucursal.pk])
        )

        self.assertTemplateUsed(movimiento, "cajas/movimiento_formulario.html")
        self.assertTemplateUsed(denominacion, "cajas/denominacion_formulario.html")
        self.assertTemplateUsed(conteo, "cajas/conteo_formulario.html")
        self.assertNotContains(movimiento, 'name="conteo-moneda"')
        self.assertNotContains(denominacion, 'name="mov-tipo"')
        self.assertNotContains(conteo, 'name="denominacion-valor"')

    def test_formulario_registra_ingreso_de_efectivo(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("cajas:registrar_movimiento", args=[self.sucursal.pk]),
            {
                "mov-tipo": MovimientoCaja.Tipo.INGRESO,
                "mov-moneda": self.moneda.pk,
                "mov-importe": "999.99",
                "mov-nota": "Fondo inicial",
                f"mov-billete_{self.centavo.pk}": "12550",
            },
        )

        self.assertRedirects(
            respuesta, reverse("cajas:detalle", args=[self.sucursal.pk])
        )
        movimiento = MovimientoCaja.objects.get()
        self.assertEqual(movimiento.realizado_por, self.admin)
        self.assertEqual(movimiento.nota, "Fondo inicial")
        self.assertEqual(movimiento.importe, Decimal("125.50"))
        self.assertEqual(movimiento.saldo_caja_resultante, Decimal("125.50"))
        detalle = self.client.get(reverse("cajas:detalle", args=[self.sucursal.pk]))
        self.assertContains(detalle, "Importe")
        self.assertContains(detalle, "Registrar movimiento")
        self.assertContains(detalle, "Agregar denominación de billete")
        self.assertContains(detalle, "Reconciliar inventario")
        self.assertNotContains(detalle, 'id="form-movimiento"')

        formulario_movimiento = self.client.get(
            reverse("cajas:registrar_movimiento", args=[self.sucursal.pk])
        )
        self.assertNotIn("importe", formulario_movimiento.context["formulario"].fields)
        self.assertContains(formulario_movimiento, "Importe calculado")
        self.assertNotContains(formulario_movimiento, 'name="mov-importe"')
        self.assertContains(formulario_movimiento, 'data-valor-centavos="1"')

    def test_formulario_calcula_importe_desde_las_cantidades(self):
        formulario = MovimientoCajaForm(
            {
                "mov-tipo": MovimientoCaja.Tipo.INGRESO,
                "mov-moneda": self.moneda.pk,
                f"mov-billete_{self.centavo.pk}": "250",
                f"mov-billete_{self.billete_10.pk}": "3",
            },
            caja=self.caja,
            prefix="mov",
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data["importe_calculado"], Decimal("32.50"))

    def test_admin_configura_denominacion_de_billete(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("cajas:registrar_denominacion", args=[self.sucursal.pk]),
            {
                "denominacion-moneda": self.moneda.pk,
                "denominacion-valor": "50.00",
            },
        )

        self.assertRedirects(
            respuesta, reverse("cajas:detalle", args=[self.sucursal.pk])
        )
        self.assertTrue(
            DenominacionBillete.objects.filter(
                moneda=self.moneda, valor=Decimal("50.00")
            ).exists()
        )

    def test_admin_modifica_denominacion_sin_referencias(self):
        self.client.force_login(self.admin)
        url = reverse(
            "cajas:editar_denominacion",
            args=[self.sucursal.pk, self.billete_10.pk],
        )
        lista = self.client.get(
            reverse("cajas:registrar_denominacion", args=[self.sucursal.pk])
        )
        formulario = self.client.get(url)

        self.assertContains(lista, "Modificar")
        self.assertContains(lista, "Eliminar")
        self.assertTemplateUsed(formulario, "cajas/denominacion_editar.html")

        respuesta = self.client.post(
            url,
            {
                "denominacion-moneda": self.moneda.pk,
                "denominacion-valor": "20.00",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("cajas:registrar_denominacion", args=[self.sucursal.pk]),
        )
        self.billete_10.refresh_from_db()
        self.assertEqual(self.billete_10.valor, Decimal("20.00"))

    def test_admin_elimina_denominacion_sin_referencias(self):
        self.client.force_login(self.admin)
        url = reverse(
            "cajas:eliminar_denominacion",
            args=[self.sucursal.pk, self.billete_10.pk],
        )

        respuesta = self.client.post(url)

        self.assertRedirects(
            respuesta,
            reverse("cajas:registrar_denominacion", args=[self.sucursal.pk]),
        )
        self.assertFalse(DenominacionBillete.objects.filter(pk=self.billete_10.pk).exists())

    def test_denominacion_usada_no_se_puede_modificar_ni_eliminar(self):
        self.client.force_login(self.admin)
        self.ingresar_efectivo(denominacion=self.billete_10)
        self.assertTrue(denominacion_tiene_referencias(self.billete_10))
        lista = self.client.get(
            reverse("cajas:registrar_denominacion", args=[self.sucursal.pk])
        )
        self.assertContains(lista, "En uso; no se puede modificar ni eliminar")
        editar_url = reverse(
            "cajas:editar_denominacion",
            args=[self.sucursal.pk, self.billete_10.pk],
        )
        eliminar_url = reverse(
            "cajas:eliminar_denominacion",
            args=[self.sucursal.pk, self.billete_10.pk],
        )

        respuesta_editar = self.client.post(
            editar_url,
            {
                "denominacion-moneda": self.moneda.pk,
                "denominacion-valor": "20.00",
            },
        )
        respuesta_eliminar = self.client.post(eliminar_url, follow=True)

        self.assertEqual(respuesta_editar.status_code, 200)
        self.assertContains(respuesta_editar, "no se puede modificar")
        self.assertContains(respuesta_eliminar, "No se puede eliminar")
        self.assertTrue(
            DenominacionBillete.objects.filter(
                pk=self.billete_10.pk, valor=Decimal("10.00")
            ).exists()
        )

    def test_editar_denominacion_rechaza_valor_duplicado(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse(
                "cajas:editar_denominacion",
                args=[self.sucursal.pk, self.billete_10.pk],
            ),
            {
                "denominacion-moneda": self.moneda.pk,
                "denominacion-valor": "0.01",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.billete_10.refresh_from_db()
        self.assertEqual(self.billete_10.valor, Decimal("10.00"))

    def test_denominaciones_no_permiten_edicion_o_borrado_a_analistas(self):
        self.client.force_login(self.analista)

        editar = self.client.get(
            reverse(
                "cajas:editar_denominacion",
                args=[self.sucursal.pk, self.billete_10.pk],
            )
        )
        eliminar = self.client.post(
            reverse(
                "cajas:eliminar_denominacion",
                args=[self.sucursal.pk, self.billete_10.pk],
            )
        )

        self.assertEqual(editar.status_code, 403)
        self.assertEqual(eliminar.status_code, 403)
        self.assertTrue(DenominacionBillete.objects.filter(pk=self.billete_10.pk).exists())

    def test_solo_usuarios_con_rol_cajero_pueden_recibir_fondos(self):
        self.ingresar_efectivo()

        with self.assertRaises(MovimientoNoPermitido):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.ASIGNACION,
                moneda_id=self.moneda.pk,
                cajero_id=self.analista.pk,
                realizado_por=self.admin,
                billetes=self.billetes("10.00"),
            )

    def test_se_pueden_devolver_fondos_a_un_usuario_que_dejo_el_rol_cajero(self):
        self.ingresar_efectivo()
        registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.ASIGNACION,
            moneda_id=self.moneda.pk,
            cajero_id=self.cajero.pk,
            realizado_por=self.admin,
            billetes=self.billetes("20.00"),
        )
        self.cajero.groups.remove(Group.objects.get(name="cajero"))
        self.client.force_login(self.admin)

        formulario_movimiento = self.client.get(
            reverse("cajas:registrar_movimiento", args=[self.sucursal.pk])
        )
        self.assertIn(
            self.cajero.pk,
            formulario_movimiento.context["formulario"].fields["cajero"].queryset.values_list(
                "pk", flat=True
            ),
        )

        respuesta = self.client.post(
            reverse("cajas:registrar_movimiento", args=[self.sucursal.pk]),
            {
                "mov-tipo": MovimientoCaja.Tipo.DEVOLUCION,
                "mov-moneda": self.moneda.pk,
                "mov-cajero": self.cajero.pk,
                f"mov-billete_{self.centavo.pk}": "2000",
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
            cajero_id=self.cajero.pk,
            realizado_por=self.admin,
            billetes=self.billetes("40.00"),
        )
        registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.DEVOLUCION,
            moneda_id=self.moneda.pk,
            cajero_id=self.cajero.pk,
            realizado_por=self.admin,
            billetes=self.billetes("10.00"),
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
        self.assertEqual(
            InventarioBilleteCaja.objects.get(
                caja=self.caja, denominacion=self.centavo
            ).cantidad,
            7000,
        )
        self.assertEqual(
            InventarioBilleteCajero.objects.get(
                caja=self.caja, cajero=self.cajero, denominacion=self.centavo
            ).cantidad,
            3000,
        )
        self.assertEqual(DetalleMovimientoBillete.objects.count(), 3)

    def test_no_permite_asignar_mas_efectivo_que_el_disponible(self):
        with self.assertRaises(MovimientoNoPermitido):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.ASIGNACION,
                moneda_id=self.moneda.pk,
                cajero_id=self.cajero.pk,
                realizado_por=self.admin,
                billetes=self.billetes("1.00"),
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
                cajero_id=self.cajero.pk,
                realizado_por=self.admin,
                billetes=self.billetes("1.00"),
            )

        self.assertEqual(MovimientoCaja.objects.count(), 1)
        self.assertEqual(SaldoCaja.objects.get(caja=self.caja, moneda=self.moneda).saldo, Decimal("100.00"))

    def test_no_permite_retirar_efectivo_asignado_al_cajero(self):
        self.ingresar_efectivo()
        registrar_movimiento(
            caja_id=self.caja.pk,
            tipo=MovimientoCaja.Tipo.ASIGNACION,
            moneda_id=self.moneda.pk,
            cajero_id=self.cajero.pk,
            realizado_por=self.admin,
            billetes=self.billetes("70.00"),
        )

        with self.assertRaises(MovimientoNoPermitido):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.RETIRO,
                moneda_id=self.moneda.pk,
                realizado_por=self.admin,
                billetes=self.billetes("31.00"),
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

    def test_movimiento_requiere_billetes_para_calcular_importe(self):
        with self.assertRaises(ValidationError):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.INGRESO,
                moneda_id=self.moneda.pk,
                realizado_por=self.admin,
                billetes={},
            )

        self.assertFalse(MovimientoCaja.objects.exists())
        self.assertFalse(InventarioBilleteCaja.objects.exists())

    def test_movimiento_no_permite_retirar_denominaciones_inexistentes(self):
        self.ingresar_efectivo("20.00", self.billete_10)
        with self.assertRaises(MovimientoNoPermitido):
            registrar_movimiento(
                caja_id=self.caja.pk,
                tipo=MovimientoCaja.Tipo.RETIRO,
                moneda_id=self.moneda.pk,
                realizado_por=self.admin,
                billetes=self.billetes("10.00", self.centavo),
            )

        self.assertEqual(
            SaldoCaja.objects.get(caja=self.caja, moneda=self.moneda).saldo,
            Decimal("20.00"),
        )

    def test_conteo_inicial_reconcilia_saldo_existente_y_guarda_auditoria(self):
        SaldoCaja.objects.create(caja=self.caja, moneda=self.moneda, saldo="20.00")

        conteo = registrar_conteo_inventario(
            caja_id=self.caja.pk,
            moneda_id=self.moneda.pk,
            realizado_por=self.admin,
            billetes=self.billetes("20.00", self.billete_10),
        )

        self.assertEqual(conteo.importe_total, Decimal("20.00"))
        self.assertEqual(conteo.detalle_billetes.get().cantidad, 2)
        self.assertEqual(
            InventarioBilleteCaja.objects.get(
                caja=self.caja, denominacion=self.billete_10
            ).cantidad,
            2,
        )
