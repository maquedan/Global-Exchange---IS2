from django import forms

from .models import RegistroAuditoria


class FiltroAuditoriaForm(forms.Form):
    usuario = forms.ChoiceField(required=False, label="Usuario")
    accion = forms.ChoiceField(
        required=False,
        label="Acción",
        choices=[("", "Todas")] + list(RegistroAuditoria.Accion.choices),
    )
    fecha_desde = forms.DateField(
        required=False,
        label="Desde",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    fecha_hasta = forms.DateField(
        required=False,
        label="Hasta",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuarios = (
            RegistroAuditoria.objects.order_by("usuario_nombre")
            .values_list("usuario_nombre", flat=True)
            .distinct()
        )
        self.fields["usuario"].choices = [("", "Todos")] + [
            (nombre, nombre) for nombre in usuarios
        ]

    def clean(self):
        datos = super().clean()
        desde = datos.get("fecha_desde")
        hasta = datos.get("fecha_hasta")
        if desde and hasta and desde > hasta:
            self.add_error("fecha_hasta", "La fecha final debe ser posterior a la inicial.")
        return datos
