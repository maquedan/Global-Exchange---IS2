from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversiones", "0011_compradivisa_espera_transferencia"),
    ]

    operations = [
        migrations.AddField(
            model_name="compradivisa",
            name="anulado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
