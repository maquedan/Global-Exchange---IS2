from django.core.validators import RegexValidator
from django.db import models


class Moneda(models.Model):
    """Divisa administrada para definir las monedas admitidas (GEG9-26 — RF014)."""

    codigo = models.CharField(
        max_length=3,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Z]{3}$",
                message="El código debe tener exactamente tres letras mayúsculas.",
            ),
        ],
    )
    nombre = models.CharField(max_length=100)
    simbolo = models.CharField(max_length=10)
    activo = models.BooleanField(default=True, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "moneda"
        verbose_name_plural = "monedas"

    def desactivar(self):
        """Deja la moneda fuera de operación sin eliminar su historial."""
        self.activo = False
        self.save(update_fields=["activo", "actualizado_en"])

    def activar(self):
        """Habilita nuevamente la moneda para futuras operaciones."""
        self.activo = True
        self.save(update_fields=["activo", "actualizado_en"])

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"