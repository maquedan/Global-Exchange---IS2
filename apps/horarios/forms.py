from django import forms

from .models import RangoHorario


class RangoHorarioForm(forms.ModelForm):
    class Meta:
        model = RangoHorario
        fields = ("dia", "hora_desde", "hora_hasta")
        widgets = {
            "hora_desde": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "hora_hasta": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["hora_desde"].input_formats = ["%H:%M"]
        self.fields["hora_hasta"].input_formats = ["%H:%M"]
