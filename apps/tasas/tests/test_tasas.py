"""Pruebas de RF016 — Visualización de Tasas en Tiempo Real (GEG9-28)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


class VisualizacionTasasTests(TestCase):
    def crear_usuario_con_rol(self, username, rol):
        usuario = get_user_model().objects.create_user(
            username=username,
            password="ClaveDePrueba123!",
        )
        grupo, _ = Group.objects.get_or_create(name=rol)
        usuario.groups.add(grupo)
        return usuario

    def setUp(self):
        self.usuario = self.crear_usuario_con_rol("carla", "usuario_cliente")
        self.usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$")
        self.pyg = Moneda.objects.create(codigo="PYG", nombre="Guaraní", simbolo="₲")
        self.eur = Moneda.objects.create(codigo="EUR", nombre="Euro", simbolo="€")

    def crear_tasa(self, compra, venta, vigente_desde, activo=True, origen=None, destino=None):
        return TasaCambio.objects.create(
            moneda_origen=origen or self.usd,
            moneda_destino=destino or self.pyg,
            tasa_compra=compra,
            tasa_venta=venta,
            vigente_desde=vigente_desde,
            activo=activo,
        )

    # --------------------------------------------------------------- acceso
    def test_exige_iniciar_sesion(self):
        respuesta = self.client.get(reverse("tasas:panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/oidc/authenticate/", respuesta["Location"])

    def test_cualquier_rol_autenticado_ve_el_panel(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("tasas:panel"))
        self.assertEqual(respuesta.status_code, 200)

    # -------------------------------------------------- selección de pares
    def test_sin_tasas_muestra_mensaje_vacio(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("tasas:panel"))

        self.assertContains(respuesta, "Todavía no hay tasas cargadas")

    def test_sin_parametros_usa_el_primer_par_disponible(self):
        """Si no viene ?origen=&destino= en la URL, no debe quedar vacío."""
        self.crear_tasa("7.10", "7.20", timezone.now())
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("tasas:panel"))

        self.assertContains(respuesta, "USD")
        self.assertContains(respuesta, "PYG")

    def test_selecciona_un_par_por_query_params(self):
        self.crear_tasa("7.10", "7.20", timezone.now())
        self.crear_tasa("1.05", "1.10", timezone.now(), origen=self.eur, destino=self.pyg)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("tasas:panel"), {"origen": "EUR", "destino": "PYG"})

        # El gráfico principal muestra el par elegido (EUR), no el otro.
        self.assertContains(respuesta, "Gráfico de EUR a PYG")
        self.assertContains(respuesta, "1.05")
        self.assertContains(respuesta, "1.10")
        # El par que NO se eligió puede seguir apareciendo en la grilla de
        # "Pares disponibles" (abajo) — eso es a propósito, no un error.

    def test_par_sin_datos_sugiere_los_disponibles(self):
        self.crear_tasa("7.10", "7.20", timezone.now())
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("tasas:panel"), {"origen": "EUR", "destino": "PYG"})

        self.assertContains(respuesta, "Pares con datos disponibles")
        self.assertContains(respuesta, "USD → PYG")

    # -------------------------------------------------------- estadísticas
    def test_calcula_variacion_maximo_minimo_y_promedio(self):
        self.crear_tasa("7.00", "7.10", timezone.now() - timezone.timedelta(days=10), activo=False)
        self.crear_tasa("7.20", "7.30", timezone.now())
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("tasas:panel"), {"origen": "USD", "destino": "PYG"})

        # subió de 7.00 a 7.20 -> +2.86%; máximo 7.20, mínimo 7.00
        self.assertContains(respuesta, "+2.86")
        self.assertContains(respuesta, "7.20")
        self.assertContains(respuesta, "7.00")

    def test_una_sola_tasa_no_muestra_grafico(self):
        self.crear_tasa("7.10", "7.20", timezone.now())
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("tasas:panel"), {"origen": "USD", "destino": "PYG"})

        self.assertContains(respuesta, "Todavía hay una sola tasa cargada")
        self.assertNotContains(respuesta, '<svg class="grafico-historial"')

    def test_grilla_muestra_todos_los_pares_sin_importar_cual_esta_elegido(self):
        self.crear_tasa("7.10", "7.20", timezone.now())
        self.crear_tasa("1.05", "1.10", timezone.now(), origen=self.eur, destino=self.pyg)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("tasas:panel"), {"origen": "EUR", "destino": "PYG"})

        self.assertContains(respuesta, "Pares disponibles")
        self.assertContains(respuesta, "EUR → PYG")
        self.assertContains(respuesta, "USD → PYG")

    # -------------------------------------------- endpoint del auto-refresco
    def test_endpoint_datos_exige_login(self):
        respuesta = self.client.get(reverse("tasas:datos_actuales"))
        self.assertEqual(respuesta.status_code, 302)

    def test_endpoint_datos_devuelve_solo_la_tasa_activa(self):
        self.crear_tasa("7.00", "7.10", timezone.now() - timezone.timedelta(days=5), activo=False)
        self.crear_tasa("7.10", "7.20", timezone.now())
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("tasas:datos_actuales"))
        cuerpo = respuesta.json()

        self.assertEqual(len(cuerpo["tasas"]), 1)
        self.assertEqual(cuerpo["tasas"][0]["par"], "USD/PYG")
        self.assertEqual(cuerpo["tasas"][0]["compra"], 7.10)
        self.assertEqual(cuerpo["tasas"][0]["venta"], 7.20)
