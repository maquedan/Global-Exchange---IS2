from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from apps.conversiones.models import CompraDivisa, VentaDivisa


DOS_DECIMALES = Decimal("0.01")


def _redondear(valor):
    return Decimal(valor).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def operaciones_confirmadas(fecha_desde=None, fecha_hasta=None):
    """Devuelve compras y ventas confirmadas dentro del rango solicitado."""
    compras = CompraDivisa.objects.filter(
        estado=CompraDivisa.Estado.CONFIRMADA,
        confirmado_en__isnull=False,
    ).select_related("moneda_adquirida", "moneda_pagada", "tasa_cambio")
    ventas = VentaDivisa.objects.filter(
        estado=VentaDivisa.Estado.CONFIRMADA,
        confirmado_en__isnull=False,
    ).select_related("moneda_acreditada", "moneda_entregada", "tasa_cambio")

    if fecha_desde:
        compras = compras.filter(confirmado_en__date__gte=fecha_desde)
        ventas = ventas.filter(confirmado_en__date__gte=fecha_desde)
    if fecha_hasta:
        compras = compras.filter(confirmado_en__date__lte=fecha_hasta)
        ventas = ventas.filter(confirmado_en__date__lte=fecha_hasta)

    return compras, ventas


def _ganancia_compra(compra):
    # La comisión está en la moneda pagada; se expresa en la moneda recibida
    # para poder sumar comisión y spread en una misma fila del desglose.
    comision = _redondear(compra.monto_comision * compra.tasa_aplicada)
    diferencia_tasa = _redondear(
        compra.monto_pagado
        * (compra.tasa_cambio.tasa_venta - compra.tasa_cambio.tasa_compra)
    )
    return compra.moneda_adquirida, comision, diferencia_tasa


def _ganancia_venta(venta):
    comision = _redondear(venta.monto_comision)
    diferencia_tasa = _redondear(
        venta.monto_entregado
        * (venta.tasa_cambio.tasa_venta - venta.tasa_cambio.tasa_compra)
    )
    return venta.moneda_acreditada, comision, diferencia_tasa


def resumen_ganancias(fecha_desde=None, fecha_hasta=None):
    """Calcula el resumen actual; al no persistirse, siempre refleja nuevas confirmaciones."""
    compras, ventas = operaciones_confirmadas(fecha_desde, fecha_hasta)
    por_moneda = defaultdict(lambda: {"comision": Decimal("0"), "diferencia_tasa": Decimal("0")})
    operaciones = 0

    for compra in compras:
        moneda, comision, diferencia_tasa = _ganancia_compra(compra)
        por_moneda[moneda.codigo]["comision"] += comision
        por_moneda[moneda.codigo]["diferencia_tasa"] += diferencia_tasa
        operaciones += 1
    for venta in ventas:
        moneda, comision, diferencia_tasa = _ganancia_venta(venta)
        por_moneda[moneda.codigo]["comision"] += comision
        por_moneda[moneda.codigo]["diferencia_tasa"] += diferencia_tasa
        operaciones += 1

    desglose = []
    for codigo in sorted(por_moneda):
        valores = por_moneda[codigo]
        valores["total"] = valores["comision"] + valores["diferencia_tasa"]
        desglose.append({"moneda": codigo, **{k: _redondear(v) for k, v in valores.items()}})

    total = {
        clave: _redondear(sum(item[clave] for item in desglose))
        for clave in ("comision", "diferencia_tasa", "total")
    }
    return {"operaciones": operaciones, "total": total, "desglose": desglose}
