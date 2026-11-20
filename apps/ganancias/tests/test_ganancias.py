from datetime import datetime
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.conversiones.models import CompraDivisa
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio
from apps.ganancias.services import resumen_ganancias


@pytest.fixture
def datos(db):
    usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$" )
    pyg = Moneda.objects.create(codigo="PYG", nombre="Guaraní", simbolo="Gs")
    tasa = TasaCambio.objects.create(
        moneda_origen=usd,
        moneda_destino=pyg,
        tasa_compra=Decimal("7100.00"),
        tasa_venta=Decimal("7200.00"),
        vigente_desde=timezone.make_aware(datetime(2026, 11, 1, 10, 0)),
    )
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Ana",
        apellidos="Pérez",
        documento="123456",
        email="ana@example.com",
        telefono="0981000000",
        direccion="Centro",
    )
    return usd, pyg, tasa, cliente


def crear_compra(datos, estado=CompraDivisa.Estado.CONFIRMADA):
    usd, pyg, tasa, cliente = datos
    return CompraDivisa.objects.create(
        cliente=cliente,
        moneda_pagada=usd,
        moneda_adquirida=pyg,
        tasa_cambio=tasa,
        monto_pagado=Decimal("10.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("0.25"),
        total_a_pagar=Decimal("10.25"),
        tasa_aplicada=Decimal("7100.00"),
        monto_recibido=Decimal("71000.00"),
        estado=estado,
        confirmado_en=timezone.make_aware(datetime(2026, 11, 10, 12, 0))
        if estado == CompraDivisa.Estado.CONFIRMADA
        else None,
    )


@pytest.mark.django_db
def test_suma_comision_y_diferencia_de_tasa_solo_confirmadas(datos):
    crear_compra(datos)
    crear_compra(datos, CompraDivisa.Estado.CANCELADA)
    resumen = resumen_ganancias()

    assert resumen["operaciones"] == 1
    assert resumen["desglose"] == [
        {
            "moneda": "PYG",
            "comision": Decimal("1775.00"),
            "diferencia_tasa": Decimal("1000.00"),
            "total": Decimal("2775.00"),
        }
    ]


@pytest.mark.django_db
def test_dashboard_solo_permite_administrador_y_analista(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="cliente-dashboard")
    client.force_login(usuario)
    assert client.get(reverse("ganancias:panel")).status_code == 403

    usuario.groups.add(Group.objects.create(name="analista_cambiario"))
    assert client.get(reverse("ganancias:panel")).status_code == 200


@pytest.mark.django_db
def test_dashboard_filtra_por_fecha(client, django_user_model, datos):
    crear_compra(datos)
    usuario = django_user_model.objects.create_user(username="admin-dashboard")
    usuario.groups.add(Group.objects.create(name="administrador"))
    client.force_login(usuario)

    respuesta = client.get(reverse("ganancias:datos"), {"fecha_desde": "2026-11-11"})
    assert respuesta.json()["operaciones"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("formato", "content_type"),
    [("pdf", "application/pdf"), ("excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
)
def test_exportacion_ganancias_incluye_totales_fecha_y_respeta_filtros(
    client, django_user_model, datos, formato, content_type
):
    crear_compra(datos)
    usuario = django_user_model.objects.create_user(username="admin-exporta-ganancias")
    usuario.groups.add(Group.objects.create(name="administrador"))
    client.force_login(usuario)
    respuesta = client.get(
        reverse("ganancias:exportar", args=[formato]),
        {"moneda": datos[1].pk, "estado": CompraDivisa.Estado.CONFIRMADA},
    )

    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == content_type
    if formato == "excel":
        with ZipFile(BytesIO(respuesta.content)) as archivo:
            assert "xl/worksheets/sheet1.xml" in archivo.namelist()
            hoja = archivo.read("xl/worksheets/sheet1.xml")
            assert b"Fecha de generaci" in hoja
            assert b"Ganancia total" in hoja
            assert b"PYG" in hoja
    else:
        assert b"Fecha de generaci" in respuesta.content
        assert b"Ganancia total" in respuesta.content


@pytest.mark.django_db
def test_exportacion_ganancias_rechaza_usuario_sin_rol(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="cliente-exporta-ganancias")
    client.force_login(usuario)
    assert client.get(reverse("ganancias:exportar", args=["pdf"])).status_code == 403
