"""Pruebas del menú principal y las vistas protegidas (GEG9-24, GEG9-25)."""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group

from apps.usuarios.menu import construir_menu, roles_de, tiene_rol

Usuario = get_user_model()


def usuario_con(*roles):
    usuario = Usuario.objects.create_user(f"u-{'-'.join(roles) or 'sin-rol'}")
    for rol in roles:
        usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


def textos_del_menu(usuario):
    return [opcion["texto"] for opcion in construir_menu(usuario)]


# --------------------------------------------------------------------- roles
def test_el_anonimo_no_tiene_roles_ni_menu():
    anonimo = AnonymousUser()
    assert roles_de(anonimo) == set()
    assert construir_menu(anonimo) == []


@pytest.mark.django_db
def test_tiene_rol_acepta_varios():
    usuario = usuario_con("analista_cambiario")
    assert tiene_rol(usuario, "administrador", "analista_cambiario")
    assert not tiene_rol(usuario, "administrador")


# ---------------------------------------------------------------------- menú
@pytest.mark.django_db
def test_solo_el_administrador_ve_administracion():
    assert "Administración" in textos_del_menu(usuario_con("administrador"))
    assert "Administración" not in textos_del_menu(usuario_con("usuario_cliente"))
    assert "Administración" not in textos_del_menu(usuario_con("analista_cambiario"))


@pytest.mark.django_db
def test_todos_los_autenticados_ven_el_panel():
    for roles in (("administrador",), ("analista_cambiario",), ("usuario_cliente",), ()):
        assert "Panel" in textos_del_menu(usuario_con(*roles))


@pytest.mark.django_db
def test_saltea_las_rutas_que_todavia_no_existen():
    """'Clientes' aparecerá sola cuando exista apps.clientes.urls (GEG9-11)."""
    assert "Clientes" not in textos_del_menu(usuario_con("administrador"))


@pytest.mark.django_db
def test_el_menu_solo_trae_direcciones_reales():
    for opcion in construir_menu(usuario_con("administrador")):
        assert opcion["url"].startswith("/")


# -------------------------------------------------------------------- vistas
@pytest.mark.django_db
def test_el_panel_exige_iniciar_sesion(client):
    respuesta = client.get("/panel/")
    assert respuesta.status_code == 302
    assert "/oidc/authenticate/" in respuesta["Location"]


@pytest.mark.django_db
def test_el_inicio_es_publico(client):
    respuesta = client.get("/")
    assert respuesta.status_code == 200
    assert "Iniciar sesión" in respuesta.content.decode()


@pytest.mark.django_db
def test_el_panel_muestra_los_roles(client):
    usuario = usuario_con("analista_cambiario")
    client.force_login(usuario)

    contenido = client.get("/panel/").content.decode()

    assert "analista_cambiario" in contenido
    assert "Administración" not in contenido


@pytest.mark.django_db
def test_al_entrar_el_inicio_redirige_al_panel(client):
    client.force_login(usuario_con("usuario_cliente"))
    assert client.get("/").status_code == 302
