from django.conf import settings
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


class MetodoPago(models.Model):
    """Forma de pago que se le ofrece al cliente (RF035 — GEG9-77).

    Antes de esta historia los métodos estaban escritos a mano en
    `templates/pagos/elegir_pago.html`: habilitar o deshabilitar uno exigía
    editar el HTML y desplegar.

    Ojo con no confundir esto con `PAGO_PROVEEDOR`, la variable de entorno
    que elige la **pasarela** (dLocal o el proveedor simulado). Esa es una
    decisión técnica —"¿llamo a la API real o al doble de pruebas?"— y no
    tiene nada que ver con qué formas de pago ofrece el negocio.
    """

    class Flujo(models.TextChoices):
        # Cómo se procesa el cobro. Define a qué vista manda el botón, así
        # que la plantilla no necesita conocer cada método por su nombre.
        PASARELA = "PASARELA", "Cobro por pasarela"
        MANUAL = "MANUAL", "Verificación manual"

    codigo = models.SlugField(max_length=30, unique=True)
    nombre = models.CharField(max_length=60)
    descripcion = models.CharField(max_length=200, blank=True)
    flujo = models.CharField(max_length=10, choices=Flujo.choices)
    habilitado = models.BooleanField(default=True, db_index=True)
    orden = models.PositiveSmallIntegerField(
        default=0, help_text="En qué orden se muestran al cliente."
    )

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "método de pago"
        verbose_name_plural = "métodos de pago"

    def __str__(self):
        return self.nombre


class CambioMetodoPago(models.Model):
    """Quién habilitó o deshabilitó un método y cuándo (RF035 — GEG9-77).

    Se crea un registro por cada cambio y nunca se edita ni se borra, igual
    que `CambioEstado` en RF023. Guardar solo el último cambio en el propio
    `MetodoPago` habría perdido el historial: si alguien deshabilita un
    método y otro lo vuelve a habilitar, el primero desaparecía.
    """

    metodo = models.ForeignKey(
        MetodoPago, on_delete=models.CASCADE, related_name="cambios"
    )
    habilitado = models.BooleanField(help_text="Estado en el que quedó.")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cambios_metodos_pago",
        help_text="Vacío si el cambio lo hizo el sistema (por ejemplo, una migración).",
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
        verbose_name = "cambio de método de pago"
        verbose_name_plural = "cambios de métodos de pago"

    def __str__(self):
        estado = "habilitado" if self.habilitado else "deshabilitado"
        return f"{self.metodo}: {estado}"
