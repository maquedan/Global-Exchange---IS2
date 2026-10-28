"""Pruebas de RF026 — Generación automática de facturas (GEG9-50).

Ninguna toca la red: el cliente real se reemplaza por dobles que cumplen la
misma interfaz (`ClienteFacturacion`), igual que en las pruebas de RF022.
"""
import logging
from decimal import Decimal
from unittest.mock import patch

import pytest
import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CompraDivisa, VentaDivisa
from apps.conversiones.services import (
    confirmar_pago_compra,
    confirmar_pago_venta,
    iniciar_compra,
    iniciar_venta,
)
from apps.cuentas.models import CuentaPago
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio

from apps.facturacion import services
from apps.facturacion.clientes.base import (
    ClienteFacturacion,
    EmisionSinConfirmar,
    FacturaRechazada,
    FacturacionNoConfigurada,
)
from apps.facturacion.clientes.facturasegura import FacturaSeguraCliente
from apps.facturacion.clientes.simulado import FacturaSimuladaCliente
from apps.facturacion.de import DatosDeFacturacionIncompletos, armar_de, monto_facturable
from apps.facturacion.models import Factura, SecuenciaFactura


class ClienteFalso(ClienteFacturacion):
    """Cumple la interfaz real, sin llamar a ningún servicio externo."""

    def __init__(self, *, error_en_generar=None, cdc="0" * 44):
        self.error_en_generar = error_en_generar
        self.cdc = cdc
        self.des_enviados = []

    def calcular_de(self, de):
        return dict(de)

    def generar_de(self, de):
        self.des_enviados.append(de)
        if self.error_en_generar is not None:
            raise self.error_en_generar
        return {
            "cdc": self.cdc,
            "operation_id": "op-falso-1",
            "respuesta": {"code": 0, "results": [{"CDC": self.cdc}]},
        }


def _con_cliente_falso(cliente_falso):
    """Reemplaza, solo durante el `with`, el cliente real por el falso."""
    return patch(
        "apps.facturacion.services._instancia_cliente", return_value=cliente_falso
    )


@pytest.fixture(autouse=True)
def configuracion_de_facturacion(settings):
    """Fija la configuración de facturación en valores conocidos.

    Sin esto las pruebas dependerían del `.env` de cada máquina: quien tenga
    cargados el punto de expedición, el rango o el emisor reales vería fallar
    pruebas que no tienen nada que ver con su cambio. Y, mucho peor, con
    `FACTURACION_PROVEEDOR=facturasegura` en el `.env` una prueba podría
    terminar llamando a la API de verdad y gastando un número del rango
    autorizado.

    Cada prueba que necesite otro valor lo sobrescribe: su propia asignación
    corre después de este fixture.
    """
    settings.FACTURACION_PROVEEDOR = "simulado"
    settings.FACTURASEGURA_TOKEN = ""
    settings.FACTURACION_ESTABLECIMIENTO = "001"
    settings.FACTURACION_PUNTO_EXPEDICION = "001"
    settings.FACTURACION_NUMERO_DESDE = 1
    settings.FACTURACION_NUMERO_HASTA = 0
    settings.FACTURACION_TIMBRADO = "00000000"
    settings.FACTURACION_TIMBRADO_INICIO = "2026-01-01"
    settings.FACTURACION_EMISOR_RUC = "00000000"
    settings.FACTURACION_EMISOR_DV = "0"
    settings.FACTURACION_EMISOR_TIPO_CONTRIBUYENTE = "2"
    settings.FACTURACION_EMISOR_NOMBRE = "EMISOR DE PRUEBA"
    settings.FACTURACION_EMISOR_DIRECCION = "Sin definir"
    settings.FACTURACION_EMISOR_NUMERO_CASA = "0"
    settings.FACTURACION_EMISOR_DEPARTAMENTO = "1"
    settings.FACTURACION_EMISOR_DEPARTAMENTO_NOMBRE = "CAPITAL"
    settings.FACTURACION_EMISOR_CIUDAD = "1"
    settings.FACTURACION_EMISOR_CIUDAD_NOMBRE = "ASUNCION (DISTRITO)"
    settings.FACTURACION_EMISOR_TELEFONO = "(021)000000"
    settings.FACTURACION_EMISOR_EMAIL = "facturacion@globalexchange.test"
    settings.FACTURACION_EMISOR_ACTIVIDADES = (
        "66190:Otras actividades auxiliares de servicios financieros"
    )


