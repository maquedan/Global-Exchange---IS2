from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.monedas.models import Moneda

from .models import (
    Caja,
    ConteoInventarioBilletes,
    DenominacionBillete,
    DetalleConteoInventarioBilletes,
    DetalleMovimientoBillete,
    FondoCajero,
    InventarioBilleteCaja,
    InventarioBilleteCajero,
    MovimientoCaja,
    SaldoCaja,
)


class MovimientoNoPermitido(Exception):
    """El movimiento solicitado no cumple las reglas de caja."""


def denominacion_tiene_referencias(denominacion):
    """Indica si una denominación forma parte de inventario o de un registro auditado."""
    return any(
        consulta.objects.filter(denominacion=denominacion).exists()
        for consulta in (
            DetalleMovimientoBillete,
            DetalleConteoInventarioBilletes,
            InventarioBilleteCaja,
            InventarioBilleteCajero,
        )
    )


def _normalizar_billetes(billetes, moneda, *, permitir_cero=False):
    if not isinstance(billetes, dict) or (not billetes and not permitir_cero):
        raise ValidationError("Ingresá la cantidad de billetes por denominación.")

    cantidades = {}
    for denominacion_id, cantidad in billetes.items():
        if isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad < 0:
            raise ValidationError("Las cantidades de billetes deben ser enteros no negativos.")
        if cantidad == 0:
            continue
        cantidades[denominacion_id] = cantidad

    if not cantidades and not permitir_cero:
        raise ValidationError("La cantidad total de billetes debe ser mayor que cero.")

    denominaciones = {
        denominacion.pk: denominacion
        for denominacion in DenominacionBillete.objects.filter(
            pk__in=cantidades, moneda=moneda
        )
    }
    if len(denominaciones) != len(cantidades):
        raise MovimientoNoPermitido(
            "Una o más denominaciones no pertenecen a la divisa seleccionada."
        )

    importe = sum(
        (denominaciones[pk].valor * cantidad for pk, cantidad in cantidades.items()),
        Decimal("0.00"),
    )
    return cantidades, denominaciones, importe


def _importe_inventario(queryset, moneda):
    total = Decimal("0.00")
    for existencia in queryset.select_related("denominacion"):
        if existencia.denominacion.moneda_id == moneda.pk:
            total += existencia.denominacion.valor * existencia.cantidad
    return total


def _verificar_inventario(queryset, moneda, saldo):
    if _importe_inventario(queryset, moneda) != saldo:
        raise MovimientoNoPermitido(
            "El inventario por denominación no coincide con el saldo. "
            "Registrá un conteo de inventario antes de continuar."
        )


