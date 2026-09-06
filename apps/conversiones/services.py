from decimal import Decimal, ROUND_HALF_UP


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
