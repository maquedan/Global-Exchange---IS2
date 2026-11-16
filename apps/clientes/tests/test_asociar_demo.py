"""Pruebas del comando `asociar_cliente_demo`.

El comando existe para poder reproducir el entorno de pruebas en otra
máquina: busca por nombre de usuario y por documento, nunca por id, porque
los ids de usuario cambian en cada instalación (los crea Keycloak al iniciar
sesión por primera vez).
"""
from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command

from apps.clientes.models import AsociacionUsuarioCliente, Cliente


@pytest.fixture
def cliente_demo(db):
    return Cliente.objects.create(
        documento="DEMO-000001",
        tipo=Cliente.Tipo.FISICA,
        categoria=Cliente.Categoria.MINORISTA,
        nombres="Ana",
        apellidos="Ejemplo",
        email="ana.ejemplo@example.org",
        telefono="+595 21 000 000",
        direccion="Dirección de prueba 100",
    )


@pytest.fixture
def usuario(django_user_model):
    usuario = django_user_model.objects.create_user(
        username="cliente.demo", email="cliente.demo@example.org"
    )
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    usuario.groups.add(grupo)
    return usuario


@pytest.mark.django_db
def test_asocia_al_usuario_con_los_clientes_demo(usuario, cliente_demo):
    salida = StringIO()
    call_command("asociar_cliente_demo", stdout=salida)

    assert AsociacionUsuarioCliente.objects.filter(
        usuario=usuario, cliente=cliente_demo
    ).exists()
    assert "1 asociación(es) nueva(s)" in salida.getvalue()


@pytest.mark.django_db
def test_correrlo_dos_veces_no_duplica(usuario, cliente_demo):
    call_command("asociar_cliente_demo", stdout=StringIO())
    salida = StringIO()
    call_command("asociar_cliente_demo", stdout=salida)

    assert AsociacionUsuarioCliente.objects.count() == 1
    assert "0 asociación(es) nueva(s)" in salida.getvalue()


@pytest.mark.django_db
def test_sin_el_usuario_avisa_que_hay_que_iniciar_sesion(cliente_demo):
    salida = StringIO()
    call_command("asociar_cliente_demo", stdout=salida)

    assert "todavía no existe" in salida.getvalue()
    assert "Keycloak" in salida.getvalue()
    assert AsociacionUsuarioCliente.objects.count() == 0


@pytest.mark.django_db
def test_sin_clientes_manda_a_cargar_los_datos_demo(usuario):
    salida = StringIO()
    call_command("asociar_cliente_demo", stdout=salida)

    assert "cargar_datos_iniciales --profile demo" in salida.getvalue()
    assert AsociacionUsuarioCliente.objects.count() == 0


@pytest.mark.django_db
def test_se_puede_indicar_un_cliente_concreto(usuario, django_user_model):
    propio = Cliente.objects.create(
        documento="9999999",
        tipo=Cliente.Tipo.FISICA,
        nombres="Otro",
        apellidos="Cliente",
        email="otro@example.org",
        telefono="0981000000",
        direccion="Asuncion",
    )

    call_command("asociar_cliente_demo", documento=["9999999"], stdout=StringIO())

    assert AsociacionUsuarioCliente.objects.filter(
        usuario=usuario, cliente=propio
    ).exists()


@pytest.mark.django_db
def test_no_asocia_clientes_dados_de_baja(usuario, cliente_demo):
    cliente_demo.desactivar()

    salida = StringIO()
    call_command("asociar_cliente_demo", stdout=salida)

    assert AsociacionUsuarioCliente.objects.count() == 0
    assert "cargar_datos_iniciales" in salida.getvalue()
