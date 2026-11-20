"""Filtros de plantilla para mostrar números y montos (GEG9-82).

Se usan en vez de `floatformat`, que respeta el idioma del sitio y da
`1250000,50` —sin separador de miles— además de redondear en float.
"""
from django import template

from apps.comun.formato import formatear_monto, formatear_numero, formatear_tasa

register = template.Library()


@register.filter(name="monto")
def monto(valor, moneda=None):
    """Importe con los decimales de su moneda: ``{{ compra.total|monto:compra.moneda }}``.

    Sin moneda usa dos decimales.
    """
    return formatear_monto(valor, moneda)


@register.filter(name="monto_con_codigo")
def monto_con_codigo(valor, moneda):
    """Igual que `monto` pero agregando el código: ``10.000 PYG``."""
    return formatear_monto(valor, moneda, con_codigo=True)


@register.filter(name="tasa")
def tasa(valor):
    """Cotización, conservando los decimales que la hacen exacta."""
    return formatear_tasa(valor)


@register.filter(name="numero")
def numero(valor, decimales=2):
    """Cualquier otro número: cantidades, porcentajes."""
    return formatear_numero(valor, decimales)
