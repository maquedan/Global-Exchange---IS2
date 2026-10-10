from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.monedas.models import Moneda

from .models import MovimientoCaja, Sucursal


class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = ("nombre", "direccion", "activa")

    def clean_activa(self):
        activa = self.cleaned_data["activa"]
        if not activa and self.instance.pk:
            caja = getattr(self.instance, "caja", None)
            if caja and (
                caja.saldos.filter(saldo__gt=0).exists()
                or caja.fondos_cajeros.filter(saldo__gt=0).exists()
            ):
                raise forms.ValidationError(
                    "No se puede desactivar una sucursal con fondos pendientes en caja o asignados a cajeros."
                )
        return activa


class MovimientoCajaForm(forms.Form):
    tipo = forms.ChoiceField(choices=MovimientoCaja.Tipo.choices)
    moneda = forms.ModelChoiceField(queryset=Moneda.objects.none())
    cajero = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(), required=False
    )
    importe = forms.DecimalField(max_digits=18, decimal_places=2, min_value=0.01)
    nota = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        caja = kwargs.pop("caja", None)
        super().__init__(*args, **kwargs)
        self.fields["moneda"].queryset = Moneda.objects.filter(activo=True).order_by(
            "codigo"
        )
        cajeros = get_user_model().objects.filter(is_active=True, groups__name="cajero")
        if caja is not None:
            cajeros = get_user_model().objects.filter(
                Q(is_active=True, groups__name="cajero")
                | Q(fondos_cajero__caja=caja, fondos_cajero__saldo__gt=0)
            )
        self.fields["cajero"].queryset = cajeros.order_by("username").distinct()

    def clean(self):
        datos = super().clean()
        if datos.get("tipo") in (
            MovimientoCaja.Tipo.ASIGNACION,
            MovimientoCaja.Tipo.DEVOLUCION,
        ) and not datos.get("cajero"):
            self.add_error("cajero", "Seleccioná un cajero para este movimiento.")
        elif datos.get("tipo") in (
            MovimientoCaja.Tipo.INGRESO,
            MovimientoCaja.Tipo.RETIRO,
        ) and datos.get("cajero"):
            self.add_error("cajero", "Este movimiento no debe indicar un cajero.")
        return datos