@transaction.atomic
def registrar_movimiento(
    *,
    caja_id,
    tipo,
    moneda_id,
    realizado_por,
    cajero_id=None,
    nota="",
    billetes=None,
):
    """Registra el movimiento y actualiza atómicamente saldos y conteos de billetes."""
    if not caja_id or not moneda_id:
        raise ValidationError("Debe indicar una caja y una divisa.")

    try:
        tipo = MovimientoCaja.Tipo(tipo)
    except ValueError:
        raise ValidationError("El tipo de movimiento no es válido.") from None

    moneda = Moneda.objects.filter(pk=moneda_id, activo=True).first()
    if moneda is None:
        raise MovimientoNoPermitido("La moneda no existe o está inactiva.")

    cantidades, denominaciones, importe = _normalizar_billetes(billetes, moneda)
    if importe >= Decimal("10000000000000000"):
        raise ValidationError(
            "El importe debe ser menor que 9.999.999.999.999.999,99."
        )
    try:
        importe = importe.quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValidationError("El importe debe tener como máximo dos decimales.")
    if importe <= 0:
        raise ValidationError("El importe calculado debe ser mayor que cero.")

    caja = Caja.objects.select_for_update().select_related("sucursal").get(pk=caja_id)
    if not caja.sucursal.activa:
        raise MovimientoNoPermitido(
            "No se pueden registrar movimientos en una sucursal inactiva."
        )

    saldo_caja, _ = SaldoCaja.objects.get_or_create(caja=caja, moneda=moneda)
    saldo_caja = SaldoCaja.objects.select_for_update().get(pk=saldo_caja.pk)
    inventario_caja = InventarioBilleteCaja.objects.filter(
        caja=caja, denominacion__moneda=moneda
    ).select_for_update()
    _verificar_inventario(inventario_caja, moneda, saldo_caja.saldo)

    fondo_cajero = None
    inventario_cajero = None
    if tipo in (MovimientoCaja.Tipo.ASIGNACION, MovimientoCaja.Tipo.DEVOLUCION):
        if cajero_id is None:
            raise ValidationError("Debe seleccionar un cajero para este movimiento.")
        if tipo == MovimientoCaja.Tipo.ASIGNACION:
            usuario_cajero = get_user_model().objects.filter(
                pk=cajero_id, is_active=True, groups__name="cajero"
            ).first()
            if usuario_cajero is None:
                raise MovimientoNoPermitido(
                    "El usuario seleccionado no es un cajero activo."
                )
            fondo_cajero, _ = FondoCajero.objects.get_or_create(
                caja=caja, cajero=usuario_cajero, moneda=moneda
            )
        else:
            fondo_cajero = FondoCajero.objects.filter(
                caja=caja, cajero_id=cajero_id, moneda=moneda
            ).first()
            if fondo_cajero is None:
                raise MovimientoNoPermitido(
                    "Ese cajero no tiene fondos asignados en esta moneda."
                )
        fondo_cajero = FondoCajero.objects.select_for_update().get(pk=fondo_cajero.pk)
        inventario_cajero = InventarioBilleteCajero.objects.filter(
            caja=caja, cajero=fondo_cajero.cajero, denominacion__moneda=moneda
        ).select_for_update()
        _verificar_inventario(inventario_cajero, moneda, fondo_cajero.saldo)
    elif cajero_id is not None:
        raise ValidationError("Este movimiento no debe indicar un cajero.")

    if tipo in (MovimientoCaja.Tipo.RETIRO, MovimientoCaja.Tipo.ASIGNACION):
        if saldo_caja.saldo < importe:
            raise MovimientoNoPermitido(
                "La caja no tiene fondos suficientes para ese movimiento."
            )
        _verificar_disponibilidad(inventario_caja, cantidades, denominaciones)
    elif tipo == MovimientoCaja.Tipo.DEVOLUCION:
        if fondo_cajero.saldo < importe:
            raise MovimientoNoPermitido(
                "El cajero no tiene fondos suficientes para esa devolución."
            )
        _verificar_disponibilidad(inventario_cajero, cantidades, denominaciones)

    if tipo == MovimientoCaja.Tipo.INGRESO:
        saldo_caja.saldo += importe
        _aplicar_cantidades_caja(caja, cantidades, sumar=True)
    elif tipo == MovimientoCaja.Tipo.RETIRO:
        saldo_caja.saldo -= importe
        _aplicar_cantidades_caja(caja, cantidades, sumar=False)
    elif tipo == MovimientoCaja.Tipo.ASIGNACION:
        saldo_caja.saldo -= importe
        fondo_cajero.saldo += importe
        _aplicar_cantidades_caja(caja, cantidades, sumar=False)
        _aplicar_cantidades_cajero(caja, fondo_cajero.cajero, cantidades, sumar=True)
    elif tipo == MovimientoCaja.Tipo.DEVOLUCION:
        fondo_cajero.saldo -= importe
        saldo_caja.saldo += importe
        _aplicar_cantidades_cajero(caja, fondo_cajero.cajero, cantidades, sumar=False)
        _aplicar_cantidades_caja(caja, cantidades, sumar=True)

    saldo_caja.save(update_fields=["saldo"])
    if fondo_cajero is not None:
        fondo_cajero.save(update_fields=["saldo"])

    movimiento = MovimientoCaja.objects.create(
        caja=caja,
        tipo=tipo,
        moneda=moneda,
        cajero=fondo_cajero.cajero if fondo_cajero is not None else None,
        importe=importe,
        saldo_caja_resultante=saldo_caja.saldo,
        saldo_cajero_resultante=(
            fondo_cajero.saldo if fondo_cajero is not None else None
        ),
        realizado_por=realizado_por,
        nota=nota.strip(),
    )
    DetalleMovimientoBillete.objects.bulk_create(
        [
            DetalleMovimientoBillete(
                movimiento=movimiento,
                denominacion_id=denominacion_id,
                cantidad=cantidad,
            )
            for denominacion_id, cantidad in cantidades.items()
        ]
    )
    return movimiento