def _asociar(cliente, username):
    """Crea un usuario con rol de cliente y lo asocia.

    Desde RF010 (GEG9-20) `iniciar_compra` exige un usuario habilitado para
    el cliente, así que un cliente suelto ya no alcanza para armar el caso.
    """
    usuario = _usuario_con_rol(username, "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)
    return usuario


def _usuario_con_rol(username, rol):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com"
    )
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    return usuario


@pytest.fixture
def monedas():
    return (
        Moneda.objects.create(codigo="USD", nombre="Dolar", simbolo="$"),
        Moneda.objects.create(codigo="PYG", nombre="Guarani", simbolo="Gs"),
    )


@pytest.fixture
def tasa(monedas):
    return TasaCambio.objects.create(
        moneda_origen=monedas[0],
        moneda_destino=monedas[1],
        tasa_compra=Decimal("7100.00"),
        tasa_venta=Decimal("7200.00"),
        vigente_desde=timezone.now(),
    )


@pytest.fixture
def comision_minorista():
    return ComisionCategoria.objects.create(
        categoria=Cliente.Categoria.MINORISTA, porcentaje=Decimal("2.50")
    )


@pytest.fixture
def cliente_y_usuario():
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Ana",
        apellidos="Gomez",
        documento="1234567",
        email="ana@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )
    usuario = _usuario_con_rol("cliente-facturacion", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)
    return cliente, usuario


@pytest.fixture
def compra_pendiente(cliente_y_usuario, monedas, tasa, comision_minorista):
    cliente, usuario = cliente_y_usuario
    return iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )


@pytest.fixture
def venta_pendiente(cliente_y_usuario, monedas, tasa, comision_minorista):
    cliente, usuario = cliente_y_usuario
    cuenta = CuentaPago.objects.create(
        cliente=cliente,
        tipo=CuentaPago.Tipo.BANCARIA,
        entidad="Banco Demo",
        numero_cuenta="123456",
        titular="Ana Gomez",
    )
    return iniciar_venta(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_entregada=monedas[0],
        moneda_acreditada=monedas[1],
        cuenta_destino=cuenta,
        monto_entregado="50.00",
    )


# ---------------------------------------------------------------------------
# Disparo automático al confirmarse la operación
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_confirmar_una_compra_genera_la_factura(
    cliente_y_usuario, compra_pendiente, django_capture_on_commit_callbacks
):
    _cliente, usuario = cliente_y_usuario
    falso = ClienteFalso()

    with _con_cliente_falso(falso):
        with django_capture_on_commit_callbacks(execute=True):
            confirmar_pago_compra(pk=compra_pendiente.pk, usuario=usuario)

    compra_pendiente.refresh_from_db()
    factura = Factura.objects.get(compra=compra_pendiente)
    assert compra_pendiente.estado == CompraDivisa.Estado.CONFIRMADA
    assert factura.estado == Factura.Estado.GENERADA
    assert len(factura.cdc) == 44
    assert factura.generada_en is not None


@pytest.mark.django_db(transaction=True)
def test_confirmar_una_venta_genera_la_factura(
    cliente_y_usuario, venta_pendiente, django_capture_on_commit_callbacks
):
    _cliente, usuario = cliente_y_usuario
    falso = ClienteFalso()

    with _con_cliente_falso(falso):
        with django_capture_on_commit_callbacks(execute=True):
            confirmar_pago_venta(pk=venta_pendiente.pk, usuario=usuario)

    venta_pendiente.refresh_from_db()
    factura = Factura.objects.get(venta=venta_pendiente)
    assert venta_pendiente.estado == VentaDivisa.Estado.CONFIRMADA
    assert factura.estado == Factura.Estado.GENERADA


