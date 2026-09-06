from django import forms

from .models import Moneda


class MonedaForm(forms.ModelForm):
    """Formulario para registrar y modificar monedas (GEG9-26 — RF014)."""

    class Meta:
        model = Moneda
        fields = (
            "codigo",
            "nombre",
            "simbolo",
        )

    def clean_codigo(self):
        """Normaliza el código de las monedas a mayúsculas antes de validarlo."""
        codigo = self.cleaned_data["codigo"].strip().upper()
        return codigo