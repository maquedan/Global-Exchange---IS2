from django import forms

from apps.clientes.models import Cliente

from .models import CuentaPago


class CuentaPagoForm(forms.ModelForm):
    """Alta y edición de medios de pago para RF020 — GEG9-30."""

    class Meta:
        model = CuentaPago
        fields = ("cliente", "tipo", "entidad", "numero_cuenta", "titular", "alias")

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None:
            # Solo puede elegir SUS PROPIOS clientes, no los de otra persona.
            self.fields["cliente"].queryset = Cliente.objects.filter(
                asociaciones_usuarios__usuario=usuario,
                activo=True,
            ).distinct()
