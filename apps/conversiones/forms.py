from decimal import Decimal

from django import forms

from apps.clientes.models import Cliente
from apps.monedas.models import Moneda

from .services import calcular_conversion


class SimulacionConversionForm(forms.Form):
    TIPOS_OPERACION = (
        ("compra", "Compra"),
        ("venta", "Venta"),
    )

    moneda_origen = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True),
        label="Moneda de origen",
    )
    moneda_destino = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True),
        label="Moneda de destino",
    )
    monto = forms.DecimalField(
        label="Monto",
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
    )
    tipo_operacion = forms.ChoiceField(
        choices=TIPOS_OPERACION,
        label="Tipo de operacion",
        widget=forms.RadioSelect,
    )

    def clean(self):
        datos = super().clean()
        origen = datos.get("moneda_origen")
        destino = datos.get("moneda_destino")

        if origen and destino and origen == destino:
            self.add_error(
                "moneda_destino",
                "La moneda de destino debe ser diferente de la de origen.",
            )

        return datos


def construir_resultado(formulario, tasa_cambio):
    datos = formulario.cleaned_data
    tipo_operacion = datos["tipo_operacion"]
    tasa = (
        tasa_cambio.tasa_compra
        if tipo_operacion == "compra"
        else tasa_cambio.tasa_venta
    )
    return {
        "monto": datos["monto"],
        "tasa": tasa,
        "resultado": calcular_conversion(datos["monto"], tasa, tipo_operacion),
        "tipo_operacion": tipo_operacion,
        "tasa_cambio": tasa_cambio,
    }


class CompraDivisaForm(forms.Form):
    """Datos que el cliente debe indicar para confirmar una compra de divisas."""

    cliente = forms.ModelChoiceField(queryset=Cliente.objects.none(), label="Cliente")
    moneda_pagada = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True),
        label="Moneda con la que pagás",
    )
    moneda_adquirida = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True),
        label="Moneda que querés adquirir",
    )
    monto_pagado = forms.DecimalField(
        label="Monto base a pagar",
        min_value=Decimal("0.01"),
        max_digits=16,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        help_text="La comisión se calcula aparte y se suma al total.",
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None:
            self.fields["cliente"].queryset = Cliente.objects.filter(
                asociaciones_usuarios__usuario=usuario,
                activo=True,
            ).distinct()

    def clean(self):
        datos = super().clean()
        if (
            datos.get("moneda_pagada")
            and datos.get("moneda_adquirida")
            and datos["moneda_pagada"] == datos["moneda_adquirida"]
        ):
            self.add_error(
                "moneda_adquirida",
                "La moneda a adquirir debe ser diferente de la moneda de pago.",
            )
        return datos
