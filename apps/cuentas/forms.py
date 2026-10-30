from django import forms

from .models import CuentaPago


class CuentaPagoForm(forms.ModelForm):
    """Alta y edición de medios de pago para RF020 — GEG9-30.

    Ya no pide elegir el cliente: la cuenta se carga para el cliente activo
    de la sesión (RF008 — GEG9-18), que asigna la vista en el servidor.
    """

    class Meta:
        model = CuentaPago
        fields = ("tipo", "entidad", "numero_cuenta", "titular", "alias")

    def __init__(self, *args, cliente=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cliente is not None:
            self.instance.cliente = cliente

    def _get_validation_exclusions(self):
        """No excluye `cliente` de la validación, aunque no esté en el formulario.

        La restricción `cuenta_pago_unica_por_cliente` es sobre
        (cliente, entidad, numero_cuenta). Django excluye por defecto los
        campos que no están en el formulario, así que sin esto la cuenta
        duplicada dejaba de detectarse acá y explotaba recién contra la base
        con un IntegrityError.
        """
        exclusiones = super()._get_validation_exclusions()
        exclusiones.discard("cliente")
        return exclusiones
