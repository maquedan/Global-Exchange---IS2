from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.monedas.models import Moneda

from .models import Caja, FondoCajero, MovimientoCaja, SaldoCaja


class MovimientoNoPermitido(Exception):
    """El movimiento solicitado no cumple las reglas de caja."""


@transaction.atomic
def registrar_movimiento(
    *, caja_id, tipo, moneda_id, importe, realizado_por, cajero_id=None, nota=""
):
    """Registra atómicamente un movimiento y conserva ambos saldos resultantes."""
    try:
        importe = Decimal(importe)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("El importe debe ser un número válido.") from None
    if (
        not importe.is_finite()
        or importe < Decimal("0.01")
        or importe >= Decimal("10000000000000000")
    ):
        raise ValidationError(
            "El importe debe estar entre 0,01 y 9.999.999.999.999.999,99."
        )
    try:
        importe_con_dos_decimales = importe.quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValidationError(
            "El importe debe tener como máximo dos decimales."
        ) from None
    if importe != importe_con_dos_decimales:
        raise ValidationError("El importe debe tener como máximo dos decimales.")

    try:
        tipo = MovimientoCaja.Tipo(tipo)
    except ValueError:
        raise ValidationError("El tipo de movimiento no es válido.") from None

    caja = Caja.objects.select_for_update().select_related("sucursal").get(pk=caja_id)
    moneda = Moneda.objects.filter(pk=moneda_id, activo=True).first()
    if moneda is None:
        raise MovimientoNoPermitido("La moneda no existe o está inactiva.")

    if not caja.sucursal.activa:
        raise MovimientoNoPermitido(
            "No se pueden registrar movimientos en una sucursal inactiva."
        )

    saldo_caja, _ = SaldoCaja.objects.get_or_create(caja=caja, moneda=moneda)
    saldo_caja = SaldoCaja.objects.select_for_update().get(pk=saldo_caja.pk)
    fondo_cajero = None

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
    elif cajero_id is not None:
        raise ValidationError("Este movimiento no debe indicar un cajero.")

    if tipo == MovimientoCaja.Tipo.INGRESO:
        saldo_caja.saldo += importe
    elif tipo == MovimientoCaja.Tipo.RETIRO:
        if saldo_caja.saldo < importe:
            raise MovimientoNoPermitido("La caja no tiene fondos suficientes para ese retiro.")
        saldo_caja.saldo -= importe
    elif tipo == MovimientoCaja.Tipo.ASIGNACION:
        if saldo_caja.saldo < importe:
            raise MovimientoNoPermitido(
                "La caja no tiene fondos suficientes para esa asignación."
            )
        saldo_caja.saldo -= importe
        fondo_cajero.saldo += importe
    elif tipo == MovimientoCaja.Tipo.DEVOLUCION:
        if fondo_cajero.saldo < importe:
            raise MovimientoNoPermitido("El cajero no tiene fondos suficientes para esa devolución.")
        fondo_cajero.saldo -= importe
        saldo_caja.saldo += importe

    saldo_caja.save(update_fields=["saldo"])
    if fondo_cajero is not None:
        fondo_cajero.save(update_fields=["saldo"])

    return MovimientoCaja.objects.create(
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
