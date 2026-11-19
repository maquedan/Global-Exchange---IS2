"""Pruebas de expiración de sesión por inactividad y cierre voluntario."""
import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.urls import reverse


@pytest.mark.django_db
def test_la_actividad_renueva_el_vencimiento_de_la_sesion(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="sesion-activa")
    client.force_login(usuario)
    session_key = client.session.session_key
    vence_inicialmente = Session.objects.get(session_key=session_key).expire_date

    respuesta = client.get(reverse("usuarios:panel"))

    vencimiento = Session.objects.get(session_key=session_key).expire_date
    assert respuesta.status_code == 200
    assert settings.SESSION_SAVE_EVERY_REQUEST
    assert vencimiento > vence_inicialmente


@pytest.mark.django_db
def test_una_sesion_vencida_exige_autenticarse_de_nuevo(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="sesion-vencida")
    client.force_login(usuario)
    sesion = client.session
    sesion.set_expiry(-1)
    sesion.save()

    respuesta = client.get(reverse("usuarios:panel"))

    assert respuesta.status_code == 302
    assert respuesta.url.startswith(settings.LOGIN_URL)
    assert client.session.get("_auth_user_id") is None


@pytest.mark.django_db
def test_cerrar_sesion_invalida_la_sesion_local_y_cierra_keycloak(
    client, django_user_model
):
    usuario = django_user_model.objects.create_user(username="sesion-cerrada")
    client.force_login(usuario)

    respuesta_logout = client.post(reverse("oidc_logout"))
    respuesta_panel = client.get(reverse("usuarios:panel"))

    assert respuesta_logout.status_code == 302
    assert respuesta_logout.url.startswith(settings.OIDC_OP_LOGOUT_ENDPOINT)
    assert respuesta_panel.status_code == 302
    assert respuesta_panel.url.startswith(settings.LOGIN_URL)