@pytest.mark.django_db(transaction=True)
def test_si_la_facturacion_falla_la_operacion_sigue_confirmada(
    cliente_y_usuario, compra_pendiente, django_capture_on_commit_callbacks
):
    """RNF011: un fallo de la factura nunca deshace ni bloquea la operación."""
    _cliente, usuario = cliente_y_usuario
    falso = ClienteFalso(
        error_en_generar=FacturaRechazada(
            "El valor del campo iTiOpe no es permitido", code=-10001
        )
    )

    with _con_cliente_falso(falso):
        with django_capture_on_commit_callbacks(execute=True):
            confirmar_pago_compra(pk=compra_pendiente.pk, usuario=usuario)

    compra_pendiente.refresh_from_db()
    factura = Factura.objects.get(compra=compra_pendiente)
    assert compra_pendiente.estado == CompraDivisa.Estado.CONFIRMADA
    assert factura.estado == Factura.Estado.ERROR
    assert "iTiOpe" in factura.mensaje_error


@pytest.mark.django_db(transaction=True)
def test_una_excepcion_inesperada_tampoco_rompe_la_confirmacion(
    cliente_y_usuario, compra_pendiente, django_capture_on_commit_callbacks
):
    _cliente, usuario = cliente_y_usuario
    falso = ClienteFalso(error_en_generar=RuntimeError("algo totalmente inesperado"))

    with _con_cliente_falso(falso):
        with django_capture_on_commit_callbacks(execute=True):
            confirmar_pago_compra(pk=compra_pendiente.pk, usuario=usuario)

    compra_pendiente.refresh_from_db()
    assert compra_pendiente.estado == CompraDivisa.Estado.CONFIRMADA
    # La factura quedó reservada y reintentable, no perdida.
    assert Factura.objects.get(compra=compra_pendiente).estado == Factura.Estado.PENDIENTE


# ---------------------------------------------------------------------------
# Timeout: queda A_VERIFICAR y no se reenvía sola
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_timeout_deja_la_factura_a_verificar(compra_pendiente):
    falso = ClienteFalso(error_en_generar=EmisionSinConfirmar("se venció el tiempo"))

    with _con_cliente_falso(falso):
        factura = services.emitir_factura(compra_pendiente)

    assert factura.estado == Factura.Estado.A_VERIFICAR
    assert factura.cdc == ""


@pytest.mark.django_db
def test_una_factura_a_verificar_no_se_reenvia_sola(compra_pendiente):
    falso = ClienteFalso(error_en_generar=EmisionSinConfirmar("se cortó la red"))
    with _con_cliente_falso(falso):
        services.emitir_factura(compra_pendiente)

    # Segundo intento: ahora el cliente responde bien, pero ni siquiera se lo
    # tiene que llamar — el documento pudo haberse generado la primera vez.
    sano = ClienteFalso()
    with _con_cliente_falso(sano):
        factura = services.emitir_factura(compra_pendiente)

    assert factura.estado == Factura.Estado.A_VERIFICAR
    assert sano.des_enviados == []


@pytest.mark.django_db
def test_el_comando_reintenta_los_errores_pero_no_los_a_verificar(
    compra_pendiente, venta_pendiente
):
    from django.core.management import call_command

    with _con_cliente_falso(ClienteFalso(error_en_generar=FacturaRechazada("error"))):
        services.emitir_factura(compra_pendiente)
    with _con_cliente_falso(ClienteFalso(error_en_generar=EmisionSinConfirmar("corte"))):
        services.emitir_factura(venta_pendiente)

    with _con_cliente_falso(ClienteFalso()):
        call_command("emitir_facturas_pendientes")

    assert Factura.objects.get(compra=compra_pendiente).estado == Factura.Estado.GENERADA
    assert Factura.objects.get(venta=venta_pendiente).estado == Factura.Estado.A_VERIFICAR


# ---------------------------------------------------------------------------
# Una factura por operación
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_emitir_dos_veces_no_duplica_la_factura(compra_pendiente):
    falso = ClienteFalso()

    with _con_cliente_falso(falso):
        primera = services.emitir_factura(compra_pendiente)
        segunda = services.emitir_factura(compra_pendiente)

    assert primera.pk == segunda.pk
    assert Factura.objects.filter(compra=compra_pendiente).count() == 1
    # La segunda vez no se volvió a llamar a la API.
    assert len(falso.des_enviados) == 1


@pytest.mark.django_db
def test_la_base_rechaza_dos_facturas_para_la_misma_operacion(compra_pendiente):
    with _con_cliente_falso(ClienteFalso()):
        services.emitir_factura(compra_pendiente)

    with pytest.raises(IntegrityError):
        Factura.objects.create(
            compra=compra_pendiente,
            timbrado="00000000",
            establecimiento="001",
            punto_expedicion="001",
            numero="0009999",
            monto=Decimal("1000"),
            monto_origen=Decimal("1000"),
            moneda_origen="PYG",
        )


