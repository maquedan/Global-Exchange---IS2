"""Pruebas de consulta de facturas (RF053 — GEG9-54)."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.conversiones.models import CompraDivisa
from apps.facturacion.models import Factura
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


def usuario_con_rol(nombre, rol):
    usuario = get_user_model().objects.create_user(nombre)
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


def cliente(nombre, documento):
    return Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres=nombre,
        apellidos="Prueba",
        documento=documento,
        email=f"{nombre.lower()}@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )


@pytest.fixture
def datos_facturacion():
    usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$")
    pyg = Moneda.objects.create(codigo="PYG", nombre="Guaraní", simbolo="Gs")
    tasa = TasaCambio.objects.create(
        moneda_origen=usd,
        moneda_destino=pyg,
        tasa_compra=Decimal("7000"),
        tasa_venta=Decimal("7100"),
        vigente_desde=timezone.now(),
    )
    return usd, pyg, tasa


def crear_factura(cliente, monedas_y_tasa, numero, estado_fiscal="APROBADA"):
    usd, pyg, tasa = monedas_y_tasa
    compra = CompraDivisa.objects.create(
        cliente=cliente,
        moneda_pagada=usd,
        moneda_adquirida=pyg,
        tasa_cambio=tasa,
        monto_pagado=Decimal("10"),
        porcentaje_comision=Decimal("0"),
        monto_comision=Decimal("0"),
        total_a_pagar=Decimal("10"),
        tasa_aplicada=Decimal("7000"),
        monto_recibido=Decimal("70000"),
        estado=CompraDivisa.Estado.CONFIRMADA,
        confirmado_en=timezone.now(),
    )
    return Factura.objects.create(
        compra=compra,
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero=numero,
        monto=Decimal("70000"),
        monto_origen=Decimal("10"),
        moneda_origen="USD",
        estado=Factura.Estado.GENERADA,
        estado_fiscal=estado_fiscal,
    )


@pytest.mark.django_db
def test_cliente_solo_ve_y_detalla_sus_facturas(client, datos_facturacion):
    ana = cliente("Ana", "111")
    otro_cliente = cliente("Bea", "222")
    usuario = usuario_con_rol("ana", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=ana)
    propia = crear_factura(ana, datos_facturacion, "0000001")
    ajena = crear_factura(otro_cliente, datos_facturacion, "0000002")
    client.force_login(usuario)

    listado = client.get("/facturas/")
    assert listado.status_code == 200
    assert propia.numero_completo in listado.content.decode()
    assert ajena.numero_completo not in listado.content.decode()
    assert client.get(f"/facturas/{propia.pk}/").status_code == 200
    assert client.get(f"/facturas/{ajena.pk}/").status_code == 404


@pytest.mark.django_db
def test_administrador_ve_todas_las_facturas_sin_cliente_activo(client, datos_facturacion):
    admin = usuario_con_rol("admin-facturas", "administrador")
    primera = crear_factura(cliente("Ana", "111"), datos_facturacion, "0000001")
    segunda = crear_factura(cliente("Bea", "222"), datos_facturacion, "0000002")
    client.force_login(admin)

    respuesta = client.get("/facturas/")
    contenido = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert primera.numero_completo in contenido
    assert segunda.numero_completo in contenido


@pytest.mark.django_db
def test_listado_filtra_por_numero_y_estado_fiscal(client, datos_facturacion):
    ana = cliente("Ana", "111")
    usuario = usuario_con_rol("ana", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=ana)
    aprobada = crear_factura(ana, datos_facturacion, "0000001", "APROBADA")
    crear_factura(ana, datos_facturacion, "0000002", "RECHAZADA")
    client.force_login(usuario)

    respuesta = client.get("/facturas/?numero=0000001&estado_fiscal=APROBADA")
    contenido = respuesta.content.decode()
    assert aprobada.numero_completo in contenido
    assert "001-001-0000002" not in contenido


@pytest.mark.django_db
def test_detalle_muestra_ruc_del_cliente(client, datos_facturacion):
    cliente_con_ruc = Cliente.objects.create(
        tipo=Cliente.Tipo.JURIDICA,
        razon_social="Empresa de Prueba S.A.",
        ruc="80012345-6",
        email="empresa@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )
    usuario = usuario_con_rol("empresa-facturas", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente_con_ruc)
    factura = crear_factura(cliente_con_ruc, datos_facturacion, "0000003")
    client.force_login(usuario)

    respuesta = client.get(f"/facturas/{factura.pk}/")
    assert "80012345-6" in respuesta.content.decode()


@pytest.mark.django_db
def test_detalle_usa_documento_como_ruc_para_persona_fisica(client, datos_facturacion):
    cliente_fisico = cliente("Carlos", "654321")
    usuario = usuario_con_rol("fisico-facturas", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente_fisico)
    factura = crear_factura(cliente_fisico, datos_facturacion, "0000004")
    client.force_login(usuario)

    respuesta = client.get(f"/facturas/{factura.pk}/")
    assert "654321" in respuesta.content.decode()


@pytest.mark.django_db
def test_menu_muestra_facturas_segun_el_rol(client, datos_facturacion):
    cliente_ana = cliente("Ana", "111")
    usuario_cliente = usuario_con_rol("ana", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario_cliente, cliente=cliente_ana)
    client.force_login(usuario_cliente)
    assert "Mis facturas" in client.get("/panel/").content.decode()

    admin = usuario_con_rol("admin-facturas", "administrador")
    client.force_login(admin)
    assert "Facturas" in client.get("/panel/").content.decode()
