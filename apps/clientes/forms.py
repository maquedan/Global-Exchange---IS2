from django import forms
from django.contrib.auth import get_user_model

from .models import Cliente


class ClienteForm(forms.ModelForm):
    """Formulario de registro de clientes para RF001 — GEG9-11."""

    class Meta:
        model = Cliente
        fields = (
            "tipo",
            "categoria",
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


class AsociacionUsuarioClienteForm(forms.Form):
    """Selecciona los clientes activos vinculados a un usuario."""

    usuario = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        label="Usuario",
    )
    clientes = forms.ModelMultipleChoiceField(
        queryset=Cliente.objects.none(),
        required=False,
        label="Clientes asociados",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuario_modelo = get_user_model()
        self.fields["usuario"].queryset = usuario_modelo.objects.filter(
            is_active=True,
        ).order_by("username")
        self.fields["clientes"].queryset = Cliente.objects.filter(activo=True)
