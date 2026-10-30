from decimal import Decimal

from django import forms

from apps.cajas.models import DenominacionBillete
from apps.monedas.models import Moneda

from .services import calcular_conversion


class SimulacionConversionForm(forms.Form):
    TIPOS_OPERACION = (
        ("compra", "Compra"),
        ("venta", "Venta"),
    )

    moneda_origen = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True),
        label="Moneda de origen",
    )
    moneda_destino = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True),
        label="Moneda de destino",
    )
    monto = forms.DecimalField(
        label="Monto",
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
    )
    tipo_operacion = forms.ChoiceField(
        choices=TIPOS_OPERACION,
        label="Tipo de operacion",
        widget=forms.RadioSelect,
    )

    def clean(self):
        datos = super().clean()
        origen = datos.get("moneda_origen")
        destino = datos.get("moneda_destino")

        if origen and destino and origen == destino:
            self.add_error(
                "moneda_destino",
                "La moneda de destino debe ser diferente de la de origen.",
            )

        return datos


def construir_resultado(formulario, tasa_cambio):
    datos = formulario.cleaned_data
    tipo_operacion = datos["tipo_operacion"]
    tasa = (
        tasa_cambio.tasa_compra
        if tipo_operacion == "compra"
        else tasa_cambio.tasa_venta
    )
    return {
        "monto": datos["monto"],
        "tasa": tasa,
        "resultado": calcular_conversion(datos["monto"], tasa, tipo_operacion),
        "tipo_operacion": tipo_operacion,
        "tasa_cambio": tasa_cambio,
    }


class CompraDivisaForm(forms.Form):
    """Datos que el cliente debe indicar para confirmar una compra de divisas.

    No pide elegir el cliente: la compra se hace en nombre del cliente
    activo de la sesión (RF008 — GEG9-18), que resuelve el servidor.
    """

    moneda_pagada = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True),
        label="Moneda con la que pagás",
    )
    moneda_adquirida = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True),
        label="Moneda que querés adquirir",
    )
    monto_pagado = forms.DecimalField(
        label="Monto base a pagar",
        min_value=Decimal("0.01"),
        max_digits=16,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        help_text="La comisión se calcula aparte y se suma al total.",
    )

    def clean(self):
        datos = super().clean()
        if (
            datos.get("moneda_pagada")
            and datos.get("moneda_adquirida")
            and datos["moneda_pagada"] == datos["moneda_adquirida"]
        ):
            self.add_error(
                "moneda_adquirida",
                "La moneda a adquirir debe ser diferente de la moneda de pago.",
            )
        return datos


class VentaDivisaForm(forms.Form):
    """Datos de una venta que el cajero liquidará en efectivo.

    Igual que la compra, opera en nombre del cliente activo de la sesión
    (RF008). El neto se entrega en efectivo al confirmar la venta (RF058).
    """

    moneda_entregada = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True), label="Divisa que vendés"
    )
    moneda_acreditada = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activo=True), label="Moneda a acreditar"
    )
    monto_entregado = forms.DecimalField(
        label="Monto de la divisa que vendés",
        min_value=Decimal("0.01"),
        max_digits=16,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        datos = super().clean()
        entregada = datos.get("moneda_entregada")
        acreditada = datos.get("moneda_acreditada")

        if entregada and acreditada and entregada == acreditada:
            self.add_error(
                "moneda_acreditada",
                "La moneda acreditada debe ser diferente de la que vendés.",
            )
        return datos


class EntregaEfectivoVentaForm(forms.Form):
    """Desglose editable con el menor total de billetes que cubre la venta."""

    def __init__(self, *args, moneda, importe, billetes_iniciales=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.moneda = moneda
        self.importe = importe
        self.denominaciones = list(
            DenominacionBillete.objects.filter(
                moneda=moneda, moneda__activo=True
            ).order_by("-valor")
        )
        self.campos_billetes = []
        billetes_iniciales = billetes_iniciales or {}
        for denominacion in self.denominaciones:
            nombre = f"billete_{denominacion.pk}"
            self.fields[nombre] = forms.IntegerField(
                label=f"{moneda.codigo} {denominacion.valor}",
                min_value=0,
                required=False,
                initial=billetes_iniciales.get(denominacion.pk, 0),
                widget=forms.NumberInput(attrs={"min": "0", "step": "1"}),
            )
            self.campos_billetes.append(
                {
                    "denominacion": denominacion,
                    "campo": self[nombre],
                }
            )

    def clean(self):
        datos = super().clean()
        cantidades = {}
        total = Decimal("0.00")
        for denominacion in self.denominaciones:
            cantidad = datos.get(f"billete_{denominacion.pk}") or 0
            if cantidad:
                cantidades[denominacion.pk] = cantidad
                total += denominacion.valor * cantidad

        if total != self.importe:
            diferencia = abs(self.importe - total)
            mensaje = (
                f"Faltan {diferencia:.2f} {self.moneda.codigo} para alcanzar "
                "el importe mínimo posible."
                if total < self.importe
                else f"El desglose supera el importe mínimo posible por "
                f"{diferencia:.2f} {self.moneda.codigo}."
            )
            self.add_error(
                None,
                mensaje,
            )
        datos["billetes"] = cantidades
        return datos
