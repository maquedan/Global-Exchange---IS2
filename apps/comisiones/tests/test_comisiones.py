from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.comisiones.models import ComisionCategoria


class ConfiguracionComisionesTests(TestCase):
    """Pruebas de GEG9-35 - RF052 — Configuración de Comisiones por Categoría."""

    def crear_usuario_con_rol(self, username, rol):
        """Crea un usuario de prueba con el rol indicado."""
        usuario = get_user_model().objects.create_user(
            username=username,
            password="ClaveDePrueba123!",
        )
        grupo, _ = Group.objects.get_or_create(name=rol)
        usuario.groups.add(grupo)
        return usuario

    def setUp(self):
        self.administrador = self.crear_usuario_con_rol(
            "admin-comisiones",
            "administrador",
        )
        self.analista = self.crear_usuario_con_rol(
            "analista-comisiones",
            "analista_cambiario",
        )

    def test_administrador_puede_ver_comisiones(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(reverse("comisiones:lista"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Comisiones por categoría")

    def test_usuario_no_administrador_no_puede_gestionar_comisiones(self):
        self.client.force_login(self.analista)

        respuesta = self.client.get(reverse("comisiones:lista"))

        self.assertEqual(respuesta.status_code, 403)

    def test_administrador_puede_configurar_comision(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("comisiones:crear"),
            {
                "categoria": Cliente.Categoria.MINORISTA,
                "porcentaje": "3.00",
            },
        )

        self.assertRedirects(respuesta, reverse("comisiones:lista"))
        comision = ComisionCategoria.objects.get(
            categoria=Cliente.Categoria.MINORISTA,
        )
        self.assertEqual(comision.porcentaje, Decimal("3.00"))

    def test_no_permite_dos_comisiones_para_la_misma_categoria(self):
        ComisionCategoria.objects.create(
            categoria=Cliente.Categoria.MINORISTA,
            porcentaje=Decimal("3.00"),
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("comisiones:crear"),
            {
                "categoria": Cliente.Categoria.MINORISTA,
                "porcentaje": "2.50",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(ComisionCategoria.objects.count(), 1)
        self.assertIn("categoria", respuesta.context["formulario"].errors)

    def test_no_permite_porcentaje_mayor_a_cien(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("comisiones:crear"),
            {
                "categoria": Cliente.Categoria.VIP,
                "porcentaje": "100.01",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(ComisionCategoria.objects.count(), 0)
        self.assertIn("porcentaje", respuesta.context["formulario"].errors)

    def test_administrador_puede_actualizar_porcentaje(self):
        comision = ComisionCategoria.objects.create(
            categoria=Cliente.Categoria.CORPORATIVO,
            porcentaje=Decimal("2.00"),
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("comisiones:editar", args=[comision.pk]),
            {
                "categoria": Cliente.Categoria.VIP,
                "porcentaje": "1.50",
            },
        )

        self.assertRedirects(respuesta, reverse("comisiones:lista"))
        comision.refresh_from_db()
        self.assertEqual(comision.categoria, Cliente.Categoria.CORPORATIVO)
        self.assertEqual(comision.porcentaje, Decimal("1.50"))