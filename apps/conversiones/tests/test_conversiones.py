from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.cajas.models import (
    Caja,
    DenominacionBillete,
    FondoCajero,
    InventarioBilleteCajero,
    MovimientoCaja,
    Sucursal,
)
from apps.cajas.services import proponer_billetes_entrega, registrar_movimiento
from apps.comisiones.models import ComisionCategoria
from apps.cuentas.models import CuentaPago
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio

from apps.conversiones.models import CambioEstado, CompraDivisa, VentaDivisa
from apps.conversiones.services import (
    CompraNoConfirmable,
    VentaNoConfirmable,
    VentaNoDisponible,
    cancelar_compra,
    cancelar_venta,
    calcular_comision,
    calcular_conversion,
    confirmar_pago_compra,
    iniciar_venta,
)


@pytest.fixture
def usuario_cliente(db):
    usuario = get_user_model().objects.create_user(username="cliente-rf017")
    usuario.groups.add(Group.objects.create(name="usuario_cliente"))
    return usuario


@pytest.fixture
def usuario_cajero(db):
    usuario = get_user_model().objects.create_user(username="cajero-rf058")
    usuario.groups.add(Group.objects.get_or_create(name="cajero")[0])
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
        tasa_compra=Decimal("7.10"),
        tasa_venta=Decimal("7.20"),
        vigente_desde=timezone.make_aware(datetime(2026, 9, 6, 10, 0)),
    )


def test_calcula_compra_y_redondea_a_dos_decimales():
    assert calcular_conversion("10", "7.105", "compra") == Decimal("71.05")


def test_calcula_venta_dividiendo_por_la_tasa():
    assert calcular_conversion("72", "7.20", "venta") == Decimal("10.00")


def test_calcula_comision_y_redondea_a_dos_decimales():
    assert calcular_comision("10.01", "2.50") == Decimal("0.25")


@pytest.mark.django_db
def test_simulacion_muestra_resultado(client, usuario_cliente, monedas, tasa):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:simular"), {
        "moneda_origen": monedas[0].pk,
        "moneda_destino": monedas[1].pk,
        "monto": "10.00",
        "tipo_operacion": "compra",
    })

    assert respuesta.status_code == 200
    assert respuesta.context["resultado"]["resultado"] == Decimal("71.00")
    assert TasaCambio.objects.count() == 1


@pytest.mark.django_db
def test_simulacion_rechaza_monedas_iguales(client, usuario_cliente, monedas):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:simular"), {
        "moneda_origen": monedas[0].pk,
        "moneda_destino": monedas[0].pk,
        "monto": "10.00",
        "tipo_operacion": "compra",
    })

    assert respuesta.status_code == 200
    assert "moneda_destino" in respuesta.context["formulario"].errors


@pytest.mark.django_db
def test_usuario_sin_rol_cliente_no_puede_simular(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="sin-rol")
    client.force_login(usuario)

    assert client.get(reverse("conversiones:simular")).status_code == 403


@pytest.fixture
def cliente_asociado(usuario_cliente):
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        categoria=Cliente.Categoria.MINORISTA,
        nombres="Ana",
        apellidos="Gomez",
        documento="1234567",
        email="ana@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )
    AsociacionUsuarioCliente.objects.create(usuario=usuario_cliente, cliente=cliente)
    return cliente


@pytest.fixture
def comision_minorista(db):
    return ComisionCategoria.objects.create(
        categoria=Cliente.Categoria.MINORISTA,
        porcentaje=Decimal("2.50"),
    )


@pytest.fixture
def cuenta_destino(cliente_asociado):
    return CuentaPago.objects.create(
        cliente=cliente_asociado,
        tipo=CuentaPago.Tipo.BANCARIA,
        entidad="Banco Itaú",
        numero_cuenta="00123456789",
        titular="Ana Gomez",
        alias="Cuenta principal",
    )


def cargar_billete(cajero, moneda, valor):
    sucursal, _ = Sucursal.objects.get_or_create(
        es_unica=True,
        defaults={"nombre": "Centro", "direccion": "Centro"},
    )
    caja, _ = Caja.objects.get_or_create(sucursal=sucursal)
    denominacion = DenominacionBillete.objects.create(moneda=moneda, valor=valor)
    registrar_movimiento(
        caja_id=caja.pk,
        tipo=MovimientoCaja.Tipo.INGRESO,
        moneda_id=moneda.pk,
        realizado_por=cajero,
        billetes={denominacion.pk: 1},
    )
    return denominacion


