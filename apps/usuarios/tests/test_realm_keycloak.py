"""Pruebas del realm de Keycloak versionado (RF012 — GEG9-22).

Keycloak no se puede levantar dentro de pytest, así que lo que se verifica
acá es el **archivo del realm**: que la configuración de la que depende la
recuperación de acceso esté efectivamente versionada y no quede librada a
los valores por defecto ni a lo que alguien haya tocado a mano en su
Keycloak.

Eso último no es teórico: al relevar esta historia se encontró que el realm
que corría apuntaba a Gmail mientras el archivo decía Mailpit. El archivo se
importa solo en el primer arranque, así que archivo y servidor divergen con
facilidad.
"""
import json
from pathlib import Path

import pytest
from django.conf import settings

RUTA_REALM = Path(settings.BASE_DIR) / "keycloak" / "realm-global-exchange.json"

# El enlace de recuperación vence a los 5 minutos. Es una decisión del
# equipo, no un valor por defecto: se fija en el archivo para que valga igual
# en cualquier instalación.
SEGUNDOS_VIDA_ENLACE = 300


@pytest.fixture(scope="module")
def realm():
    assert RUTA_REALM.exists(), f"No existe {RUTA_REALM}"
    with RUTA_REALM.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def test_el_realm_permite_recuperar_la_contrasena(realm):
    """Sin esto, la pantalla de login no ofrece "¿Olvidaste tu contraseña?"."""
    assert realm["resetPasswordAllowed"] is True


def test_el_realm_exige_verificar_el_correo(realm):
    """El ERS habla de "correo verificado" (RF012).

    Keycloak manda el enlace de recuperación aunque el correo no esté
    verificado —se comprobó contra el servidor real—, así que lo que protege
    la cuenta es esta opción: mientras el correo no se verifique, no se puede
    usar la cuenta.
    """
    assert realm["verifyEmail"] is True


def test_el_realm_tiene_servidor_de_correo_definido(realm):
    """Sin SMTP, el enlace no se manda y el flujo no existe."""
    smtp = realm.get("smtpServer") or {}
    assert smtp.get("host"), "Falta el host SMTP en el realm"
    assert smtp.get("port"), "Falta el puerto SMTP en el realm"
    assert smtp.get("from"), "Falta la dirección remitente en el realm"


def test_el_realm_no_trae_credenciales_de_correo(realm):
    """El archivo se versiona: no puede llevar usuario ni contraseña.

    En desarrollo apunta a Mailpit, que no pide autenticación. Las
    credenciales reales se aplican con `scripts/configurar_smtp.py`, que las
    lee del `.env`.
    """
    smtp = realm.get("smtpServer") or {}
    assert "password" not in smtp, "El realm versionado no debe traer contraseñas"
    assert smtp.get("auth") in (None, "false", False)


def test_el_enlace_de_recuperacion_tiene_vencimiento_fijado(realm):
    """Si no está en el archivo, queda al valor por defecto de Keycloak."""
    assert realm["actionTokenGeneratedByUserLifespan"] == SEGUNDOS_VIDA_ENLACE
    assert realm["accessCodeLifespanUserAction"] == SEGUNDOS_VIDA_ENLACE


def test_el_realm_esta_en_espanol(realm):
    """Las pantallas y los correos de Keycloak los ve el usuario final."""
    assert realm["internationalizationEnabled"] is True
    assert realm["defaultLocale"] == "es"
    assert "es" in realm["supportedLocales"]


def test_los_usuarios_demo_tienen_correo(realm):
    """Sin dirección no hay a dónde mandar el enlace de recuperación."""
    usuarios = realm.get("users") or []
    assert usuarios, "El realm no define usuarios de prueba"
    for usuario in usuarios:
        assert usuario.get("email"), f"{usuario['username']} no tiene correo"
