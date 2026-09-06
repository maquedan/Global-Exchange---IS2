from django import forms

from apps.monedas.models import Moneda

from .models import TasaCambio


class TasaCambioForm(forms.ModelForm):
    """Formulario para registrar y modificar tasas de cambio."""

    class Meta:
        model = TasaCambio
        fields = (
            "moneda_origen",
            "moneda_destino",
            "tasa_compra",
            "tasa_venta",
            "vigente_desde",
            "activo",
        )
        widgets = {
            "tasa_compra": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "tasa_venta": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "vigente_desde": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["moneda_origen"].queryset = Moneda.objects.filter(activo=True)
        self.fields["moneda_destino"].queryset = Moneda.objects.filter(activo=True)
        self.fields["vigente_desde"].input_formats = ["%Y-%m-%dT%H:%M"]
