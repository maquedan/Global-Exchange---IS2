from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.monedas.models import Moneda


class Sucursal(models.Model):
    """Sucursal única del sistema, con una caja asociada."""

    nombre = models.CharField(max_length=120, unique=True)
    direccion = models.CharField(max_length=255)
    activa = models.BooleanField(default=True, db_index=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    es_unica = models.BooleanField(default=True, editable=False, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "sucursal"
        verbose_name_plural = "sucursales"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(es_unica=True),
                name="sucursal_es_unica",
            ),
        ]

    def __str__(self):
        return self.nombre


class Caja(models.Model):
    """Caja principal de efectivo de una sucursal."""

    sucursal = models.OneToOneField(
        Sucursal, on_delete=models.PROTECT, related_name="caja"
    )
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "caja"
        verbose_name_plural = "cajas"

    def __str__(self):
        return f"Caja — {self.sucursal.nombre}"


class SaldoCaja(models.Model):
    """Saldo disponible en la caja principal para una moneda."""

    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="saldos")
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)
    saldo = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        ordering = ["moneda__codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["caja", "moneda"], name="saldo_caja_moneda_unico"
            ),
            models.CheckConstraint(
                condition=models.Q(saldo__gte=0), name="saldo_caja_no_negativo"
            ),
        ]
        verbose_name = "saldo de caja"
        verbose_name_plural = "saldos de caja"

    def __str__(self):
        return f"{self.caja} — {self.moneda.codigo}: {self.saldo}"


class FondoCajero(models.Model):
    """Saldo de efectivo asignado a un cajero por caja y moneda."""

    caja = models.ForeignKey(
        Caja, on_delete=models.PROTECT, related_name="fondos_cajeros"
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="fondos_cajero",
    )
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)
    saldo = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        ordering = ["cajero__username", "moneda__codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["caja", "cajero", "moneda"], name="fondo_cajero_moneda_unico"
            ),
            models.CheckConstraint(
                condition=models.Q(saldo__gte=0), name="fondo_cajero_no_negativo"
            ),
        ]
        verbose_name = "fondo de cajero"
        verbose_name_plural = "fondos de cajeros"

    def __str__(self):
        return f"{self.cajero} — {self.moneda.codigo}: {self.saldo}"


class DenominacionBillete(models.Model):
    """Denominación de billete habilitada para una moneda."""

    moneda = models.ForeignKey(
        Moneda, on_delete=models.PROTECT, related_name="denominaciones_billetes"
    )
    valor = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        ordering = ["moneda__codigo", "-valor"]
        constraints = [
            models.UniqueConstraint(
                fields=["moneda", "valor"], name="denominacion_billete_moneda_valor"
            ),
            models.CheckConstraint(condition=models.Q(valor__gt=0), name="denominacion_billete_valor_positivo"),
        ]
        verbose_name = "denominación de billete"
        verbose_name_plural = "denominaciones de billetes"

    def __str__(self):
        return f"{self.moneda.codigo} {self.valor}"


class InventarioBilleteCaja(models.Model):
    """Cantidad disponible por denominación en la caja de una sucursal."""

    caja = models.ForeignKey(
        Caja, on_delete=models.PROTECT, related_name="inventario_billetes"
    )
    denominacion = models.ForeignKey(DenominacionBillete, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["denominacion__moneda__codigo", "-denominacion__valor"]
        constraints = [
            models.UniqueConstraint(
                fields=["caja", "denominacion"], name="inventario_billete_caja_unico"
            )
        ]
        verbose_name = "existencia de billetes en caja"
        verbose_name_plural = "existencias de billetes en caja"


class InventarioBilleteCajero(models.Model):
    """Cantidad por denominación asignada a un cajero en una caja."""

    caja = models.ForeignKey(
        Caja, on_delete=models.PROTECT, related_name="inventario_billetes_cajeros"
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventario_billetes_cajero",
    )
    denominacion = models.ForeignKey(DenominacionBillete, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["cajero__username", "denominacion__moneda__codigo", "-denominacion__valor"]
        constraints = [
            models.UniqueConstraint(
                fields=["caja", "cajero", "denominacion"],
                name="inventario_billete_cajero_unico",
            )
        ]
        verbose_name = "existencia de billetes de cajero"
        verbose_name_plural = "existencias de billetes de cajeros"


class MovimientoCaja(models.Model):
    """Registro inmutable de ingresos, retiros, asignaciones y devoluciones."""

    class Tipo(models.TextChoices):
        INGRESO = "INGRESO", "Ingreso a caja"
        RETIRO = "RETIRO", "Retiro de caja"
        ASIGNACION = "ASIGNACION", "Asignación a cajero"
        DEVOLUCION = "DEVOLUCION", "Devolución de cajero"
        INGRESO_CAJERO = "INGRESO_CAJERO", "Ingreso a fondo de cajero"
        RETIRO_CAJERO = "RETIRO_CAJERO", "Retiro de fondo de cajero"
        AJUSTE_INGRESO = "AJUSTE_INGRESO", "Ajuste de ingreso autorizado"
        AJUSTE_EGRESO = "AJUSTE_EGRESO", "Ajuste de egreso autorizado"

    caja = models.ForeignKey(
        Caja, on_delete=models.PROTECT, related_name="movimientos"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_caja",
        null=True,
        blank=True,
    )
    diferencia = models.OneToOneField(
    "DiferenciaCaja",
    on_delete=models.PROTECT,
    related_name="movimiento_ajuste",
    null=True,
    blank=True,
    )
    importe = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    saldo_caja_resultante = models.DecimalField(max_digits=18, decimal_places=2)
    saldo_cajero_resultante = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    realizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_caja_realizados",
    )
    nota = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        verbose_name = "movimiento de caja"
        verbose_name_plural = "movimientos de caja"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(importe__gt=0),
                name="movimiento_caja_importe_positivo",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.importe} {self.moneda.codigo}"


