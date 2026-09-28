from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.comisiones.models import ComisionCategoria
from apps.cuentas.models import CuentaPago
from apps.tasa_cambios.models import TasaCambio

from .models import CompraDivisa, VentaDivisa


DOS_DECIMALES = Decimal("0.01")


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
    """La compra no puede confirmarse con la configuración vigente."""


@transaction.atomic
def confirmar_compra(*, cliente_id, moneda_pagada, moneda_adquirida, monto_pagado):
    """Confirma una compra usando la tasa y comisión vigentes en ese instante.

    El monto ingresado es la base de conversión. La comisión se cobra aparte y
    forma parte del total a pagar.
    """
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

    return CompraDivisa.objects.create(
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


class VentaNoDisponible(Exception):
    """La venta no puede confirmarse con la configuración vigente."""


@transaction.atomic
def confirmar_venta(
    *, cliente_id, moneda_entregada, moneda_acreditada, cuenta_destino, monto_entregado
):
    """Confirma una venta y registra el neto que debe acreditarse al cliente."""
    cliente = Cliente.objects.select_for_update().filter(pk=cliente_id, activo=True).first()
    if cliente is None:
        raise VentaNoDisponible("El cliente ya no está habilitado para operar.")
    if moneda_entregada == moneda_acreditada:
        raise VentaNoDisponible("Las monedas deben ser diferentes.")

    cuenta = (
        CuentaPago.objects.select_for_update()
        .filter(pk=cuenta_destino.pk, cliente=cliente, activa=True)
        .first()
    )
    if cuenta is None:
        raise VentaNoDisponible("La cuenta de destino no está activa o no pertenece al cliente.")

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

    return VentaDivisa.objects.create(
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
