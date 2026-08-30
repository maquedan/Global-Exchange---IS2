"""Permisos funcionales locales asociados a roles del realm de Keycloak."""
from django.db import models


class PermisoSistema(models.Model):
    """Una capacidad de la aplicación que puede otorgarse a un rol."""

    codigo = models.SlugField(
        max_length=80,
        unique=True,
        help_text="Identificador técnico, por ejemplo: gestionar_clientes.",
    )
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "permiso del sistema"
        verbose_name_plural = "permisos del sistema"

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"


class PermisoRol(models.Model):
    """Relación entre un rol (gestionado por Keycloak) y un permiso local."""

    rol = models.CharField(max_length=255)
    permiso = models.ForeignKey(PermisoSistema, on_delete=models.CASCADE, related_name="roles")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["rol", "permiso"], name="rol_permiso_unico")]
        verbose_name = "asignación permiso-rol"
        verbose_name_plural = "asignaciones permiso-rol"

    def __str__(self):
        return f"{self.rol}: {self.permiso.codigo}"
