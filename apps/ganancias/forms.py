from django import forms
from apps.monedas.models import Moneda
from apps.conversiones.models import CompraDivisa


class FiltrosGananciasForm(forms.Form):
    fecha_desde = forms.DateField(required=False, input_formats=["%Y-%m-%d"], widget=forms.DateInput(attrs={"type": "date"}))
    fecha_hasta = forms.DateField(required=False, input_formats=["%Y-%m-%d"], widget=forms.DateInput(attrs={"type": "date"}))
    moneda = forms.ModelChoiceField(queryset=Moneda.objects.all(), required=False, label="Moneda")
    estado = forms.ChoiceField(choices=(("", "Todos"), *CompraDivisa.Estado.choices), required=False, label="Estado")
