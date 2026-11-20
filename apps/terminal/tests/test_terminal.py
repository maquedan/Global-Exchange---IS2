"""Pruebas de RF054 — Modo Terminal de Autoservicio (GEG9-55)."""
import pytest

from unittest.mock import patch
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CompraDivisa, VentaDivisa
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.menu import construir_menu
from apps.facturacion.models import Factura

Usuario = get_user_model()


def usuario_con_rol(rol):
    usuario = Usuario.objects.create_user(
        username=f"usuario-{rol}",
        password="test",
    )
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


@pytest.mark.django_db
def test_terminal_solo_muestra_panel_y_terminal_en_el_menu():
    usuario = usuario_con_rol("terminal")

    textos = [opcion["texto"] for opcion in construir_menu(usuario)]

    assert textos == ["Panel", "Terminal"]


@pytest.mark.django_db
def test_usuario_terminal_puede_abrir_el_inicio(client):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    respuesta = client.get(reverse("terminal:inicio"))

    assert respuesta.status_code == 200
    assert "Terminal de autoservicio" in respuesta.content.decode()
    assert "Comprar divisas" in respuesta.content.decode()
    assert "Vender divisas" in respuesta.content.decode()
    assert "Ver cotizaciones" in respuesta.content.decode()


@pytest.mark.django_db
def test_terminal_enlaza_y_puede_consultar_cotizaciones(client):
    """El perfil terminal reutiliza el panel público de tasas (RF016)."""
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    respuesta_inicio = client.get(reverse("terminal:inicio"))
    respuesta_cotizaciones = client.get(reverse("tasas:panel"))

    assert respuesta_inicio.status_code == 200
    assert f'href="{reverse("tasas:panel")}"' in respuesta_inicio.content.decode()
    assert respuesta_cotizaciones.status_code == 200


@pytest.mark.django_db
def test_otro_rol_no_puede_abrir_la_terminal(client):
    usuario = usuario_con_rol("usuario_cliente")
    client.force_login(usuario)

    respuesta = client.get(reverse("terminal:inicio"))

    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_reiniciar_terminal_exige_post(client):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    respuesta = client.get(reverse("terminal:reiniciar"))

    assert respuesta.status_code == 405


@pytest.mark.django_db
def test_reiniciar_terminal_limpia_la_sesion(client):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    sesion = client.session
    sesion["terminal_cliente_id"] = 10
    sesion["terminal_tipo_operacion"] = "compra"
    sesion["terminal_compra_id"] = 20
    sesion["terminal_venta_id"] = 30
    sesion["terminal_moneda_origen_id"] = 1
    sesion["terminal_moneda_destino_id"] = 2
    sesion["terminal_monto"] = "100.00"
    sesion["terminal_tasa_cambio_id"] = 3
    sesion.save()

    respuesta = client.post(reverse("terminal:reiniciar"))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("terminal:inicio")

    sesion = client.session
    assert "terminal_cliente_id" not in sesion
    assert "terminal_tipo_operacion" not in sesion
    assert "terminal_compra_id" not in sesion
    assert "terminal_venta_id" not in sesion
    assert "terminal_moneda_origen_id" not in sesion
    assert "terminal_moneda_destino_id" not in sesion
    assert "terminal_monto" not in sesion
    assert "terminal_tasa_cambio_id" not in sesion


@pytest.fixture
def cliente_terminal(db):
    return Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        categoria=Cliente.Categoria.MINORISTA,
        nombres="Ana",
        apellidos="Gómez",
        documento="1234567",
        email="ana.terminal@example.com",
        telefono="0981000000",
        direccion="Asunción",
    )


@pytest.fixture
def monedas_terminal(db):
    return (
        Moneda.objects.create(
            codigo="USD",
            nombre="Dólar estadounidense",
            simbolo="$",
        ),
        Moneda.objects.create(
            codigo="PYG",
            nombre="Guaraní",
            simbolo="₲",
        ),
    )


@pytest.fixture
def tasa_terminal(monedas_terminal):
    return TasaCambio.objects.create(
        moneda_origen=monedas_terminal[0],
        moneda_destino=monedas_terminal[1],
        tasa_compra=Decimal("7.10"),
        tasa_venta=Decimal("7.20"),
        vigente_desde=timezone.now() - timedelta(minutes=2),
    )


@pytest.fixture
def comision_terminal(db):
    return ComisionCategoria.objects.create(
        categoria=Cliente.Categoria.MINORISTA,
        porcentaje=Decimal("2.50"),
    )


def preparar_sesion_operacion(
    client,
    cliente,
    monedas,
    tasa,
    *,
    tipo_operacion="compra",
    monto="100.00",
):
    """Carga en sesión los datos previamente elegidos en la terminal."""
    sesion = client.session
    sesion["terminal_cliente_id"] = cliente.pk
    sesion["terminal_tipo_operacion"] = tipo_operacion
    sesion["terminal_moneda_origen_id"] = monedas[0].pk
    sesion["terminal_moneda_destino_id"] = monedas[1].pk
    sesion["terminal_monto"] = monto
    sesion["terminal_tasa_cambio_id"] = tasa.pk
    sesion.save()