def preparar_desgloses_venta(cajero, venta, importes_entregados=None):
    sucursal, _ = Sucursal.objects.get_or_create(
        es_unica=True,
        defaults={"nombre": "Centro", "direccion": "Centro"},
    )
    caja, _ = Caja.objects.get_or_create(sucursal=sucursal)
    importes_entregados = importes_entregados or [venta.monto_acreditado]
    datos = {}
    denominaciones_entregadas = []

    for importe in importes_entregados:
        denominacion = DenominacionBillete.objects.create(
            moneda=venta.moneda_acreditada,
            valor=importe,
        )
        registrar_movimiento(
            caja_id=caja.pk,
            tipo=MovimientoCaja.Tipo.INGRESO,
            moneda_id=venta.moneda_acreditada_id,
            realizado_por=cajero,
            billetes={denominacion.pk: 1},
        )
        registrar_movimiento(
            caja_id=caja.pk,
            tipo=MovimientoCaja.Tipo.ASIGNACION,
            moneda_id=venta.moneda_acreditada_id,
            cajero_id=cajero.pk,
            realizado_por=cajero,
            billetes={denominacion.pk: 1},
        )
        datos[f"billete_entregado_{denominacion.pk}"] = "1"
        denominaciones_entregadas.append(denominacion)

    denominacion_recibida = DenominacionBillete.objects.create(
        moneda=venta.moneda_entregada,
        valor=venta.monto_entregado,
    )
    datos[f"billete_recibido_{denominacion_recibida.pk}"] = "1"
    return datos, denominaciones_entregadas, denominacion_recibida


@pytest.mark.django_db
def test_cliente_confirma_compra_y_guarda_valores_historicos(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    compra = CompraDivisa.objects.get()
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("conversiones:comprobante_compra", args=[compra.pk])
    assert compra.estado == CompraDivisa.Estado.PENDIENTE
    assert compra.tasa_aplicada == Decimal("7.10")
    assert compra.porcentaje_comision == Decimal("2.50")
    assert compra.monto_comision == Decimal("2.50")
    assert compra.total_a_pagar == Decimal("102.50")
    assert compra.monto_recibido == Decimal("710.00")


@pytest.mark.django_db
def test_compra_requiere_comision_para_la_categoria(
    client, usuario_cliente, cliente_asociado, monedas, tasa
):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    assert respuesta.status_code == 200
    assert "No existe una comisión" in str(respuesta.context["formulario"].non_field_errors())
    assert CompraDivisa.objects.count() == 0


@pytest.mark.django_db
def test_compra_rechaza_tasa_programada_para_el_futuro(
    client, usuario_cliente, cliente_asociado, monedas, comision_minorista
):
    TasaCambio.objects.create(
        moneda_origen=monedas[0],
        moneda_destino=monedas[1],
        tasa_compra=Decimal("7.10"),
        tasa_venta=Decimal("7.20"),
        vigente_desde=timezone.now() + timedelta(days=1),
    )
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    assert respuesta.status_code == 200
    assert "No existe una tasa vigente" in str(respuesta.context["formulario"].non_field_errors())
    assert CompraDivisa.objects.count() == 0


@pytest.mark.django_db
def test_venta_calcula_comision_y_registra_importe_neto(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista, cuenta_destino
):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })

    venta = VentaDivisa.objects.get()
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("conversiones:comprobante_venta", args=[venta.pk])
    assert venta.estado == VentaDivisa.Estado.PENDIENTE
    assert venta.tasa_aplicada == Decimal("7.10")
    assert venta.monto_convertido == Decimal("710.00")
    assert venta.porcentaje_comision == Decimal("2.50")
    assert venta.monto_comision == Decimal("17.75")
    assert venta.monto_acreditado == Decimal("692.25")
    assert venta.cuenta_destino is None


@pytest.mark.django_db
def test_venta_no_permite_usar_cuenta_de_otro_cliente(
    usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    otro_cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Luis",
        apellidos="Lopez",
        documento="7654321",
        email="luis@example.com",
        telefono="0981222222",
        direccion="Asuncion",
    )
    cuenta_ajena = CuentaPago.objects.create(
        cliente=otro_cliente,
        tipo=CuentaPago.Tipo.BILLETERA,
        entidad="Tigo Money",
        numero_cuenta="0981999999",
        titular="Luis Lopez",
    )

    with pytest.raises(VentaNoDisponible, match="no pertenece al cliente"):
        iniciar_venta(
            usuario=usuario_cliente,
            cliente_id=cliente_asociado.pk,
            moneda_entregada=monedas[0],
            moneda_acreditada=monedas[1],
            cuenta_destino=cuenta_ajena,
            monto_entregado="100.00",
        )

    assert VentaDivisa.objects.count() == 0


