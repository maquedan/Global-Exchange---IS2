from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.cajas.models import Caja, MovimientoCaja, SaldoCaja
from apps.cajas.services import (
    MovimientoNoPermitido,
    proponer_billetes_entrega,
    registrar_movimiento,
)
from apps.clientes.models import Cliente
from apps.comisiones.models import ComisionCategoria
from apps.cuentas.models import CuentaPago
from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.services import cliente_habilitado_para

from .models import CambioEstado, CompraDivisa, VentaDivisa


DOS_DECIMALES = Decimal("0.01")

# Tiempo que un cliente tiene para confirmar el pago antes de que la operación
# pendiente se cancele sola: una cotización vieja no debería quedar disponible
# para confirmar indefinidamente (RF051 — GEG9-51).
MINUTOS_EXPIRACION_PENDIENTE = 15


def _vencio_el_plazo(operacion):
    limite = operacion.creado_en + timedelta(minutes=MINUTOS_EXPIRACION_PENDIENTE)
    return timezone.now() > limite


def registrar_cambio_estado(operacion, estado_anterior, estado_nuevo, *, motivo="", usuario=None):
    """Deja constancia de una transición de estado (RF023 — GEG9-37).

    `estado_anterior` vacío significa que la operación recién se crea (todavía
    no tenía ningún estado previo). Todo cambio de `.estado` en este archivo
    debe pasar por acá, para que el historial quede completo.
    """
    campo_operacion = "compra" if isinstance(operacion, CompraDivisa) else "venta"
    return CambioEstado.objects.create(
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        motivo=motivo,
        usuario=usuario,
        **{campo_operacion: operacion},
    )


def _facturar(operacion):
    """Agenda la emisión de la factura electrónica de la operación (RF026).

    El import va acá adentro y no arriba porque `apps.facturacion` importa
    los modelos de esta app: hacerlo a nivel de módulo sería circular.

    `programar_emision` usa `transaction.on_commit`, así que la factura se
    emite recién cuando la confirmación quedó guardada, y un fallo de la
    facturación nunca revierte la operación.
    """
    from apps.facturacion.services import programar_emision

    programar_emision(operacion)


def calcular_conversion(monto, tasa, tipo_operacion):
    """Calcula el resultado de una simulacion de conversion."""
    monto = Decimal(monto)
    tasa = Decimal(tasa)

    if tipo_operacion == "compra":
        resultado = monto * tasa
    elif tipo_operacion == "venta":
        resultado = monto / tasa
    else:
        raise ValueError("El tipo de operacion no es valido.")

    return resultado.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def calcular_comision(monto, porcentaje):
    """Calcula y redondea la comisión aplicable al importe base."""
    return (Decimal(monto) * Decimal(porcentaje) / Decimal("100")).quantize(
        DOS_DECIMALES,
        rounding=ROUND_HALF_UP,
    )


class CompraNoDisponible(Exception):
    """La compra no puede iniciarse con la configuración vigente."""


class CompraNoConfirmable(Exception):
    """La compra pendiente no puede confirmarse ni cancelarse por acción del cliente."""


