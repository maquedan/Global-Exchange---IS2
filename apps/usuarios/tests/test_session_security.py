"""Pruebas de expiración de sesión por inactividad y cierre voluntario."""
from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import override_settings
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
@override_settings(SESSION_COOKIE_AGE=30)
def test_pagina_autenticada_programa_cierre_por_inactividad(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="sesion-temporizador")
    client.force_login(usuario)

    respuesta = client.get(reverse("usuarios:panel"))
    contenido = respuesta.content.decode()

    assert 'data-session-idle-timeout="30"' in contenido
    assert 'action="/cerrar-sesion-inactiva/"' in contenido
    assert "logoutForm.requestSubmit()" in contenido
    assert "idleTimeoutMs - Math.min(2000, idleTimeoutMs * 0.1)" in contenido
    assert "window.setTimeout(cerrarSesion, logoutDelayMs)" in contenido


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


@pytest.mark.django_db
def test_cierre_por_inactividad_cierra_keycloak_si_django_ya_vencio(
    client, django_user_model
):
    usuario = django_user_model.objects.create_user(username="sesion-expirada")
    client.force_login(usuario)
    sesion = client.session
    sesion.set_expiry(-1)
    sesion.save()

    respuesta = client.post(reverse("usuarios:cerrar_sesion_inactividad"))

    parametros = parse_qs(urlsplit(respuesta.url).query)
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(settings.OIDC_OP_LOGOUT_ENDPOINT)
    assert parametros["client_id"] == [settings.OIDC_RP_CLIENT_ID]
    assert client.get(reverse("usuarios:panel")).url.startswith(settings.LOGIN_URL)


@pytest.mark.django_db
def test_cierre_por_inactividad_usa_id_token_para_evitar_confirmacion_keycloak(
    client, django_user_model
):
    usuario = django_user_model.objects.create_user(username="sesion-con-token")
    client.force_login(usuario)
    sesion = client.session
    sesion["oidc_id_token"] = "token-id-para-logout"
    sesion.save()

    respuesta = client.post(reverse("usuarios:cerrar_sesion_inactividad"))

    assert "id_token_hint=token-id-para-logout" in respuesta.url
