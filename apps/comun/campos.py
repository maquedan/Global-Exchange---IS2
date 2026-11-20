"""Campos de formulario que entienden el formato local (GEG9-82).

El criterio de la historia es que los formularios acepten el importe escrito
como se muestra: `10.000` y `1.234,56`.

Eso **no se puede hacer con `<input type="number">`**: ese tipo de campo
solo admite un número con punto decimal, y el navegador vacía o rechaza
cualquier otra cosa antes de que llegue al servidor. Por eso `MontoField`
usa un campo de texto y hace la conversión acá.

El contrapeso, que conviene tener presente: se pierde el teclado numérico
del celular y la validación del propio navegador. La validación de Django
sigue intacta, y el valor que se guarda y con el que se calcula **no
cambia**: sigue siendo el mismo `Decimal` de siempre.
"""
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError


def interpretar_monto(texto, agrupa_con_punto=True):
    """Convierte lo que escribió la persona en un `Decimal`.

    Acepta las dos formas, porque la gente escribe de las dos maneras:

    >>> interpretar_monto("1.250.000,50")
    Decimal('1250000.50')
    >>> interpretar_monto("1250000.50")
    Decimal('1250000.50')
    >>> interpretar_monto("10.000")
    Decimal('10000')

    La regla para desambiguar `10.000` —¿diez mil, o diez con tres
    decimales?— es la que usa la gente al escribir: si hay coma, el punto es
    separador de miles; si no hay coma, un punto con exactamente tres
    dígitos detrás también es de miles. Un punto con otra cantidad de
    dígitos es decimal: `10.5` son diez y medio.

    `agrupa_con_punto=False` desactiva esa última regla, y es lo que usan
    las **tasas**: una cotización de `7.120` significa siete coma doce, no
    siete mil ciento veinte, porque las tasas llevan hasta seis decimales.
    Ahí un punto suelto siempre es decimal, y para los miles hay que usar la
    coma: `7.120,50`.
    """
    if texto is None:
        return None

    limpio = str(texto).strip().replace(" ", "")
    if not limpio:
        return None

    if "," in limpio:
        # Hay coma: es el separador decimal, los puntos son de miles.
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count(".") > 1:
        # Varios puntos solo puede ser agrupación de miles.
        limpio = limpio.replace(".", "")
    elif agrupa_con_punto and "." in limpio:
        entero, _, decimal = limpio.partition(".")
        if len(decimal) == 3 and entero.lstrip("-").isdigit():
            limpio = entero + decimal

    try:
        return Decimal(limpio)
    except InvalidOperation as error:
        raise ValidationError(
            "Escribí un importe válido, por ejemplo 10.000 o 1.234,56.",
            code="invalid",
        ) from error


class MontoField(forms.DecimalField):
    """`DecimalField` que acepta el importe con punto de miles y coma decimal.

    Hereda de `DecimalField`, así que `max_digits`, `decimal_places`, los
    validadores de mínimo y máximo y todo lo demás siguen funcionando igual.
    Lo único que cambia es cómo se interpreta el texto que llega.
    """

    widget = forms.TextInput

    #: Si un punto suelto con tres dígitos detrás se lee como miles.
    agrupa_con_punto = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget.attrs.setdefault("inputmode", "decimal")
        self.widget.attrs.setdefault("placeholder", "10.000")
        clases = self.widget.attrs.get("class", "")
        self.widget.attrs["class"] = f"{clases} monto-entrada".strip()

    def to_python(self, value):
        if value in self.empty_values:
            return None
        return super().to_python(
            interpretar_monto(value, agrupa_con_punto=self.agrupa_con_punto)
        )


class TasaField(MontoField):
    """Como `MontoField`, pero para cotizaciones.

    Una tasa puede tener hasta seis decimales, así que `7.120` tiene que
    seguir significando siete coma doce. Para escribir siete mil ciento
    veinte hay que usar la coma: `7.120,00`.
    """

    agrupa_con_punto = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget.attrs["placeholder"] = "7.120,00"
        # Se le saca la clase que dispara el formateo automático: en una
        # tasa, poner los puntos mientras se escribe sería un desastre.
        # Escribir 7120 se convertiría en "7.120", que esta misma clase lee
        # como 7,12 — mil veces menos. Las tasas se escriben tal cual.
        clases = self.widget.attrs.get("class", "").replace("monto-entrada", "")
        self.widget.attrs["class"] = f"{clases} tasa-entrada".strip()
