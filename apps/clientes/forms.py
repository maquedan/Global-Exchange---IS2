from django import forms

from .models import Cliente


class ClienteForm(forms.ModelForm):
    """Formulario de registro de clientes para RF001 — GEG9-11."""

    class Meta:
        model = Cliente
        fields = (
            "tipo",
            "nombres",
            "apellidos",
            "documento",
            "razon_social",
            "ruc",
            "email",
            "telefono",
            "direccion",
        )
        widgets = {
            "direccion": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        """Limpia los datos que no corresponden al tipo de cliente elegido."""
        datos = super().clean()
        tipo = datos.get("tipo")

        if tipo == Cliente.Tipo.FISICA:
            datos["razon_social"] = ""
            datos["ruc"] = None

        elif tipo == Cliente.Tipo.JURIDICA:
            datos["nombres"] = ""
            datos["apellidos"] = ""
            datos["documento"] = None

        return datos