from django import forms

from .models import ComisionCategoria


class ComisionCategoriaForm(forms.ModelForm):
    """Formulario para configurar la comisión de una categoría — GEG9-35 - RF052."""

    class Meta:
        model = ComisionCategoria
        fields = (
            "categoria",
            "porcentaje",
        )
        widgets = {
            "porcentaje": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "max": "100",
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        """Evita cambiar la categoría al editar una configuración existente."""
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields["categoria"].disabled = True