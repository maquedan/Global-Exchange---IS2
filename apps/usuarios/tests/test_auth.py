"""Pruebas del backend de autenticación con Keycloak (GEG9-24)."""
import base64
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.usuarios.auth import (
    KeycloakOIDCBackend,
    _leer_payload_del_token,
    cerrar_sesion_en_keycloak,
)

Usuario = get_user_model()


def token_falso(contenido):
    """Arma un JWT de mentira: cabecera.contenido.firma"""
    cuerpo = base64.urlsafe_b64encode(json.dumps(contenido).encode()).decode().rstrip("=")
    return f"cabecera.{cuerpo}.firma"


# ---------------------------------------------------------------- lectura JWT
def test_lee_el_contenido_de_un_token():
    token = token_falso({"realm_access": {"roles": ["administrador"]}})
    assert _leer_payload_del_token(token)["realm_access"]["roles"] == ["administrador"]


@pytest.mark.parametrize("basura", ["", "no-es-un-jwt", "a.b", "a.####.c"])
def test_un_token_roto_no_revienta(basura):
    """Ante un token inválido devolvemos {} en vez de tirar excepción."""
    assert _leer_payload_del_token(basura) == {}


# ------------------------------------------------------- armado de los claims
def test_los_roles_salen_del_access_token():
    """Keycloak manda los roles en el access_token, no en el id_token."""
    backend = KeycloakOIDCBackend()
    id_token_claims = {"email": "ana@ejemplo.com", "given_name": "Ana"}
    access = token_falso({"realm_access": {"roles": ["administrador", "offline_access"]}})

    claims = backend.get_userinfo(access, "id-token", id_token_claims)

    assert claims["email"] == "ana@ejemplo.com"      # viene del id_token
    assert claims["roles"] == ["administrador", "offline_access"]


# ------------------------------------------------- sincronización con Django
@pytest.mark.django_db
def test_asigna_grupos_segun_los_roles():
    backend = KeycloakOIDCBackend()
    usuario = Usuario.objects.create_user("hash-feo", email="ana@ejemplo.com")

    backend._sincronizar(usuario, {
        "roles": ["administrador", "offline_access"],
        "preferred_username": "ana",
        "given_name": "Ana", "family_name": "Gómez",
    })

    assert set(usuario.groups.values_list("name", flat=True)) == {"administrador"}
    assert usuario.username == "ana"          # usa el nombre de Keycloak
    assert usuario.first_name == "Ana"
    assert usuario.is_staff and usuario.is_superuser


@pytest.mark.django_db
def test_keycloak_es_la_fuente_de_verdad():
    """Si en Keycloak le sacan un rol, en Django también se lo sacamos."""
    backend = KeycloakOIDCBackend()
    usuario = Usuario.objects.create_user("u1", email="u1@ejemplo.com")
    backend._sincronizar(usuario, {"roles": ["administrador"]})

    backend._sincronizar(usuario, {"roles": ["usuario_cliente"]})

    assert set(usuario.groups.values_list("name", flat=True)) == {"usuario_cliente"}
    assert not usuario.is_staff and not usuario.is_superuser


@pytest.mark.django_db
def test_ignora_los_roles_internos_de_keycloak():
    backend = KeycloakOIDCBackend()
    usuario = Usuario.objects.create_user("u2", email="u2@ejemplo.com")

    backend._sincronizar(usuario, {
        "roles": ["offline_access", "uma_authorization", "default-roles-global-exchange"],
    })

    assert usuario.groups.count() == 0


@pytest.mark.django_db
def test_no_pisa_el_nombre_de_otro_usuario():
    """Si el preferred_username ya está ocupado, conservamos el que tenía."""
    backend = KeycloakOIDCBackend()
    Usuario.objects.create_user("ana", email="otra@ejemplo.com")
    usuario = Usuario.objects.create_user("hash-feo", email="ana@ejemplo.com")

    backend._sincronizar(usuario, {"roles": [], "preferred_username": "ana"})

    assert usuario.username == "hash-feo"


@pytest.mark.django_db
def test_sin_roles_no_es_administrador():
    backend = KeycloakOIDCBackend()
    usuario = Usuario.objects.create_user("u3", email="u3@ejemplo.com")
    usuario.is_staff = usuario.is_superuser = True
    usuario.save()

    backend._sincronizar(usuario, {"roles": []})

    assert not usuario.is_staff and not usuario.is_superuser


# ------------------------------------------------------------------- logout
def test_logout_usa_el_id_token(rf):
    """Keycloak necesita el id_token para saber qué sesión cerrar."""
    peticion = rf.get("/")
    peticion.session = {"oidc_id_token": "token-guardado"}

    url = cerrar_sesion_en_keycloak(peticion)

    assert "id_token_hint=token-guardado" in url
    assert "post_logout_redirect_uri=http%3A%2F%2Ftestserver%2F" in url


def test_logout_sin_id_token_manda_el_client_id(rf):
    peticion = rf.get("/")
    peticion.session = {}

    url = cerrar_sesion_en_keycloak(peticion)

    assert "client_id=global-exchange-web" in url
