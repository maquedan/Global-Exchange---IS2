from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.clientes.models import AsociacionUsuarioCliente, Cliente


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

    def test_registra_cliente_con_categoria(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("clientes:crear"),
            {
                "tipo": Cliente.Tipo.FISICA,
                "categoria": Cliente.Categoria.VIP,
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
        self.assertEqual(cliente.categoria, Cliente.Categoria.VIP)

    def test_administrador_puede_editar_cliente(self):
        cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            categoria=Cliente.Categoria.MINORISTA,
            nombres="Luis",
            apellidos="Pérez",
            documento="1010101",
            email="luis@example.com",
            telefono="098765432",
            direccion="Asunción",
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("clientes:editar", args=[cliente.pk]),
            {
                "tipo": Cliente.Tipo.FISICA,
                "categoria": Cliente.Categoria.CORPORATIVO,
                "nombres": "Luis",
                "apellidos": "Pérez",
                "documento": "1010101",
                "email": "luis.nuevo@example.com",
                "telefono": "098765432",
                "direccion": "Asunción",
            },
        )

        self.assertRedirects(respuesta, reverse("clientes:lista"))
        cliente.refresh_from_db()
        self.assertEqual(cliente.categoria, Cliente.Categoria.CORPORATIVO)
        self.assertEqual(cliente.email, "luis.nuevo@example.com")

    def test_administrador_puede_filtrar_clientes_por_criterios(self):
        Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            categoria=Cliente.Categoria.MINORISTA,
            nombres="Ana",
            apellidos="García",
            documento="1111111",
            email="ana@example.com",
            telefono="098111111",
            direccion="Asunción",
        )
        Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            categoria=Cliente.Categoria.VIP,
            nombres="Pedro",
            apellidos="Rojas",
            documento="2222222",
            email="pedro@example.com",
            telefono="098222222",
            direccion="Ciudad del Este",
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.get(
            reverse("clientes:lista"),
            {"categoria": Cliente.Categoria.VIP, "q": "Pedro"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Pedro")
        self.assertNotContains(respuesta, "Ana")
        self.assertEqual(len(respuesta.context["clientes"]), 1)

    def test_administrador_puede_asociar_usuario_a_varios_clientes(self):
        usuario = self.crear_usuario_con_rol("operador-prueba", "usuario_cliente")
        primer_cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="Ana",
            apellidos="García",
            documento="3333333",
            email="ana.garcia@example.com",
            telefono="098111111",
            direccion="Asunción",
        )
        segundo_cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.JURIDICA,
            razon_social="Empresa S.A.",
            ruc="80012345-7",
            email="empresa@example.com",
            telefono="021123456",
            direccion="Asunción",
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse("clientes:asociaciones"),
            {"usuario": usuario.pk, "clientes": [primer_cliente.pk, segundo_cliente.pk]},
        )

        self.assertRedirects(
            respuesta,
            f"{reverse('clientes:asociaciones')}?usuario={usuario.pk}",
        )
        self.assertSetEqual(
            set(
                AsociacionUsuarioCliente.objects.filter(usuario=usuario).values_list(
                    "cliente_id",
                    flat=True,
                ),
            ),
            {primer_cliente.pk, segundo_cliente.pk},
        )

    def test_actualizar_asociaciones_elimina_las_que_no_selecciona(self):
        usuario = self.crear_usuario_con_rol("operador-prueba", "usuario_cliente")
        primer_cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="Ana",
            apellidos="García",
            documento="4444444",
            email="ana.garcia@example.com",
            telefono="098111111",
            direccion="Asunción",
        )
        segundo_cliente = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="Pedro",
            apellidos="Rojas",
            documento="5555555",
            email="pedro.rojas@example.com",
            telefono="098222222",
            direccion="Asunción",
        )
        AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=primer_cliente)
        AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=segundo_cliente)
        self.client.force_login(self.administrador)

        self.client.post(
            reverse("clientes:asociaciones"),
            {"usuario": usuario.pk, "clientes": [segundo_cliente.pk]},
        )

        self.assertSetEqual(
            set(
                AsociacionUsuarioCliente.objects.filter(usuario=usuario).values_list(
                    "cliente_id",
                    flat=True,
                ),
            ),
            {segundo_cliente.pk},
        )

    def test_usuario_no_administrador_no_puede_gestionar_asociaciones(self):
        self.client.force_login(self.analista)

        respuesta = self.client.get(reverse("clientes:asociaciones"))

        self.assertEqual(respuesta.status_code, 403)

    def test_no_muestra_clientes_inactivos_para_asociar(self):
        cliente_inactivo = Cliente.objects.create(
            tipo=Cliente.Tipo.FISICA,
            nombres="Cliente",
            apellidos="Inactivo",
            documento="6666666",
            email="inactivo@example.com",
            telefono="098333333",
            direccion="Asunción",
            activo=False,
        )
        self.client.force_login(self.administrador)

        respuesta = self.client.get(reverse("clientes:asociaciones"))

        self.assertNotContains(respuesta, str(cliente_inactivo))
