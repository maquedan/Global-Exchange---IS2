from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.conversiones.models import CompraDivisa, VentaDivisa
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


@pytest.fixture
def datos_reporte(db):
    usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$", decimales=2)
    pyg = Moneda.objects.create(codigo="PYG", nombre="Guaraní", simbolo="Gs", decimales=0)
    tasa = TasaCambio.objects.create(
        moneda_origen=usd,
        moneda_destino=pyg,
        tasa_compra=Decimal("7100.00"),
        tasa_venta=Decimal("7200.00"),
        vigente_desde=timezone.now(),
    )
    ana = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Ana",
        apellidos="Gómez",
        documento="1000001",
        email="ana@example.com",
        telefono="0981000001",
        direccion="Asunción",
    )
    luis = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Luis",
        apellidos="Pérez",
        documento="1000002",
        email="luis@example.com",
        telefono="0981000002",
        direccion="Luque",
    )
    compra = CompraDivisa.objects.create(
        cliente=ana,
        moneda_pagada=usd,
        moneda_adquirida=pyg,
        tasa_cambio=tasa,
        monto_pagado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("2.50"),
        total_a_pagar=Decimal("102.50"),
        tasa_aplicada=Decimal("7100.00"),
        monto_recibido=Decimal("710000.00"),
        estado=CompraDivisa.Estado.PENDIENTE,
    )
    venta = VentaDivisa.objects.create(
        cliente=luis,
        moneda_entregada=usd,
        moneda_acreditada=pyg,
        tasa_cambio=tasa,
        monto_entregado=Decimal("50.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("8875.00"),
        monto_convertido=Decimal("355000.00"),
        monto_acreditado=Decimal("346125.00"),
        tasa_aplicada=Decimal("7100.00"),
        estado=VentaDivisa.Estado.CONFIRMADA,
    )
    return {"usd": usd, "pyg": pyg, "ana": ana, "luis": luis, "compra": compra, "venta": venta}


def usuario_con_rol(django_user_model, rol):
    usuario = django_user_model.objects.create_user(username=f"usuario-{rol}")
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


@pytest.mark.django_db
def test_reporte_lista_compras_ventas_y_todos_los_estados(client, django_user_model, datos_reporte):
    client.force_login(usuario_con_rol(django_user_model, "administrador"))

    respuesta = client.get(reverse("conversiones:reporte_transacciones"))

    assert respuesta.status_code == 200
    transacciones = respuesta.context["transacciones"]
    assert {(item["tipo"], item["id"]) for item in transacciones} == {
        ("Compra", datos_reporte["compra"].pk),
        ("Venta", datos_reporte["venta"].pk),
    }
    assert {item["estado"] for item in transacciones} == {"Pendiente de confirmación", "Pagada"}


@pytest.mark.django_db
def test_reporte_filtra_cliente_moneda_tipo_estado_y_fechas(
    client, django_user_model, datos_reporte
):
    client.force_login(usuario_con_rol(django_user_model, "analista_cambiario"))
    datos = datos_reporte

    respuesta = client.get(
        reverse("conversiones:reporte_transacciones"),
        {
            "cliente": datos["ana"].pk,
            "moneda": datos["usd"].pk,
            "tipo_operacion": "compra",
            "estado": CompraDivisa.Estado.PENDIENTE,
            "fecha_desde": timezone.localdate().isoformat(),
            "fecha_hasta": timezone.localdate().isoformat(),
        },
    )

    assert [item["id"] for item in respuesta.context["transacciones"]] == [datos["compra"].pk]


@pytest.mark.django_db
def test_reporte_filtra_moneda_en_cualquiera_de_los_extremos(client, django_user_model, datos_reporte):
    client.force_login(usuario_con_rol(django_user_model, "administrador"))

    respuesta = client.get(
        reverse("conversiones:reporte_transacciones"),
        {"moneda": datos_reporte["pyg"].pk},
    )

    assert len(respuesta.context["transacciones"]) == 2


@pytest.mark.django_db
@pytest.mark.parametrize("rol", ["usuario_cliente", "cajero"])
def test_reporte_rechaza_roles_sin_acceso(client, django_user_model, rol):
    client.force_login(usuario_con_rol(django_user_model, rol))
    assert client.get(reverse("conversiones:reporte_transacciones")).status_code == 403


@pytest.mark.django_db
def test_reporte_no_reemplaza_historial_del_cliente(client, django_user_model, datos_reporte):
    administrador = usuario_con_rol(django_user_model, "administrador")
    client.force_login(administrador)

    assert client.get(reverse("conversiones:historial")).status_code == 403
    assert client.get(reverse("conversiones:reporte_transacciones")).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("formato", "content_type", "extension"),
    [("pdf", "application/pdf", ".pdf"), ("excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx")],
)
def test_exportacion_transacciones_aplica_filtros_e_incluye_totales_y_fecha(
    client, django_user_model, datos_reporte, formato, content_type, extension
):
    client.force_login(usuario_con_rol(django_user_model, "analista_cambiario"))
    respuesta = client.get(
        reverse("conversiones:exportar_reporte_transacciones", args=[formato]),
        {"tipo_operacion": "compra", "estado": CompraDivisa.Estado.PENDIENTE},
    )

    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == content_type
    assert respuesta["Content-Disposition"].endswith(extension + '"')
    if formato == "excel":
        with ZipFile(BytesIO(respuesta.content)) as archivo:
            assert "xl/worksheets/sheet1.xml" in archivo.namelist()
            hoja = archivo.read("xl/worksheets/sheet1.xml")
            assert b"Fecha de generaci" in hoja
            assert b"Operaciones" in hoja
            assert b"Pendiente de confirmaci" in hoja
            assert b"Pagada" not in hoja
    else:
        assert b"Fecha de generaci" in respuesta.content
        assert b"Operaciones" in respuesta.content


@pytest.mark.django_db
def test_exportacion_transacciones_rechaza_usuario_sin_rol(client, django_user_model):
    client.force_login(usuario_con_rol(django_user_model, "usuario_cliente"))
    assert client.get(reverse("conversiones:exportar_reporte_transacciones", args=["pdf"])).status_code == 403
