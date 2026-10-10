from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.clientes.models import Cliente
from apps.cuentas.models import CuentaPago
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


class CompraDivisa(models.Model):
    """Compra de divisas para RF018 (GEG9-31), con cancelación por cambio de
    cotización para RF051 (GEG9-51).

    Los importes, la tasa y la comisión se almacenan como una fotografía de la
    operación, tomada al iniciarla. Queda en estado PENDIENTE hasta que el
    cliente confirma el pago; si la tasa vigente para el par ya cambió en ese
    momento, la operación se cancela sola en vez de cobrar una tasa distinta a
    la que el cliente vio.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de confirmación"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        CANCELADA = "CANCELADA", "Cancelada"

    class MotivoCancelacion(models.TextChoices):
        CAMBIO_COTIZACION = "CAMBIO_COTIZACION", "La cotización cambió antes de confirmar"
        CLIENTE = "CLIENTE", "Cancelada por el cliente"
        EXPIRADA = "EXPIRADA", "Se venció el tiempo para confirmar"

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
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDIENTE
    )
    motivo_cancelacion = models.CharField(
        max_length=20, choices=MotivoCancelacion.choices, blank=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    confirmado_en = models.DateTimeField(null=True, blank=True)
    cancelado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
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


class VentaDivisa(models.Model):
    """Venta de divisas con el importe neto y cuenta destino como histórico.

    Igual que `CompraDivisa`, queda PENDIENTE hasta que el cliente confirma el
    pago; si la cotización cambió para entonces, se cancela sola (RF051).
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de confirmación"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        CANCELADA = "CANCELADA", "Cancelada"

    class MotivoCancelacion(models.TextChoices):
        CAMBIO_COTIZACION = "CAMBIO_COTIZACION", "La cotización cambió antes de confirmar"
        CLIENTE = "CLIENTE", "Cancelada por el cliente"
        EXPIRADA = "EXPIRADA", "Se venció el tiempo para confirmar"

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="ventas_divisas",
    )
    moneda_entregada = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="ventas_como_moneda_entregada",
    )
    moneda_acreditada = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="ventas_como_moneda_acreditada",
    )
    tasa_cambio = models.ForeignKey(
        TasaCambio,
        on_delete=models.PROTECT,
        related_name="ventas_confirmadas",
    )
    cuenta_destino = models.ForeignKey(
        CuentaPago,
        on_delete=models.PROTECT,
        related_name="ventas_divisas",
    )
    monto_entregado = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    porcentaje_comision = models.DecimalField(max_digits=5, decimal_places=2)
    monto_comision = models.DecimalField(max_digits=18, decimal_places=2)
    monto_convertido = models.DecimalField(max_digits=18, decimal_places=2)
    monto_acreditado = models.DecimalField(max_digits=18, decimal_places=2)
    tasa_aplicada = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDIENTE
    )
    motivo_cancelacion = models.CharField(
        max_length=20, choices=MotivoCancelacion.choices, blank=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    confirmado_en = models.DateTimeField(null=True, blank=True)
    cancelado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "venta de divisa"
        verbose_name_plural = "ventas de divisas"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(moneda_entregada=models.F("moneda_acreditada")),
                name="venta_divisa_monedas_diferentes",
            ),
        ]

    def clean(self):
        errores = {}
        if (
            self.moneda_entregada_id
            and self.moneda_acreditada_id
            and self.moneda_entregada_id == self.moneda_acreditada_id
        ):
            errores["moneda_acreditada"] = "La moneda acreditada debe ser diferente."
        if (
            self.cliente_id
            and self.cuenta_destino_id
            and self.cuenta_destino.cliente_id != self.cliente_id
        ):
            errores["cuenta_destino"] = "La cuenta debe pertenecer al cliente de la venta."
        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"Venta #{self.pk} — {self.cliente}"
