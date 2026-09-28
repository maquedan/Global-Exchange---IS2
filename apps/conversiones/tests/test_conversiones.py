from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.cuentas.models import CuentaPago
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio

from apps.conversiones.models import CompraDivisa, VentaDivisa
from apps.conversiones.services import (
    VentaNoDisponible,
    calcular_comision,
    calcular_conversion,
    confirmar_venta,
)


@pytest.fixture
def usuario_cliente(db):
    usuario = get_user_model().objects.create_user(username="cliente-rf017")
    usuario.groups.add(Group.objects.create(name="usuario_cliente"))
    return usuario


@pytest.fixture
def monedas(db):
    return (
        Moneda.objects.create(codigo="USD", nombre="Dolar", simbolo="$"),
        Moneda.objects.create(codigo="PYG", nombre="Guarani", simbolo="Gs"),
    )


@pytest.fixture
def tasa(monedas):
    return TasaCambio.objects.create(
        moneda_origen=monedas[0],
        moneda_destino=monedas[1],
        tasa_compra=Decimal("7.10"),
        tasa_venta=Decimal("7.20"),
        vigente_desde=timezone.make_aware(datetime(2026, 9, 6, 10, 0)),
    )


def test_calcula_compra_y_redondea_a_dos_decimales():
    assert calcular_conversion("10", "7.105", "compra") == Decimal("71.05")


def test_calcula_venta_dividiendo_por_la_tasa():
    assert calcular_conversion("72", "7.20", "venta") == Decimal("10.00")


def test_calcula_comision_y_redondea_a_dos_decimales():
    assert calcular_comision("10.01", "2.50") == Decimal("0.25")


@pytest.mark.django_db
def test_simulacion_muestra_resultado(client, usuario_cliente, monedas, tasa):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:simular"), {
        "moneda_origen": monedas[0].pk,
        "moneda_destino": monedas[1].pk,
        "monto": "10.00",
        "tipo_operacion": "compra",
    })

    assert respuesta.status_code == 200
    assert respuesta.context["resultado"]["resultado"] == Decimal("71.00")
    assert TasaCambio.objects.count() == 1


@pytest.mark.django_db
def test_simulacion_rechaza_monedas_iguales(client, usuario_cliente, monedas):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:simular"), {
        "moneda_origen": monedas[0].pk,
        "moneda_destino": monedas[0].pk,
        "monto": "10.00",
        "tipo_operacion": "compra",
    })

    assert respuesta.status_code == 200
    assert "moneda_destino" in respuesta.context["formulario"].errors


@pytest.mark.django_db
def test_usuario_sin_rol_cliente_no_puede_simular(client, django_user_model):
    usuario = django_user_model.objects.create_user(username="sin-rol")
    client.force_login(usuario)

    assert client.get(reverse("conversiones:simular")).status_code == 403


@pytest.fixture
def cliente_asociado(usuario_cliente):
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        categoria=Cliente.Categoria.MINORISTA,
        nombres="Ana",
        apellidos="Gomez",
        documento="1234567",
        email="ana@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )
    AsociacionUsuarioCliente.objects.create(usuario=usuario_cliente, cliente=cliente)
    return cliente


@pytest.fixture
def comision_minorista(db):
    return ComisionCategoria.objects.create(
        categoria=Cliente.Categoria.MINORISTA,
        porcentaje=Decimal("2.50"),
    )


@pytest.fixture
def cuenta_destino(cliente_asociado):
    return CuentaPago.objects.create(
        cliente=cliente_asociado,
        tipo=CuentaPago.Tipo.BANCARIA,
        entidad="Banco Itaú",
        numero_cuenta="00123456789",
        titular="Ana Gomez",
        alias="Cuenta principal",
    )


