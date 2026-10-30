from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("conversiones", "0005_alter_compradivisa_estado_alter_ventadivisa_estado_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ventadivisa",
            name="cuenta_destino",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ventas_divisas",
                to="cuentas.cuentapago",
            ),
        ),
    ]
