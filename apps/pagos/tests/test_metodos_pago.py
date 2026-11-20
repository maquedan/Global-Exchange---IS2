"""Pruebas de RF035 — Configuración de Pagos (GEG9-77).

Lo que más importa acá es el punto 5 del ERS: deshabilitar un método **no
puede trabar** las operaciones que ya lo estaban usando. El cliente que
transfirió el dinero tiene que poder confirmar o cancelar igual.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CompraDivisa
from apps.conversiones.services import cancelar_compra, iniciar_compra
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio

from apps.pagos import services
from apps.pagos.models import CambioMetodoPago, MetodoPago, Pago
from apps.pagos.services import (
    CODIGO_TARJETA,
    CODIGO_TRANSFERENCIA,
    MetodoPagoNoDisponible,
)
from apps.pagos.tests.test_pagos import ProveedorFalso


def _usuario(django_user_model, username, rol):
    usuario = django_user_model.objects.create_user(
        username=username, email=f"{username}@example.com"
    )
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    return usuario


@pytest.fixture
def administrador(db, django_user_model):
    return _usuario(django_user_model, "admin-metodos", "administrador")


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
def cliente_y_usuario(db, django_user_model):
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Ana",
        apellidos="Gomez",
        documento="1234567",
        email="ana@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )
    usuario = _usuario(django_user_model, "cliente-metodos", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)
    return cliente, usuario


@pytest.fixture
def compra(cliente_y_usuario, monedas, tasa, comision):
    cliente, usuario = cliente_y_usuario
    return iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )


def _apagar(codigo, usuario=None):
    return services.cambiar_estado_metodo(
        codigo=codigo, habilitado=False, usuario=usuario
    )


# ---------------------------------------------------------------------------
# La migración de datos
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_existen_los_dos_metodos_que_ya_funcionaban():
    """Solo los que tienen código detrás: nada de botones que no hacen nada."""
    codigos = set(MetodoPago.objects.values_list("codigo", flat=True))

    assert codigos == {CODIGO_TARJETA, CODIGO_TRANSFERENCIA}
    assert MetodoPago.objects.filter(habilitado=True).count() == 2


# ---------------------------------------------------------------------------
# Habilitar y deshabilitar
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_deshabilitar_y_volver_a_habilitar(administrador):
    services.cambiar_estado_metodo(
        codigo=CODIGO_TARJETA, habilitado=False, usuario=administrador
    )
    assert MetodoPago.objects.get(codigo=CODIGO_TARJETA).habilitado is False

    services.cambiar_estado_metodo(
        codigo=CODIGO_TARJETA, habilitado=True, usuario=administrador
    )
    assert MetodoPago.objects.get(codigo=CODIGO_TARJETA).habilitado is True


@pytest.mark.django_db
def test_queda_registro_de_quien_y_cuando(administrador):
    services.cambiar_estado_metodo(
        codigo=CODIGO_TARJETA, habilitado=False, usuario=administrador
    )

    cambio = CambioMetodoPago.objects.get()
    assert cambio.metodo.codigo == CODIGO_TARJETA
    assert cambio.habilitado is False
    assert cambio.usuario == administrador
    assert cambio.fecha is not None


@pytest.mark.django_db
def test_el_historial_guarda_todos_los_cambios(administrador):
    """Si guardara solo el último, el primero se perdería."""
    for habilitado in (False, True, False):
        services.cambiar_estado_metodo(
            codigo=CODIGO_TARJETA, habilitado=habilitado, usuario=administrador
        )

    assert CambioMetodoPago.objects.filter(metodo__codigo=CODIGO_TARJETA).count() == 3


@pytest.mark.django_db
def test_no_registra_un_cambio_que_no_ocurrio(administrador):
    """Deshabilitar algo ya deshabilitado no es un cambio."""
    _apagar(CODIGO_TARJETA, administrador)
    _apagar(CODIGO_TARJETA, administrador)

    assert CambioMetodoPago.objects.count() == 1


# ---------------------------------------------------------------------------
# Lo que ve y puede hacer el cliente
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_el_metodo_deshabilitado_no_aparece_al_pagar(
    client, cliente_y_usuario, compra, administrador
):
    _cliente, usuario = cliente_y_usuario
    _apagar(CODIGO_TRANSFERENCIA, administrador)
    client.force_login(usuario)

    html = client.get(reverse("pagos:elegir_pago", args=[compra.pk])).content.decode()

    assert "Tarjeta" in html
    assert "Transferencia bancaria" not in html


@pytest.mark.django_db
def test_no_se_puede_iniciar_un_pago_con_la_tarjeta_deshabilitada(
    cliente_y_usuario, compra, administrador
):
    """Aunque se fuerce el POST sin pasar por la pantalla."""
    _cliente, usuario = cliente_y_usuario
    _apagar(CODIGO_TARJETA, administrador)

    with pytest.raises(MetodoPagoNoDisponible):
        services.iniciar_pago(compra.pk, usuario=usuario)

    assert Pago.objects.count() == 0


@pytest.mark.django_db
def test_no_se_puede_elegir_transferencia_deshabilitada(
    client, cliente_y_usuario, compra, administrador
):
    _cliente, usuario = cliente_y_usuario
    _apagar(CODIGO_TRANSFERENCIA, administrador)
    client.force_login(usuario)

    client.post(reverse("pagos:esperar_transferencia", args=[compra.pk]))

    compra.refresh_from_db()
    assert compra.espera_transferencia is False


@pytest.mark.django_db
def test_sin_ningun_metodo_habilitado_avisa_y_no_rompe(
    client, cliente_y_usuario, compra, administrador
):
    _cliente, usuario = cliente_y_usuario
    _apagar(CODIGO_TARJETA, administrador)
    _apagar(CODIGO_TRANSFERENCIA, administrador)
    client.force_login(usuario)

    respuesta = client.get(reverse("pagos:elegir_pago", args=[compra.pk]))

    assert respuesta.status_code == 200
    assert "No hay ningún método de pago disponible" in respuesta.content.decode()


# ---------------------------------------------------------------------------
# El punto delicado: no trabar lo que ya estaba en curso
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_un_pago_ya_iniciado_se_puede_confirmar_aunque_apaguen_el_metodo(
    cliente_y_usuario, compra, administrador
):
    """El cliente ya pagó: dejarlo trabado sería quedarse con su plata."""
    _cliente, usuario = cliente_y_usuario
    falso = ProveedorFalso(estado_crear="PENDIENTE", estado_consultar="APROBADO")

    with patch("apps.pagos.services._instancia_proveedor", return_value=falso):
        pago = services.iniciar_pago(compra.pk, usuario=usuario)
        _apagar(CODIGO_TARJETA, administrador)
        pago = services.confirmar_pago(pago, usuario=usuario)

    compra.refresh_from_db()
    assert pago.estado == Pago.Estado.APROBADO
    assert compra.estado == CompraDivisa.Estado.CONFIRMADA


@pytest.mark.django_db
def test_una_compra_esperando_transferencia_se_puede_cancelar(
    client, cliente_y_usuario, compra, administrador
):
    _cliente, usuario = cliente_y_usuario
    client.force_login(usuario)
    client.post(reverse("pagos:esperar_transferencia", args=[compra.pk]))
    compra.refresh_from_db()
    assert compra.espera_transferencia is True

    _apagar(CODIGO_TRANSFERENCIA, administrador)

    cancelar_compra(pk=compra.pk, usuario=usuario)

    compra.refresh_from_db()
    assert compra.estado == CompraDivisa.Estado.CANCELADA


@pytest.mark.django_db
def test_una_transferencia_pendiente_se_puede_conciliar_igual(
    cliente_y_usuario, compra, administrador
):
    """Lo mismo del lado del administrador: la conciliación de RF025 sigue."""
    from apps.conversiones.services import conciliar_compra

    _cliente, _usuario = cliente_y_usuario
    compra.espera_transferencia = True
    compra.save(update_fields=["espera_transferencia"])
    _apagar(CODIGO_TRANSFERENCIA, administrador)

    conciliada = conciliar_compra(
        pk=compra.pk, usuario=administrador, referencia="TRF-1"
    )

    assert conciliada.estado == CompraDivisa.Estado.CONFIRMADA


# ---------------------------------------------------------------------------
# Acceso
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "vista,args,metodo",
    [
        ("pagos:metodos", [], "GET"),
        ("pagos:cambiar_metodo", ["tarjeta"], "POST"),
    ],
)
def test_un_no_administrador_recibe_403(client, cliente_y_usuario, vista, args, metodo):
    _cliente, usuario = cliente_y_usuario
    client.force_login(usuario)
    url = reverse(vista, args=args)

    respuesta = client.post(url, {}) if metodo == "POST" else client.get(url)

    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_el_administrador_cambia_el_estado_desde_la_pantalla(client, administrador):
    client.force_login(administrador)

    client.post(
        reverse("pagos:cambiar_metodo", args=[CODIGO_TARJETA]), {"habilitado": "0"}
    )

    assert MetodoPago.objects.get(codigo=CODIGO_TARJETA).habilitado is False
    assert CambioMetodoPago.objects.get().usuario == administrador


@pytest.mark.django_db
def test_cambiar_el_estado_exige_post(client, administrador):
    """Cambiar configuración del negocio no puede hacerse con un GET."""
    client.force_login(administrador)

    respuesta = client.get(reverse("pagos:cambiar_metodo", args=[CODIGO_TARJETA]))

    assert respuesta.status_code == 405
    assert MetodoPago.objects.get(codigo=CODIGO_TARJETA).habilitado is True
