from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.monedas.models import Moneda

from .models import (
    ArqueoCaja,
    Caja,
    DenominacionBillete,
    DiferenciaCaja,
    FondoCajero,
    MovimientoCaja,
)


class MovimientoCajaForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=[
            choice
            for choice in MovimientoCaja.Tipo.choices
            if choice[0]
            not in (
                MovimientoCaja.Tipo.INGRESO_CAJERO,
                MovimientoCaja.Tipo.RETIRO_CAJERO,
            )
        ]
    )
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


class ArqueoCajaForm(forms.Form):
    moneda = forms.ModelChoiceField(queryset=Moneda.objects.none())
    observaciones = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, cajero=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cajero = cajero
        self.caja = (
            Caja.objects.filter(fondos_cajeros__cajero=cajero)
            .distinct()
            .select_related("sucursal")
            .first()
        )
        self.fields["moneda"].queryset = Moneda.objects.filter(
            activo=True, fondocajero__cajero=cajero
        ).distinct().order_by("codigo")
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
                widget=forms.NumberInput(attrs={"min": "0", "step": "1"}),
            )
            self.campos_billetes.append({"denominacion": denominacion, "campo": self[nombre]})

    def clean(self):
        datos = super().clean()
        moneda = datos.get("moneda")
        cantidades = {}
        if moneda:
            if not FondoCajero.objects.filter(
                caja=self.caja, cajero=self.cajero, moneda=moneda
            ).exists():
                self.add_error("moneda", "No tenés fondos asignados en esa caja y moneda.")
            total = 0
            for item in self.campos_billetes:
                denominacion = item["denominacion"]
                cantidad = datos.get(f"billete_{denominacion.pk}") or 0
                if denominacion.moneda_id != moneda.pk:
                    if cantidad:
                        self.add_error(
                            f"billete_{denominacion.pk}",
                            "La denominación no pertenece a la moneda seleccionada.",
                        )
                    continue
                if cantidad:
                    cantidades[denominacion.pk] = cantidad
                    total += cantidad * denominacion.valor
            datos["importe_calculado"] = total
        datos["billetes"] = cantidades
        return datos


class DiferenciaCajaForm(forms.Form):
    arqueo = forms.ModelChoiceField(queryset=ArqueoCaja.objects.none())
    monto = forms.DecimalField(min_value=0.01, max_digits=18, decimal_places=2)
    moneda = forms.ModelChoiceField(queryset=Moneda.objects.none())
    motivo = forms.CharField(max_length=255)
    responsable = forms.ModelChoiceField(queryset=get_user_model().objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["arqueo"].queryset = ArqueoCaja.objects.select_related(
            "caja__sucursal", "cajero", "moneda"
        ).order_by("-creado_en", "-pk")
        self.fields["moneda"].queryset = Moneda.objects.filter(activo=True).order_by(
            "codigo"
        )
        self.fields["responsable"].queryset = get_user_model().objects.filter(
            is_active=True
        ).order_by("username")

    def clean(self):
        datos = super().clean()
        arqueo = datos.get("arqueo")
        moneda = datos.get("moneda")
        if arqueo and moneda and arqueo.moneda_id != moneda.pk:
            self.add_error("moneda", "La divisa debe coincidir con la del arqueo.")
        return datos

class AjusteDiferenciaCajaForm(forms.Form):
    """Desglose físico para autorizar el ajuste de una diferencia de caja."""

    def __init__(self, *args, diferencia, **kwargs):
        super().__init__(*args, **kwargs)
        self.diferencia = diferencia
        self.campos_billetes = []

        denominaciones = DenominacionBillete.objects.filter(
            moneda=diferencia.moneda
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
                    }
                ),
            )
            self.campos_billetes.append(
                {
                    "denominacion": denominacion,
                    "campo": self[nombre],
                    "valor_centavos": int(denominacion.valor * 100),
                }
            )

    def clean(self):
        datos = super().clean()
        cantidades = {}
        total = 0

        for item in self.campos_billetes:
            denominacion = item["denominacion"]
            cantidad = datos.get(f"billete_{denominacion.pk}") or 0

            if cantidad:
                cantidades[denominacion.pk] = cantidad
                total += cantidad * denominacion.valor

        if not cantidades:
            self.add_error(
                None,
                "Ingresá al menos una cantidad de billetes para el ajuste.",
            )
        elif total != self.diferencia.monto:
            self.add_error(
                None,
                "El total de billetes debe coincidir con el monto de la diferencia.",
            )

        datos["billetes"] = cantidades
        datos["importe_calculado"] = total
        return datos