@pytest.mark.django_db
def test_cliente_confirma_compra_y_guarda_valores_historicos(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    compra = CompraDivisa.objects.get()
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("conversiones:comprobante_compra", args=[compra.pk])
    assert compra.tasa_aplicada == Decimal("7.10")
    assert compra.porcentaje_comision == Decimal("2.50")
    assert compra.monto_comision == Decimal("2.50")
    assert compra.total_a_pagar == Decimal("102.50")
    assert compra.monto_recibido == Decimal("710.00")


@pytest.mark.django_db
def test_compra_requiere_comision_para_la_categoria(
    client, usuario_cliente, cliente_asociado, monedas, tasa
):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    assert respuesta.status_code == 200
    assert "No existe una comisión" in str(respuesta.context["formulario"].non_field_errors())
    assert CompraDivisa.objects.count() == 0


@pytest.mark.django_db
def test_compra_rechaza_tasa_programada_para_el_futuro(
    client, usuario_cliente, cliente_asociado, monedas, comision_minorista
):
    TasaCambio.objects.create(
        moneda_origen=monedas[0],
        moneda_destino=monedas[1],
        tasa_compra=Decimal("7.10"),
        tasa_venta=Decimal("7.20"),
        vigente_desde=timezone.now() + timedelta(days=1),
    )
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:comprar"), {
        "cliente": cliente_asociado.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    assert respuesta.status_code == 200
    assert "No existe una tasa vigente" in str(respuesta.context["formulario"].non_field_errors())
    assert CompraDivisa.objects.count() == 0


@pytest.mark.django_db
def test_venta_calcula_comision_y_registra_importe_y_cuenta_destino(
    client, usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista, cuenta_destino
):
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:vender"), {
        "cliente": cliente_asociado.pk,
        "moneda_entregada": monedas[0].pk,
        "moneda_acreditada": monedas[1].pk,
        "cuenta_destino": cuenta_destino.pk,
        "monto_entregado": "100.00",
    })

    venta = VentaDivisa.objects.get()
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("conversiones:comprobante_venta", args=[venta.pk])
    assert venta.tasa_aplicada == Decimal("7.10")
    assert venta.monto_convertido == Decimal("710.00")
    assert venta.porcentaje_comision == Decimal("2.50")
    assert venta.monto_comision == Decimal("17.75")
    assert venta.monto_acreditado == Decimal("692.25")
    assert venta.cuenta_destino == cuenta_destino


@pytest.mark.django_db
def test_venta_no_permite_usar_cuenta_de_otro_cliente(
    usuario_cliente, cliente_asociado, monedas, tasa, comision_minorista
):
    otro_cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Luis",
        apellidos="Lopez",
        documento="7654321",
        email="luis@example.com",
        telefono="0981222222",
        direccion="Asuncion",
    )
    cuenta_ajena = CuentaPago.objects.create(
        cliente=otro_cliente,
        tipo=CuentaPago.Tipo.BILLETERA,
        entidad="Tigo Money",
        numero_cuenta="0981999999",
        titular="Luis Lopez",
    )

    with pytest.raises(VentaNoDisponible, match="no pertenece al cliente"):
        confirmar_venta(
            cliente_id=cliente_asociado.pk,
            moneda_entregada=monedas[0],
            moneda_acreditada=monedas[1],
            cuenta_destino=cuenta_ajena,
            monto_entregado="100.00",
        )

    assert VentaDivisa.objects.count() == 0


@pytest.mark.django_db
def test_cliente_no_puede_confirmar_compra_para_otro_cliente(
    client, usuario_cliente, monedas, tasa, comision_minorista
):
    ajeno = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Luis",
        apellidos="Lopez",
        documento="7654321",
        email="luis@example.com",
        telefono="0981222222",
        direccion="Asuncion",
    )
    client.force_login(usuario_cliente)

    respuesta = client.post(reverse("conversiones:comprar"), {
        "cliente": ajeno.pk,
        "moneda_pagada": monedas[0].pk,
        "moneda_adquirida": monedas[1].pk,
        "monto_pagado": "100.00",
    })

    assert respuesta.status_code == 200
    assert "cliente" in respuesta.context["formulario"].errors
    assert CompraDivisa.objects.count() == 0
