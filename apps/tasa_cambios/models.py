from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.monedas.models import Moneda


class TasaCambio(models.Model):
	"""Tasa de compra y venta vigente para un par de monedas."""

	moneda_origen = models.ForeignKey(
		Moneda,
		on_delete=models.PROTECT,
		related_name="tasas_como_origen",
	)
	moneda_destino = models.ForeignKey(
		Moneda,
		on_delete=models.PROTECT,
		related_name="tasas_como_destino",
	)
	tasa_compra = models.DecimalField(
		max_digits=12,
		decimal_places=2,
		validators=[MinValueValidator(Decimal("0.01"))],
	)
	tasa_venta = models.DecimalField(
		max_digits=12,
		decimal_places=2,
		validators=[MinValueValidator(Decimal("0.01"))],
	)
	vigente_desde = models.DateTimeField()
	activo = models.BooleanField(default=True, db_index=True)
	creado_en = models.DateTimeField(auto_now_add=True)
	actualizado_en = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-vigente_desde"]
		verbose_name = "tasa de cambio"
		verbose_name_plural = "tasas de cambio"
		constraints = [
			models.CheckConstraint(
				condition=~models.Q(moneda_origen=models.F("moneda_destino")),
				name="tasa_cambio_monedas_diferentes",
			),
			models.CheckConstraint(
				condition=models.Q(tasa_compra__gt=0),
				name="tasa_cambio_compra_positiva",
			),
			models.CheckConstraint(
				condition=models.Q(tasa_venta__gt=0),
				name="tasa_cambio_venta_positiva",
			),
			models.UniqueConstraint(
				fields=["moneda_origen", "moneda_destino"],
				condition=models.Q(activo=True),
				name="tasa_cambio_unica_activa_por_par",
			),
		]

	def clean(self):
		errores = {}
		if (
			self.moneda_origen_id
			and self.moneda_destino_id
			and self.moneda_origen_id == self.moneda_destino_id
		):
			errores["moneda_destino"] = "La moneda de destino debe ser diferente de la de origen."

		if errores:
			raise ValidationError(errores)

	def desactivar(self):
		"""Deja la tasa fuera de vigencia sin eliminar su historial."""
		self.activo = False
		self.save(update_fields=["activo", "actualizado_en"])

	def activar(self):
		"""Vuelve a poner la tasa en vigencia."""
		self.activo = True
		self.save(update_fields=["activo", "actualizado_en"])


	def __str__(self):
		return f"{self.moneda_origen.codigo}/{self.moneda_destino.codigo}"

