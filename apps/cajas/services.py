from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.monedas.models import Moneda

from .models import (
    Caja,
    ConteoInventarioBilletes,
    ArqueoCaja,
    DetalleArqueoBillete,
    DiferenciaCaja,
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


def proponer_billetes_entrega(*, caja, moneda, importe):
    """Propone el menor importe posible que cubra la entrega con el inventario."""
    existencias = list(
        InventarioBilleteCaja.objects.filter(
            caja=caja, denominacion__moneda=moneda
        )
        .select_related("denominacion")
        .order_by("-denominacion__valor")
    )
    disponible = sum(
        (
            existencia.denominacion.valor * existencia.cantidad
            for existencia in existencias
        ),
        Decimal("0.00"),
    )

    importe = Decimal(importe).quantize(Decimal("0.01"))
    if disponible < importe:
        return {
            "billetes": {},
            "disponible": disponible,
            "faltante": importe - disponible,
            "importe_entrega": None,
            "excedente": None,
        }

    objetivo_centavos = int(importe * 100)
    cantidades_disponibles = [
        (
            existencia.denominacion_id,
            int(existencia.denominacion.valor * 100),
            existencia.cantidad,
        )
        for existencia in existencias
    ]

    # Greedy provides an initial upper bound; bounded search proves that no
    # available combination reaches the target with a smaller total.
    restante = objetivo_centavos
    mejor_total = 0
    mejor_billetes = {}
    for denominacion_id, valor, cantidad_disponible in cantidades_disponibles:
        cantidad = min(cantidad_disponible, (restante + valor - 1) // valor)
        if cantidad:
            mejor_billetes[denominacion_id] = cantidad
            mejor_total += cantidad * valor
            restante -= cantidad * valor
        if restante <= 0:
            break

    sufijos_disponibles = [0] * (len(cantidades_disponibles) + 1)
    for indice in range(len(cantidades_disponibles) - 1, -1, -1):
        _, valor, cantidad = cantidades_disponibles[indice]
        sufijos_disponibles[indice] = (
            sufijos_disponibles[indice + 1] + valor * cantidad
        )

    elegidos = {}

    def buscar(indice, subtotal):
        nonlocal mejor_total, mejor_billetes
        if subtotal >= objetivo_centavos:
            if subtotal < mejor_total:
                mejor_total = subtotal
                mejor_billetes = elegidos.copy()
            return
        if (
            indice == len(cantidades_disponibles)
            or subtotal + sufijos_disponibles[indice] < objetivo_centavos
        ):
            return

        denominacion_id, valor, cantidad_disponible = cantidades_disponibles[indice]
        cantidad_minima = max(
            0,
            (
                objetivo_centavos
                - subtotal
                - sufijos_disponibles[indice + 1]
                + valor
                - 1
            )
            // valor,
        )
        cantidad_maxima = min(
            cantidad_disponible,
            (mejor_total - 1 - subtotal) // valor,
        )
        if cantidad_minima > cantidad_maxima:
            return

        for cantidad in range(cantidad_maxima, cantidad_minima - 1, -1):
            nuevo_subtotal = subtotal + cantidad * valor
            if cantidad:
                elegidos[denominacion_id] = cantidad
            else:
                elegidos.pop(denominacion_id, None)
            buscar(indice + 1, nuevo_subtotal)
        elegidos.pop(denominacion_id, None)

    buscar(0, 0)
    importe_entrega = Decimal(mejor_total) / 100
    billetes = mejor_billetes

    return {
        "billetes": billetes,
        "disponible": disponible,
        "faltante": Decimal("0.00"),
        "importe_entrega": importe_entrega,
        "excedente": importe_entrega - importe,
    }


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
    if tipo in (
        MovimientoCaja.Tipo.AJUSTE_INGRESO,
        MovimientoCaja.Tipo.AJUSTE_EGRESO,
    ):
        raise MovimientoNoPermitido(
            "Los ajustes solo pueden registrarse desde una diferencia de caja."
        )

    fondo_cajero = None
    inventario_cajero = None

    if tipo in (
        MovimientoCaja.Tipo.ASIGNACION,
        MovimientoCaja.Tipo.DEVOLUCION,
    ):
        if cajero_id is None:
            raise ValidationError("Debe seleccionar un cajero para este movimiento.")

        if tipo == MovimientoCaja.Tipo.ASIGNACION:
            usuario_cajero = get_user_model().objects.filter(
                pk=cajero_id,
                is_active=True,
                groups__name="cajero",
            ).first()
            if usuario_cajero is None:
                raise MovimientoNoPermitido(
                    "El usuario seleccionado no es un cajero activo."
                )
            fondo_cajero, _ = FondoCajero.objects.get_or_create(
                caja=caja,
                cajero=usuario_cajero,
                moneda=moneda,
            )
        else:
            fondo_cajero = FondoCajero.objects.filter(
                caja=caja,
                cajero_id=cajero_id,
                moneda=moneda,
            ).first()
            if fondo_cajero is None:
                raise MovimientoNoPermitido(
                    "Ese cajero no tiene fondos asignados en esta moneda."
                )

        fondo_cajero = FondoCajero.objects.select_for_update().get(
            pk=fondo_cajero.pk
        )
        inventario_cajero = InventarioBilleteCajero.objects.filter(
            caja=caja,
            cajero=fondo_cajero.cajero,
            denominacion__moneda=moneda,
        ).select_for_update()
        _verificar_inventario(
            inventario_cajero,
            moneda,
            fondo_cajero.saldo,
        )

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


@transaction.atomic
def registrar_arqueo(*, caja_id, cajero_id, moneda_id, billetes, observaciones=""):
    """Registra el cierre de efectivo del fondo de un cajero."""
    caja = Caja.objects.select_for_update().select_related("sucursal").get(pk=caja_id)
    cajero = get_user_model().objects.filter(
        pk=cajero_id, is_active=True, groups__name="cajero"
    ).first()
    if cajero is None:
        raise MovimientoNoPermitido("El usuario no es un cajero activo.")
    moneda = Moneda.objects.filter(pk=moneda_id, activo=True).first()
    if moneda is None:
        raise MovimientoNoPermitido("La moneda no existe o está inactiva.")
    fondo = FondoCajero.objects.select_for_update().filter(
        caja=caja, cajero=cajero, moneda=moneda
    ).first()
    if fondo is None:
        raise MovimientoNoPermitido("No tenés fondos asignados en esa caja y moneda.")

    cantidades, denominaciones, total_contado = _normalizar_billetes(
        billetes, moneda, permitir_cero=True
    )
    total_contado = total_contado.quantize(Decimal("0.01"))
    diferencia = (total_contado - fondo.saldo).quantize(Decimal("0.01"))
    if diferencia == 0:
        estado = ArqueoCaja.Estado.CUADRADO
    elif diferencia < 0:
        estado = ArqueoCaja.Estado.FALTANTE
    else:
        estado = ArqueoCaja.Estado.SOBRANTE

    arqueo = ArqueoCaja.objects.create(
        caja=caja,
        cajero=cajero,
        moneda=moneda,
        saldo_esperado=fondo.saldo,
        total_contado=total_contado,
        diferencia=diferencia,
        estado=estado,
        observaciones=observaciones.strip(),
    )
    DetalleArqueoBillete.objects.bulk_create(
        [
            DetalleArqueoBillete(
                arqueo=arqueo, denominacion_id=denominacion_id, cantidad=cantidad
            )
            for denominacion_id, cantidad in cantidades.items()
        ]
    )
    return arqueo


@transaction.atomic
def registrar_diferencia_caja(
    *, arqueo_id, monto, moneda_id, motivo, responsable_id, registrado_por
):
    """Registra una diferencia detectada durante un arqueo."""
    arqueo = ArqueoCaja.objects.select_for_update().get(pk=arqueo_id)
    moneda = Moneda.objects.filter(pk=moneda_id, activo=True).first()
    if moneda is None:
        raise MovimientoNoPermitido("La divisa no existe o está inactiva.")
    if arqueo.moneda_id != moneda.pk:
        raise MovimientoNoPermitido("La divisa debe coincidir con la del arqueo.")
    if not motivo.strip():
        raise MovimientoNoPermitido("El motivo es obligatorio.")
    responsable = get_user_model().objects.filter(pk=responsable_id, is_active=True).first()
    if responsable is None:
        raise MovimientoNoPermitido("El responsable debe ser un usuario activo.")
    return DiferenciaCaja.objects.create(
        arqueo=arqueo,
        monto=monto,
        moneda=moneda,
        motivo=motivo.strip(),
        responsable=responsable,
        registrado_por=registrado_por,
    )

@transaction.atomic
def registrar_ajuste_por_diferencia(*, diferencia_id, realizado_por, billetes):
    """Regulariza una diferencia de arqueo mediante un único ajuste autorizado."""
    diferencia = (
        DiferenciaCaja.objects.select_for_update()
        .select_related("arqueo__caja", "arqueo__cajero", "arqueo__moneda", "moneda")
        .get(pk=diferencia_id)
    )
    arqueo = diferencia.arqueo

    if arqueo.estado == ArqueoCaja.Estado.CUADRADO:
        raise MovimientoNoPermitido(
            "Un arqueo sin diferencia no puede generar un ajuste."
        )

    if diferencia.monto != abs(arqueo.diferencia):
        raise MovimientoNoPermitido(
            "El monto registrado debe coincidir con la diferencia del arqueo."
        )

    if MovimientoCaja.objects.filter(diferencia=diferencia).exists():
        raise MovimientoNoPermitido(
            "Esta diferencia ya fue regularizada mediante un ajuste."
        )

    cantidades, denominaciones, importe = _normalizar_billetes(
        billetes, diferencia.moneda
    )
    importe = importe.quantize(Decimal("0.01"))

    if importe != diferencia.monto:
        raise MovimientoNoPermitido(
            "El desglose de billetes debe coincidir con el monto de la diferencia."
        )

    caja = Caja.objects.select_for_update().get(pk=arqueo.caja_id)
    fondo = FondoCajero.objects.select_for_update().filter(
        caja=caja,
        cajero=arqueo.cajero,
        moneda=diferencia.moneda,
    ).first()
    if fondo is None:
        raise MovimientoNoPermitido(
            "El cajero no tiene fondos asignados para regularizar esta diferencia."
        )

    saldo_caja, _ = SaldoCaja.objects.get_or_create(
        caja=caja,
        moneda=diferencia.moneda,
    )
    saldo_caja = SaldoCaja.objects.select_for_update().get(pk=saldo_caja.pk)

    inventario_cajero = InventarioBilleteCajero.objects.filter(
        caja=caja,
        cajero=arqueo.cajero,
        denominacion__moneda=diferencia.moneda,
    ).select_for_update()
    _verificar_inventario(inventario_cajero, diferencia.moneda, fondo.saldo)

    if arqueo.estado == ArqueoCaja.Estado.FALTANTE:
        tipo = MovimientoCaja.Tipo.AJUSTE_EGRESO
        if fondo.saldo < importe:
            raise MovimientoNoPermitido(
                "El fondo del cajero no alcanza para regularizar el faltante."
            )
        _verificar_disponibilidad(
            inventario_cajero,
            cantidades,
            denominaciones,
        )
        fondo.saldo -= importe
        _aplicar_cantidades_cajero(
            caja,
            arqueo.cajero,
            cantidades,
            sumar=False,
        )
    else:
        tipo = MovimientoCaja.Tipo.AJUSTE_INGRESO
        fondo.saldo += importe
        _aplicar_cantidades_cajero(
            caja,
            arqueo.cajero,
            cantidades,
            sumar=True,
        )

    fondo.save(update_fields=["saldo"])

    movimiento = MovimientoCaja.objects.create(
        caja=caja,
        tipo=tipo,
        moneda=diferencia.moneda,
        cajero=arqueo.cajero,
        diferencia=diferencia,
        importe=importe,
        saldo_caja_resultante=saldo_caja.saldo,
        saldo_cajero_resultante=fondo.saldo,
        realizado_por=realizado_por,
        nota=f"Ajuste autorizado por diferencia #{diferencia.pk}: {diferencia.motivo}",
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