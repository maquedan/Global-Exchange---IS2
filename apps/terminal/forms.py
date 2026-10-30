from decimal import Decimal

from django import forms

from apps.monedas.models import Moneda


class IdentificarClienteTerminalForm(forms.Form):
    """Solicita el documento o RUC para iniciar una operación en Terminal."""

    identificador = forms.CharField(
        label="Documento o RUC",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ingresá tu documento o RUC",
                "autocomplete": "off",
                "autofocus": True,
                "class": (
                    "w-full rounded-xl border-2 border-slate-300 px-5 py-4 "
                    "text-xl text-slate-900 outline-none transition "
                    "focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100"
                ),
            }
        ),
    )


    def clean_identificador(self):
        identificador = self.cleaned_data["identificador"].strip()

        if not identificador:
            raise forms.ValidationError(
                "Ingresá tu número de documento o RUC para continuar."
            )

        return identificador


class DatosOperacionTerminalForm(forms.Form):
    """Solicita monedas y monto para simular una operación de Terminal."""

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
        max_digits=16,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "min": "0.01",
            }
        ),
    )

    def __init__(self, *args, tipo_operacion, **kwargs):
        super().__init__(*args, **kwargs)

        if tipo_operacion == "compra":
            self.fields["moneda_origen"].label = "Moneda con la que vas a pagar"
            self.fields["moneda_destino"].label = "Moneda que querés comprar"
            self.fields["monto"].label = "Monto base a pagar"
        else:
            self.fields["moneda_origen"].label = "Divisa que vas a vender"
            self.fields["moneda_destino"].label = "Moneda que querés recibir"
            self.fields["monto"].label = "Monto de la divisa que vas a vender"

    def clean(self):
        datos = super().clean()

        if (
            datos.get("moneda_origen")
            and datos.get("moneda_destino")
            and datos["moneda_origen"] == datos["moneda_destino"]
        ):
            self.add_error(
                "moneda_destino",
                "Las monedas deben ser diferentes.",
            )

        return datos