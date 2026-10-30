from django.db import migrations


def vincular_retiros_legacy_de_ventas(apps, schema_editor):
    alias = schema_editor.connection.alias
    VentaDivisa = apps.get_model("conversiones", "VentaDivisa")
    MovimientoCaja = apps.get_model("cajas", "MovimientoCaja")

    ventas = VentaDivisa.objects.using(alias).filter(
        estado="CONFIRMADA",
        movimiento_efectivo_entregado__isnull=True,
    )
    for venta in ventas.iterator():
        movimientos = MovimientoCaja.objects.using(alias).filter(
            moneda_id=venta.moneda_acreditada_id,
            tipo__in=("RETIRO", "RETIRO_CAJERO"),
            nota=f"Entrega de efectivo por venta #{venta.pk}",
        )
        if movimientos.count() == 1:
            movimiento = movimientos.get()
            VentaDivisa.objects.using(alias).filter(pk=venta.pk).update(
                movimiento_efectivo_entregado_id=movimiento.pk,
                monto_efectivo_entregado=movimiento.importe,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("conversiones", "0008_ventadivisa_movimiento_efectivo_entregado_and_more"),
    ]

    operations = [
        migrations.RunPython(
            vincular_retiros_legacy_de_ventas,
            migrations.RunPython.noop,
        ),
    ]
