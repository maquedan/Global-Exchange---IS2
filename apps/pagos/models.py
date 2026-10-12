from django.db import models

from apps.conversiones.models import CompraDivisa, VentaDivisa


class Pago(models.Model):
    """Pago de una operación a través de una pasarela (RF022 — GEG9-36).

    Por decisión del equipo la pasarela solo aplica a **Compra**: en una
    Venta el cliente entrega divisas y recibe PYG, no paga nada con tarjeta.
    El campo `venta` queda igual para no romper el patrón ya usado en RF023
    (dos FK nullable + "exactamente una completa"), aunque hoy nunca se usa.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        REEMBOLSADO = "REEMBOLSADO", "Reembolsado"
        REQUIERE_REVISION = "REQUIERE_REVISION", "Requiere revisión manual"

    compra = models.ForeignKey(
        CompraDivisa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagos",
    )
    venta = models.ForeignKey(
        VentaDivisa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagos",
    )
    proveedor = models.CharField(max_length=20)
    id_externo = models.CharField(max_length=100, blank=True)
    order_id = models.CharField(max_length=60, unique=True)
    monto = models.DecimalField(max_digits=16, decimal_places=2)
    moneda = models.CharField(max_length=3)
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    redirect_url = models.URLField(blank=True)
    respuesta_cruda = models.JSONField(
        default=dict,
        blank=True,
        help_text="Respuesta de la pasarela, sin claves ni cabeceras de autenticación.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(compra__isnull=False, venta__isnull=True)
                    | models.Q(compra__isnull=True, venta__isnull=False)
                ),
                name="pago_pertenece_a_una_sola_operacion",
            ),
        ]

    def __str__(self):
        return f"Pago {self.order_id} ({self.estado})"
