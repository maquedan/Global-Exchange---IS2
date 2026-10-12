from django.conf import settings
from django.db import models

from apps.tasa_cambios.models import TasaCambio


class Notificacion(models.Model):
    """Notificación interna para un usuario (RF033 — GEG9-38).

    Respeta la clase `Notificacion` del diagrama de clases del Hito 2:
    usuario, tipo, mensaje, fecha, leída. El campo `tipo` es un
    `TextChoices` con un solo valor por ahora (`CAMBIO_TASA`), pensado para
    que una historia futura (RF034) agregue más sin tener que migrar de
    nuevo la forma del modelo.
    """

    class Tipo(models.TextChoices):
        CAMBIO_TASA = "CAMBIO_TASA", "Cambio de tasa de cambio"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notificaciones",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    mensaje = models.CharField(max_length=500)
    tasa = models.ForeignKey(
        TasaCambio,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notificaciones",
        help_text="De qué tasa se trata, para poder reconstruir el cambio.",
    )
    leida = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en"]
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"

    def __str__(self):
        return f"{self.usuario}: {self.mensaje[:40]}"
