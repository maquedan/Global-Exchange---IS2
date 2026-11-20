from datetime import datetime, time
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.conversiones.services import confirmar_pago_venta, iniciar_compra, iniciar_venta
from apps.horarios.models import RangoHorario
from apps.horarios.services import FueraDeHorarioOperativo, horario_operativo_abierto


Usuario = get_user_model()


def usuario_con_rol(username, rol):
    usuario = Usuario.objects.create_user(username=username, password="test")
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


def instante(dia, hora):
    return timezone.make_aware(datetime(2026, 11, dia, *hora))


@pytest.mark.django_db
def test_rango_horario_abre_y_cierra_en_el_limite():
    RangoHorario.objects.create(dia=4, hora_desde=time(8), hora_hasta=time(17))

    assert horario_operativo_abierto(instante(20, (8, 0)))
    assert horario_operativo_abierto(instante(20, (16, 59)))
    assert not horario_operativo_abierto(instante(20, (17, 0)))
    assert not horario_operativo_abierto(instante(21, (10, 0)))


@pytest.mark.django_db
def test_sin_configuracion_el_sistema_sigue_abierto_para_la_puesta_en_marcha():
    assert horario_operativo_abierto(instante(21, (23, 59)))


@pytest.mark.django_db
def test_iniciar_compra_y_venta_rechazan_fuera_de_horario():
    RangoHorario.objects.create(dia=4, hora_desde=time(8), hora_hasta=time(17))
    fuera = instante(20, (19, 0))

    with patch("apps.horarios.services.timezone.localtime", return_value=fuera):
        with pytest.raises(FueraDeHorarioOperativo, match="fuera del horario operativo"):
            iniciar_compra(
                usuario=None, cliente_id=1, moneda_pagada=1,
                moneda_adquirida=2, monto_pagado="100.00",
                desde_terminal=True,
            )
        with pytest.raises(FueraDeHorarioOperativo, match="fuera del horario operativo"):
            iniciar_venta(
                usuario=None, cliente_id=1, moneda_entregada=1,
                moneda_acreditada=2, monto_entregado="100.00",
            )
        with pytest.raises(FueraDeHorarioOperativo, match="fuera del horario operativo"):
            confirmar_pago_venta(
                pk=1, usuario=None, billetes_recibidos={}, billetes_entregados={}
            )


@pytest.mark.django_db
def test_configuracion_solo_es_visible_y_editable_por_administrador(client):
    administrador = usuario_con_rol("admin-horarios", "administrador")
    cliente = usuario_con_rol("cliente-horarios", "usuario_cliente")
    client.force_login(cliente)
    assert client.get(reverse("horarios:lista")).status_code == 403

    client.force_login(administrador)
    respuesta = client.post(
        reverse("horarios:crear"),
        {"dia": 0, "hora_desde": "08:00", "hora_hasta": "12:00"},
    )
    assert respuesta.status_code == 302
    assert RangoHorario.objects.get().hora_hasta == time(12)


@pytest.mark.django_db
def test_no_se_permite_rango_invertido(client):
    administrador = usuario_con_rol("admin-horarios-invalido", "administrador")
    client.force_login(administrador)
    respuesta = client.post(
        reverse("horarios:crear"),
        {"dia": 0, "hora_desde": "18:00", "hora_hasta": "08:00"},
    )
    assert respuesta.status_code == 200
    assert RangoHorario.objects.count() == 0


@pytest.mark.django_db
def test_simulacion_sigue_disponible_fuera_de_horario(client):
    usuario = usuario_con_rol("cliente-simula-horario", "usuario_cliente")
    client.force_login(usuario)
    RangoHorario.objects.create(dia=4, hora_desde=time(8), hora_hasta=time(17))
    fuera = instante(20, (19, 0))

    with patch("apps.horarios.services.timezone.localtime", return_value=fuera):
        respuesta = client.get(reverse("conversiones:simular"))

    assert respuesta.status_code == 200