@transaction.atomic
def iniciar_compra(*, usuario, cliente_id, moneda_pagada, moneda_adquirida, monto_pagado):
    """Congela la tasa y comisión vigentes y deja la compra en estado PENDIENTE.

    El monto ingresado es la base de conversión. La comisión se cobra aparte y
    forma parte del total a pagar. La operación recién queda CONFIRMADA cuando
    el cliente confirma el pago en `confirmar_pago_compra` (RF051).

    `usuario` es obligatorio desde RF010 (GEG9-20): el servicio comprueba por
    su cuenta que esa persona pueda operar en nombre del cliente, en vez de
    confiar en que la vista ya lo verificó.
    """
    cliente_habilitado_para(usuario, cliente_id)

    cliente = Cliente.objects.select_for_update().filter(pk=cliente_id, activo=True).first()
    if cliente is None:
        raise CompraNoDisponible("El cliente ya no está habilitado para operar.")

    tasa = (
        TasaCambio.objects.select_for_update()
        .filter(
            moneda_origen=moneda_pagada,
            moneda_destino=moneda_adquirida,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )
    if tasa is None:
        raise CompraNoDisponible("No existe una tasa vigente para el par seleccionado.")

    comision = (
        ComisionCategoria.objects.select_for_update()
        .filter(categoria=cliente.categoria)
        .first()
    )
    if comision is None:
        raise CompraNoDisponible(
            "No existe una comisión configurada para la categoría del cliente."
        )

    monto_pagado = Decimal(monto_pagado).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
    monto_comision = calcular_comision(monto_pagado, comision.porcentaje)
    total_a_pagar = monto_pagado + monto_comision
    monto_recibido = calcular_conversion(monto_pagado, tasa.tasa_compra, "compra")

    compra = CompraDivisa.objects.create(
        cliente=cliente,
        moneda_pagada=moneda_pagada,
        moneda_adquirida=moneda_adquirida,
        tasa_cambio=tasa,
        monto_pagado=monto_pagado,
        porcentaje_comision=comision.porcentaje,
        monto_comision=monto_comision,
        total_a_pagar=total_a_pagar,
        tasa_aplicada=tasa.tasa_compra,
        monto_recibido=monto_recibido,
    )
    registrar_cambio_estado(compra, "", compra.estado)
    return compra


@transaction.atomic
def expirar_compra_si_corresponde(compra):
    """Cancela una compra pendiente si superó el tiempo límite para confirmar.

    Se llama tanto al mostrarla como al intentar confirmarla o cancelarla, para
    que una cotización vieja nunca quede disponible para pagar (RF051).
    """
    if compra.estado == CompraDivisa.Estado.PENDIENTE and _vencio_el_plazo(compra):
        estado_anterior = compra.estado
        compra.estado = CompraDivisa.Estado.CANCELADA
        compra.motivo_cancelacion = CompraDivisa.MotivoCancelacion.EXPIRADA
        compra.cancelado_en = timezone.now()
        compra.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
        registrar_cambio_estado(
            compra, estado_anterior, compra.estado,
            motivo="Se venció el tiempo para confirmar.",
        )
    return compra


@transaction.atomic
def confirmar_pago_compra(*, pk, usuario):
    """Confirma el pago de una compra pendiente, si la cotización no cambió.

    Si la tasa activa para el par ya no es la que se congeló al iniciar la
    compra, la operación se cancela sola: el cliente no debe pagar una tasa
    distinta a la que aceptó (RF051 — GEG9-51).
    """
    compra = (
        CompraDivisa.objects.select_for_update()
        # cliente__activo: si al cliente lo dieron de baja (RF003) con la
        # operación pendiente, tampoco se puede confirmar ni cancelar
        # (RF010 — GEG9-20).
        .filter(
            pk=pk,
            cliente__asociaciones_usuarios__usuario=usuario,
            cliente__activo=True,
        )
        .first()
    )
    if compra is None:
        raise CompraNoConfirmable("La operación no existe o no te pertenece.")
    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        raise CompraNoConfirmable("Esta operación ya fue confirmada o cancelada.")

    compra = expirar_compra_si_corresponde(compra)
    if compra.estado == CompraDivisa.Estado.CANCELADA:
        return compra

    tasa_vigente = (
        TasaCambio.objects.filter(
            moneda_origen=compra.moneda_pagada,
            moneda_destino=compra.moneda_adquirida,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )

    if tasa_vigente is None or tasa_vigente.pk != compra.tasa_cambio_id:
        estado_anterior = compra.estado
        compra.estado = CompraDivisa.Estado.CANCELADA
        compra.motivo_cancelacion = CompraDivisa.MotivoCancelacion.CAMBIO_COTIZACION
        compra.cancelado_en = timezone.now()
        compra.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
        registrar_cambio_estado(
            compra, estado_anterior, compra.estado,
            motivo="La cotización cambió antes de confirmar.", usuario=usuario,
        )
        return compra

    estado_anterior = compra.estado
    compra.estado = CompraDivisa.Estado.CONFIRMADA
    compra.confirmado_en = timezone.now()
    compra.save(update_fields=["estado", "confirmado_en"])
    registrar_cambio_estado(compra, estado_anterior, compra.estado, usuario=usuario)
    _facturar(compra)
    return compra


@transaction.atomic
def cancelar_compra(*, pk, usuario):
    """Cancela una compra pendiente por decisión del cliente."""
    compra = (
        CompraDivisa.objects.select_for_update()
        # cliente__activo: si al cliente lo dieron de baja (RF003) con la
        # operación pendiente, tampoco se puede confirmar ni cancelar
        # (RF010 — GEG9-20).
        .filter(
            pk=pk,
            cliente__asociaciones_usuarios__usuario=usuario,
            cliente__activo=True,
        )
        .first()
    )
    if compra is None:
        raise CompraNoConfirmable("La operación no existe o no te pertenece.")
    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        raise CompraNoConfirmable("Esta operación ya no se puede cancelar.")

    compra = expirar_compra_si_corresponde(compra)
    if compra.estado == CompraDivisa.Estado.CANCELADA:
        return compra

    estado_anterior = compra.estado
    compra.estado = CompraDivisa.Estado.CANCELADA
    compra.motivo_cancelacion = CompraDivisa.MotivoCancelacion.CLIENTE
    compra.cancelado_en = timezone.now()
    compra.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
    registrar_cambio_estado(
        compra, estado_anterior, compra.estado,
        motivo="Cancelada por el cliente.", usuario=usuario,
    )
    return compra


class VentaNoDisponible(Exception):
    """La venta no puede iniciarse con la configuración vigente."""


class VentaNoConfirmable(Exception):
    """La venta pendiente no puede confirmarse ni cancelarse por acción del cliente."""


@transaction.atomic
def iniciar_venta(
    *, usuario, cliente_id, moneda_entregada, moneda_acreditada,
    monto_entregado, cuenta_destino=None,
):
    """Congela la tasa y comisión y deja la venta PENDIENTE de entrega en efectivo.

    `usuario` es obligatorio desde RF010 (GEG9-20), igual que en
    `iniciar_compra`.
    """
    cliente_habilitado_para(usuario, cliente_id)

    cliente = Cliente.objects.select_for_update().filter(pk=cliente_id, activo=True).first()
    if cliente is None:
        raise VentaNoDisponible("El cliente ya no está habilitado para operar.")
    if moneda_entregada == moneda_acreditada:
        raise VentaNoDisponible("Las monedas deben ser diferentes.")

    cuenta = None
    if cuenta_destino is not None:
        cuenta = (
            CuentaPago.objects.select_for_update()
            .filter(pk=cuenta_destino.pk, cliente=cliente, activa=True)
            .first()
        )
        if cuenta is None:
            raise VentaNoDisponible(
                "La cuenta de destino no está activa o no pertenece al cliente."
            )

    tasa = (
        TasaCambio.objects.select_for_update()
        .filter(
            moneda_origen=moneda_entregada,
            moneda_destino=moneda_acreditada,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )
    if tasa is None:
        raise VentaNoDisponible("No existe una tasa vigente para el par seleccionado.")

    comision = (
        ComisionCategoria.objects.select_for_update()
        .filter(categoria=cliente.categoria)
        .first()
    )
    if comision is None:
        raise VentaNoDisponible(
            "No existe una comisión configurada para la categoría del cliente."
        )

    monto_entregado = Decimal(monto_entregado).quantize(
        DOS_DECIMALES, rounding=ROUND_HALF_UP
    )
    monto_convertido = calcular_conversion(monto_entregado, tasa.tasa_compra, "compra")
    monto_comision = calcular_comision(monto_convertido, comision.porcentaje)

    venta = VentaDivisa.objects.create(
        cliente=cliente,
        moneda_entregada=moneda_entregada,
        moneda_acreditada=moneda_acreditada,
        tasa_cambio=tasa,
        cuenta_destino=cuenta,
        monto_entregado=monto_entregado,
        porcentaje_comision=comision.porcentaje,
        monto_comision=monto_comision,
        monto_convertido=monto_convertido,
        monto_acreditado=monto_convertido - monto_comision,
        tasa_aplicada=tasa.tasa_compra,
    )
    registrar_cambio_estado(venta, "", venta.estado)
    return venta


@transaction.atomic
def expirar_venta_si_corresponde(venta):
    """Cancela una venta pendiente si superó el tiempo límite para confirmar."""
    if venta.estado == VentaDivisa.Estado.PENDIENTE and _vencio_el_plazo(venta):
        estado_anterior = venta.estado
        venta.estado = VentaDivisa.Estado.CANCELADA
        venta.motivo_cancelacion = VentaDivisa.MotivoCancelacion.EXPIRADA
        venta.cancelado_en = timezone.now()
        venta.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
        registrar_cambio_estado(
            venta, estado_anterior, venta.estado,
            motivo="Se venció el tiempo para confirmar.",
        )
    return venta


@transaction.atomic
def confirmar_pago_venta(*, pk, usuario, billetes):
    """Confirma una venta pendiente y entrega el neto en efectivo (RF058).

    Misma protección que `confirmar_pago_compra`: si la tasa activa para el
    par ya cambió respecto a la congelada al iniciar la venta, se cancela sola
    en vez de entregar un importe calculado con una tasa distinta (RF051).
    La entrega se registra como retiro de caja en la misma transacción.
    """
    if not usuario or not usuario.is_authenticated or not usuario.groups.filter(
        name="cajero"
    ).exists():
        raise VentaNoConfirmable("Solo un cajero puede entregar efectivo de una venta.")

    venta = (
        VentaDivisa.objects.select_for_update()
        .filter(
            pk=pk,
            cliente__activo=True,
        )
        .first()
    )
    if venta is None:
        raise VentaNoConfirmable("La operación no existe o no te pertenece.")
    if venta.estado != VentaDivisa.Estado.PENDIENTE:
        raise VentaNoConfirmable("Esta operación ya fue confirmada o cancelada.")

    venta = expirar_venta_si_corresponde(venta)
    if venta.estado == VentaDivisa.Estado.CANCELADA:
        return venta

    tasa_vigente = (
        TasaCambio.objects.filter(
            moneda_origen=venta.moneda_entregada,
            moneda_destino=venta.moneda_acreditada,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )

    if tasa_vigente is None or tasa_vigente.pk != venta.tasa_cambio_id:
        estado_anterior = venta.estado
        venta.estado = VentaDivisa.Estado.CANCELADA
        venta.motivo_cancelacion = VentaDivisa.MotivoCancelacion.CAMBIO_COTIZACION
        venta.cancelado_en = timezone.now()
        venta.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
        registrar_cambio_estado(
            venta, estado_anterior, venta.estado,
            motivo="La cotización cambió antes de confirmar.", usuario=usuario,
        )
        return venta

    cantidades = billetes
    if not isinstance(cantidades, dict) or not cantidades:
        raise VentaNoDisponible("Ingresá el desglose de billetes para la entrega.")

    caja = (
        Caja.objects.select_for_update()
        .filter(sucursal__activa=True)
        .select_related("sucursal")
        .first()
    )
    if caja is None:
        raise VentaNoDisponible("No hay una caja activa configurada para la entrega.")

    saldo_caja = SaldoCaja.objects.select_for_update().filter(
        caja=caja, moneda=venta.moneda_acreditada
    ).first()
    disponible = saldo_caja.saldo if saldo_caja is not None else Decimal("0.00")
    if disponible < venta.monto_acreditado:
        faltante = venta.monto_acreditado - disponible
        raise VentaNoDisponible(
            f"Faltan {faltante:.2f} {venta.moneda_acreditada.codigo} en la caja "
            "para cubrir la entrega."
        )

    propuesta = proponer_billetes_entrega(
        caja=caja,
        moneda=venta.moneda_acreditada,
        importe=venta.monto_acreditado,
    )
    importe_minimo = propuesta["importe_entrega"]
    if importe_minimo is None:
        raise VentaNoDisponible(
            f"Faltan {propuesta['faltante']:.2f} {venta.moneda_acreditada.codigo} "
            "en billetes para cubrir la entrega."
        )

    try:
        movimiento = registrar_movimiento(
            caja_id=caja.pk,
            tipo=MovimientoCaja.Tipo.RETIRO,
            moneda_id=venta.moneda_acreditada_id,
            realizado_por=usuario,
            nota=f"Entrega de efectivo por venta #{venta.pk}",
            billetes=cantidades,
        )
    except MovimientoNoPermitido as error:
        raise VentaNoDisponible(str(error)) from error

    if movimiento.importe != importe_minimo:
        raise VentaNoDisponible(
            f"El desglose debe sumar el importe mínimo posible de "
            f"{importe_minimo:.2f} {venta.moneda_acreditada.codigo}."
        )

    estado_anterior = venta.estado
    venta.estado = VentaDivisa.Estado.CONFIRMADA
    venta.confirmado_en = timezone.now()
    venta.monto_efectivo_entregado = movimiento.importe
    venta.save(
        update_fields=["estado", "confirmado_en", "monto_efectivo_entregado"]
    )
    registrar_cambio_estado(venta, estado_anterior, venta.estado, usuario=usuario)
    _facturar(venta)
    return venta


@transaction.atomic
def cancelar_venta(*, pk, usuario):
    """Cancela una venta pendiente por decisión del cliente."""
    venta = (
        VentaDivisa.objects.select_for_update()
        # Ver el comentario en confirmar_pago_compra (RF010 — GEG9-20).
        .filter(
            pk=pk,
            cliente__asociaciones_usuarios__usuario=usuario,
            cliente__activo=True,
        )
        .first()
    )
    if venta is None:
        raise VentaNoConfirmable("La operación no existe o no te pertenece.")
    if venta.estado != VentaDivisa.Estado.PENDIENTE:
        raise VentaNoConfirmable("Esta operación ya no se puede cancelar.")

    venta = expirar_venta_si_corresponde(venta)
    if venta.estado == VentaDivisa.Estado.CANCELADA:
        return venta

    estado_anterior = venta.estado
    venta.estado = VentaDivisa.Estado.CANCELADA
    venta.motivo_cancelacion = VentaDivisa.MotivoCancelacion.CLIENTE
    venta.cancelado_en = timezone.now()
    venta.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
    registrar_cambio_estado(
        venta, estado_anterior, venta.estado,
        motivo="Cancelada por el cliente.", usuario=usuario,
    )
    return venta
