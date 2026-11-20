from django import forms

from apps.comun.campos import TasaField

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
        # Las tasas entran con el mismo formato que los montos: 7.120,00
        # (GEG9-82). Se usa `field_classes` y no `widgets` porque hay que
        # cambiar cómo se interpreta el texto, no solo cómo se dibuja.
        field_classes = {
            "tasa_compra": TasaField,
            "tasa_venta": TasaField,
        }
        widgets = {
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