@pytest.mark.django_db
def test_la_base_rechaza_una_factura_sin_operacion():
    with pytest.raises(IntegrityError):
        Factura.objects.create(
            timbrado="00000000",
            establecimiento="001",
            punto_expedicion="001",
            numero="0000001",
            monto=Decimal("1000"),
            monto_origen=Decimal("1000"),
            moneda_origen="PYG",
        )


@pytest.mark.django_db
def test_la_numeracion_no_se_repite(compra_pendiente, venta_pendiente):
    with _con_cliente_falso(ClienteFalso()):
        primera = services.emitir_factura(compra_pendiente)
        segunda = services.emitir_factura(venta_pendiente)

    assert primera.numero != segunda.numero
    assert int(segunda.numero) == int(primera.numero) + 1
    assert len(primera.numero) == 7


@pytest.mark.django_db
def test_reintentar_reusa_el_mismo_numero(compra_pendiente):
    """Así la secuencia del SIFEN no queda con huecos."""
    with _con_cliente_falso(ClienteFalso(error_en_generar=FacturaRechazada("error"))):
        fallida = services.emitir_factura(compra_pendiente)
    numero_reservado = fallida.numero

    with _con_cliente_falso(ClienteFalso()):
        generada = services.emitir_factura(compra_pendiente)

    assert generada.numero == numero_reservado
    assert generada.intentos == 2
    assert SecuenciaFactura.objects.get(
        establecimiento="001", punto_expedicion="001"
    ).ultimo_numero == int(numero_reservado)


@pytest.mark.django_db
def test_la_numeracion_arranca_en_el_rango_autorizado(settings, compra_pendiente):
    settings.FACTURACION_NUMERO_DESDE = 489
    settings.FACTURACION_NUMERO_HASTA = 500

    with _con_cliente_falso(ClienteFalso()):
        factura = services.emitir_factura(compra_pendiente)

    assert factura.numero == "0000489"
    assert factura.estado == Factura.Estado.GENERADA


@pytest.mark.django_db
def test_pasado_el_rango_la_factura_queda_en_error_sin_llamar_a_la_api(
    settings, compra_pendiente, venta_pendiente
):
    settings.FACTURACION_NUMERO_DESDE = 489
    settings.FACTURACION_NUMERO_HASTA = 489  # un solo número disponible

    falso = ClienteFalso()
    with _con_cliente_falso(falso):
        primera = services.emitir_factura(compra_pendiente)
        segunda = services.emitir_factura(venta_pendiente)

    assert primera.estado == Factura.Estado.GENERADA
    assert segunda.estado == Factura.Estado.ERROR
    assert "rango de numeración" in segunda.mensaje_error
    assert len(falso.des_enviados) == 1


@pytest.mark.django_db
def test_el_de_lleva_todas_las_actividades_economicas(settings, compra_pendiente):
    settings.FACTURACION_EMISOR_ACTIVIDADES = (
        "62010:Actividades de programación informática"
        "|74909:Otras actividades profesionales, científicas y técnicas n.c.p."
    )

    falso = ClienteFalso()
    with _con_cliente_falso(falso):
        services.emitir_factura(compra_pendiente)

    actividades = falso.des_enviados[0]["gActEco"]
    assert [a["cActEco"] for a in actividades] == ["62010", "74909"]
    assert actividades[1]["dDesActEco"].endswith("n.c.p.")


@pytest.mark.django_db
def test_una_actividad_mal_escrita_da_un_error_claro(settings, compra_pendiente):
    settings.FACTURACION_EMISOR_ACTIVIDADES = "62010"

    with _con_cliente_falso(ClienteFalso()):
        factura = services.emitir_factura(compra_pendiente)

    assert factura.estado == Factura.Estado.ERROR
    assert "codigo:descripcion" in factura.mensaje_error


# ---------------------------------------------------------------------------
# Armado del DE
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_el_monto_se_convierte_a_guaranies(compra_pendiente):
    """100 USD + 2,50% de comisión = 102,50 USD, a 7100 PYG por dólar."""
    monto_pyg, monto_origen, moneda_origen = monto_facturable(compra_pendiente)

    assert moneda_origen == "USD"
    assert monto_origen == Decimal("102.50")
    assert monto_pyg == Decimal("727750")


