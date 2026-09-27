from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.clientes.models import Cliente
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


class CompraDivisa(models.Model):
    """Compra de divisas confirmada para RF018 (GEG9-31).

    Los importes, la tasa y la comisión se almacenan como una fotografía de la
    operación. Así, un cambio posterior de cotización o de categoría no altera
    las compras que ya fueron confirmadas.
    """

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="compras_divisas",
    )
    moneda_pagada = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="compras_como_moneda_pagada",
    )
    moneda_adquirida = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="compras_como_moneda_adquirida",
    )
    tasa_cambio = models.ForeignKey(
        TasaCambio,
        on_delete=models.PROTECT,
        related_name="compras_confirmadas",
    )
    monto_pagado = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Importe base indicado por el cliente, sin comisión.",
    )
    porcentaje_comision = models.DecimalField(max_digits=5, decimal_places=2)
    monto_comision = models.DecimalField(max_digits=16, decimal_places=2)
    total_a_pagar = models.DecimalField(max_digits=16, decimal_places=2)
    tasa_aplicada = models.DecimalField(max_digits=12, decimal_places=2)
    monto_recibido = models.DecimalField(max_digits=18, decimal_places=2)
    confirmado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-confirmado_en"]
        verbose_name = "compra de divisa"
        verbose_name_plural = "compras de divisas"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(moneda_pagada=models.F("moneda_adquirida")),
                name="compra_divisa_monedas_diferentes",
            ),
        ]

    def clean(self):
        if (
            self.moneda_pagada_id
            and self.moneda_adquirida_id
            and self.moneda_pagada_id == self.moneda_adquirida_id
        ):
            raise ValidationError(
                {"moneda_adquirida": "La moneda a adquirir debe ser diferente."}
            )

    def __str__(self):
        return f"Compra #{self.pk} — {self.cliente}"