class DetalleMovimientoBillete(models.Model):
    """Desglose inmutable de billetes que componen un movimiento de caja."""

    movimiento = models.ForeignKey(
        MovimientoCaja, on_delete=models.PROTECT, related_name="detalle_billetes"
    )
    denominacion = models.ForeignKey(DenominacionBillete, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()

    class Meta:
        ordering = ["-denominacion__valor"]
        constraints = [
            models.UniqueConstraint(
                fields=["movimiento", "denominacion"],
                name="detalle_movimiento_billete_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name="detalle_movimiento_billete_cantidad_positiva",
            ),
        ]
        verbose_name = "detalle de billetes del movimiento"
        verbose_name_plural = "detalles de billetes del movimiento"


class ConteoInventarioBilletes(models.Model):
    """Auditoría del conteo que inicializa o reconcilia existencias de billetes."""

    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="conteos_billetes")
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="conteos_inventario_billetes",
        null=True,
        blank=True,
    )
    importe_total = models.DecimalField(max_digits=18, decimal_places=2)
    realizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="conteos_billetes_realizados",
    )
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        verbose_name = "conteo de inventario de billetes"
        verbose_name_plural = "conteos de inventario de billetes"


class DetalleConteoInventarioBilletes(models.Model):
    conteo = models.ForeignKey(
        ConteoInventarioBilletes, on_delete=models.PROTECT, related_name="detalle_billetes"
    )
    denominacion = models.ForeignKey(DenominacionBillete, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()

    class Meta:
        ordering = ["-denominacion__valor"]
        constraints = [
            models.UniqueConstraint(
                fields=["conteo", "denominacion"],
                name="detalle_conteo_billete_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name="detalle_conteo_billete_cantidad_positiva",
            ),
        ]


class ArqueoCaja(models.Model):
    """Cierre auditado del efectivo asignado a un cajero."""

    class Estado(models.TextChoices):
        CUADRADO = "CUADRADO", "Cuadrado"
        FALTANTE = "FALTANTE", "Faltante"
        SOBRANTE = "SOBRANTE", "Sobrante"

    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="arqueos")
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="arqueos_caja"
    )
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)
    saldo_esperado = models.DecimalField(max_digits=18, decimal_places=2)
    total_contado = models.DecimalField(max_digits=18, decimal_places=2)
    diferencia = models.DecimalField(max_digits=18, decimal_places=2)
    estado = models.CharField(max_length=10, choices=Estado.choices)
    observaciones = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        verbose_name = "arqueo de caja"
        verbose_name_plural = "arqueos de caja"

    def __str__(self):
        return (
            f"Arqueo #{self.pk} — {self.moneda.codigo} — "
            f"{self.cajero.username} — {self.creado_en:%d/%m/%Y %H:%M}"
        )


class DetalleArqueoBillete(models.Model):
    """Desglose inmutable del efectivo físico contado en un arqueo."""

    arqueo = models.ForeignKey(
        ArqueoCaja, on_delete=models.PROTECT, related_name="detalle_billetes"
    )
    denominacion = models.ForeignKey(DenominacionBillete, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()

    class Meta:
        ordering = ["-denominacion__valor"]
        constraints = [
            models.UniqueConstraint(
                fields=["arqueo", "denominacion"], name="detalle_arqueo_billete_unico"
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name="detalle_arqueo_billete_cantidad_positiva",
            ),
        ]


class DiferenciaCaja(models.Model):
    """Diferencia detectada en un arqueo y registrada para seguimiento."""

    arqueo = models.ForeignKey(
        ArqueoCaja, on_delete=models.PROTECT, related_name="diferencias"
    )
    monto = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    moneda = models.ForeignKey(Moneda, on_delete=models.PROTECT)
    motivo = models.CharField(max_length=255)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="diferencias_caja_responsable",
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="diferencias_caja_registradas",
    )
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]
        verbose_name = "diferencia de caja"
        verbose_name_plural = "diferencias de caja"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto__gt=0), name="diferencia_caja_monto_positivo"
            ),
        ]

    def __str__(self):
        return f"{self.monto} {self.moneda.codigo} — {self.arqueo}"
