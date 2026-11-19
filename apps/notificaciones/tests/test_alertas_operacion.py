"""Pruebas de RF034 — Alertas de Operación (GEG9-76).

El aviso se dispara desde `registrar_cambio_estado`, que es el único punto
por donde pasan los once cambios de estado del proyecto (RF023). Por eso las
pruebas llaman a los servicios de negocio de verdad —confirmar, cancelar,
anular— en vez de al servicio de notificaciones directamente: así se
verifica también que el enganche esté puesto.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CompraDivisa
from apps.conversiones.services import (
    cancelar_compra,
    confirmar_pago_compra,
    expirar_compra_si_corresponde,
    iniciar_compra,
    registrar_cambio_estado,
)
from apps.monedas.models import Moneda
from apps.notificaciones.models import Notificacion
from apps.tasa_cambios.models import TasaCambio


def _usuario(django_user_model, username):
    usuario = django_user_model.objects.create_user(
        username=username, email=f"{username}@example.com"
    )
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    usuario.groups.add(grupo)
    return usuario


def _cliente(nombres, documento):
    return Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres=nombres,
        apellidos="Prueba",
        documento=documento,
        email=f"{nombres.lower()}@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )


@pytest.fixture
def monedas(db):
    return (
        Moneda.objects.create(codigo="USD", nombre="Dolar", simbolo="$"),
        Moneda.objects.create(codigo="PYG", nombre="Guarani", simbolo="Gs"),
    )


@pytest.fixture
def tasa(monedas):
    return TasaCambio.objects.create(
        moneda_origen=monedas[0],
        moneda_destino=monedas[1],
        tasa_compra=Decimal("7100.00"),
        tasa_venta=Decimal("7200.00"),
        vigente_desde=timezone.now(),
    )


@pytest.fixture
def comision(db):
    return ComisionCategoria.objects.create(
        categoria=Cliente.Categoria.MINORISTA, porcentaje=Decimal("2.50")
    )


@pytest.fixture
def duenio(db, django_user_model):
    """Usuario asociado al cliente de la operación: el que debe recibir."""
    usuario = _usuario(django_user_model, "duenio")
    cliente = _cliente("Ana", "1111111")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)
    return usuario, cliente


@pytest.fixture
def compra(duenio, monedas, tasa, comision):
    usuario, cliente = duenio
    return iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )


def _avisos(usuario, tipo=None):
    consulta = Notificacion.objects.filter(usuario=usuario)
    return consulta.filter(tipo=tipo) if tipo else consulta


# ---------------------------------------------------------------------------
# Cada transición relevante avisa
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_confirmar_avisa_al_duenio(duenio, compra, django_capture_on_commit_callbacks):
    usuario, _cliente = duenio

    with django_capture_on_commit_callbacks(execute=True):
        confirmar_pago_compra(pk=compra.pk, usuario=usuario)

    aviso = _avisos(usuario, Notificacion.Tipo.OPERACION_CONFIRMADA).get()
    assert f"Compra #{compra.pk}" in aviso.mensaje
    assert "Pagada" in aviso.mensaje
    assert aviso.leida is False


@pytest.mark.django_db(transaction=True)
def test_cancelar_avisa_con_el_motivo(duenio, compra, django_capture_on_commit_callbacks):
    usuario, _cliente = duenio

    with django_capture_on_commit_callbacks(execute=True):
        cancelar_compra(pk=compra.pk, usuario=usuario)

    aviso = _avisos(usuario, Notificacion.Tipo.OPERACION_CANCELADA).get()
    assert "Cancelada por el cliente." in aviso.mensaje


@pytest.mark.django_db(transaction=True)
def test_el_vencimiento_tambien_avisa(duenio, compra, django_capture_on_commit_callbacks):
    """Lo dispara el sistema, sin usuario: igual hay que avisarle al cliente."""
    usuario, _cliente = duenio
    compra.creado_en = timezone.now() - timezone.timedelta(hours=2)
    compra.save(update_fields=["creado_en"])

    with django_capture_on_commit_callbacks(execute=True):
        expirar_compra_si_corresponde(compra)

    aviso = _avisos(usuario, Notificacion.Tipo.OPERACION_CANCELADA).get()
    assert "Se venció el tiempo para confirmar." in aviso.mensaje


@pytest.mark.django_db(transaction=True)
def test_la_anulacion_avisa(duenio, compra, django_capture_on_commit_callbacks):
    usuario, _cliente = duenio

    with django_capture_on_commit_callbacks(execute=True):
        registrar_cambio_estado(
            compra, compra.estado, CompraDivisa.Estado.ANULADA,
            motivo="Anulada por el administrador.", usuario=usuario,
        )

    assert _avisos(usuario, Notificacion.Tipo.OPERACION_ANULADA).count() == 1


@pytest.mark.django_db(transaction=True)
def test_crear_la_operacion_no_genera_aviso(
    duenio, monedas, tasa, comision, django_capture_on_commit_callbacks
):
    """Nacer no es cambiar de estado: avisarle sería contarle lo que acaba de hacer."""
    usuario, cliente = duenio

    with django_capture_on_commit_callbacks(execute=True):
        iniciar_compra(
            usuario=usuario,
            cliente_id=cliente.pk,
            moneda_pagada=monedas[0],
            moneda_adquirida=monedas[1],
            monto_pagado="100.00",
        )

    assert _avisos(usuario).count() == 0


# ---------------------------------------------------------------------------
# Solo al dueño
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_un_usuario_ajeno_no_recibe_nada(
    duenio, compra, django_user_model, django_capture_on_commit_callbacks
):
    usuario, _suyo = duenio
    ajeno = _usuario(django_user_model, "ajeno")
    AsociacionUsuarioCliente.objects.create(
        usuario=ajeno, cliente=_cliente("Beto", "2222222")
    )

    with django_capture_on_commit_callbacks(execute=True):
        confirmar_pago_compra(pk=compra.pk, usuario=usuario)

    assert _avisos(usuario).count() == 1
    assert _avisos(ajeno).count() == 0


@pytest.mark.django_db(transaction=True)
def test_avisa_a_todos_los_usuarios_del_cliente(
    duenio, compra, django_user_model, django_capture_on_commit_callbacks
):
    """Un cliente puede tener varias personas con cuenta: reciben todas."""
    usuario, cliente = duenio
    companiero = _usuario(django_user_model, "companiero")
    AsociacionUsuarioCliente.objects.create(usuario=companiero, cliente=cliente)

    with django_capture_on_commit_callbacks(execute=True):
        confirmar_pago_compra(pk=compra.pk, usuario=usuario)

    assert _avisos(usuario).count() == 1
    assert _avisos(companiero).count() == 1


@pytest.mark.django_db(transaction=True)
def test_un_cliente_sin_usuarios_no_rompe(
    monedas, tasa, comision, django_user_model, django_capture_on_commit_callbacks
):
    """Caso de la terminal: el cliente puede no tener a nadie con cuenta."""
    operador = _usuario(django_user_model, "operador")
    cliente = _cliente("Sin", "3333333")
    AsociacionUsuarioCliente.objects.create(usuario=operador, cliente=cliente)
    compra = iniciar_compra(
        usuario=operador,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )
    AsociacionUsuarioCliente.objects.filter(cliente=cliente).delete()

    with django_capture_on_commit_callbacks(execute=True):
        registrar_cambio_estado(
            compra, CompraDivisa.Estado.PENDIENTE, CompraDivisa.Estado.CANCELADA,
            motivo="Sin nadie a quien avisar.",
        )

    compra.refresh_from_db()
    assert Notificacion.objects.count() == 0


# ---------------------------------------------------------------------------
# Que avisar no rompa nada
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_un_fallo_al_avisar_no_deshace_la_confirmacion(
    duenio, compra, django_capture_on_commit_callbacks
):
    """RNF: el aviso es un efecto secundario, la transición es el hecho."""
    usuario, _cliente = duenio

    with patch(
        "apps.notificaciones.services.notificar_cambio_de_estado",
        side_effect=RuntimeError("se cayo el servicio de avisos"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            confirmar_pago_compra(pk=compra.pk, usuario=usuario)

    compra.refresh_from_db()
    assert compra.estado == CompraDivisa.Estado.CONFIRMADA
    assert _avisos(usuario).count() == 0


@pytest.mark.django_db(transaction=True)
def test_registrar_el_mismo_cambio_dos_veces_no_duplica(
    duenio, compra, django_capture_on_commit_callbacks
):
    usuario, _cliente = duenio

    with django_capture_on_commit_callbacks(execute=True):
        cambio = registrar_cambio_estado(
            compra, CompraDivisa.Estado.PENDIENTE, CompraDivisa.Estado.CONFIRMADA,
            usuario=usuario,
        )

    from apps.notificaciones.services import notificar_cambio_de_estado

    with django_capture_on_commit_callbacks(execute=True):
        notificar_cambio_de_estado(cambio)
        notificar_cambio_de_estado(cambio)

    assert _avisos(usuario).count() == 1


# ---------------------------------------------------------------------------
# Que se vea
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_aparece_en_la_lista_y_en_el_contador(
    client, duenio, compra, django_capture_on_commit_callbacks
):
    from django.urls import reverse

    usuario, _cliente = duenio
    with django_capture_on_commit_callbacks(execute=True):
        confirmar_pago_compra(pk=compra.pk, usuario=usuario)

    client.force_login(usuario)
    respuesta = client.get(reverse("notificaciones:lista"))

    assert f"Compra #{compra.pk}" in respuesta.content.decode()
    # El contador del menú no filtra por tipo: las nuevas entran solas.
    assert respuesta.context["notificaciones_no_leidas"] == 1


@pytest.mark.django_db(transaction=True)
def test_se_puede_marcar_como_leida(
    client, duenio, compra, django_capture_on_commit_callbacks
):
    from django.urls import reverse

    usuario, _cliente = duenio
    with django_capture_on_commit_callbacks(execute=True):
        confirmar_pago_compra(pk=compra.pk, usuario=usuario)
    aviso = _avisos(usuario).get()

    client.force_login(usuario)
    client.post(reverse("notificaciones:marcar_leida", args=[aviso.pk]))

    aviso.refresh_from_db()
    assert aviso.leida is True


@pytest.mark.django_db
def test_el_monto_se_formatea_en_un_solo_lugar():
    """GEG9-82 todavía no está: cuando llegue, se cambia solo acá."""
    from apps.notificaciones.services import formatear_monto

    assert formatear_monto(Decimal("71200"), "PYG") == "71.200 PYG"
    assert formatear_monto(Decimal("102.5"), "USD") == "102.50 USD"
