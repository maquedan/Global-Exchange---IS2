"""Crea los métodos de pago que ya funcionaban (RF035 — GEG9-77).

Son exactamente los dos que estaban escritos a mano en
`templates/pagos/elegir_pago.html`. No se agrega "billetera" ni ningún otro:
cada fila de esta tabla tiene que corresponder a algo que de verdad anda, y
ofrecer un método sin código detrás sería un botón que no hace nada.
"""
from django.db import migrations

METODOS = (
    {
        "codigo": "tarjeta",
        "nombre": "Tarjeta",
        "descripcion": (
            "Te llevamos a la pasarela para completar el cobro de forma "
            "segura. La operación se confirma al instante."
        ),
        "flujo": "PASARELA",
        "orden": 1,
    },
    {
        "codigo": "transferencia",
        "nombre": "Transferencia bancaria",
        "descripcion": (
            "Hacés la transferencia por tu banco y nosotros la verificamos. "
            "La operación queda reservada, sin vencimiento, hasta que un "
            "administrador la concilie."
        ),
        "flujo": "MANUAL",
        "orden": 2,
    },
)


def crear(apps, schema_editor):
    MetodoPago = apps.get_model("pagos", "MetodoPago")
    for datos in METODOS:
        MetodoPago.objects.get_or_create(codigo=datos["codigo"], defaults=datos)


def borrar(apps, schema_editor):
    MetodoPago = apps.get_model("pagos", "MetodoPago")
    MetodoPago.objects.filter(codigo__in=[m["codigo"] for m in METODOS]).delete()


class Migration(migrations.Migration):
    dependencies = [("pagos", "0002_metodopago_cambiometodopago")]
    operations = [migrations.RunPython(crear, borrar)]
