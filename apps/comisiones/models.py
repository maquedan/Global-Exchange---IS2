from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.clientes.models import Cliente


class ComisionCategoria(models.Model):
    """Porcentaje de comisión vigente para una categoría de cliente — GEG9-35 - RF052."""

    categoria = models.CharField(
        max_length=20,
        choices=Cliente.Categoria.choices,
        unique=True,
    )
    porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        help_text="Porcentaje entre 0.00 y 100.00.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["categoria"]
        verbose_name = "comisión por categoría"
        verbose_name_plural = "comisiones por categoría"

    def __str__(self):
        return f"{self.get_categoria_display()}: {self.porcentaje}%"