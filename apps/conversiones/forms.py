from decimal import Decimal

from django import forms

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
