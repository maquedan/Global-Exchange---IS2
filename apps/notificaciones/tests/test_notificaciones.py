"""Pruebas de RF033 — Alertas de Tasas (GEG9-38)."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio

from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import notificar_cambio_de_tasa


def _usuario_con_rol(username, rol):
    usuario = get_user_model().objects.create_user(username=username, email=f"{username}@example.com")
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    return usuario


def _cliente(nombres="Ana", activo=True):
    return Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres=nombres,
        apellidos="Gomez",
        documento=f"doc-{nombres}",
        email="cliente@example.com",
        telefono="0981000000",
        direccion="Asuncion",
        activo=activo,
    )


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
def analista():
    return _usuario_con_rol("analista-rf033", "analista_cambiario")


def _datos_formulario(tasa, **cambios):
    datos = {
        "moneda_origen": tasa.moneda_origen_id,
        "moneda_destino": tasa.moneda_destino_id,
        "tasa_compra": str(tasa.tasa_compra),
        "tasa_venta": str(tasa.tasa_venta),
        "vigente_desde": tasa.vigente_desde.strftime("%Y-%m-%dT%H:%M"),
        "activo": "on",
    }
    datos.update(cambios)
    return datos


@pytest.mark.django_db
def test_cambiar_tasa_compra_notifica_a_clientes_asociados_activos(
    client, analista, tasa, django_capture_on_commit_callbacks
):
    cliente_activo = _cliente("Ana", activo=True)
    usuario_cliente_ok = _usuario_con_rol("cliente-ok", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario_cliente_ok, cliente=cliente_activo)

    cliente_inactivo = _cliente("Luis", activo=False)
    usuario_cliente_inactivo = _usuario_con_rol("cliente-inactivo", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario_cliente_inactivo, cliente=cliente_inactivo)

    usuario_sin_asociacion = _usuario_con_rol("cliente-sin-asociacion", "usuario_cliente")
    admin = _usuario_con_rol("admin-rf033", "administrador")

    client.force_login(analista)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("tasa_cambios:editar", args=[tasa.pk]),
            _datos_formulario(tasa, tasa_compra="7.50"),
        )

    assert Notificacion.objects.filter(usuario=usuario_cliente_ok).count() == 1
    assert not Notificacion.objects.filter(usuario=usuario_cliente_inactivo).exists()
    assert not Notificacion.objects.filter(usuario=usuario_sin_asociacion).exists()
    assert not Notificacion.objects.filter(usuario=admin).exists()
    assert not Notificacion.objects.filter(usuario=analista).exists()


@pytest.mark.django_db
def test_editar_sin_cambiar_los_valores_no_notifica(
    client, analista, tasa, django_capture_on_commit_callbacks
):
    cliente_activo = _cliente()
    usuario_cliente = _usuario_con_rol("cliente-sin-cambio", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario_cliente, cliente=cliente_activo)

    client.force_login(analista)
    with django_capture_on_commit_callbacks(execute=True):
        # Mismo tasa_compra/tasa_venta; solo cambia vigente_desde.
        client.post(
            reverse("tasa_cambios:editar", args=[tasa.pk]),
            _datos_formulario(tasa, vigente_desde=timezone.now().strftime("%Y-%m-%dT%H:%M")),
        )

    assert Notificacion.objects.count() == 0


@pytest.mark.django_db
def test_activar_y_desactivar_no_notifican(
    client, analista, tasa, django_capture_on_commit_callbacks
):
    cliente_activo = _cliente()
    usuario_cliente = _usuario_con_rol("cliente-activar-desactivar", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario_cliente, cliente=cliente_activo)

    client.force_login(analista)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("tasa_cambios:desactivar", args=[tasa.pk]))
        client.post(reverse("tasa_cambios:activar", args=[tasa.pk]))

    assert Notificacion.objects.count() == 0


@pytest.mark.django_db
def test_usuario_sin_email_recibe_la_notificacion_interna_sin_fallar(
    tasa, django_capture_on_commit_callbacks
):
    cliente_activo = _cliente()
    usuario_sin_email = get_user_model().objects.create_user(username="cliente-sin-email", email="")
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    usuario_sin_email.groups.add(grupo)
    AsociacionUsuarioCliente.objects.create(usuario=usuario_sin_email, cliente=cliente_activo)

    with django_capture_on_commit_callbacks(execute=True):
        notificar_cambio_de_tasa(tasa, compra_anterior=Decimal("7.00"), venta_anterior=Decimal("7.10"))

    assert Notificacion.objects.filter(usuario=usuario_sin_email).count() == 1
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_un_error_de_correo_no_impide_guardar_la_tasa_ni_la_notificacion(
    client, analista, tasa, django_capture_on_commit_callbacks
):
    cliente_activo = _cliente()
    usuario_cliente = _usuario_con_rol("cliente-con-email", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario_cliente, cliente=cliente_activo)

    client.force_login(analista)
    with patch(
        "apps.notificaciones.services.send_mail", side_effect=Exception("SMTP caido")
    ):
        with django_capture_on_commit_callbacks(execute=True):
            respuesta = client.post(
                reverse("tasa_cambios:editar", args=[tasa.pk]),
                _datos_formulario(tasa, tasa_compra="8.00"),
            )

    assert respuesta.status_code == 302
    tasa.refresh_from_db()
    assert tasa.tasa_compra == Decimal("8.00")
    assert Notificacion.objects.filter(usuario=usuario_cliente).count() == 1


@pytest.mark.django_db
def test_usuario_solo_ve_y_marca_como_leidas_sus_propias_notificaciones(client, tasa):
    usuario_a = _usuario_con_rol("notif-usuario-a", "usuario_cliente")
    usuario_b = _usuario_con_rol("notif-usuario-b", "usuario_cliente")

    notificacion_a = Notificacion.objects.create(
        usuario=usuario_a, tipo=Notificacion.Tipo.CAMBIO_TASA, mensaje="Para A", tasa=tasa
    )
    notificacion_b = Notificacion.objects.create(
        usuario=usuario_b, tipo=Notificacion.Tipo.CAMBIO_TASA, mensaje="Para B", tasa=tasa
    )

    client.force_login(usuario_a)
    respuesta = client.get(reverse("notificaciones:lista"))
    assert respuesta.status_code == 200
    ids_vistos = {n.pk for n in respuesta.context["notificaciones"]}
    assert ids_vistos == {notificacion_a.pk}

    # No puede marcar como leída la de otro usuario.
    respuesta_ajena = client.post(
        reverse("notificaciones:marcar_leida", args=[notificacion_b.pk])
    )
    assert respuesta_ajena.status_code == 404
    notificacion_b.refresh_from_db()
    assert notificacion_b.leida is False

    respuesta_propia = client.post(
        reverse("notificaciones:marcar_leida", args=[notificacion_a.pk])
    )
    assert respuesta_propia.status_code == 302
    notificacion_a.refresh_from_db()
    assert notificacion_a.leida is True


@pytest.mark.django_db
def test_usuario_sin_rol_cliente_no_puede_ver_notificaciones(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="sin-rol-notificaciones")
    client.force_login(usuario)

    assert client.get(reverse("notificaciones:lista")).status_code == 403


@pytest.mark.django_db
def test_contador_del_menu_cuenta_solo_las_no_leidas_del_usuario(client, tasa):
    usuario = _usuario_con_rol("notif-contador", "usuario_cliente")
    Notificacion.objects.create(
        usuario=usuario, tipo=Notificacion.Tipo.CAMBIO_TASA, mensaje="1", tasa=tasa, leida=True
    )
    Notificacion.objects.create(
        usuario=usuario, tipo=Notificacion.Tipo.CAMBIO_TASA, mensaje="2", tasa=tasa
    )
    Notificacion.objects.create(
        usuario=usuario, tipo=Notificacion.Tipo.CAMBIO_TASA, mensaje="3", tasa=tasa
    )

    client.force_login(usuario)
    respuesta = client.get(reverse("usuarios:panel"))

    assert respuesta.context["notificaciones_no_leidas"] == 2


@pytest.mark.django_db
def test_cargar_fixture_tasas_demo_no_genera_notificaciones(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        call_command("loaddata", "monedas_demo", "tasas_demo", verbosity=0)

    assert Notificacion.objects.count() == 0
