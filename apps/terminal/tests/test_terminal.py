"""Pruebas de RF054 — Modo Terminal de Autoservicio (GEG9-55)."""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.usuarios.menu import construir_menu


Usuario = get_user_model()


def usuario_con_rol(rol):
    usuario = Usuario.objects.create_user(
        username=f"usuario-{rol}",
        password="test",
    )
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


@pytest.mark.django_db
def test_terminal_solo_muestra_panel_y_terminal_en_el_menu():
    usuario = usuario_con_rol("terminal")

    textos = [opcion["texto"] for opcion in construir_menu(usuario)]

    assert textos == ["Panel", "Terminal"]


@pytest.mark.django_db
def test_usuario_terminal_puede_abrir_el_inicio(client):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    respuesta = client.get(reverse("terminal:inicio"))

    assert respuesta.status_code == 200
    assert "Terminal de autoservicio" in respuesta.content.decode()
    assert "Comprar divisas" in respuesta.content.decode()
    assert "Vender divisas" in respuesta.content.decode()
    assert "Ver cotizaciones" in respuesta.content.decode()


@pytest.mark.django_db
def test_otro_rol_no_puede_abrir_la_terminal(client):
    usuario = usuario_con_rol("usuario_cliente")
    client.force_login(usuario)

    respuesta = client.get(reverse("terminal:inicio"))

    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_reiniciar_terminal_exige_post(client):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    respuesta = client.get(reverse("terminal:reiniciar"))

    assert respuesta.status_code == 405


@pytest.mark.django_db
def test_reiniciar_terminal_limpia_la_sesion(client):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    sesion = client.session
    sesion["terminal_cliente_id"] = 10
    sesion["terminal_tipo_operacion"] = "compra"
    sesion["terminal_compra_id"] = 20
    sesion["terminal_venta_id"] = 30
    sesion.save()

    respuesta = client.post(reverse("terminal:reiniciar"))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("terminal:inicio")

    sesion = client.session
    assert "terminal_cliente_id" not in sesion
    assert "terminal_tipo_operacion" not in sesion
    assert "terminal_compra_id" not in sesion
    assert "terminal_venta_id" not in sesion