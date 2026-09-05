from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.cuentas.models import CuentaPago


class CuentasPagoTests(TestCase):
    """Pruebas de RF020 — Registro de Cuentas y Billeteras (GEG9-30)."""

    def crear_usuario_con_rol(self, username, rol):
        usuario = get_user_model().objects.create_user(
            username=username,
            password="ClaveDePrueba123!",
        )
        grupo, _ = Group.objects.get_or_create(name=rol)
        usuario.groups.add(grupo)
        return usuario

    def setUp(self):
        # Un cliente-usuario con SU cliente asociado (el caso normal)
        self.usuario = self.crear_usuario_con_rol("carla", "usuario_cliente")
        self.cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="Carla", apellidos="Gómez",
            documento="1112223", email="carla@example.com",
            telefono="0981000000", direccion="Asunción",
        )
        AsociacionUsuarioCliente.objects.create(usuario=self.usuario, cliente=self.cliente)

        # Un administrador, para el test de permisos
        self.administrador = self.crear_usuario_con_rol("admin-prueba", "administrador")

    def crear_segundo_cliente(self):
        """Un usuario y cliente aparte, para probar que nadie ve lo ajeno."""
        usuario = self.crear_usuario_con_rol("bruno", "usuario_cliente")
        cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="Bruno", apellidos="Díaz",
            documento="9998887", email="bruno@example.com",
            telefono="0982000000", direccion="Luque",
        )
        AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)
        return usuario, cliente

    # ---------------------------------------------------------- permisos
    def test_usuario_sin_rol_cliente_no_accede(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(reverse("cuentas:lista"))

        self.assertEqual(respuesta.status_code, 403)

    # ---------------------------------------------------------- alcance
    def test_cliente_ve_sus_propias_cuentas(self):
        CuentaPago.objects.create(
            cliente=self.cliente, tipo=CuentaPago.Tipo.BANCARIA,
            entidad="Banco Itaú", numero_cuenta="123456", titular="Carla Gómez",
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("cuentas:lista"))

        self.assertContains(respuesta, "Banco Itaú")

    def test_no_ve_cuentas_de_otro_cliente(self):
        _, cliente_de_bruno = self.crear_segundo_cliente()
        CuentaPago.objects.create(
            cliente=cliente_de_bruno, tipo=CuentaPago.Tipo.BILLETERA,
            entidad="Tigo Money", numero_cuenta="0981555555", titular="Bruno Díaz",
        )
        self.client.force_login(self.usuario)  # entra Carla, no Bruno

        respuesta = self.client.get(reverse("cuentas:lista"))

        self.assertNotContains(respuesta, "Tigo Money")

    # ---------------------------------------------------------- creación
    def test_registra_cuenta_bancaria(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.post(reverse("cuentas:crear"), {
            "cliente": self.cliente.pk,
            "tipo": CuentaPago.Tipo.BANCARIA,
            "entidad": "Banco Itaú",
            "numero_cuenta": "123456",
            "titular": "Carla Gómez",
            "alias": "",
        })

        self.assertRedirects(respuesta, reverse("cuentas:lista"))
        self.assertEqual(CuentaPago.objects.count(), 1)

    def test_no_permite_elegir_cliente_ajeno(self):
        _, cliente_de_bruno = self.crear_segundo_cliente()
        self.client.force_login(self.usuario)  # Carla intenta usar el cliente de Bruno

        respuesta = self.client.post(reverse("cuentas:crear"), {
            "cliente": cliente_de_bruno.pk,
            "tipo": CuentaPago.Tipo.BANCARIA,
            "entidad": "Banco Itaú",
            "numero_cuenta": "123456",
            "titular": "Carla Gómez",
        })

        self.assertEqual(respuesta.status_code, 200)  # no redirige: hay error
        self.assertEqual(CuentaPago.objects.count(), 0)
        self.assertIn("cliente", respuesta.context["formulario"].errors)

    def test_no_permite_cuenta_duplicada(self):
        CuentaPago.objects.create(
            cliente=self.cliente, tipo=CuentaPago.Tipo.BANCARIA,
            entidad="Banco Itaú", numero_cuenta="123456", titular="Carla Gómez",
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.post(reverse("cuentas:crear"), {
            "cliente": self.cliente.pk,
            "tipo": CuentaPago.Tipo.BANCARIA,
            "entidad": "Banco Itaú",
            "numero_cuenta": "123456",
            "titular": "Carla Gómez",
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(CuentaPago.objects.count(), 1)  # sigue habiendo 1, no 2

    # ------------------------------------------------ editar y eliminar
    def test_edita_cuenta_propia(self):
        cuenta = CuentaPago.objects.create(
            cliente=self.cliente, tipo=CuentaPago.Tipo.BANCARIA,
            entidad="Banco Itaú", numero_cuenta="123456", titular="Carla Gómez",
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.post(reverse("cuentas:editar", args=[cuenta.pk]), {
            "cliente": self.cliente.pk,
            "tipo": CuentaPago.Tipo.BANCARIA,
            "entidad": "Banco Itaú",
            "numero_cuenta": "999999",  # cambiamos el número
            "titular": "Carla Gómez",
        })

        self.assertRedirects(respuesta, reverse("cuentas:lista"))
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.numero_cuenta, "999999")

    def test_no_puede_editar_cuenta_ajena(self):
        _, cliente_de_bruno = self.crear_segundo_cliente()
        cuenta_de_bruno = CuentaPago.objects.create(
            cliente=cliente_de_bruno, tipo=CuentaPago.Tipo.BILLETERA,
            entidad="Tigo Money", numero_cuenta="0981555555", titular="Bruno Díaz",
        )
        self.client.force_login(self.usuario)  # Carla intenta tocar la cuenta de Bruno

        respuesta = self.client.get(reverse("cuentas:editar", args=[cuenta_de_bruno.pk]))

        self.assertEqual(respuesta.status_code, 404)

    def test_elimina_cuenta_es_baja_logica(self):
        cuenta = CuentaPago.objects.create(
            cliente=self.cliente, tipo=CuentaPago.Tipo.BANCARIA,
            entidad="Banco Itaú", numero_cuenta="123456", titular="Carla Gómez",
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.post(reverse("cuentas:eliminar", args=[cuenta.pk]))

        self.assertRedirects(respuesta, reverse("cuentas:lista"))
        cuenta.refresh_from_db()
        self.assertFalse(cuenta.activa)                  # se desactivó...
        self.assertEqual(CuentaPago.objects.count(), 1)   # ...pero la fila sigue existiendo

    # ------------------------------------------- regla de negocio sola
    def test_no_registra_cuenta_para_cliente_inactivo(self):
        self.cliente.desactivar()
        cuenta = CuentaPago(
            cliente=self.cliente, tipo=CuentaPago.Tipo.BANCARIA,
            entidad="Banco Itaú", numero_cuenta="123456", titular="Carla Gómez",
        )

        with self.assertRaises(ValidationError):
            cuenta.full_clean()
