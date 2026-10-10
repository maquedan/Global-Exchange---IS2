# Generado a mano para RF051 (GEG9-51): estado PENDIENTE/CONFIRMADA/CANCELADA.
#
# El campo que antes se llamaba "confirmado_en" (con auto_now_add) en realidad
# marcaba cuándo se CREABA la operación, porque antes se creaba ya confirmada.
# Ahora que queda pendiente hasta que el cliente confirma el pago, se renombra
# a "creado_en" y se agrega un "confirmado_en" nuevo, que recién se completa al
# confirmar. Las operaciones que ya existían se marcan como CONFIRMADA con la
# misma fecha que tenían, para no perder su significado histórico.

from django.db import migrations, models


def marcar_operaciones_existentes_como_confirmadas(apps, schema_editor):
    CompraDivisa = apps.get_model("conversiones", "CompraDivisa")
    VentaDivisa = apps.get_model("conversiones", "VentaDivisa")

    CompraDivisa.objects.all().update(estado="CONFIRMADA")
    VentaDivisa.objects.all().update(estado="CONFIRMADA")
    for compra in CompraDivisa.objects.all():
        compra.confirmado_en = compra.creado_en
        compra.save(update_fields=["confirmado_en"])
    for venta in VentaDivisa.objects.all():
        venta.confirmado_en = venta.creado_en
        venta.save(update_fields=["confirmado_en"])


def revertir(apps, schema_editor):
    """No hay nada que deshacer: al volver, el campo default PENDIENTE alcanza."""


class Migration(migrations.Migration):

    dependencies = [
        ("conversiones", "0002_ventadivisa"),
    ]

    operations = [
        migrations.RenameField(
            model_name="compradivisa", old_name="confirmado_en", new_name="creado_en"
        ),
        migrations.RenameField(
            model_name="ventadivisa", old_name="confirmado_en", new_name="creado_en"
        ),
        migrations.AddField(
            model_name="compradivisa",
            name="estado",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente de confirmación"),
                    ("CONFIRMADA", "Confirmada"),
                    ("CANCELADA", "Cancelada"),
                ],
                default="PENDIENTE",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="ventadivisa",
            name="estado",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente de confirmación"),
                    ("CONFIRMADA", "Confirmada"),
                    ("CANCELADA", "Cancelada"),
                ],
                default="PENDIENTE",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="compradivisa",
            name="motivo_cancelacion",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CAMBIO_COTIZACION", "La cotización cambió antes de confirmar"),
                    ("CLIENTE", "Cancelada por el cliente"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="ventadivisa",
            name="motivo_cancelacion",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CAMBIO_COTIZACION", "La cotización cambió antes de confirmar"),
                    ("CLIENTE", "Cancelada por el cliente"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="compradivisa",
            name="confirmado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ventadivisa",
            name="confirmado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="compradivisa",
            name="cancelado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ventadivisa",
            name="cancelado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(
            marcar_operaciones_existentes_como_confirmadas, revertir
        ),
        migrations.AlterModelOptions(
            name="compradivisa",
            options={
                "ordering": ["-creado_en"],
                "verbose_name": "compra de divisa",
                "verbose_name_plural": "compras de divisas",
            },
        ),
        migrations.AlterModelOptions(
            name="ventadivisa",
            options={
                "ordering": ["-creado_en"],
                "verbose_name": "venta de divisa",
                "verbose_name_plural": "ventas de divisas",
            },
        ),
    ]
