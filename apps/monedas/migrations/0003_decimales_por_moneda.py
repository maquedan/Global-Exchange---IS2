"""Pone los decimales que corresponden a cada moneda (GEG9-82).

El campo nace con 2, que sirve para la mayoría. Las excepciones son las
monedas que no usan decimales: el guaraní y el yen.
"""
from django.db import migrations

SIN_DECIMALES = ("PYG", "JPY")


def ajustar(apps, schema_editor):
    Moneda = apps.get_model("monedas", "Moneda")
    Moneda.objects.filter(codigo__in=SIN_DECIMALES).update(decimales=0)


def revertir(apps, schema_editor):
    Moneda = apps.get_model("monedas", "Moneda")
    Moneda.objects.filter(codigo__in=SIN_DECIMALES).update(decimales=2)


class Migration(migrations.Migration):
    dependencies = [("monedas", "0002_moneda_decimales")]
    operations = [migrations.RunPython(ajustar, revertir)]
