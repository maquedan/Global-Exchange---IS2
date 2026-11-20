"""Formato de números y montos para todo el sistema (GEG9-82).

Un solo lugar donde se decide cómo se ve un número, para no repetir
`floatformat` con criterios distintos en cada plantilla.

**Punto como separador de miles y coma como decimal**: `1.250.000` y
`1.234,56`. Es lo que pidió la cátedra y lo que se usa en Paraguay.

Se descartó `USE_THOUSAND_SEPARATOR` de Django: con `LANGUAGE_CODE = "es"`
agrupa con **espacio fino** (`1 250 000`), no con punto, así que daría un
formato distinto al pedido. Cambiar el locale a `es_PY` habría arrastrado
también el formato de fechas en todo el sistema. Un filtro propio da el
formato exacto, donde lo queremos y sin efectos a distancia.

Todo trabaja con `Decimal`, **nunca con `float`**: un `float` no puede
representar exactamente 0,1 y en importes de dinero eso se nota.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Decimales que se usan cuando no se sabe de qué moneda se trata.
DECIMALES_POR_DEFECTO = 2


def _a_decimal(valor):
    """Convierte a `Decimal` sin pasar por `float` en ningún caso."""
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    try:
        # `str()` primero: Decimal(float) arrastra el error de representación
        # binaria y 0.1 se vuelve 0.1000000000000000055511151231257827.
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return None


def formatear_numero(valor, decimales=DECIMALES_POR_DEFECTO):
    """Devuelve el número con punto de miles y coma decimal.

    >>> formatear_numero(Decimal("1250000.5"), 2)
    '1.250.000,50'
    >>> formatear_numero(Decimal("10000"), 0)
    '10.000'
    >>> formatear_numero(Decimal("-1234.5"), 2)
    '-1.234,50'

    Un valor que no se puede interpretar devuelve cadena vacía en vez de
    romper la plantilla: en una pantalla, un dato faltante no debería tumbar
    todo lo demás.
    """
    numero = _a_decimal(valor)
    if numero is None:
        return ""

    decimales = max(0, int(decimales))
    cuantizado = numero.quantize(
        Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP
    )

    negativo = cuantizado < 0
    texto = f"{abs(cuantizado):,.{decimales}f}"
    # El formato de Python usa coma para miles y punto para decimales; acá
    # va al revés. Se cambia en dos pasos para no pisar un separador con el
    # otro a mitad de camino.
    texto = texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"-{texto}" if negativo else texto


def decimales_de(moneda):
    """Cuántos decimales corresponden a esa moneda.

    Acepta un objeto `Moneda` o un código. El guaraní no tiene decimales y
    el dólar tiene dos, pero eso lo define cada moneda en su propio campo
    (GEG9-82), no una lista escrita acá.
    """
    if moneda is None:
        return DECIMALES_POR_DEFECTO

    decimales = getattr(moneda, "decimales", None)
    if decimales is not None:
        return decimales

    # Vino un código suelto: hay que buscar la moneda.
    from apps.monedas.models import Moneda

    encontrada = Moneda.objects.filter(codigo=str(moneda)).first()
    return encontrada.decimales if encontrada else DECIMALES_POR_DEFECTO


def formatear_monto(valor, moneda=None, con_codigo=False):
    """Un importe, con los decimales que le correspondan a su moneda.

    >>> formatear_monto(Decimal("10000"), "PYG")
    '10.000'
    >>> formatear_monto(Decimal("102.5"), "USD")
    '102,50'
    """
    texto = formatear_numero(valor, decimales_de(moneda))
    if not texto or not con_codigo or moneda is None:
        return texto

    codigo = getattr(moneda, "codigo", moneda)
    return f"{texto} {codigo}"


def formatear_tasa(valor):
    """Una cotización, conservando los decimales que la hacen exacta.

    A diferencia de un importe, una tasa no se redondea a dos decimales
    porque dejaría de ser la que se aplicó. Se muestran al menos dos y se
    conservan hasta seis si son significativos.

    >>> formatear_tasa(Decimal("7120.00"))
    '7.120,00'
    >>> formatear_tasa(Decimal("0.000125"))
    '0,000125'
    """
    numero = _a_decimal(valor)
    if numero is None:
        return ""

    # Cuántos decimales hacen falta: se quitan los ceros de la derecha, con
    # un mínimo de dos y un máximo de seis.
    texto_plano = f"{numero:.6f}"
    decimales_significativos = len(texto_plano.split(".")[1].rstrip("0"))
    return formatear_numero(numero, max(2, min(6, decimales_significativos)))
