"""Pruebas de RF054 — Modo Terminal de Autoservicio (GEG9-55)."""
import pytest

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