@pytest.mark.django_db
def test_terminal_identifica_cliente_activo_por_documento(
    client,
    cliente_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    respuesta = client.post(
        reverse("terminal:identificar"),
        {"identificador": cliente_terminal.documento},
    )

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("terminal:seleccionar_operacion")
    assert client.session["terminal_cliente_id"] == cliente_terminal.pk


@pytest.mark.django_db
def test_terminal_muestra_simulacion_con_tasa_y_comision(
    client,
    cliente_terminal,
    monedas_terminal,
    tasa_terminal,
    comision_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    preparar_sesion_operacion(
        client,
        cliente_terminal,
        monedas_terminal,
        tasa_terminal,
    )

    respuesta = client.get(reverse("terminal:simulacion"))

    assert respuesta.status_code == 200
    assert respuesta.context["tasa_aplicada"] == Decimal("7.10")
    assert respuesta.context["monto_comision"] == Decimal("2.50")
    assert respuesta.context["total"] == Decimal("102.50")


@pytest.mark.django_db
def test_terminal_confirma_compra_y_la_deja_pendiente(
    client,
    cliente_terminal,
    monedas_terminal,
    tasa_terminal,
    comision_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    preparar_sesion_operacion(
        client,
        cliente_terminal,
        monedas_terminal,
        tasa_terminal,
    )

    respuesta = client.post(reverse("terminal:confirmar_operacion"))

    compra = CompraDivisa.objects.get()

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("terminal:operacion_pendiente")
    assert compra.cliente == cliente_terminal
    assert compra.estado == CompraDivisa.Estado.PENDIENTE
    assert compra.tasa_cambio == tasa_terminal
    assert compra.total_a_pagar == Decimal("102.50")
    assert client.session["terminal_compra_id"] == compra.pk


@pytest.mark.django_db
def test_terminal_confirma_venta_y_la_deja_pendiente(
    client,
    cliente_terminal,
    monedas_terminal,
    tasa_terminal,
    comision_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    preparar_sesion_operacion(
        client,
        cliente_terminal,
        monedas_terminal,
        tasa_terminal,
        tipo_operacion="venta",
    )

    respuesta = client.post(reverse("terminal:confirmar_operacion"))

    venta = VentaDivisa.objects.get()

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("terminal:operacion_pendiente")
    assert venta.cliente == cliente_terminal
    assert venta.estado == VentaDivisa.Estado.PENDIENTE
    assert venta.tasa_cambio == tasa_terminal
    assert client.session["terminal_venta_id"] == venta.pk


@pytest.mark.django_db
def test_terminal_no_crea_operacion_si_cambia_la_cotizacion(
    client,
    cliente_terminal,
    monedas_terminal,
    tasa_terminal,
    comision_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    preparar_sesion_operacion(
        client,
        cliente_terminal,
        monedas_terminal,
        tasa_terminal,
    )

    tasa_terminal.activo = False
    tasa_terminal.save(update_fields=["activo"])

    TasaCambio.objects.create(
        moneda_origen=monedas_terminal[0],
        moneda_destino=monedas_terminal[1],
        tasa_compra=Decimal("7.30"),
        tasa_venta=Decimal("7.40"),
        vigente_desde=timezone.now() - timedelta(minutes=1),
    )

    respuesta = client.post(reverse("terminal:confirmar_operacion"))

    assert respuesta.status_code == 200
    assert "La cotización cambió" in respuesta.content.decode()
    assert CompraDivisa.objects.count() == 0
    assert VentaDivisa.objects.count() == 0


@pytest.fixture
def compra_confirmada_terminal(
    cliente_terminal,
    monedas_terminal,
    tasa_terminal,
):
    return CompraDivisa.objects.create(
        cliente=cliente_terminal,
        moneda_pagada=monedas_terminal[0],
        moneda_adquirida=monedas_terminal[1],
        tasa_cambio=tasa_terminal,
        monto_pagado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("2.50"),
        total_a_pagar=Decimal("102.50"),
        tasa_aplicada=Decimal("7.10"),
        monto_recibido=Decimal("710.00"),
        estado=CompraDivisa.Estado.CONFIRMADA,
        confirmado_en=timezone.now(),
    )


@pytest.fixture
def venta_confirmada_terminal(
    cliente_terminal,
    monedas_terminal,
    tasa_terminal,
):
    return VentaDivisa.objects.create(
        cliente=cliente_terminal,
        moneda_entregada=monedas_terminal[0],
        moneda_acreditada=monedas_terminal[1],
        tasa_cambio=tasa_terminal,
        monto_entregado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("17.75"),
        monto_convertido=Decimal("710.00"),
        monto_acreditado=Decimal("692.25"),
        tasa_aplicada=Decimal("7.10"),
        estado=VentaDivisa.Estado.CONFIRMADA,
        confirmado_en=timezone.now(),
    )


def preparar_sesion_comprobante(
    client,
    cliente,
    *,
    compra=None,
    venta=None,
):
    """Guarda en sesión la operación finalizada por la terminal."""
    sesion = client.session
    sesion["terminal_cliente_id"] = cliente.pk

    if compra is not None:
        sesion["terminal_compra_id"] = compra.pk
        sesion.pop("terminal_venta_id", None)

    if venta is not None:
        sesion["terminal_venta_id"] = venta.pk
        sesion.pop("terminal_compra_id", None)

    sesion.save()


@pytest.mark.django_db
def test_terminal_muestra_comprobante_de_compra_confirmada(
    client,
    cliente_terminal,
    compra_confirmada_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    preparar_sesion_comprobante(
        client,
        cliente_terminal,
        compra=compra_confirmada_terminal,
    )

    respuesta = client.get(reverse("terminal:comprobante"))
    contenido = respuesta.content.decode()

    assert respuesta.status_code == 200
    assert "Comprobante de operación" in contenido
    assert "Compra de divisas" in contenido
    assert respuesta.context["monto_origen"] == Decimal("102.50")
    assert respuesta.context["monto_resultado"] == Decimal("710.00")
    assert respuesta.context["moneda_origen"].codigo == "USD"
    assert respuesta.context["moneda_destino"].codigo == "PYG"


@pytest.mark.django_db
def test_terminal_muestra_comprobante_de_venta_confirmada(
    client,
    cliente_terminal,
    venta_confirmada_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    preparar_sesion_comprobante(
        client,
        cliente_terminal,
        venta=venta_confirmada_terminal,
    )

    respuesta = client.get(reverse("terminal:comprobante"))
    contenido = respuesta.content.decode()

    assert respuesta.status_code == 200
    assert "Venta de divisas" in contenido
    assert respuesta.context["monto_origen"] == Decimal("100.00")
    assert respuesta.context["monto_resultado"] == Decimal("692.25")
    assert respuesta.context["moneda_origen"].codigo == "USD"
    assert respuesta.context["moneda_destino"].codigo == "PYG"


@pytest.mark.django_db
def test_terminal_no_muestra_comprobante_de_operacion_pendiente(
    client,
    cliente_terminal,
    monedas_terminal,
    tasa_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    compra = CompraDivisa.objects.create(
        cliente=cliente_terminal,
        moneda_pagada=monedas_terminal[0],
        moneda_adquirida=monedas_terminal[1],
        tasa_cambio=tasa_terminal,
        monto_pagado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("2.50"),
        total_a_pagar=Decimal("102.50"),
        tasa_aplicada=Decimal("7.10"),
        monto_recibido=Decimal("710.00"),
    )

    preparar_sesion_comprobante(
        client,
        cliente_terminal,
        compra=compra,
    )

    respuesta = client.get(reverse("terminal:comprobante"))

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("terminal:operacion_pendiente")


@pytest.mark.django_db
def test_terminal_indica_si_la_factura_no_esta_disponible(
    client,
    cliente_terminal,
    compra_confirmada_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    Factura.objects.create(
        compra=compra_confirmada_terminal,
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="003",
        numero="0000494",
        monto=Decimal("710.00"),
        monto_origen=Decimal("102.50"),
        moneda_origen="USD",
        estado=Factura.Estado.ERROR,
    )

    preparar_sesion_comprobante(
        client,
        cliente_terminal,
        compra=compra_confirmada_terminal,
    )

    respuesta = client.get(reverse("terminal:comprobante"))

    assert respuesta.status_code == 200
    assert "todavía no está disponible para descargar" in respuesta.content.decode()


@pytest.mark.django_db
def test_terminal_descarga_pdf_y_xml_de_factura_con_cdc(
    client,
    cliente_terminal,
    compra_confirmada_terminal,
):
    usuario = usuario_con_rol("terminal")
    client.force_login(usuario)

    factura = Factura.objects.create(
        compra=compra_confirmada_terminal,
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="003",
        numero="0000495",
        monto=Decimal("710.00"),
        monto_origen=Decimal("102.50"),
        moneda_origen="USD",
        estado=Factura.Estado.GENERADA,
        cdc="9" * 44,
    )

    preparar_sesion_comprobante(
        client,
        cliente_terminal,
        compra=compra_confirmada_terminal,
    )

    with patch("apps.terminal.views.cliente_configurado") as configurado:
        proveedor = configurado.return_value[1]
        configurado.return_value = ("simulado", proveedor)
        proveedor.descargar_documento.side_effect = (
            lambda cdc, formato: (
                b"%PDF-1.4 comprobante"
                if formato == "pdf"
                else b"<FacturaSimulada />"
            )
        )

        respuesta_pdf = client.get(
            reverse("terminal:descargar_factura", args=["pdf"])
        )
        respuesta_xml = client.get(
            reverse("terminal:descargar_factura", args=["xml"])
        )

    assert factura.cdc == "9" * 44
    assert respuesta_pdf.status_code == 200
    assert respuesta_pdf["Content-Type"] == "application/pdf"
    assert respuesta_xml.status_code == 200
    assert respuesta_xml["Content-Type"] == "application/xml"
    proveedor.descargar_documento.assert_any_call("9" * 44, "pdf")
    proveedor.descargar_documento.assert_any_call("9" * 44, "xml")
