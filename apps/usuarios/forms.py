"""Formularios de configuración de seguridad."""
from django import forms

from .models import (
    MAX_TIEMPO_INACTIVIDAD_MINUTOS,
    MIN_TIEMPO_INACTIVIDAD_MINUTOS,
    ConfiguracionSeguridad,
)


class ConfiguracionSeguridadForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionSeguridad
        fields = ["tiempo_inactividad_minutos"]
        labels = {"tiempo_inactividad_minutos": "Tiempo de inactividad"}
        help_texts = {
            "tiempo_inactividad_minutos": (
                f"Entre {MIN_TIEMPO_INACTIVIDAD_MINUTOS} y "
                f"{MAX_TIEMPO_INACTIVIDAD_MINUTOS} minutos."
            ),
        }
        widgets = {
            "tiempo_inactividad_minutos": forms.NumberInput(
                attrs={
                    "min": MIN_TIEMPO_INACTIVIDAD_MINUTOS,
                    "max": MAX_TIEMPO_INACTIVIDAD_MINUTOS,
                    "step": 1,
                    "required": True,
                }
            ),
        }
