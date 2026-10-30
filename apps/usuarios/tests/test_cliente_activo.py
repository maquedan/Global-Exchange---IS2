"""Pruebas de RF008 — Selección de Cliente Activo (GEG9-18)."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CompraDivisa
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio

from apps.usuarios.services import CLAVE_SESION


def _cliente(nombres, documento):
    return Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres=nombres,
        apellidos="Gomez",
        documento=documento,
        email=f"{nombres.lower()}@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )


@pytest.fixture
def usuario():
    usuario = get_user_model().objects.create_user(username="cliente-rf008")
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    usuario.groups.add(grupo)
    return usuario


@pytest.fixture
def monedas():
    return (
        Moneda.objects.create(codigo="USD", nombre="Dolar", simbolo="$"),
        Moneda.objects.create(codigo="PYG", nombre="Guarani", simbolo="Gs"),
    )


@pytest.fixture
def tasa(monedas):
    return TasaCambio.objects.create(
        moneda_origen=monedas[0],
        moneda_destino=monedas[1],
        tasa_compra=Decimal("7.10"),
        tasa_venta=Decimal("7.20"),
        vigente_desde=timezone.now(),
    )


@pytest.fixture
def comision():
    return ComisionCategoria.objects.create(
        categoria=Cliente.Categoria.MINORISTA, porcentaje=Decimal("2.50")
    )


@pytest.mark.django_db
def test_con_un_solo_cliente_queda_seleccionado_solo(client, usuario):
    unico = _cliente("Ana", "111")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=unico)
    client.force_login(usuario)

    respuesta = client.get(reverse("usuarios:panel"))

    assert respuesta.status_code == 200
    assert respuesta.context["cliente_activo"] == unico


@pytest.mark.django_db
def test_con_varios_clientes_redirige_a_elegir_antes_de_operar(client, usuario):
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=_cliente("Ana", "111"))
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=_cliente("Luis", "222"))
    client.force_login(usuario)

    respuesta = client.get(reverse("conversiones:comprar"))

    assert respuesta.status_code == 302
    assert reverse("usuarios:seleccionar_cliente") in respuesta.url


@pytest.mark.django_db
def test_elegir_un_cliente_que_no_es_mio_se_rechaza(client, usuario):
    mio = _cliente("Ana", "111")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=mio)
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=_cliente("Luis", "222"))
    ajeno = _cliente("Carla", "999")  # de nadie: no está asociado a este usuario
    client.force_login(usuario)

    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": ajeno.pk})

    assert client.session.get(CLAVE_SESION) is None


@pytest.mark.django_db
def test_elegir_un_cliente_propio_lo_guarda_en_la_sesion(client, usuario):
    primero = _cliente("Ana", "111")
    segundo = _cliente("Luis", "222")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=primero)
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=segundo)
    client.force_login(usuario)

    respuesta = client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": segundo.pk})

    assert respuesta.status_code == 302
    assert client.session[CLAVE_SESION] == segundo.pk


@pytest.mark.django_db
def test_si_dan_de_baja_al_cliente_activo_se_vuelve_a_pedir(client, usuario):
    elegido = _cliente("Ana", "111")
    otro = _cliente("Luis", "222")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=elegido)
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=otro)
    client.force_login(usuario)
    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": elegido.pk})

    elegido.desactivar()  # RF003: lo dan de baja mientras la sesión sigue abierta

    respuesta = client.get(reverse("conversiones:comprar"), follow=False)

    # Queda uno solo activo, así que ese pasa a ser el cliente activo.
    assert respuesta.status_code == 200
    assert respuesta.context["cliente_activo"] == otro
    assert client.session[CLAVE_SESION] == otro.pk


@pytest.mark.django_db
def test_si_desvinculan_al_cliente_activo_se_limpia_la_eleccion(client, usuario):
    elegido = _cliente("Ana", "111")
    otro = _cliente("Luis", "222")
    tercero = _cliente("Carla", "333")
    asociacion = AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=elegido)
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=otro)
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=tercero)
    client.force_login(usuario)
    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": elegido.pk})

    asociacion.delete()  # lo desvinculan del usuario

    respuesta = client.get(reverse("conversiones:comprar"))

    assert respuesta.status_code == 302
    assert reverse("usuarios:seleccionar_cliente") in respuesta.url
    assert client.session.get(CLAVE_SESION) is None


@pytest.mark.django_db
def test_usuario_sin_clientes_no_rompe_y_no_tiene_cliente_activo(client, usuario):
    client.force_login(usuario)

    respuesta = client.get(reverse("usuarios:panel"))

    assert respuesta.status_code == 200
    assert respuesta.context["cliente_activo"] is None


@pytest.mark.django_db
def test_usuario_sin_clientes_no_puede_operar_pero_no_se_rompe(client, usuario):
    client.force_login(usuario)

    respuesta = client.get(reverse("conversiones:comprar"))

    # No va a elegir (no hay nada que elegir): lo corta con un mensaje.
    assert respuesta.status_code == 302
    # Desde RF010 (GEG9-20) el bloqueo no vuelve al panel: manda a la
    # pantalla que explica qué le falta y qué sí puede consultar.
    assert respuesta.url == reverse("usuarios:sin_cliente")


@pytest.mark.django_db
def test_la_compra_se_registra_a_nombre_del_cliente_activo(
    client, usuario, monedas, tasa, comision
):
    primero = _cliente("Ana", "111")
    segundo = _cliente("Luis", "222")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=primero)
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=segundo)
    client.force_login(usuario)
    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": segundo.pk})

    client.post(reverse("conversiones:comprar"), {
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    compra = CompraDivisa.objects.get()
    assert compra.cliente == segundo


@pytest.mark.django_db
def test_las_pantallas_de_consulta_no_piden_elegir_cliente(client, usuario):
    """Cotizaciones y el panel no operan en nombre de nadie: no deben
    bloquearse por no haber elegido cliente todavía."""
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=_cliente("Ana", "111"))
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=_cliente("Luis", "222"))
    client.force_login(usuario)

    assert client.get(reverse("usuarios:panel")).status_code == 200
    assert client.get(reverse("tasas:panel")).status_code == 200
