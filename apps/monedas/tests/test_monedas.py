from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


class AdministracionMonedasTests(TestCase):
    """Pruebas de GEG9-26 — RF014 — Administración de Monedas."""

    def crear_usuario_con_rol(self, username, rol):
        usuario = get_user_model().objects.create_user(
            username=username,
            password="ClaveDePrueba123!",
        )
        grupo, _ = Group.objects.get_or_create(name=rol)
        usuario.groups.add(grupo)
        return usuario

    def setUp(self):
        self.administrador = self.crear_usuario_con_rol(
            "admin-monedas",
            "administrador",
        )
        self.analista = self.crear_usuario_con_rol(
            "analista-monedas",
            "analista_cambiario",
        )

    def test_administrador_puede_registrar_moneda(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("monedas:crear"),
            {
                "codigo": "usd",
                "nombre": "Dólar estadounidense",
                "simbolo": "$",
            },
        )

        self.assertRedirects(respuesta, reverse("monedas:lista"))
        moneda = Moneda.objects.get(codigo="USD")
        self.assertEqual(moneda.nombre, "Dólar estadounidense")
        self.assertTrue(moneda.activo)

    def test_no_permite_codigo_de_moneda_duplicado(self):
        Moneda.objects.create(
            codigo="USD",
            nombre="Dólar estadounidense",
            simbolo="$",
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("monedas:crear"),
            {
                "codigo": "USD",
                "nombre": "Otro dólar",
                "simbolo": "$",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Moneda.objects.count(), 1)
        self.assertIn("codigo", respuesta.context["formulario"].errors)

    def test_no_permite_codigo_fuera_del_formato_iso(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("monedas:crear"),
            {
                "codigo": "US",
                "nombre": "Dólar estadounidense",
                "simbolo": "$",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Moneda.objects.count(), 0)
        self.assertIn("codigo", respuesta.context["formulario"].errors)

    def test_usuario_no_administrador_no_puede_gestionar_monedas(self):
        self.client.force_login(self.analista)

        respuesta = self.client.get(reverse("monedas:lista"))

        self.assertEqual(respuesta.status_code, 403)

    def test_administrador_puede_modificar_moneda(self):
        moneda = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar americano",
            simbolo="US$",
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("monedas:editar", args=[moneda.pk]),
            {
                "codigo": "USD",
                "nombre": "Dólar estadounidense",
                "simbolo": "$",
            },
        )

        self.assertRedirects(respuesta, reverse("monedas:lista"))
        moneda.refresh_from_db()
        self.assertEqual(moneda.nombre, "Dólar estadounidense")
        self.assertEqual(moneda.simbolo, "$")

    def test_administrador_puede_desactivar_y_reactivar_moneda(self):
        moneda = Moneda.objects.create(
            codigo="EUR",
            nombre="Euro",
            simbolo="€",
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("monedas:desactivar", args=[moneda.pk]),
        )

        self.assertRedirects(respuesta, reverse("monedas:lista"))
        moneda.refresh_from_db()
        self.assertFalse(moneda.activo)

        respuesta = self.client.post(
            reverse("monedas:activar", args=[moneda.pk]),
        )

        self.assertRedirects(respuesta, reverse("monedas:inactivas"))
        moneda.refresh_from_db()
        self.assertTrue(moneda.activo)

    def test_no_puede_desactivar_moneda_con_tasa_activa(self):
        moneda_origen = Moneda.objects.create(
            codigo="USD",
            nombre="Dólar estadounidense",
            simbolo="$",
        )
        moneda_destino = Moneda.objects.create(
            codigo="EUR",
            nombre="Euro",
            simbolo="€",
        )
        TasaCambio.objects.create(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
            tasa_compra="7.10",
            tasa_venta="7.20",
            vigente_desde=timezone.now(),
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("monedas:desactivar", args=[moneda_origen.pk]),
            follow=True,
        )

        self.assertEqual(
            respuesta.redirect_chain,
            [(reverse("monedas:lista"), 302)],
        )
        moneda_origen.refresh_from_db()
        moneda_destino.refresh_from_db()
        self.assertTrue(moneda_origen.activo)
        self.assertTrue(moneda_destino.activo)
        self.assertContains(
            respuesta,
            "No se puede desactivar una moneda con tasas de cambio activas.",
        )