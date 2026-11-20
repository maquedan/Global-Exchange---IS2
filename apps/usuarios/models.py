"""Permisos funcionales locales asociados a roles del realm de Keycloak."""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


MIN_TIEMPO_INACTIVIDAD_MINUTOS = 5
MAX_TIEMPO_INACTIVIDAD_MINUTOS = 480


class ConfiguracionSeguridad(models.Model):
    """Parámetros de seguridad dinámicos de la plataforma."""

    tiempo_inactividad_minutos = models.PositiveSmallIntegerField(
        default=15,
        validators=[
            MinValueValidator(MIN_TIEMPO_INACTIVIDAD_MINUTOS),
            MaxValueValidator(MAX_TIEMPO_INACTIVIDAD_MINUTOS),
        ],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    tiempo_inactividad_minutos__gte=MIN_TIEMPO_INACTIVIDAD_MINUTOS,
                    tiempo_inactividad_minutos__lte=MAX_TIEMPO_INACTIVIDAD_MINUTOS,
                ),
                name="tiempo_inactividad_en_rango_seguro",
            ),
        ]
        verbose_name = "configuración de seguridad"
        verbose_name_plural = "configuraciones de seguridad"


class CambioConfiguracionSeguridad(models.Model):
    """Registro inmutable de cambios a la configuración de seguridad."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="cambios_configuracion_seguridad",
    )
    usuario_nombre = models.CharField(max_length=150)
    tiempo_inactividad_anterior_minutos = models.PositiveSmallIntegerField()
    tiempo_inactividad_nuevo_minutos = models.PositiveSmallIntegerField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        verbose_name = "cambio de configuración de seguridad"
        verbose_name_plural = "cambios de configuración de seguridad"

    def __str__(self):
        return (
            f"{self.usuario_nombre}: {self.tiempo_inactividad_anterior_minutos} "
            f"→ {self.tiempo_inactividad_nuevo_minutos} min ({self.creado_en})"
        )


class RegistroAuditoria(models.Model):
    """Registro de solo consulta de las operaciones críticas administrativas."""

    class Accion(models.TextChoices):
        TASA_CREADA = "TASA_CREADA", "Tasa creada"
        TASA_MODIFICADA = "TASA_MODIFICADA", "Tasa modificada"
        TASA_ACTIVADA = "TASA_ACTIVADA", "Tasa activada"
        TASA_DESACTIVADA = "TASA_DESACTIVADA", "Tasa desactivada"
        COMISION_CREADA = "COMISION_CREADA", "Comisión creada"
        COMISION_MODIFICADA = "COMISION_MODIFICADA", "Comisión modificada"
        CLIENTE_CREADO = "CLIENTE_CREADO", "Cliente registrado"
        CLIENTE_MODIFICADO = "CLIENTE_MODIFICADO", "Cliente modificado"
        CLIENTE_DESACTIVADO = "CLIENTE_DESACTIVADO", "Cliente dado de baja"
        CLIENTE_ACTIVADO = "CLIENTE_ACTIVADO", "Cliente reactivado"
        CLIENTE_ASOCIACIONES_ACTUALIZADAS = (
            "CLIENTE_ASOCIACIONES_ACTUALIZADAS",
            "Asociaciones de clientes actualizadas",
        )
        COMPRA_ANULADA = "COMPRA_ANULADA", "Compra anulada"
        VENTA_ANULADA = "VENTA_ANULADA", "Venta anulada"
        COMPRA_CONCILIADA = "COMPRA_CONCILIADA", "Compra conciliada"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    usuario_nombre = models.CharField(max_length=150, db_index=True)
    accion = models.CharField(max_length=40, choices=Accion.choices, db_index=True)
    detalles = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"

    def __str__(self):
        return f"{self.usuario_nombre}: {self.get_accion_display()} ({self.creado_en})"


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
