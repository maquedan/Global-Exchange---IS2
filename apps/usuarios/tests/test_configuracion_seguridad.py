"""Pruebas de configuración dinámica de seguridad (RF036)."""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.models import CambioConfiguracionSeguridad, ConfiguracionSeguridad

Usuario = get_user_model()


def usuario_con_rol(nombre, rol):
    usuario = Usuario.objects.create_user(nombre)
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


@pytest.mark.django_db
def test_solo_administrador_accede_a_configuracion_de_seguridad(client):
    cliente = usuario_con_rol("cliente-rf036", "usuario_cliente")
    client.force_login(cliente)

    respuesta = client.get(reverse("usuarios:configuracion_seguridad"))

    assert respuesta.status_code == 302


@pytest.mark.django_db
def test_admin_actualiza_timeout_y_se_registra_el_cambio(client):
    admin = usuario_con_rol("admin-rf036", "administrador")
    ConfiguracionSeguridad.objects.create(pk=1, tiempo_inactividad_minutos=15)
    client.force_login(admin)

    respuesta = client.post(
        reverse("usuarios:configuracion_seguridad"),
        {"tiempo_inactividad_minutos": 30},
    )

    configuracion = ConfiguracionSeguridad.objects.get(pk=1)
    cambio = CambioConfiguracionSeguridad.objects.get()
    assert respuesta.status_code == 302
    assert configuracion.tiempo_inactividad_minutos == 30
    assert cambio.usuario == admin
    assert cambio.usuario_nombre == admin.username
    assert cambio.tiempo_inactividad_anterior_minutos == 15
    assert cambio.tiempo_inactividad_nuevo_minutos == 30
    assert cambio.creado_en <= timezone.now()


@pytest.mark.django_db
@pytest.mark.parametrize("minutos", [4, 481, "no-numérico"])
def test_rechaza_tiempos_fuera_del_rango_seguro(client, minutos):
    admin = usuario_con_rol("admin-rf036", "administrador")
    ConfiguracionSeguridad.objects.create(pk=1, tiempo_inactividad_minutos=15)
    client.force_login(admin)

    respuesta = client.post(
        reverse("usuarios:configuracion_seguridad"),
        {"tiempo_inactividad_minutos": minutos},
    )

    assert respuesta.status_code == 200
    assert ConfiguracionSeguridad.objects.get(pk=1).tiempo_inactividad_minutos == 15
    assert not CambioConfiguracionSeguridad.objects.exists()


@pytest.mark.django_db
def test_timeout_actualizado_se_aplica_a_sesiones_activas_sin_reinicio(client):
    admin = usuario_con_rol("admin-rf036", "administrador")
    ConfiguracionSeguridad.objects.create(pk=1, tiempo_inactividad_minutos=15)
    client.force_login(admin)
    client.post(
        reverse("usuarios:configuracion_seguridad"),
        {"tiempo_inactividad_minutos": 30},
    )

    respuesta = client.get(reverse("usuarios:panel"))

    assert respuesta.status_code == 200
    assert 'data-session-idle-timeout="1800"' in respuesta.content.decode()

