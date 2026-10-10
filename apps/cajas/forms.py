from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.monedas.models import Moneda

from .models import DenominacionBillete, MovimientoCaja, Sucursal


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
    nota = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        caja = kwargs.pop("caja", None)
        super().__init__(*args, **kwargs)
        self.fields["moneda"].queryset = Moneda.objects.filter(activo=True).order_by(
            "codigo"
        )
        self.campos_billetes = []
        denominaciones = DenominacionBillete.objects.filter(
            moneda__activo=True
        ).select_related("moneda")
        for denominacion in denominaciones:
            nombre = f"billete_{denominacion.pk}"
            self.fields[nombre] = forms.IntegerField(
                label=f"{denominacion.moneda.codigo} {denominacion.valor}",
                min_value=0,
                required=False,
                initial=0,
                widget=forms.NumberInput(
                    attrs={
                        "min": "0",
                        "step": "1",
                        "data-billete-moneda": denominacion.moneda_id,
                    }
                ),
            )
            self.campos_billetes.append(
                {
                    "moneda": denominacion.moneda,
                    "denominacion": denominacion,
                    "valor_centavos": int(denominacion.valor * 100),
                    "campo": self[nombre],
                }
            )
        self.campos_generales = [
            self[name] for name in ("tipo", "moneda", "cajero", "nota")
        ]
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
        moneda = datos.get("moneda")
        cantidades = {}
        total = 0
        if moneda is not None:
            for denominacion in DenominacionBillete.objects.filter(
                moneda__activo=True
            ).select_related("moneda"):
                cantidad = datos.get(f"billete_{denominacion.pk}") or 0
                if denominacion.moneda_id != moneda.pk:
                    if cantidad:
                        self.add_error(
                            f"billete_{denominacion.pk}",
                            "La denominación no pertenece a la divisa seleccionada.",
                        )
                    continue
                if cantidad:
                    cantidades[denominacion.pk] = cantidad
                    total += cantidad * denominacion.valor
            if not cantidades:
                self.add_error(None, "Ingresá al menos una cantidad de billetes.")
        datos["billetes"] = cantidades
        datos["importe_calculado"] = total
        return datos


class DenominacionBilleteForm(forms.ModelForm):
    class Meta:
        model = DenominacionBillete
        fields = ("moneda", "valor")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["moneda"].queryset = Moneda.objects.filter(activo=True).order_by(
            "codigo"
        )


class ConteoInventarioBilletesForm(forms.Form):
    moneda = forms.ModelChoiceField(queryset=Moneda.objects.none())
    cajero = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(), required=False
    )

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
        self.campos_billetes = []
        for denominacion in DenominacionBillete.objects.filter(
            moneda__activo=True
        ).select_related("moneda"):
            nombre = f"billete_{denominacion.pk}"
            self.fields[nombre] = forms.IntegerField(
                label=f"{denominacion.moneda.codigo} {denominacion.valor}",
                min_value=0,
                required=False,
                initial=0,
                widget=forms.NumberInput(
                    attrs={
                        "min": "0",
                        "step": "1",
                        "data-billete-moneda": denominacion.moneda_id,
                    }
                ),
            )
            self.campos_billetes.append(
                {
                    "moneda": denominacion.moneda,
                    "denominacion": denominacion,
                    "campo": self[nombre],
                }
            )
        self.campos_generales = [self[name] for name in ("moneda", "cajero")]

    def clean(self):
        datos = super().clean()
        moneda = datos.get("moneda")
        cantidades = {}
        if moneda is not None:
            for denominacion in DenominacionBillete.objects.filter(
                moneda__activo=True
            ).select_related("moneda"):
                cantidad = datos.get(f"billete_{denominacion.pk}") or 0
                if denominacion.moneda_id != moneda.pk:
                    if cantidad:
                        self.add_error(
                            f"billete_{denominacion.pk}",
                            "La denominación no pertenece a la divisa seleccionada.",
                        )
                    continue
                if cantidad:
                    cantidades[denominacion.pk] = cantidad
        datos["billetes"] = cantidades
        return datos
