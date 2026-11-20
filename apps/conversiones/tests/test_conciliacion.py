"""Pruebas de RF025 — Conciliación Manual (GEG9-75).

La idea de fondo que se verifica acá es que conciliar **no es un camino
paralelo**: usa el mismo núcleo que el pago normal, así que dispara la
factura (RF026), el historial de estados (RF023) y la revalidación de tasa
(RF051) exactamente igual.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CambioEstado, CompraDivisa
from apps.conversiones.services import (
    ConciliacionNoPermitida,
    compras_pendientes_de_conciliar,
    conciliar_compra,
    iniciar_compra,
)
from apps.facturacion.models import Factura
from apps.monedas.models import Moneda
from apps.pagos.models import Pago
from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.models import RegistroAuditoria


def _usuario(django_user_model, username, rol):
    usuario = django_user_model.objects.create_user(
        username=username, email=f"{username}@example.com"
    )
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    return usuario


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
def administrador(django_user_model):
    return _usuario(django_user_model, "admin-concilia", "administrador")


@pytest.fixture
def cliente_y_usuario(django_user_model):
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Ana",
        apellidos="Gomez",
        documento="1234567",
        email="ana@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )
    usuario = _usuario(django_user_model, "cliente-concilia", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)
    return cliente, usuario


@pytest.fixture
def compra_por_transferencia(cliente_y_usuario, monedas, tasa, comision):
    """Compra pendiente que el cliente marcó para pagar por transferencia."""
    cliente, usuario = cliente_y_usuario
    compra = iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )
    compra.espera_transferencia = True
    compra.save(update_fields=["espera_transferencia"])
    return compra


# ---------------------------------------------------------------------------
# El camino feliz
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_conciliar_confirma_la_compra_y_emite_la_factura(
    administrador, compra_por_transferencia, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        compra = conciliar_compra(
            pk=compra_por_transferencia.pk,
            usuario=administrador,
            referencia="TRF-998877",
        )

    assert compra.estado == CompraDivisa.Estado.CONFIRMADA
    assert compra.confirmado_en is not None
    # La factura sale por el mismo camino que en un pago con tarjeta.
    factura = Factura.objects.get(compra=compra)
    assert factura.estado == Factura.Estado.GENERADA


@pytest.mark.django_db
def test_queda_registrado_quien_concilio_y_con_que_referencia(
    administrador, compra_por_transferencia
):
    conciliar_compra(
        pk=compra_por_transferencia.pk,
        usuario=administrador,
        referencia="TRF-998877",
        observacion="Verificado en el extracto del Itau.",
    )

    cambio = CambioEstado.objects.filter(
        compra=compra_por_transferencia,
        estado_nuevo=CompraDivisa.Estado.CONFIRMADA,
    ).get()
    assert cambio.usuario == administrador
    assert "TRF-998877" in cambio.motivo
    assert "Itau" in cambio.motivo


@pytest.mark.django_db
def test_se_registra_un_pago_manual_con_la_referencia(
    administrador, compra_por_transferencia
):
    conciliar_compra(
        pk=compra_por_transferencia.pk,
        usuario=administrador,
        referencia="TRF-998877",
    )

    pago = Pago.objects.get(compra=compra_por_transferencia)
    assert pago.proveedor == "manual"
    assert pago.estado == Pago.Estado.APROBADO
    assert pago.id_externo == "TRF-998877"
    # El importe es el que transfirió el cliente, en la moneda de la
    # operación: acá no hubo pasarela que convierta nada.
    assert pago.monto == compra_por_transferencia.total_a_pagar
    assert pago.moneda == "USD"
    assert pago.respuesta_cruda["conciliado_por"] == administrador.get_username()


# ---------------------------------------------------------------------------
# Lo que no se puede conciliar
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_se_puede_conciliar_una_compra_cancelada(
    administrador, cliente_y_usuario, compra_por_transferencia
):
    from apps.conversiones.services import cancelar_compra

    _cliente, usuario = cliente_y_usuario
    cancelar_compra(pk=compra_por_transferencia.pk, usuario=usuario)

    with pytest.raises(ConciliacionNoPermitida, match="ya no está pendiente"):
        conciliar_compra(
            pk=compra_por_transferencia.pk,
            usuario=administrador,
            referencia="TRF-1",
        )

    assert Pago.objects.count() == 0


@pytest.mark.django_db
def test_conciliar_dos_veces_no_duplica_nada(administrador, compra_por_transferencia):
    conciliar_compra(
        pk=compra_por_transferencia.pk, usuario=administrador, referencia="TRF-1"
    )

    with pytest.raises(ConciliacionNoPermitida, match="ya no está pendiente"):
        conciliar_compra(
            pk=compra_por_transferencia.pk, usuario=administrador, referencia="TRF-2"
        )

    assert Pago.objects.filter(compra=compra_por_transferencia).count() == 1
    assert Factura.objects.filter(compra=compra_por_transferencia).count() <= 1
    assert (
        CambioEstado.objects.filter(
            compra=compra_por_transferencia,
            estado_nuevo=CompraDivisa.Estado.CONFIRMADA,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_la_referencia_es_obligatoria(administrador, compra_por_transferencia):
    with pytest.raises(ConciliacionNoPermitida, match="referencia"):
        conciliar_compra(
            pk=compra_por_transferencia.pk, usuario=administrador, referencia="   "
        )

    compra_por_transferencia.refresh_from_db()
    assert compra_por_transferencia.estado == CompraDivisa.Estado.PENDIENTE
    assert Pago.objects.count() == 0


@pytest.mark.django_db
def test_si_la_cotizacion_cambio_no_se_concilia(
    administrador, compra_por_transferencia, monedas, tasa
):
    """RF051 sigue valiendo: no se confirma con una tasa distinta."""
    tasa.activo = False
    tasa.save(update_fields=["activo"])
    TasaCambio.objects.create(
        moneda_origen=monedas[0],
        moneda_destino=monedas[1],
        tasa_compra=Decimal("7500.00"),
        tasa_venta=Decimal("7600.00"),
        vigente_desde=timezone.now(),
    )

    # No lanza: devuelve la compra ya cancelada. Si lanzara, la transacción
    # revertiría la cancelación que acaba de hacer RF051.
    compra = conciliar_compra(
        pk=compra_por_transferencia.pk,
        usuario=administrador,
        referencia="TRF-1",
    )

    assert compra.estado == CompraDivisa.Estado.CANCELADA
    assert compra.motivo_cancelacion == CompraDivisa.MotivoCancelacion.CAMBIO_COTIZACION
    compra_por_transferencia.refresh_from_db()
    assert compra_por_transferencia.estado == CompraDivisa.Estado.CANCELADA
    assert Pago.objects.count() == 0


# ---------------------------------------------------------------------------
# La compra por transferencia no se vence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_compra_por_transferencia_no_se_vence(compra_por_transferencia, administrador):
    """Sin esto la conciliación no serviría: 15 minutos no alcanzan."""
    from apps.conversiones.services import expirar_compra_si_corresponde

    compra_por_transferencia.creado_en = timezone.now() - timezone.timedelta(days=2)
    compra_por_transferencia.save(update_fields=["creado_en"])

    compra = expirar_compra_si_corresponde(compra_por_transferencia)

    assert compra.estado == CompraDivisa.Estado.PENDIENTE
    # Y se puede conciliar dos días después.
    conciliada = conciliar_compra(
        pk=compra.pk, usuario=administrador, referencia="TRF-1"
    )
    assert conciliada.estado == CompraDivisa.Estado.CONFIRMADA


@pytest.mark.django_db
def test_una_compra_normal_sigue_venciendo(cliente_y_usuario, monedas, tasa, comision):
    from apps.conversiones.services import expirar_compra_si_corresponde

    cliente, usuario = cliente_y_usuario
    compra = iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )
    compra.creado_en = timezone.now() - timezone.timedelta(hours=2)
    compra.save(update_fields=["creado_en"])

    compra = expirar_compra_si_corresponde(compra)

    assert compra.estado == CompraDivisa.Estado.CANCELADA
    assert compra.motivo_cancelacion == CompraDivisa.MotivoCancelacion.EXPIRADA


@pytest.mark.django_db
def test_la_lista_solo_trae_las_que_esperan_transferencia(
    compra_por_transferencia, cliente_y_usuario, monedas, tasa, comision
):
    cliente, usuario = cliente_y_usuario
    iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="50.00",
    )

    pendientes = list(compras_pendientes_de_conciliar())

    assert pendientes == [compra_por_transferencia]


# ---------------------------------------------------------------------------
# Acceso: solo administrador
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_el_servicio_rechaza_a_quien_no_es_administrador(
    cliente_y_usuario, compra_por_transferencia
):
    _cliente, usuario = cliente_y_usuario

    with pytest.raises(ConciliacionNoPermitida, match="Solo un administrador"):
        conciliar_compra(
            pk=compra_por_transferencia.pk, usuario=usuario, referencia="TRF-1"
        )

    assert Pago.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("vista,args", [
    ("conversiones:conciliaciones", []),
    ("conversiones:conciliar", [1]),
])
def test_un_no_administrador_recibe_403(client, cliente_y_usuario, vista, args):
    _cliente, usuario = cliente_y_usuario
    client.force_login(usuario)

    url = reverse(vista, args=args)
    assert client.get(url).status_code == 403
    assert client.post(url, {}).status_code == 403


@pytest.mark.django_db
def test_el_administrador_concilia_desde_la_pantalla(
    client, administrador, compra_por_transferencia
):
    client.force_login(administrador)

    respuesta = client.post(
        reverse("conversiones:conciliar", args=[compra_por_transferencia.pk]),
        {"referencia": "TRF-555", "observacion": "ok"},
    )

    compra_por_transferencia.refresh_from_db()
    assert respuesta.url == reverse("conversiones:conciliaciones")
    assert compra_por_transferencia.estado == CompraDivisa.Estado.CONFIRMADA
    assert Pago.objects.get(compra=compra_por_transferencia).id_externo == "TRF-555"
    assert RegistroAuditoria.objects.get().accion == (
        RegistroAuditoria.Accion.COMPRA_CONCILIADA
    )


@pytest.mark.django_db
def test_la_pantalla_exige_la_referencia(client, administrador, compra_por_transferencia):
    client.force_login(administrador)

    respuesta = client.post(
        reverse("conversiones:conciliar", args=[compra_por_transferencia.pk]),
        {"referencia": "", "observacion": ""},
    )

    compra_por_transferencia.refresh_from_db()
    assert respuesta.status_code == 200
    assert compra_por_transferencia.estado == CompraDivisa.Estado.PENDIENTE


@pytest.mark.django_db
def test_un_fallo_de_la_facturacion_no_deshace_la_conciliacion(
    administrador, compra_por_transferencia, django_capture_on_commit_callbacks
):
    """RNF011: la operación queda confirmada aunque la factura falle."""
    with patch(
        "apps.facturacion.services.emitir_factura",
        side_effect=RuntimeError("Factura Segura caida"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            compra = conciliar_compra(
                pk=compra_por_transferencia.pk,
                usuario=administrador,
                referencia="TRF-1",
            )

    compra.refresh_from_db()
    assert compra.estado == CompraDivisa.Estado.CONFIRMADA
    assert Pago.objects.filter(compra=compra).count() == 1


@pytest.mark.django_db
def test_un_administrador_con_cliente_asociado_llega_igual_a_conciliar(
    client, administrador, compra_por_transferencia
):
    """Caso borde de RF008: la pantalla vive bajo /conversiones/.

    El middleware del cliente activo intercepta todo ese prefijo y manda a
    elegir cliente a quien tenga clientes y no haya elegido. Un administrador
    que además esté asociado a algún cliente quedaría atrapado ahí sin poder
    conciliar nunca.
    """
    otro = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Otro",
        apellidos="Cliente",
        documento="5555555",
        email="otro@example.com",
        telefono="0981555555",
        direccion="Asuncion",
    )
    AsociacionUsuarioCliente.objects.create(usuario=administrador, cliente=otro)
    # Dos clientes: con uno solo se autoselecciona y no habria redireccion.
    AsociacionUsuarioCliente.objects.create(
        usuario=administrador,
        cliente=compra_por_transferencia.cliente,
    )
    client.force_login(administrador)

    respuesta = client.get(reverse("conversiones:conciliaciones"))

    assert respuesta.status_code == 200