@pytest.mark.django_db
def test_cliente_no_puede_confirmar_compra_para_otro_cliente(
    client, usuario_cliente, monedas, tasa, comision_minorista
):
    ajeno = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Luis",
        apellidos="Lopez",
        documento="7654321",
        email="luis@example.com",
        telefono="0981222222",
        direccion="Asuncion",
    )
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:comprar"), {
        "cliente": ajeno.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    # Desde RF008 no hay campo "cliente" en el formulario: se opera en
    # nombre del cliente activo. Este usuario no tiene ninguno asociado,
    # así que ni siquiera puede operar.
    assert respuesta.status_code == 302
    assert CompraDivisa.objects.count() == 0


@pytest.mark.django_db
def test_mandar_un_cliente_ajeno_en_el_post_no_tiene_efecto(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    """El id de cliente del POST se ignora: la compra siempre se registra a
    nombre del cliente activo de la sesión (RF008 — GEG9-18)."""
    ajeno = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Luis",
        apellidos="Lopez",
        documento="7654321",
        email="luis@example.com",
        telefono="0981222222",
        direccion="Asuncion",
    )
    client.force_login(usuario_cliente)

    client.post(reverse("conversiones:comprar"), {
        "cliente": ajeno.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    compra = CompraDivisa.objects.get()
    assert compra.cliente == cliente_asociado
    assert compra.cliente != ajeno


# --------------------------------------------------------------------------
# RF051 (GEG9-51) — Cancelación de transacción por cambio de cotización
# --------------------------------------------------------------------------

def _cambiar_cotizacion(tasa_vieja, nueva_compra, nueva_venta):
    """Simula al analista actualizando la tasa: desactiva la vieja y activa otra."""
    tasa_vieja.activo = False
    tasa_vieja.save(update_fields=["activo"])
    return TasaCambio.objects.create(
        moneda_origen=tasa_vieja.moneda_origen,
        moneda_destino=tasa_vieja.moneda_destino,
        tasa_compra=nueva_compra,
        tasa_venta=nueva_venta,
        vigente_desde=timezone.now(),
    )


@pytest.mark.django_db
def test_confirma_el_pago_si_la_cotizacion_no_cambio(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()

    respuesta = client.post(reverse("conversiones:confirmar_compra", args=[compra.pk]))

    compra.refresh_from_db()
    assert respuesta.status_code == 302
    assert compra.estado == CompraDivisa.Estado.CONFIRMADA
    assert compra.confirmado_en is not None


@pytest.mark.django_db
def test_compra_se_cancela_sola_si_la_cotizacion_cambio_antes_de_confirmar(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()

    _cambiar_cotizacion(tasa, Decimal("7.50"), Decimal("7.60"))

    client.post(reverse("conversiones:confirmar_compra", args=[compra.pk]))

    compra.refresh_from_db()
    assert compra.estado == CompraDivisa.Estado.CANCELADA
    assert compra.motivo_cancelacion == CompraDivisa.MotivoCancelacion.CAMBIO_COTIZACION
    assert compra.cancelado_en is not None
    # Los valores originales quedan intactos: no se le cobró la tasa nueva.
    assert compra.tasa_aplicada == Decimal("7.10")


@pytest.mark.django_db
def test_cliente_puede_cancelar_una_compra_pendiente(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()

    client.post(reverse("conversiones:cancelar_compra", args=[compra.pk]))

    compra.refresh_from_db()
    assert compra.estado == CompraDivisa.Estado.CANCELADA
    assert compra.motivo_cancelacion == CompraDivisa.MotivoCancelacion.CLIENTE


@pytest.mark.django_db
def test_no_se_puede_confirmar_una_compra_ya_confirmada(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()
    confirmar_pago_compra(pk=compra.pk, usuario=usuario_cliente)

    with pytest.raises(CompraNoConfirmable):
        confirmar_pago_compra(pk=compra.pk, usuario=usuario_cliente)


@pytest.mark.django_db
def test_otro_usuario_no_puede_confirmar_la_compra_de_otro_cliente(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista, django_user_model
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()

    otro_usuario = django_user_model.objects.create_user(username="otro-cliente-rf051")
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    otro_usuario.groups.add(grupo)

    with pytest.raises(CompraNoConfirmable):
        confirmar_pago_compra(pk=compra.pk, usuario=otro_usuario)


@pytest.mark.django_db
def test_venta_se_cancela_sola_si_la_cotizacion_cambio_antes_de_confirmar(
    client, usuario_cliente, usuario_cajero, cliente_asociado, monedas, tasa,
    comision_minorista, cuenta_destino
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()
    datos_billetes, _entregados, _recibido = preparar_desgloses_venta(
        usuario_cajero, venta
    )

    _cambiar_cotizacion(tasa, Decimal("7.50"), Decimal("7.60"))

    client.force_login(usuario_cajero)
    client.post(
        reverse("conversiones:confirmar_venta", args=[venta.pk]),
        datos_billetes,
    )

    venta.refresh_from_db()
    assert venta.estado == VentaDivisa.Estado.CANCELADA
    assert venta.motivo_cancelacion == VentaDivisa.MotivoCancelacion.CAMBIO_COTIZACION


@pytest.mark.django_db
def test_venta_confirma_el_pago_si_la_cotizacion_no_cambio(
    client, usuario_cliente, usuario_cajero, cliente_asociado, monedas, tasa,
    comision_minorista, cuenta_destino
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()

    datos_billetes, denominaciones_entregadas, denominacion_recibida = (
        preparar_desgloses_venta(usuario_cajero, venta)
    )
    client.force_login(usuario_cajero)
    respuesta = client.post(
        reverse("conversiones:confirmar_venta", args=[venta.pk]),
        datos_billetes,
        follow=True,
    )

    venta.refresh_from_db()
    assert respuesta.status_code == 200
    assert "Volver a ventas pendientes" in respuesta.content.decode()
    assert venta.estado == VentaDivisa.Estado.CONFIRMADA
    assert venta.confirmado_en is not None
    assert venta.monto_efectivo_entregado == venta.monto_acreditado
    fondo_entregado = FondoCajero.objects.get(
        cajero=usuario_cajero, moneda=monedas[1]
    )
    fondo_recibido = FondoCajero.objects.get(
        cajero=usuario_cajero, moneda=monedas[0]
    )
    assert fondo_entregado.saldo == Decimal("0.00")
    assert fondo_recibido.saldo == venta.monto_entregado
    assert not InventarioBilleteCajero.objects.filter(
        denominacion=denominaciones_entregadas[0], cantidad__gt=0
    ).exists()
    assert InventarioBilleteCajero.objects.get(
        cajero=usuario_cajero,
        denominacion=denominacion_recibida,
    ).cantidad == 1
    movimiento_recibido = venta.movimiento_efectivo_recibido
    movimiento_entregado = venta.movimiento_efectivo_entregado
    assert movimiento_recibido.tipo == MovimientoCaja.Tipo.INGRESO_CAJERO
    assert movimiento_recibido.importe == venta.monto_entregado
    assert movimiento_recibido.nota == f"Divisa recibida del cliente por venta #{venta.pk}"
    assert movimiento_entregado.tipo == MovimientoCaja.Tipo.RETIRO_CAJERO
    assert movimiento_entregado.importe == venta.monto_acreditado
    assert movimiento_entregado.nota == f"Efectivo entregado al cliente por venta #{venta.pk}"
    assert movimiento_recibido.cajero == usuario_cajero
    assert movimiento_entregado.cajero == usuario_cajero
    comprobante = client.get(
        reverse("conversiones:comprobante_venta", args=[venta.pk])
    )
    assert str(movimiento_recibido.pk) in comprobante.content.decode()
    assert str(movimiento_entregado.pk) in comprobante.content.decode()

    administrador = get_user_model().objects.create_user(username="admin-traza-rf058")
    administrador.groups.add(Group.objects.get_or_create(name="administrador")[0])
    client.force_login(administrador)
    historial = client.get(reverse("cajas:historial_movimientos"))
    assert historial.status_code == 200
    assert f"Venta #{venta.pk}" in historial.content.decode()


@pytest.mark.django_db
def test_propuesta_usa_el_menor_total_posible_y_no_solo_la_denominacion_mayor(
    usuario_cajero, monedas,
):
    sucursal, _ = Sucursal.objects.get_or_create(
        es_unica=True,
        defaults={"nombre": "Centro", "direccion": "Centro"},
    )
    caja, _ = Caja.objects.get_or_create(sucursal=sucursal)
    billete_10 = DenominacionBillete.objects.create(
        moneda=monedas[1], valor=Decimal("10.00")
    )
    billete_6 = DenominacionBillete.objects.create(
        moneda=monedas[1], valor=Decimal("6.00")
    )
    registrar_movimiento(
        caja_id=caja.pk,
        tipo=MovimientoCaja.Tipo.INGRESO,
        moneda_id=monedas[1].pk,
        realizado_por=usuario_cajero,
        billetes={billete_10.pk: 1, billete_6.pk: 2},
    )

    propuesta = proponer_billetes_entrega(
        caja=caja, moneda=monedas[1], importe=Decimal("12.00")
    )

    assert propuesta["importe_entrega"] == Decimal("12.00")
    assert propuesta["excedente"] == Decimal("0.00")
    assert propuesta["billetes"] == {billete_6.pk: 2}


@pytest.mark.django_db
def test_entrega_acepta_y_guarda_el_excedente_minimo(
    client, usuario_cliente, usuario_cajero, cliente_asociado, monedas, tasa,
    comision_minorista,
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()
    datos, denominaciones, _recibido = preparar_desgloses_venta(
        usuario_cajero,
        venta,
        [
            venta.monto_acreditado + Decimal("0.25"),
            venta.monto_acreditado + Decimal("1.00"),
        ],
    )
    datos.pop(f"billete_entregado_{denominaciones[1].pk}")

    client.force_login(usuario_cajero)
    formulario = client.get(
        reverse("conversiones:confirmar_venta", args=[venta.pk])
    )
    assert formulario.status_code == 200
    assert formulario.context["excedente"] == Decimal("0.25")
    respuesta = client.post(
        reverse("conversiones:confirmar_venta", args=[venta.pk]),
        datos,
    )

    venta.refresh_from_db()
    assert respuesta.status_code == 302
    assert venta.estado == VentaDivisa.Estado.CONFIRMADA
    assert venta.monto_efectivo_entregado == venta.monto_acreditado + Decimal("0.25")
    movimiento = venta.movimiento_efectivo_entregado
    assert movimiento.importe == venta.monto_efectivo_entregado

    client.force_login(usuario_cliente)
    comprobante = client.get(
        reverse("conversiones:comprobante_venta", args=[venta.pk])
    )
    assert comprobante.status_code == 200
    assert "Excedente mínimo por denominaciones: 0,25" in comprobante.content.decode()


@pytest.mark.django_db
def test_no_permite_un_excedente_mayor_que_el_minimo_posible(
    client, usuario_cliente, usuario_cajero, cliente_asociado, monedas, tasa,
    comision_minorista,
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()
    datos, denominaciones, _recibido = preparar_desgloses_venta(
        usuario_cajero,
        venta,
        [
            venta.monto_acreditado + Decimal("0.25"),
            venta.monto_acreditado + Decimal("1.00"),
        ],
    )
    datos.pop(f"billete_entregado_{denominaciones[0].pk}")

    client.force_login(usuario_cajero)
    respuesta = client.post(
        reverse("conversiones:confirmar_venta", args=[venta.pk]),
        datos,
    )

    venta.refresh_from_db()
    assert respuesta.status_code == 200
    assert "supera el importe mínimo posible" in respuesta.content.decode()
    assert venta.estado == VentaDivisa.Estado.PENDIENTE
    assert MovimientoCaja.objects.filter(
        tipo=MovimientoCaja.Tipo.RETIRO_CAJERO
    ).count() == 0


@pytest.mark.django_db
def test_cajero_no_confirma_venta_si_falta_efectivo_en_caja(
    client, usuario_cliente, usuario_cajero, cliente_asociado, monedas, tasa,
    comision_minorista, cuenta_destino,
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()
    billete_disponible = cargar_billete(
        usuario_cajero, monedas[1], Decimal("500.00")
    )
    sucursal = Sucursal.objects.get(es_unica=True)
    caja = Caja.objects.get(sucursal=sucursal)
    registrar_movimiento(
        caja_id=caja.pk,
        tipo=MovimientoCaja.Tipo.ASIGNACION,
        moneda_id=monedas[1].pk,
        cajero_id=usuario_cajero.pk,
        realizado_por=usuario_cajero,
        billetes={billete_disponible.pk: 1},
    )
    billete_solicitado = DenominacionBillete.objects.create(
        moneda=monedas[1], valor=venta.monto_acreditado
    )
    billete_recibido = DenominacionBillete.objects.create(
        moneda=monedas[0], valor=venta.monto_entregado
    )

    client.force_login(usuario_cajero)
    respuesta = client.post(
        reverse("conversiones:confirmar_venta", args=[venta.pk]),
        {
            f"billete_entregado_{billete_solicitado.pk}": "1",
            f"billete_recibido_{billete_recibido.pk}": "1",
        },
    )

    venta.refresh_from_db()
    assert respuesta.status_code == 200
    assert f"Faltan {venta.monto_acreditado - Decimal('500.00')}" in respuesta.content.decode()
    assert venta.estado == VentaDivisa.Estado.PENDIENTE
    assert MovimientoCaja.objects.filter(
        tipo=MovimientoCaja.Tipo.RETIRO_CAJERO
    ).count() == 0


@pytest.mark.django_db
def test_cliente_no_puede_entregar_efectivo_ni_confirmar_una_venta(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista,
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()

    respuesta = client.get(
        reverse("conversiones:confirmar_venta", args=[venta.pk])
    )

    venta.refresh_from_db()
    assert respuesta.status_code == 403
    assert venta.estado == VentaDivisa.Estado.PENDIENTE


@pytest.mark.django_db
def test_cajero_ve_la_cola_de_ventas_pendientes(
    client, usuario_cliente, usuario_cajero, cliente_asociado, monedas, tasa,
    comision_minorista,
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()

    client.force_login(usuario_cajero)
    respuesta = client.get(reverse("conversiones:ventas_pendientes"))

    assert respuesta.status_code == 200
    assert venta in respuesta.context["ventas"]


@pytest.mark.django_db
def test_cliente_puede_cancelar_una_venta_pendiente(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista, cuenta_destino
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()

    client.post(reverse("conversiones:cancelar_venta", args=[venta.pk]))

    venta.refresh_from_db()
    assert venta.estado == VentaDivisa.Estado.CANCELADA
    assert venta.motivo_cancelacion == VentaDivisa.MotivoCancelacion.CLIENTE


@pytest.mark.django_db
def test_no_se_puede_cancelar_una_venta_ya_cancelada(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista, cuenta_destino
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()
    cancelar_venta(pk=venta.pk, usuario=usuario_cliente)

    with pytest.raises(VentaNoConfirmable):
        cancelar_venta(pk=venta.pk, usuario=usuario_cliente)


@pytest.mark.django_db
def test_compra_se_cancela_sola_si_se_vencio_el_plazo_para_confirmar(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()
    compra.creado_en = timezone.now() - timedelta(minutes=16)
    compra.save(update_fields=["creado_en"])

    client.post(reverse("conversiones:confirmar_compra", args=[compra.pk]))

    compra.refresh_from_db()
    assert compra.estado == CompraDivisa.Estado.CANCELADA
    assert compra.motivo_cancelacion == CompraDivisa.MotivoCancelacion.EXPIRADA


@pytest.mark.django_db
def test_ver_una_compra_vencida_la_muestra_ya_cancelada(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()
    compra.creado_en = timezone.now() - timedelta(minutes=16)
    compra.save(update_fields=["creado_en"])

    respuesta = client.get(reverse("conversiones:comprobante_compra", args=[compra.pk]))

    assert respuesta.context["compra"].estado == CompraDivisa.Estado.CANCELADA
    assert respuesta.context["compra"].motivo_cancelacion == CompraDivisa.MotivoCancelacion.EXPIRADA


@pytest.mark.django_db
def test_venta_se_cancela_sola_si_se_vencio_el_plazo_para_confirmar(
    client, usuario_cliente, usuario_cajero, cliente_asociado, monedas, tasa,
    comision_minorista, cuenta_destino
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()
    venta.creado_en = timezone.now() - timedelta(minutes=16)
    venta.save(update_fields=["creado_en"])

    client.force_login(usuario_cajero)
    client.post(
        reverse("conversiones:confirmar_venta", args=[venta.pk]),
        {},
    )

    venta.refresh_from_db()
    assert venta.estado == VentaDivisa.Estado.CANCELADA
    assert venta.motivo_cancelacion == VentaDivisa.MotivoCancelacion.EXPIRADA


@pytest.mark.django_db
def test_comprar_prellena_el_formulario_desde_el_boton_repetir(
    client, usuario_cliente, cliente_asociado, monedas
):
    client.force_login(usuario_cliente)

    respuesta = client.get(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    formulario = respuesta.context["formulario"]
    assert formulario.initial.get("cliente") == str(cliente_asociado.pk)
    assert formulario.initial.get("moneda_pagada") == str(monedas[0].pk)
    assert formulario.initial.get("monto_pagado") == "100.00"


@pytest.mark.django_db
def test_vender_prellena_el_formulario_desde_el_boton_repetir(
    client, usuario_cliente, cliente_asociado, monedas, cuenta_destino
):
    client.force_login(usuario_cliente)

    respuesta = client.get(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })

    formulario = respuesta.context["formulario"]
    assert "cuenta_destino" not in formulario.fields
    assert formulario.initial.get("monto_entregado") == "100.00"


@pytest.mark.django_db
def test_comprobante_de_compra_cancelada_ofrece_repetir_la_operacion(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()
    cancelar_compra(pk=compra.pk, usuario=usuario_cliente)

    respuesta = client.get(reverse("conversiones:comprobante_compra", args=[compra.pk]))

    contenido = respuesta.content.decode()
    assert "Repetir esta operación" in contenido
    assert f"monto_pagado={compra.monto_pagado}" in contenido.replace("&amp;", "&")

# --------------------------------------------------------------------------
# RF030 (GEG9-34) — Consulta de historial de transacciones
# --------------------------------------------------------------------------

@pytest.mark.django_db
def test_historial_muestra_solo_transacciones_confirmadas(
    client,
    usuario_cliente,
    usuario_cajero,
    cliente_asociado,
    monedas,
    tasa,
    comision_minorista,
    cuenta_destino,
):
    client.force_login(usuario_cliente)

    # Compra confirmada.
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra_confirmada = CompraDivisa.objects.get(
        estado=CompraDivisa.Estado.PENDIENTE
    )
    client.post(
        reverse("conversiones:confirmar_compra", args=[compra_confirmada.pk])
    )

    # Venta confirmada.
    client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })
    venta_confirmada = VentaDivisa.objects.get(
        estado=VentaDivisa.Estado.PENDIENTE
    )
    datos_billetes, _denominaciones_entregadas, _recibida = (
        preparar_desgloses_venta(usuario_cajero, venta_confirmada)
    )
    client.force_login(usuario_cajero)
    client.post(
        reverse("conversiones:confirmar_venta", args=[venta_confirmada.pk]),
        datos_billetes,
    )
    client.force_login(usuario_cliente)

    # Una operación pendiente no debe aparecer.
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "50.00",
    })
    compra_pendiente = CompraDivisa.objects.get(
        estado=CompraDivisa.Estado.PENDIENTE
    )

    # Una operación cancelada tampoco debe aparecer.
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "25.00",
    })
    compra_cancelada = (
        CompraDivisa.objects.filter(
            estado=CompraDivisa.Estado.PENDIENTE
        )
    .order_by("-pk")
    .first()
    )
    client.post(
        reverse("conversiones:cancelar_compra", args=[compra_cancelada.pk])
    )

    respuesta = client.get(reverse("conversiones:historial"))

    assert respuesta.status_code == 200

    transacciones = respuesta.context["transacciones"]
    identificadores = {
        (transaccion["tipo"], transaccion["id"])
        for transaccion in transacciones
    }

    assert identificadores == {
        ("Compra", compra_confirmada.pk),
        ("Venta", venta_confirmada.pk),
    }
    assert ("Compra", compra_pendiente.pk) not in identificadores
    assert ("Compra", compra_cancelada.pk) not in identificadores


@pytest.mark.django_db
def test_historial_no_muestra_transacciones_de_otro_cliente(
    client,
    usuario_cliente,
    cliente_asociado,
    monedas,
    tasa,
    comision_minorista,
    django_user_model,
):
    otro_usuario = django_user_model.objects.create_user(
        username="otro-cliente-historial"
    )
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    otro_usuario.groups.add(grupo)

    otro_cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        categoria=Cliente.Categoria.MINORISTA,
        nombres="Luis",
        apellidos="Lopez",
        documento="9876543",
        email="luis@example.com",
        telefono="0981222222",
        direccion="Asuncion",
    )
    AsociacionUsuarioCliente.objects.create(
        usuario=otro_usuario,
        cliente=otro_cliente,
    )

    compra_ajena = CompraDivisa.objects.create(
        cliente=otro_cliente,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        tasa_cambio=tasa,
        monto_pagado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("2.50"),
        total_a_pagar=Decimal("102.50"),
        tasa_aplicada=Decimal("7.10"),
        monto_recibido=Decimal("710.00"),
        estado=CompraDivisa.Estado.CONFIRMADA,
        confirmado_en=timezone.now(),
    )

    client.force_login(usuario_cliente)
    respuesta = client.get(reverse("conversiones:historial"))

    assert respuesta.status_code == 200
    assert compra_ajena.pk not in {
        transaccion["id"]
        for transaccion in respuesta.context["transacciones"]
    }


@pytest.mark.django_db
def test_usuario_sin_rol_cliente_no_puede_consultar_historial(
    client, django_user_model
):
    usuario = django_user_model.objects.create_user(
        username="sin-rol-historial"
    )
    client.force_login(usuario)

    respuesta = client.get(reverse("conversiones:historial"))

    assert respuesta.status_code == 403


# --------------------------------------------------------------------------
# RF023 (GEG9-37) — Trazabilidad de estados
# --------------------------------------------------------------------------

@pytest.mark.django_db
def test_iniciar_compra_registra_la_transicion_nada_a_pendiente(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()

    cambios = list(CambioEstado.objects.filter(compra=compra))
    assert len(cambios) == 1
    assert cambios[0].estado_anterior == ""
    assert cambios[0].estado_nuevo == CompraDivisa.Estado.PENDIENTE
    assert cambios[0].venta is None


@pytest.mark.django_db
def test_iniciar_venta_registra_la_transicion_nada_a_pendiente(
    client, usuario_cliente, cliente_asociado, monedas, cuenta_destino, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })
    venta = VentaDivisa.objects.get()

    cambios = list(CambioEstado.objects.filter(venta=venta))
    assert len(cambios) == 1
    assert cambios[0].estado_anterior == ""
    assert cambios[0].estado_nuevo == VentaDivisa.Estado.PENDIENTE
    assert cambios[0].compra is None


@pytest.mark.django_db
def test_confirmar_pago_registra_la_transicion_pendiente_a_confirmada(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()

    confirmar_pago_compra(pk=compra.pk, usuario=usuario_cliente)

    cambio = CambioEstado.objects.filter(compra=compra).latest("fecha")
    assert cambio.estado_anterior == CompraDivisa.Estado.PENDIENTE
    assert cambio.estado_nuevo == CompraDivisa.Estado.CONFIRMADA
    assert cambio.usuario == usuario_cliente


@pytest.mark.django_db
def test_cancelar_por_cliente_registra_el_motivo(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()

    cancelar_compra(pk=compra.pk, usuario=usuario_cliente)

    cambio = CambioEstado.objects.filter(compra=compra).latest("fecha")
    assert cambio.estado_anterior == CompraDivisa.Estado.PENDIENTE
    assert cambio.estado_nuevo == CompraDivisa.Estado.CANCELADA
    assert cambio.motivo == "Cancelada por el cliente."
    assert cambio.usuario == usuario_cliente


@pytest.mark.django_db
def test_cancelar_por_cambio_de_cotizacion_registra_el_motivo(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()
    _cambiar_cotizacion(tasa, Decimal("7.50"), Decimal("7.60"))

    confirmar_pago_compra(pk=compra.pk, usuario=usuario_cliente)

    cambio = CambioEstado.objects.filter(compra=compra).latest("fecha")
    assert cambio.estado_anterior == CompraDivisa.Estado.PENDIENTE
    assert cambio.estado_nuevo == CompraDivisa.Estado.CANCELADA
    assert cambio.motivo == "La cotización cambió antes de confirmar."


@pytest.mark.django_db
def test_cancelar_por_expiracion_registra_el_motivo(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()
    compra.creado_en = timezone.now() - timedelta(minutes=16)
    compra.save(update_fields=["creado_en"])

    confirmar_pago_compra(pk=compra.pk, usuario=usuario_cliente)

    cambio = CambioEstado.objects.filter(compra=compra).latest("fecha")
    assert cambio.estado_anterior == CompraDivisa.Estado.PENDIENTE
    assert cambio.estado_nuevo == CompraDivisa.Estado.CANCELADA
    assert cambio.motivo == "Se venció el tiempo para confirmar."
    assert cambio.usuario is None


@pytest.mark.django_db
def test_cambio_estado_rechaza_un_registro_sin_operacion():
    with pytest.raises(IntegrityError):
        CambioEstado.objects.create(estado_anterior="", estado_nuevo="PENDIENTE")


@pytest.mark.django_db
def test_cambio_estado_rechaza_un_registro_con_las_dos_operaciones(
    cliente_asociado, monedas, tasa, comision_minorista, cuenta_destino
):
    compra = CompraDivisa.objects.create(
        cliente=cliente_asociado,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        tasa_cambio=tasa,
        monto_pagado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("2.50"),
        total_a_pagar=Decimal("102.50"),
        tasa_aplicada=Decimal("7.10"),
        monto_recibido=Decimal("710.00"),
    )
    venta = VentaDivisa.objects.create(
        cliente=cliente_asociado,
        moneda_entregada=monedas[0],
        moneda_acreditada=monedas[1],
        tasa_cambio=tasa,
        cuenta_destino=cuenta_destino,
        monto_entregado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("2.50"),
        monto_convertido=Decimal("710.00"),
        monto_acreditado=Decimal("707.50"),
        tasa_aplicada=Decimal("7.10"),
    )

    with pytest.raises(IntegrityError):
        CambioEstado.objects.create(
            compra=compra, venta=venta, estado_anterior="", estado_nuevo="PENDIENTE"
        )


@pytest.mark.django_db
def test_comprobante_de_compra_muestra_la_linea_de_tiempo(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()
    confirmar_pago_compra(pk=compra.pk, usuario=usuario_cliente)

    respuesta = client.get(reverse("conversiones:comprobante_compra", args=[compra.pk]))

    assert "Línea de tiempo" in respuesta.content.decode()
    assert "Pagada" in respuesta.content.decode()


@pytest.mark.django_db
def test_comprobante_no_lo_puede_ver_un_usuario_que_no_es_dueno_de_la_operacion(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista,
    django_user_model,
):
    client.force_login(usuario_cliente)
    client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })
    compra = CompraDivisa.objects.get()

    otro_usuario = django_user_model.objects.create_user(username="otro-cliente-rf023")
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    otro_usuario.groups.add(grupo)
    client.force_login(otro_usuario)

    respuesta = client.get(reverse("conversiones:comprobante_compra", args=[compra.pk]))

    assert respuesta.status_code == 404