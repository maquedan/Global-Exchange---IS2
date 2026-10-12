from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cajas", "0002_conteoinventariobilletes_denominacionbillete_and_more"),
        ("monedas", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ArqueoCaja",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("saldo_esperado", models.DecimalField(decimal_places=2, max_digits=18)),
                ("total_contado", models.DecimalField(decimal_places=2, max_digits=18)),
                ("diferencia", models.DecimalField(decimal_places=2, max_digits=18)),
                ("estado", models.CharField(choices=[("CUADRADO", "Cuadrado"), ("FALTANTE", "Faltante"), ("SOBRANTE", "Sobrante")], max_length=10)),
                ("observaciones", models.CharField(blank=True, max_length=255)),
                ("creado_en", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("caja", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="arqueos", to="cajas.caja")),
                ("cajero", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="arqueos_caja", to=settings.AUTH_USER_MODEL)),
                ("moneda", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="monedas.moneda")),
            ],
            options={
                "verbose_name": "arqueo de caja",
                "verbose_name_plural": "arqueos de caja",
                "ordering": ["-creado_en", "-pk"],
            },
        ),
        migrations.CreateModel(
            name="DetalleArqueoBillete",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cantidad", models.PositiveIntegerField()),
                ("arqueo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="detalle_billetes", to="cajas.arqueocaja")),
                ("denominacion", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="cajas.denominacionbillete")),
            ],
            options={"ordering": ["-denominacion__valor"]},
        ),
        migrations.AddConstraint(
            model_name="detallearqueobillete",
            constraint=models.UniqueConstraint(fields=("arqueo", "denominacion"), name="detalle_arqueo_billete_unico"),
        ),
        migrations.AddConstraint(
            model_name="detallearqueobillete",
            constraint=models.CheckConstraint(condition=models.Q(("cantidad__gt", 0)), name="detalle_arqueo_billete_cantidad_positiva"),
        ),
    ]
