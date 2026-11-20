from django.core.exceptions import ValidationError
from django.db import models


class RangoHorario(models.Model):
    """Rango en el que se pueden iniciar o confirmar operaciones."""

    class Dia(models.IntegerChoices):
        LUNES = 0, "Lunes"
        MARTES = 1, "Martes"
        MIERCOLES = 2, "Miércoles"
        JUEVES = 3, "Jueves"
        VIERNES = 4, "Viernes"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    dia = models.PositiveSmallIntegerField(choices=Dia.choices)
    hora_desde = models.TimeField()
    hora_hasta = models.TimeField()

    class Meta:
        ordering = ["dia", "hora_desde"]
        constraints = [
            models.UniqueConstraint(
                fields=["dia", "hora_desde", "hora_hasta"],
                name="rango_horario_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(hora_desde__lt=models.F("hora_hasta")),
                name="rango_horario_inicio_antes_fin",
            ),
        ]
        verbose_name = "rango horario operativo"
        verbose_name_plural = "rangos horarios operativos"

    def clean(self):
        if self.hora_desde and self.hora_hasta and self.hora_desde >= self.hora_hasta:
            raise ValidationError("La hora de inicio debe ser anterior a la hora de fin.")

    def __str__(self):
        return f"{self.get_dia_display()}: {self.hora_desde:%H:%M}–{self.hora_hasta:%H:%M}"
