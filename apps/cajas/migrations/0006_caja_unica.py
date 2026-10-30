from django.db import migrations, models


def conservar_sucursal_centro_y_eliminar_las_demas(apps, schema_editor):
    db = schema_editor.connection.alias
    Sucursal = apps.get_model("cajas", "Sucursal")
    Caja = apps.get_model("cajas", "Caja")
    SaldoCaja = apps.get_model("cajas", "SaldoCaja")
    FondoCajero = apps.get_model("cajas", "FondoCajero")
    InventarioBilleteCaja = apps.get_model("cajas", "InventarioBilleteCaja")
    InventarioBilleteCajero = apps.get_model("cajas", "InventarioBilleteCajero")
    MovimientoCaja = apps.get_model("cajas", "MovimientoCaja")
    DetalleMovimientoBillete = apps.get_model("cajas", "DetalleMovimientoBillete")
    Conteo = apps.get_model("cajas", "ConteoInventarioBilletes")
    DetalleConteo = apps.get_model("cajas", "DetalleConteoInventarioBilletes")
    Arqueo = apps.get_model("cajas", "ArqueoCaja")
    DetalleArqueo = apps.get_model("cajas", "DetalleArqueoBillete")
    Diferencia = apps.get_model("cajas", "DiferenciaCaja")

    centro, _ = Sucursal.objects.using(db).get_or_create(
        nombre="Centro",
        defaults={"direccion": "Centro", "activa": True},
    )
    Sucursal.objects.using(db).filter(pk=centro.pk).update(activa=True)

    otras_sucursales = Sucursal.objects.using(db).exclude(pk=centro.pk)
    otras_sucursal_ids = list(otras_sucursales.values_list("pk", flat=True))
    caja_ids = list(
        Caja.objects.using(db)
        .filter(sucursal_id__in=otras_sucursal_ids)
        .values_list("pk", flat=True)
    )

    movimiento_ids = list(
        MovimientoCaja.objects.using(db)
        .filter(caja_id__in=caja_ids)
        .values_list("pk", flat=True)
    )
    DetalleMovimientoBillete.objects.using(db).filter(
        movimiento_id__in=movimiento_ids
    ).delete()
    MovimientoCaja.objects.using(db).filter(pk__in=movimiento_ids).delete()

    arqueo_ids = list(
        Arqueo.objects.using(db)
        .filter(caja_id__in=caja_ids)
        .values_list("pk", flat=True)
    )
    DetalleArqueo.objects.using(db).filter(arqueo_id__in=arqueo_ids).delete()
    Diferencia.objects.using(db).filter(arqueo_id__in=arqueo_ids).delete()
    Arqueo.objects.using(db).filter(pk__in=arqueo_ids).delete()

    conteo_ids = list(
        Conteo.objects.using(db)
        .filter(caja_id__in=caja_ids)
        .values_list("pk", flat=True)
    )
    DetalleConteo.objects.using(db).filter(conteo_id__in=conteo_ids).delete()
    Conteo.objects.using(db).filter(pk__in=conteo_ids).delete()

    InventarioBilleteCaja.objects.using(db).filter(caja_id__in=caja_ids).delete()
    InventarioBilleteCajero.objects.using(db).filter(caja_id__in=caja_ids).delete()
    FondoCajero.objects.using(db).filter(caja_id__in=caja_ids).delete()
    SaldoCaja.objects.using(db).filter(caja_id__in=caja_ids).delete()
    Caja.objects.using(db).filter(pk__in=caja_ids).delete()
    otras_sucursales.delete()

    Caja.objects.using(db).get_or_create(sucursal_id=centro.pk)

    if schema_editor.connection.vendor == "postgresql":
        # Flush deferred FK trigger events before the following schema changes.
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):
    dependencies = [
        ("cajas", "0005_movimientocaja_diferencia_alter_movimientocaja_tipo"),
    ]

    operations = [
        migrations.RunPython(conservar_sucursal_centro_y_eliminar_las_demas),
        migrations.AddField(
            model_name="sucursal",
            name="es_unica",
            field=models.BooleanField(default=True, editable=False, unique=True),
        ),
        migrations.AddConstraint(
            model_name="sucursal",
            constraint=models.CheckConstraint(
                condition=models.Q(es_unica=True),
                name="sucursal_es_unica",
            ),
        ),
    ]