@pytest.mark.django_db
def test_una_operacion_en_guaranies_no_se_convierte(
    cliente_y_usuario, monedas, comision_minorista
):
    cliente, usuario = cliente_y_usuario
    usd, pyg = monedas
    TasaCambio.objects.create(
        moneda_origen=pyg,
        moneda_destino=usd,
        tasa_compra=Decimal("1.00"),
        tasa_venta=Decimal("1.00"),
        vigente_desde=timezone.now(),
    )
    compra = iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=pyg,
        moneda_adquirida=usd,
        monto_pagado="100000.00",
    )

    monto_pyg, _monto_origen, moneda_origen = monto_facturable(compra)

    assert moneda_origen == "PYG"
    assert monto_pyg == Decimal("102500")


@pytest.mark.django_db
def test_el_de_lleva_el_receptor_el_item_y_la_forma_de_pago(compra_pendiente):
    falso = ClienteFalso()
    with _con_cliente_falso(falso):
        services.emitir_factura(compra_pendiente)

    de = falso.des_enviados[0]

    assert de["cMoneOpe"] == "PYG"
    assert de["dEmailRec"] == "ana@example.com"
    # Persona física: consumidor final identificado con la cédula, sin DV.
    assert de["iNatRec"] == "2"
    assert de["dNumIDRec"] == "1234567"
    assert "dDVRec" not in de
    # Un solo ítem, por el total de la operación en guaraníes.
    assert len(de["gCamItem"]) == 1
    assert de["gCamItem"][0]["dPUniProSer"] == "727750"
    assert de["gCamItem"][0]["dTasaIVA"] == "10"
    assert de["gCamItem"][0]["cUniMed"] == "77"
    # Obligatorio por ser al contado.
    assert de["gPaConEIni"][0]["dMonTiPag"] == "727750"
    # Las dos cifras quedan a la vista en el KuDE.
    assert "102.50 USD" in de["dInfAdic"]
    assert "727750 PYG" in de["dInfAdic"]


@pytest.mark.django_db
def test_un_cliente_juridico_va_como_contribuyente_con_ruc_y_dv(
    monedas, tasa, comision_minorista
):
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.JURIDICA,
        razon_social="Comercial Demo S.A.",
        ruc="80002247-5",
        email="facturas@demo.com",
        telefono="021000000",
        direccion="Asuncion",
        categoria=Cliente.Categoria.MINORISTA,
    )
    compra = iniciar_compra(
        usuario=_asociar(cliente, f"op-{cliente.pk}"),
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )

    falso = ClienteFalso()
    with _con_cliente_falso(falso):
        services.emitir_factura(compra)

    de = falso.des_enviados[0]
    assert de["iNatRec"] == "1"
    assert de["dRucRec"] == "80002247"
    assert de["dDVRec"] == "5"


@pytest.mark.django_db
def test_un_ruc_sin_dv_no_inventa_el_digito(monedas, tasa, comision_minorista):
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.JURIDICA,
        razon_social="Sin DV S.A.",
        ruc="80002247",
        email="facturas@sindv.com",
        telefono="021000000",
        direccion="Asuncion",
        categoria=Cliente.Categoria.MINORISTA,
    )
    compra = iniciar_compra(
        usuario=_asociar(cliente, f"op-{cliente.pk}"),
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )

    falso = ClienteFalso()
    with _con_cliente_falso(falso):
        factura = services.emitir_factura(compra)

    assert factura.estado == Factura.Estado.ERROR
    assert "RUC-DV" in factura.mensaje_error
    assert falso.des_enviados == []


@pytest.mark.django_db
def test_un_cliente_sin_correo_da_un_error_claro(monedas, tasa, comision_minorista):
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Sin",
        apellidos="Correo",
        documento="7654321",
        email="",
        telefono="0981000000",
        direccion="Asuncion",
    )
    compra = iniciar_compra(
        usuario=_asociar(cliente, f"op-{cliente.pk}"),
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )

    with _con_cliente_falso(ClienteFalso()):
        factura = services.emitir_factura(compra)

    assert factura.estado == Factura.Estado.ERROR
    assert "correo electrónico" in factura.mensaje_error


