"""Pruebas unitarias de RF028: estado fiscal, auditoría y reintentos."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.conversiones.models import CompraDivisa
from apps.facturacion import services
from apps.facturacion.models import Factura, HistorialEstadoFiscal
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


@pytest.fixture
def factura():
    usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$" )
    pyg = Moneda.objects.create(codigo="PYG", nombre="Guaraní", simbolo="Gs")
    tasa = TasaCambio.objects.create(
        moneda_origen=usd, moneda_destino=pyg, tasa_compra=Decimal("7000"),
        tasa_venta=Decimal("7100"), vigente_desde=timezone.now(),
    )
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA, nombres="Ana", apellidos="Prueba",
        documento="123", email="ana-rf028@example.com", telefono="0981", direccion="Asunción",
    )
    compra = CompraDivisa.objects.create(
        cliente=cliente, moneda_pagada=usd, moneda_adquirida=pyg, tasa_cambio=tasa,
        monto_pagado=Decimal("10"), porcentaje_comision=Decimal("0"), monto_comision=Decimal("0"),
        total_a_pagar=Decimal("10"), tasa_aplicada=Decimal("7000"), monto_recibido=Decimal("70000"),
        estado=CompraDivisa.Estado.CONFIRMADA, confirmado_en=timezone.now(),
    )
    return Factura.objects.create(
        compra=compra, timbrado="12345678", establecimiento="001", punto_expedicion="001",
        numero="0000001", cdc="1" * 44, monto=Decimal("70000"), monto_origen=Decimal("10"), moneda_origen="USD",
    )


class ClienteEstadoFalso:
    def __init__(self, estado="APROBADA"):
        self.estado = estado
        self.consultas = []
        self.emisiones = 0

    def consultar_estado(self, cdc):
        self.consultas.append(cdc)
        return {"estado_fiscal": self.estado, "motivo": "Documento validado", "operation_id": "consulta-1", "respuesta": {"estado": self.estado}}

    def calcular_de(self, de):
        return de

    def generar_de(self, de):
        self.emisiones += 1
        return {"cdc": "2" * 44, "operation_id": "emision-1", "respuesta": {"code": 0}}


@pytest.mark.django_db
def test_consultar_estado_actualiza_y_audita_la_transicion(factura, settings):
    cliente = ClienteEstadoFalso("RECHAZADA")
    settings.FACTURACION_PROVEEDOR = "simulado"
    with patch("apps.facturacion.services._instancia_cliente", return_value=cliente):
        resultado = services.consultar_estado_fiscal(factura)

    resultado.refresh_from_db()
    assert resultado.estado_fiscal == Factura.EstadoFiscal.RECHAZADA
    assert resultado.motivo_rechazo == "Documento validado"
    cambio = HistorialEstadoFiscal.objects.get(factura=resultado)
    assert cambio.estado_anterior == ""
    assert cambio.estado_nuevo == "RECHAZADA"
    assert cambio.operation_id == "consulta-1"


@pytest.mark.django_db
def test_no_reenvia_si_la_consulta_previa_confirma_la_factura(factura, settings):
    factura.estado = Factura.Estado.ERROR
    factura.save(update_fields=["estado"])
    cliente = ClienteEstadoFalso("APROBADA")
    settings.FACTURACION_PROVEEDOR = "simulado"
    with patch("apps.facturacion.services._instancia_cliente", return_value=cliente):
        resultado = services.emitir_factura(factura.operacion)

    assert resultado.estado_fiscal == "APROBADA"
    assert cliente.consultas == [factura.cdc]
    assert cliente.emisiones == 0


@pytest.mark.django_db
def test_reintento_de_rechazada_consulta_antes_de_emitir(factura, settings):
    factura.estado = Factura.Estado.ERROR
    factura.estado_fiscal = Factura.EstadoFiscal.RECHAZADA
    factura.save(update_fields=["estado", "estado_fiscal"])
    cliente = ClienteEstadoFalso("RECHAZADA")
    settings.FACTURACION_PROVEEDOR = "simulado"
    with patch("apps.facturacion.services._instancia_cliente", return_value=cliente):
        resultado = services.reintentar_factura(factura)

    assert cliente.consultas == [factura.cdc]
    assert cliente.emisiones == 1
    assert resultado.estado == Factura.Estado.GENERADA
