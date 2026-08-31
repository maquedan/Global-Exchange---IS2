"""Pruebas unitarias del caso de uso RF011."""
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.usuarios.menu import tiene_permiso
from apps.usuarios.models import PermisoRol, PermisoSistema

Usuario = get_user_model()


def admin():
    usuario = Usuario.objects.create_user("admin-rf011")
    usuario.groups.add(Group.objects.create(name="administrador"))
    return usuario


@pytest.mark.django_db
def test_solo_administrador_accede_al_panel(client):
    cliente = Usuario.objects.create_user("cliente-rf011")
    cliente.groups.add(Group.objects.create(name="usuario_cliente"))
    client.force_login(cliente)
    assert client.get("/administracion/roles-permisos/").status_code == 302


@pytest.mark.django_db
@patch("apps.usuarios.views.KeycloakAdmin")
def test_admin_crea_rol_en_keycloak(admin_api, client):
    client.force_login(admin())
    api = admin_api.return_value
    respuesta = client.post("/administracion/roles-permisos/", {
        "accion": "crear_rol", "nombre": "supervisor", "descripcion": "Supervisa operaciones",
    })
    assert respuesta.status_code == 302
    api.crear_rol.assert_called_once_with("supervisor", "Supervisa operaciones")


@pytest.mark.django_db
@patch("apps.usuarios.views.KeycloakAdmin")
def test_admin_asigna_roles_a_usuario_en_keycloak(admin_api, client):
    client.force_login(admin())
    api = admin_api.return_value
    respuesta = client.post("/administracion/roles-permisos/", {
        "accion": "asignar_roles", "usuario": "id-keycloak", "roles": ["analista_cambiario"],
    })
    assert respuesta.status_code == 302
    api.establecer_roles_usuario.assert_called_once_with("id-keycloak", ["analista_cambiario"])


@pytest.mark.django_db
def test_permiso_se_resuelve_desde_los_roles_del_usuario():
    usuario = Usuario.objects.create_user("analista-rf011")
    usuario.groups.add(Group.objects.create(name="analista_cambiario"))
    permiso = PermisoSistema.objects.create(codigo="gestionar_clientes", nombre="Gestionar clientes")
    PermisoRol.objects.create(rol="analista_cambiario", permiso=permiso)
    assert tiene_permiso(usuario, "gestionar_clientes")
    assert not tiene_permiso(usuario, "aprobar_operaciones")