# ---------------------------------------------------------------------------
# Cliente de la API
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_el_cliente_simulado_devuelve_un_cdc_de_44_digitos_marcado(compra_pendiente):
    factura = services._reservar_factura(compra_pendiente)
    de = armar_de(compra_pendiente, factura=factura)

    resultado = FacturaSimuladaCliente().generar_de(de)

    assert len(resultado["cdc"]) == 44
    assert resultado["cdc"].isdigit()
    # El prefijo 99 lo delata como simulado (un CDC real arranca con 01).
    assert resultado["cdc"].startswith("99")
    assert resultado["respuesta"]["simulado"] is True


def test_sin_token_el_cliente_real_falla_con_un_mensaje_claro(settings):
    settings.FACTURACION_PROVEEDOR = "facturasegura"
    settings.FACTURASEGURA_TOKEN = ""

    with pytest.raises(FacturacionNoConfigurada) as error:
        FacturaSeguraCliente()

    assert "FACTURASEGURA_TOKEN" in str(error.value)


def test_con_datos_de_prueba_el_cliente_real_se_niega_a_emitir(settings):
    settings.FACTURASEGURA_TOKEN = "token-de-prueba"
    settings.FACTURACION_EMISOR_RUC = "00000000"

    with pytest.raises(FacturacionNoConfigurada) as error:
        FacturaSeguraCliente()

    assert "valor de prueba" in str(error.value)


def test_un_code_negativo_se_traduce_a_factura_rechazada(settings):
    settings.FACTURASEGURA_TOKEN = "token-de-prueba"
    settings.FACTURACION_EMISOR_RUC = "80002247"
    settings.FACTURACION_TIMBRADO = "80002247"
    respuesta_api = {
        "code": -10001,
        "description": "El valor del campo iTiOpe no es permitido",
        "operation_info": {"id": "0b44f5f9"},
        "results": [{"Exception": "Longitud de campo incorrecta"}],
    }

    with patch("apps.facturacion.clientes.facturasegura.requests.post") as post:
        post.return_value.json.return_value = respuesta_api
        with pytest.raises(FacturaRechazada) as error:
            FacturaSeguraCliente().generar_de({"iTiDE": "1"})

    assert error.value.code == -10001
    assert error.value.operation_id == "0b44f5f9"
    assert "iTiOpe" in str(error.value)


def test_un_timeout_se_traduce_a_emision_sin_confirmar(settings):
    settings.FACTURASEGURA_TOKEN = "token-de-prueba"
    settings.FACTURACION_EMISOR_RUC = "80002247"
    settings.FACTURACION_TIMBRADO = "80002247"

    with patch(
        "apps.facturacion.clientes.facturasegura.requests.post",
        side_effect=requests.Timeout("se venció el tiempo"),
    ):
        with pytest.raises(EmisionSinConfirmar):
            FacturaSeguraCliente().generar_de({"iTiDE": "1"})


def test_el_token_nunca_aparece_en_los_logs(settings, caplog):
    settings.FACTURASEGURA_TOKEN = "token-secretisimo-123"
    settings.FACTURACION_EMISOR_RUC = "80002247"
    settings.FACTURACION_TIMBRADO = "80002247"
    respuesta_api = {
        "code": -10001,
        "description": "error cualquiera",
        "operation_info": {"id": "abc"},
        "results": [],
    }

    with caplog.at_level(logging.DEBUG):
        with patch("apps.facturacion.clientes.facturasegura.requests.post") as post:
            post.return_value.json.return_value = respuesta_api
            with pytest.raises(FacturaRechazada):
                FacturaSeguraCliente().generar_de({"iTiDE": "1"})

    assert "token-secretisimo-123" not in caplog.text


@pytest.mark.django_db
def test_lo_que_se_guarda_de_la_peticion_no_tiene_el_token(settings, compra_pendiente):
    settings.FACTURASEGURA_TOKEN = "token-secretisimo-123"

    with _con_cliente_falso(ClienteFalso()):
        factura = services.emitir_factura(compra_pendiente)

    guardado = f"{factura.peticion}{factura.respuesta}"
    assert "token-secretisimo-123" not in guardado
    assert "Authentication-Token" not in guardado
