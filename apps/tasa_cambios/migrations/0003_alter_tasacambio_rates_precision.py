# Generated for restoring the six-decimal rate precision.

import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasa_cambios", "0002_alter_tasacambio_tasa_compra_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tasacambio",
            name="tasa_compra",
            field=models.DecimalField(
                decimal_places=6,
                max_digits=12,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.000001"))
                ],
            ),
        ),
        migrations.AlterField(
            model_name="tasacambio",
            name="tasa_venta",
            field=models.DecimalField(
                decimal_places=6,
                max_digits=12,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.000001"))
                ],
            ),
        ),
    ]
