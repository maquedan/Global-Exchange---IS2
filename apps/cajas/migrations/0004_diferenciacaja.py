from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cajas", "0003_arqueocaja_detallearqueobillete"),
        ("monedas", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DiferenciaCaja",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "monto",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=18,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                    ),
                ),
                ("moneda", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="monedas.moneda")),
                ("motivo", models.CharField(max_length=255)),
                ("creado_en", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "arqueo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="diferencias",
                        to="cajas.arqueocaja",
                    ),
                ),
                (
                    "registrado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="diferencias_caja_registradas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "responsable",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="diferencias_caja_responsable",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "diferencia de caja",
                "verbose_name_plural": "diferencias de caja",
                "ordering": ["-creado_en", "-pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="diferenciacaja",
            constraint=models.CheckConstraint(
                condition=models.Q(("monto__gt", 0)),
                name="diferencia_caja_monto_positivo",
            ),
        ),
    ]
