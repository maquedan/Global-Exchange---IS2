"""Pruebas de RF022 — Pago con pasarela real en modo prueba (GEG9-36)."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CompraDivisa
from apps.conversiones.services import cancelar_compra, iniciar_compra
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio

from apps.pagos import services
from apps.pagos.models import Pago
from apps.pagos.proveedores.base import ProveedorPago
from apps.pagos.proveedores.dlocal import DLocalNoConfigurado, DLocalProveedor, _firmar


class ProveedorFalso(ProveedorPago):
    """Cumple la interfaz real, pero no llama a ningún servicio externo."""

    def __init__(self, estado_crear="PENDIENTE", estado_consultar="PENDIENTE", estado_reembolso="REEMBOLSADO"):
        self.estado_crear = estado_crear
        self.estado_consultar = estado_consultar
        self.estado_reembolso = estado_reembolso
        self.llamadas_consultar = 0
        self.reembolsos_pedidos = []

    def crear_pago(self, *, order_id, monto, moneda, compra, callback_url):
        return {
            "id_externo": "FALSO-1",
            "redirect_url": "https://sandbox.dlocal.com/checkout/falso",
            "estado": self.estado_crear,
            "respuesta_cruda": {"status": self.estado_crear},
        }

    def consultar_pago(self, id_externo):
        self.llamadas_consultar += 1
        return {"estado": self.estado_consultar, "respuesta_cruda": {"status": self.estado_consultar}}

    def reembolsar(self, id_externo, monto, moneda):
        self.reembolsos_pedidos.append((id_externo, monto, moneda))
        return {"estado": self.estado_reembolso, "respuesta_cruda": {"status": self.estado_reembolso}}


def _usuario_con_rol(username, rol):
    usuario = get_user_model().objects.create_user(username=username, email=f"{username}@example.com")
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    return usuario


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
    usuario = _usuario_con_rol("cliente-pagos", "usuario_cliente")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)
    return cliente, usuario


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
        tasa_compra=Decimal("7.10"),
        tasa_venta=Decimal("7.20"),
        vigente_desde=timezone.now(),
    )


@pytest.fixture
def comision_minorista():
    return ComisionCategoria.objects.create(categoria=Cliente.Categoria.MINORISTA, porcentaje=Decimal("2.50"))


@pytest.fixture
def compra_pendiente(cliente_y_usuario, monedas, tasa, comision_minorista):
    cliente, _usuario = cliente_y_usuario
    return iniciar_compra(
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )


def _con_proveedor_falso(proveedor_falso):
    """Reemplaza, solo durante el `with`, la instancia real por la falsa."""
    return patch("apps.pagos.services._instancia_proveedor", return_value=proveedor_falso)


@pytest.mark.django_db
def test_pago_aprobado_confirma_la_compra(cliente_y_usuario, compra_pendiente):
    _cliente, usuario = cliente_y_usuario
    falso = ProveedorFalso(estado_crear="PENDIENTE")

    with _con_proveedor_falso(falso):
        pago = services.iniciar_pago(compra_pendiente.pk)
        falso.estado_consultar = "APROBADO"
        pago = services.confirmar_pago(pago, usuario=usuario)

    compra_pendiente.refresh_from_db()
    assert pago.estado == Pago.Estado.APROBADO
    assert compra_pendiente.estado == CompraDivisa.Estado.CONFIRMADA


@pytest.mark.django_db
def test_pago_rechazado_no_confirma_la_compra(cliente_y_usuario, compra_pendiente):
    _cliente, usuario = cliente_y_usuario
    falso = ProveedorFalso(estado_crear="PENDIENTE", estado_consultar="RECHAZADO")

    with _con_proveedor_falso(falso):
        pago = services.iniciar_pago(compra_pendiente.pk)
        pago = services.confirmar_pago(pago, usuario=usuario)

    compra_pendiente.refresh_from_db()
    assert pago.estado == Pago.Estado.RECHAZADO
    assert compra_pendiente.estado == CompraDivisa.Estado.PENDIENTE


@pytest.mark.django_db
def test_consultar_dos_veces_no_confirma_dos_veces(cliente_y_usuario, compra_pendiente):
    _cliente, usuario = cliente_y_usuario
    falso = ProveedorFalso(estado_crear="PENDIENTE", estado_consultar="APROBADO")

    with _con_proveedor_falso(falso):
        pago = services.iniciar_pago(compra_pendiente.pk)
        services.confirmar_pago(pago, usuario=usuario)
        services.confirmar_pago(pago, usuario=usuario)

    # La segunda llamada no debe volver a consultar al proveedor ni re-confirmar.
    assert falso.llamadas_consultar == 1


@pytest.mark.django_db
def test_pago_aprobado_con_cotizacion_cambiada_no_confirma_e_intenta_reembolso(
    cliente_y_usuario, compra_pendiente, tasa
):
    _cliente, usuario = cliente_y_usuario
    falso = ProveedorFalso(estado_crear="PENDIENTE", estado_consultar="APROBADO")

    with _con_proveedor_falso(falso):
        pago = services.iniciar_pago(compra_pendiente.pk)

        # El analista actualiza la tasa mientras el cliente paga.
        tasa.activo = False
        tasa.save(update_fields=["activo"])
        TasaCambio.objects.create(
            moneda_origen=tasa.moneda_origen,
            moneda_destino=tasa.moneda_destino,
            tasa_compra=Decimal("7.50"),
            tasa_venta=Decimal("7.60"),
            vigente_desde=timezone.now(),
        )

        pago = services.confirmar_pago(pago, usuario=usuario)

    compra_pendiente.refresh_from_db()
    assert compra_pendiente.estado == CompraDivisa.Estado.CANCELADA
    assert pago.estado == Pago.Estado.REEMBOLSADO
    assert falso.reembolsos_pedidos == [("FALSO-1", pago.monto, pago.moneda)]


@pytest.mark.django_db
def test_pago_aprobado_con_operacion_vencida_no_confirma_e_intenta_reembolso(
    cliente_y_usuario, compra_pendiente
):
    from datetime import timedelta

    _cliente, usuario = cliente_y_usuario
    falso = ProveedorFalso(estado_crear="PENDIENTE", estado_consultar="APROBADO")

    with _con_proveedor_falso(falso):
        pago = services.iniciar_pago(compra_pendiente.pk)

        compra_pendiente.creado_en = timezone.now() - timedelta(minutes=16)
        compra_pendiente.save(update_fields=["creado_en"])

        pago = services.confirmar_pago(pago, usuario=usuario)

    compra_pendiente.refresh_from_db()
    assert compra_pendiente.estado == CompraDivisa.Estado.CANCELADA
    assert compra_pendiente.motivo_cancelacion == CompraDivisa.MotivoCancelacion.EXPIRADA
    assert pago.estado == Pago.Estado.REEMBOLSADO


@pytest.mark.django_db
def test_no_se_puede_iniciar_un_pago_para_una_compra_que_ya_no_esta_pendiente(
    cliente_y_usuario, compra_pendiente
):
    _cliente, usuario = cliente_y_usuario
    cancelar_compra(pk=compra_pendiente.pk, usuario=usuario)

    with pytest.raises(services.OperacionNoDisponibleParaPago):
        services.iniciar_pago(compra_pendiente.pk)


@pytest.mark.django_db
def test_monto_para_pasarela_cobra_pyg_sin_decimales(cliente_y_usuario, monedas, tasa, comision_minorista):
    # PYG no puede ser moneda_pagada de una compra real (la tasa PYG->XXX no
    # entra en 2 decimales), así que se arma la CompraDivisa directo, sin
    # pasar por iniciar_compra, solo para probar el redondeo de la pasarela.
    cliente, _usuario = cliente_y_usuario
    pyg = monedas[1]
    compra = CompraDivisa.objects.create(
        cliente=cliente,
        moneda_pagada=pyg,
        moneda_adquirida=monedas[0],
        tasa_cambio=tasa,
        monto_pagado=Decimal("50000.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("1250.00"),
        total_a_pagar=Decimal("51250.00"),
        tasa_aplicada=Decimal("7.10"),
        monto_recibido=Decimal("7217.00"),
    )

    monto, moneda = services.monto_para_pasarela(compra)

    assert moneda == "PYG"
    assert monto == compra.total_a_pagar.to_integral_value()


@pytest.mark.django_db
def test_monto_para_pasarela_convierte_moneda_no_soportada_a_pyg(cliente_y_usuario, comision_minorista):
    cliente, _usuario = cliente_y_usuario
    eur = Moneda.objects.create(codigo="EUR", nombre="Euro", simbolo="€")
    pyg = Moneda.objects.create(codigo="PYG", nombre="Guarani", simbolo="Gs")
    TasaCambio.objects.create(
        moneda_origen=eur, moneda_destino=pyg,
        tasa_compra=Decimal("7700.00"), tasa_venta=Decimal("7820.00"),
        vigente_desde=timezone.now(),
    )
    compra = iniciar_compra(cliente_id=cliente.pk, moneda_pagada=eur, moneda_adquirida=pyg, monto_pagado="100.00")

    monto, moneda = services.monto_para_pasarela(compra)

    # EUR no lo cobra dLocal en Paraguay: se convierte al equivalente en PYG.
    assert moneda == "PYG"
    assert monto == (compra.total_a_pagar * compra.tasa_aplicada).to_integral_value()


@pytest.mark.django_db
def test_pago_exige_compra_o_venta_pero_no_las_dos(compra_pendiente):
    with pytest.raises(IntegrityError):
        Pago.objects.create(
            order_id="duplicado-sin-operacion",
            proveedor="simulado",
            monto=Decimal("100.00"),
            moneda="PYG",
        )


def test_dlocal_sin_credenciales_da_error_claro(settings):
    settings.DLOCAL_X_LOGIN = ""
    settings.DLOCAL_X_TRANS_KEY = ""
    settings.DLOCAL_SECRET_KEY = ""
    proveedor = DLocalProveedor()

    with pytest.raises(DLocalNoConfigurado):
        proveedor.crear_pago(order_id="x", monto=Decimal("100"), moneda="PYG", compra=None, callback_url="https://example.com/retorno/")


def test_firma_hmac_concatena_login_fecha_cuerpo_sin_separadores():
    firma = _firmar("mi-login", "2024-01-01T00:00:00.000+0000", '{"a":1}', "mi-secreto")

    import hashlib
    import hmac as hmac_lib

    esperada = hmac_lib.new(
        "mi-secreto".encode("utf-8"),
        'mi-login2024-01-01T00:00:00.000+0000{"a":1}'.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert firma == esperada


@pytest.mark.django_db
def test_elegir_pago_requiere_ser_el_dueno_de_la_compra(client, compra_pendiente, django_user_model):
    otro = django_user_model.objects.create_user(username="otro-cliente-pagos")
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    otro.groups.add(grupo)
    client.force_login(otro)

    respuesta = client.get(reverse("pagos:elegir_pago", args=[compra_pendiente.pk]))

    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_confirmar_pago_sin_usuario_autenticado_igual_confirma_la_compra(compra_pendiente):
    """dLocal vuelve al navegador con un POST entre sitios: puede no traer la
    cookie de sesión. La confirmación no debe depender de eso (bug real
    encontrado probando contra el sandbox)."""
    falso = ProveedorFalso(estado_crear="PENDIENTE", estado_consultar="APROBADO")

    with _con_proveedor_falso(falso):
        pago = services.iniciar_pago(compra_pendiente.pk)
        pago = services.confirmar_pago(pago, usuario=None)

    compra_pendiente.refresh_from_db()
    assert compra_pendiente.estado == CompraDivisa.Estado.CONFIRMADA
    assert pago.estado == Pago.Estado.APROBADO


@pytest.mark.django_db
def test_retorno_acepta_post_sin_csrf_y_sin_sesion(compra_pendiente):
    """Simula exactamente lo que hace dLocal: un POST del navegador, sin
    token CSRF ni cookie de sesión. Se usa un `Client` que SÍ exige CSRF
    (a diferencia del fixture `client` normal, que no lo exige nunca) para
    probar de verdad que `@csrf_exempt` hace falta."""
    from django.test import Client

    falso = ProveedorFalso(estado_crear="PENDIENTE", estado_consultar="APROBADO")
    cliente_estricto = Client(enforce_csrf_checks=True)

    with _con_proveedor_falso(falso):
        pago = services.iniciar_pago(compra_pendiente.pk)
        respuesta = cliente_estricto.post(reverse("pagos:retorno", args=[pago.pk]))

    assert respuesta.status_code == 302
    compra_pendiente.refresh_from_db()
    assert compra_pendiente.estado == CompraDivisa.Estado.CONFIRMADA
