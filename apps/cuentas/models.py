from django.core.exceptions import ValidationError
from django.db import models

from apps.clientes.models import Cliente


class CuentaPago(models.Model):
    """Cuenta bancaria o billetera electrónica de un cliente (RF020 — GEG9-30)."""

    class Tipo(models.TextChoices):
        BANCARIA = "BANCARIA", "Cuenta bancaria"
        BILLETERA = "BILLETERA", "Billetera electrónica"

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="cuentas_pago",
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    entidad = models.CharField(
        max_length=100,
        help_text="Banco (ej. Banco Itaú) o billetera (ej. Tigo Money).",
    )
    numero_cuenta = models.CharField(
        max_length=30,
        verbose_name="Número de cuenta / teléfono",
    )
    titular = models.CharField(max_length=150)
    alias = models.CharField(max_length=50, blank=True)

    activa = models.BooleanField(default=True, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "cuenta de pago"
        verbose_name_plural = "cuentas de pago"
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "entidad", "numero_cuenta"],
                name="cuenta_pago_unica_por_cliente",
            ),
        ]

    def clean(self):
        if self.cliente_id and not self.cliente.activo:
            raise ValidationError(
                {"cliente": "Solo se pueden registrar medios de pago para clientes activos."}
            )

    def desactivar(self):
        """Baja lógica: no se borra, se marca inactiva."""
        self.activa = False
        self.save(update_fields=["activa"])

    def activar(self):
        self.activa = True
        self.save(update_fields=["activa"])

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.entidad} ({self.numero_cuenta})"
