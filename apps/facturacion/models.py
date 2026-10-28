"""Factura electrónica de una operación confirmada (RF026 — GEG9-50).

Esta historia es la base de la facturación: RF027 (envío por correo), RF028
(estado en el SIFEN), RF029 (descarga de KuDE/XML) y RF053 (visualización) se
construyen encima de `Factura`, sin cambiarle la forma. Por eso guarda el CDC
(lo necesitan las tres) y deja `estado_fiscal` vacío para que RF028 lo
complete.
"""
from django.db import models

from apps.conversiones.models import CompraDivisa, VentaDivisa


class SecuenciaFactura(models.Model):
    """Último número de factura usado en un establecimiento y punto de expedición.

    El SIFEN exige que `dNumDoc` sea una secuencia sin saltos ni
    repeticiones por establecimiento + punto de expedición. Un `max() + 1`
    sobre `Factura` se repetiría si dos operaciones se confirman a la vez,
    así que el número sale de acá tomando el candado de la fila con
    `select_for_update` (igual que el resto de los servicios del proyecto).
    """

    establecimiento = models.CharField(max_length=3)
    punto_expedicion = models.CharField(max_length=3)
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "secuencia de facturación"
        verbose_name_plural = "secuencias de facturación"
        constraints = [
            models.UniqueConstraint(
                fields=["establecimiento", "punto_expedicion"],
                name="secuencia_factura_unica_por_punto",
            ),
        ]

    def __str__(self):
        return f"{self.establecimiento}-{self.punto_expedicion}: {self.ultimo_numero}"

    @classmethod
    def siguiente_numero(cls, establecimiento, punto_expedicion, *, desde=1):
        """Reserva y devuelve el próximo `dNumDoc` como texto de 7 dígitos.

        `desde` es el primer número del rango que la cátedra autorizó para
        este punto de expedición: la secuencia arranca ahí, no en 1. Los ceros
        iniciales se conservan porque el SIFEN lo pide como texto de siete
        dígitos.

        Tiene que llamarse dentro de una transacción: el candado se libera al
        terminarla. Quien reserva un número está obligado a usarlo — si la
        emisión falla, la `Factura` se reintenta con el mismo número (ver
        `apps.facturacion.services`), para no dejar huecos en la secuencia.
        """
        secuencia, _ = cls.objects.get_or_create(
            establecimiento=establecimiento, punto_expedicion=punto_expedicion
        )
        secuencia = cls.objects.select_for_update().get(pk=secuencia.pk)
        secuencia.ultimo_numero = max(secuencia.ultimo_numero + 1, desde)
        secuencia.save(update_fields=["ultimo_numero"])
        return f"{secuencia.ultimo_numero:07d}"


class Factura(models.Model):
    """Factura electrónica emitida por una compra o una venta de divisas.

    Siempre pertenece a una compra o a una venta, nunca a las dos ni a
    ninguna, y una operación no puede tener más de una factura — lo exigen
    los `constraints` de abajo. Es el mismo patrón que `CambioEstado`
    (RF023) y `Pago` (RF022).
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de emisión"
        GENERADA = "GENERADA", "Generada en Factura Segura"
        ERROR = "ERROR", "Error al emitir"
        # La petición es síncrona: si se corta la conexión o se vence el
        # tiempo, el servidor pudo haberla procesado igual. Sin el CDC no hay
        # forma de consultar qué pasó, así que NO se reintenta sola: queda
        # para revisión manual.
        A_VERIFICAR = "A_VERIFICAR", "A verificar manualmente"

    compra = models.ForeignKey(
        CompraDivisa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="facturas",
    )
    venta = models.ForeignKey(
        VentaDivisa,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="facturas",
    )

    # Identificación del documento ante el SIFEN
    timbrado = models.CharField(max_length=20)
    establecimiento = models.CharField(max_length=3)
    punto_expedicion = models.CharField(max_length=3)
    numero = models.CharField(max_length=7, help_text="dNumDoc")
    cdc = models.CharField(
        max_length=44,
        blank=True,
        help_text="Código de Control que devuelve Factura Segura (44 dígitos).",
    )

    # Importes. Se factura siempre en guaraníes; `monto_origen` guarda la
    # cifra en la moneda real de la operación para poder mostrar las dos.
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    moneda = models.CharField(max_length=3, default="PYG")
    monto_origen = models.DecimalField(max_digits=18, decimal_places=2)
    moneda_origen = models.CharField(max_length=3)

    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDIENTE
    )
    mensaje_error = models.CharField(max_length=500, blank=True)
    estado_fiscal = models.CharField(
        max_length=50,
        blank=True,
        help_text="Estado en el SIFEN. Lo completa RF028; esta historia lo deja vacío.",
    )
    operation_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="operation_info.id de la última llamada, para auditoría.",
    )
    intentos = models.PositiveSmallIntegerField(default=0)

    peticion = models.JSONField(
        default=dict,
        blank=True,
        help_text="DE enviado a Factura Segura. Nunca incluye el token ni cabeceras.",
    )
    respuesta = models.JSONField(
        default=dict,
        blank=True,
        help_text="Respuesta de Factura Segura, tal como vino.",
    )

    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)
    generada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creada_en"]
        verbose_name = "factura electrónica"
        verbose_name_plural = "facturas electrónicas"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(compra__isnull=False, venta__isnull=True)
                    | models.Q(compra__isnull=True, venta__isnull=False)
                ),
                name="factura_pertenece_a_una_sola_operacion",
            ),
            models.UniqueConstraint(
                fields=["compra"],
                condition=models.Q(compra__isnull=False),
                name="factura_unica_por_compra",
            ),
            models.UniqueConstraint(
                fields=["venta"],
                condition=models.Q(venta__isnull=False),
                name="factura_unica_por_venta",
            ),
            models.UniqueConstraint(
                fields=["establecimiento", "punto_expedicion", "numero"],
                name="factura_numero_unico_por_punto",
            ),
        ]

    def __str__(self):
        return f"Factura {self.numero_completo} ({self.estado})"

    @property
    def numero_completo(self):
        """El número como se imprime en el KuDE: ``001-001-0000001``."""
        return f"{self.establecimiento}-{self.punto_expedicion}-{self.numero}"

    @property
    def operacion(self):
        """La compra o la venta a la que pertenece, la que esté cargada."""
        return self.compra or self.venta