def _verificar_disponibilidad(queryset, cantidades, denominaciones):
    disponibles = {
        existencia.denominacion_id: existencia.cantidad for existencia in queryset
    }
    for denominacion_id, cantidad in cantidades.items():
        if disponibles.get(denominacion_id, 0) < cantidad:
            raise MovimientoNoPermitido(
                f"No hay suficientes billetes de {denominaciones[denominacion_id].valor} "
                f"{denominaciones[denominacion_id].moneda.codigo} en el origen."
            )


def _aplicar_cantidades_caja(caja, cantidades, *, sumar):
    for denominacion_id, cantidad in cantidades.items():
        existencia, _ = InventarioBilleteCaja.objects.get_or_create(
            caja=caja, denominacion_id=denominacion_id
        )
        existencia.cantidad += cantidad if sumar else -cantidad
        existencia.save(update_fields=["cantidad"])


def _aplicar_cantidades_cajero(caja, cajero, cantidades, *, sumar):
    for denominacion_id, cantidad in cantidades.items():
        existencia, _ = InventarioBilleteCajero.objects.get_or_create(
            caja=caja, cajero=cajero, denominacion_id=denominacion_id
        )
        existencia.cantidad += cantidad if sumar else -cantidad
        existencia.save(update_fields=["cantidad"])


@transaction.atomic
def registrar_conteo_inventario(
    *, caja_id, moneda_id, realizado_por, billetes, cajero_id=None
):
    """Registra un conteo auditado que reconcilia existencias con el saldo actual."""
    caja = Caja.objects.select_for_update().get(pk=caja_id)
    moneda = Moneda.objects.filter(pk=moneda_id, activo=True).first()
    if moneda is None:
        raise MovimientoNoPermitido("La moneda no existe o está inactiva.")
    cantidades, _, importe_billetes = _normalizar_billetes(
        billetes, moneda, permitir_cero=True
    )

    if cajero_id is None:
        saldo, _ = SaldoCaja.objects.get_or_create(caja=caja, moneda=moneda)
        saldo = SaldoCaja.objects.select_for_update().get(pk=saldo.pk)
        inventario = InventarioBilleteCaja.objects.filter(
            caja=caja, denominacion__moneda=moneda
        ).select_for_update()
    else:
        fondo = FondoCajero.objects.filter(
            caja=caja, cajero_id=cajero_id, moneda=moneda
        ).first()
        if fondo is None:
            raise MovimientoNoPermitido(
                "El cajero no tiene un saldo registrado en esta moneda."
            )
        fondo = FondoCajero.objects.select_for_update().get(pk=fondo.pk)
        saldo = fondo
        inventario = InventarioBilleteCajero.objects.filter(
            caja=caja, cajero_id=cajero_id, denominacion__moneda=moneda
        ).select_for_update()

    if importe_billetes != saldo.saldo:
        raise ValidationError(
            f"El conteo suma {importe_billetes} {moneda.codigo} y debe coincidir "
            f"con el saldo actual de {saldo.saldo}."
        )

    conteo = ConteoInventarioBilletes.objects.create(
        caja=caja,
        moneda=moneda,
        cajero_id=cajero_id,
        importe_total=importe_billetes,
        realizado_por=realizado_por,
    )
    if cajero_id is None:
        existentes = InventarioBilleteCaja
        filtros = {"caja": caja, "denominacion__moneda": moneda}
        campos = {"caja": caja}
    else:
        existentes = InventarioBilleteCajero
        filtros = {
            "caja": caja,
            "cajero_id": cajero_id,
            "denominacion__moneda": moneda,
        }
        campos = {"caja": caja, "cajero_id": cajero_id}

    existentes.objects.filter(**filtros).update(cantidad=0)
    for denominacion_id, cantidad in cantidades.items():
        existentes.objects.update_or_create(
            **campos,
            denominacion_id=denominacion_id,
            defaults={"cantidad": cantidad},
        )
    DetalleConteoInventarioBilletes.objects.bulk_create(
        [
            DetalleConteoInventarioBilletes(
                conteo=conteo,
                denominacion_id=denominacion_id,
                cantidad=cantidad,
            )
            for denominacion_id, cantidad in cantidades.items()
        ]
    )
    return conteo
