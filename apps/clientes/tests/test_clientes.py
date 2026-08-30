from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import Cliente


class RegistroClientesTests(TestCase):
    """Pruebas de RF001 — Registro de Clientes (GEG9-11)."""

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
            "admin-prueba",
            "administrador",
        )
        self.analista = self.crear_usuario_con_rol(
            "analista-prueba",
            "analista_cambiario",
        )

    def test_administrador_puede_ver_formulario_de_registro(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(reverse("clientes:crear"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Registrar cliente")

    def test_usuario_no_administrador_no_puede_registrar_clientes(self):
        self.client.force_login(self.analista)

        respuesta = self.client.get(reverse("clientes:crear"))

        self.assertEqual(respuesta.status_code, 403)

    def test_registra_persona_fisica(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("clientes:crear"),
            {
                "tipo": Cliente.Tipo.FISICA,
                "nombres": "Ana",
                "apellidos": "Gómez",
                "documento": "1234567",
                "email": "ana@example.com",
                "telefono": "0981123456",
                "direccion": "Asunción",
            },
        )

        self.assertRedirects(respuesta, reverse("clientes:lista"))
        cliente = Cliente.objects.get(documento="1234567")
        self.assertEqual(cliente.nombres, "Ana")
        self.assertIsNone(cliente.ruc)

    def test_registra_persona_juridica(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("clientes:crear"),
            {
                "tipo": Cliente.Tipo.JURIDICA,
                "razon_social": "Global S.A.",
                "ruc": "80012345-6",
                "email": "contacto@global.com",
                "telefono": "021123456",
                "direccion": "Asunción",
            },
        )

        self.assertRedirects(respuesta, reverse("clientes:lista"))
        cliente = Cliente.objects.get(ruc="80012345-6")
        self.assertEqual(cliente.razon_social, "Global S.A.")
        self.assertIsNone(cliente.documento)

    def test_no_registra_persona_fisica_sin_documento(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("clientes:crear"),
            {
                "tipo": Cliente.Tipo.FISICA,
                "nombres": "Ana",
                "apellidos": "Gómez",
                "email": "ana@example.com",
                "telefono": "0981123456",
                "direccion": "Asunción",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertContains(respuesta, "El documento es obligatorio.")

    def test_no_permite_documento_duplicado(self):
        Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="Ana",
            apellidos="Gómez",
            documento="1234567",
            email="ana@example.com",
            telefono="0981123456",
            direccion="Asunción",
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("clientes:crear"),
            {
                "tipo": Cliente.Tipo.FISICA,
                "nombres": "Luis",
                "apellidos": "Pérez",
                "documento": "1234567",
                "email": "luis@example.com",
                "telefono": "0981765432",
                "direccion": "San Lorenzo",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertIn(
            "documento",
            respuesta.context["formulario"].errors,
        )

    def test_administrador_puede_ver_clientes_eliminados(self):
        cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="Pedro",
            apellidos="López",
            documento="7654321",
            email="pedro@example.com",
            telefono="097123456",
            direccion="Encarnación",
            activo=False,
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.get(reverse("clientes:eliminados"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Pedro López")
        self.assertContains(respuesta, "Activar")
        self.assertIn(cliente, respuesta.context["clientes"])

    def test_administrador_puede_activar_cliente_eliminado(self):
        cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="María",
            apellidos="Ramírez",
            documento="3322111",
            email="maria@example.com",
            telefono="098765432",
            direccion="Ciudad del Este",
            activo=False,
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(reverse("clientes:activar", args=[cliente.pk]))

        self.assertRedirects(respuesta, reverse("clientes:eliminados"))
        cliente.refresh_from_db()
        self.assertTrue(cliente.activo)