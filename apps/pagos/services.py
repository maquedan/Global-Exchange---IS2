"""Confirmación de pagos vía pasarela (RF022 — GEG9-36).

El flujo de "Confirmar pago" de RF051 (`apps.conversiones.services`) seguía
confirmando directo con un clic. Acá se intercala un paso: la compra recién
pasa de PENDIENTE a CONFIRMADA cuando el pago en la pasarela sale aprobado.
"""
import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.urls import reverse

from apps.clientes.models import AsociacionUsuarioCliente
from apps.usuarios.services import cliente_habilitado_para
from apps.conversiones.models import CompraDivisa
from apps.conversiones.services import (
    CompraNoConfirmable,
    confirmar_pago_compra,
    expirar_compra_si_corresponde,
)

from .models import CambioMetodoPago, MetodoPago, Pago
from .proveedores.dlocal import (
    DLocalErrorDeRed,
    DLocalNoConfigurado,
    DLocalProveedor,
)
from .proveedores.simulado import SimuladoProveedor

logger = logging.getLogger(__name__)


class OperacionNoDisponibleParaPago(Exception):
    """La compra no está en condiciones de iniciar o resolver un pago."""


class ReembolsoPagoNoDisponible(Exception):
    """No se puede solicitar un reembolso para el proveedor del pago."""


def _instancia_proveedor(nombre):
    if nombre == "dlocal":
        return DLocalProveedor()
    return SimuladoProveedor()


def solicitar_reembolso_pago(pago):
    """Solicita el reembolso de un pago aprobado a su proveedor original."""
    if pago.proveedor not in {"dlocal", "simulado"}:
        raise ReembolsoPagoNoDisponible(
            "El pago no tiene un proveedor con reembolso automático."
        )

    proveedor = _instancia_proveedor(pago.proveedor)
    try:
        return proveedor.reembolsar(pago.id_externo, pago.monto, pago.moneda)
    except (DLocalNoConfigurado, DLocalErrorDeRed, requests.RequestException) as error:
        logger.exception("No se pudo solicitar el reembolso del pago %s", pago.order_id)
        return {
            "estado": "REQUIERE_REVISION",
            "respuesta_cruda": {"error": type(error).__name__},
        }


def _proveedor_configurado():
    nombre = getattr(settings, "PAGO_PROVEEDOR", "simulado")
    return nombre, _instancia_proveedor(nombre)


def monto_para_pasarela(compra):
    """Moneda y monto que realmente se le cobra al cliente por la pasarela.

    dLocal en Paraguay solo cobra en PYG (sin decimales) o en USD (tarjetas,
    vía ``currency_to_charge``). Si `moneda_pagada` es otra divisa (EUR, BRL,
    ARS, GBP, JPY), se convierte al equivalente en PYG usando `tasa_aplicada`
    —ya congelada en la operación, son PYG por unidad de `moneda_pagada`—,
    en vez de rechazar la operación. Decisión de equipo para RF022.
    """
    codigo = compra.moneda_pagada.codigo

    if codigo == "PYG":
        return compra.total_a_pagar.to_integral_value(rounding=ROUND_HALF_UP), "PYG"

    if codigo == "USD":
        return compra.total_a_pagar.quantize(Decimal("0.01")), "USD"

    monto_pyg = (compra.total_a_pagar * compra.tasa_aplicada).to_integral_value(
        rounding=ROUND_HALF_UP
    )
    return monto_pyg, "PYG"


class MetodoPagoNoDisponible(Exception):
    """El método de pago está deshabilitado o no existe (RF035 — GEG9-77)."""


# Códigos de los métodos que crea la migración 0003. Se nombran acá para que
# los servicios no dependan de un texto suelto repartido por el código.
CODIGO_TARJETA = "tarjeta"
CODIGO_TRANSFERENCIA = "transferencia"


def metodos_habilitados():
    """Los métodos que hoy se le pueden ofrecer al cliente."""
    return MetodoPago.objects.filter(habilitado=True)


def exigir_metodo_habilitado(codigo):
    """Corta si ese método no está disponible para iniciar un pago nuevo.

    **Solo se usa al iniciar.** Confirmar o cancelar un pago ya iniciado
    nunca pasa por acá: si se deshabilitara un método mientras hay
    operaciones esperando, esas operaciones quedarían trabadas sin forma de
    resolverse, y el cliente ya transfirió el dinero (RF035, punto 5).
    """
    metodo = MetodoPago.objects.filter(codigo=codigo, habilitado=True).first()
    if metodo is None:
        raise MetodoPagoNoDisponible(
            "Ese método de pago no está disponible en este momento. "
            "Elegí otro o probá más tarde."
        )
    return metodo


@transaction.atomic
def cambiar_estado_metodo(*, codigo, habilitado, usuario):
    """Habilita o deshabilita un método y deja constancia de quién lo hizo.

    Es idempotente: si ya estaba en ese estado no registra un cambio que no
    ocurrió.
    """
    metodo = MetodoPago.objects.select_for_update().filter(codigo=codigo).first()
    if metodo is None:
        raise MetodoPagoNoDisponible("Ese método de pago no existe.")

    if metodo.habilitado == habilitado:
        return metodo

    metodo.habilitado = habilitado
    metodo.save(update_fields=["habilitado"])
    CambioMetodoPago.objects.create(
        metodo=metodo, habilitado=habilitado, usuario=usuario
    )
    logger.info(
        "Método de pago %s %s por %s",
        codigo,
        "habilitado" if habilitado else "deshabilitado",
        getattr(usuario, "username", "sistema"),
    )
    return metodo


@transaction.atomic
def iniciar_pago(compra_pk, *, usuario):
    """Crea el `Pago` y le pide a la pasarela el link de cobro.

    Recibe el `pk`, no un objeto ya cargado: hace su propio
    `select_for_update`, igual que `confirmar_pago_compra`/`cancelar_compra`
    en RF051 — un objeto pasado de afuera podría estar desactualizado si
    algo más cambió la compra mientras tanto.

    `usuario` es obligatorio desde RF010 (GEG9-20): antes este servicio
    cobraba la compra de cualquiera con solo pasarle el `pk`.
    """
    compra = CompraDivisa.objects.select_for_update().filter(pk=compra_pk).first()
    if compra is None:
        raise OperacionNoDisponibleParaPago("La operación no existe.")

    cliente_habilitado_para(usuario, compra.cliente_id)

    # RF035: iniciar un cobro por pasarela exige que la tarjeta esté
    # habilitada, aunque alguien fuerce el POST sin pasar por la pantalla.
    exigir_metodo_habilitado(CODIGO_TARJETA)

    compra = expirar_compra_si_corresponde(compra)
    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        raise OperacionNoDisponibleParaPago(
            "Esta operación ya no está pendiente: no se puede iniciar un pago."
        )

    monto, moneda = monto_para_pasarela(compra)
    nombre_proveedor, proveedor = _proveedor_configurado()
    order_id = f"GE-{compra.pk}-{uuid.uuid4().hex[:8]}"

    pago = Pago.objects.create(
        compra=compra,
        proveedor=nombre_proveedor,
        order_id=order_id,
        monto=monto,
        moneda=moneda,
    )

    callback_url = f"{settings.SITE_BASE_URL}{reverse('pagos:retorno', args=[pago.pk])}"
    resultado = proveedor.crear_pago(
        order_id=order_id, monto=monto, moneda=moneda, compra=compra, callback_url=callback_url
    )

    pago.id_externo = resultado["id_externo"]
    pago.redirect_url = resultado["redirect_url"]
    pago.estado = resultado["estado"]
    pago.respuesta_cruda = resultado["respuesta_cruda"]
    pago.save(update_fields=["id_externo", "redirect_url", "estado", "respuesta_cruda", "actualizado_en"])

    return pago


@transaction.atomic
def _aplicar_resultado_de_pago(pago, usuario):
    """Con `pago.estado` ya actualizado, confirma o no la compra asociada.

    Es el tramo común entre el flujo real (`confirmar_pago`, que consulta la
    pasarela) y el simulado (`resolver_pago_simulado`, que lo decide la
    persona que prueba la demo): ambos terminan acá.

    Caso borde: si el pago salió aprobado pero la compra ya no se puede
    confirmar (se canceló por cambio de cotización o por vencimiento
    mientras se esperaba el pago), se intenta reembolsar. Si el reembolso
    también falla, el `Pago` queda en `REQUIERE_REVISION` en vez de fallar
    con un error críptico.
    """
    if pago.estado != Pago.Estado.APROBADO:
        return pago

    if usuario is None:
        # El navegador volvió de la pasarela sin la cookie de sesión (puede
        # pasar en un POST entre sitios). `confirmar_pago_compra` exige un
        # usuario asociado al cliente de la compra para encontrarla — se
        # usa cualquiera de los ya asociados, no el que inició el pago en
        # particular: la operación ya se verificó como legítima contra la
        # pasarela, esto es solo para cumplir esa firma.
        asociacion = (
            AsociacionUsuarioCliente.objects.filter(cliente=pago.compra.cliente_id)
            .select_related("usuario")
            .first()
        )
        usuario = asociacion.usuario if asociacion else None

    proveedor = _instancia_proveedor(pago.proveedor)

    try:
        compra = confirmar_pago_compra(pk=pago.compra_id, usuario=usuario)
    except CompraNoConfirmable:
        compra = None

    if compra is not None and compra.estado == CompraDivisa.Estado.CONFIRMADA:
        return pago

    # El pago ya se cobró pero la compra no quedó confirmada: hay que
    # devolver el dinero, no dejarlo cobrado sin nada a cambio.
    try:
        resultado = proveedor.reembolsar(pago.id_externo, pago.monto, pago.moneda)
        pago.estado = resultado["estado"]
        pago.respuesta_cruda = {**pago.respuesta_cruda, "reembolso": resultado["respuesta_cruda"]}
    except Exception:
        logger.exception(
            "No se pudo reembolsar el pago %s; queda para revisión manual", pago.order_id
        )
        pago.estado = Pago.Estado.REQUIERE_REVISION

    pago.save(update_fields=["estado", "respuesta_cruda", "actualizado_en"])
    return pago


@transaction.atomic
def confirmar_pago(pago, *, usuario):
    """Confirma el pago real: consulta el estado en la pasarela.

    Nunca confía en los parámetros de la URL de retorno del cliente — eso es
    fácil de falsificar. Es idempotente: si el pago ya estaba resuelto
    (aprobado, rechazado, reembolsado o en revisión), no vuelve a golpear a
    la pasarela ni a confirmar la compra de nuevo.
    """
    pago = Pago.objects.select_for_update().get(pk=pago.pk)
    if pago.estado != Pago.Estado.PENDIENTE:
        return pago

    proveedor = _instancia_proveedor(pago.proveedor)
    resultado = proveedor.consultar_pago(pago.id_externo)
    pago.estado = resultado["estado"]
    pago.respuesta_cruda = resultado["respuesta_cruda"]
    pago.save(update_fields=["estado", "respuesta_cruda", "actualizado_en"])

    return _aplicar_resultado_de_pago(pago, usuario)


@transaction.atomic
def resolver_pago_simulado(pago, *, aprobar, usuario):
    """Aprueba o rechaza a mano un pago del proveedor Simulado."""
    pago = Pago.objects.select_for_update().get(pk=pago.pk)
    if pago.proveedor != "simulado" or pago.estado != Pago.Estado.PENDIENTE:
        raise OperacionNoDisponibleParaPago("Este pago ya no está pendiente.")

    pago.estado = Pago.Estado.APROBADO if aprobar else Pago.Estado.RECHAZADO
    pago.save(update_fields=["estado", "actualizado_en"])

    return _aplicar_resultado_de_pago(pago, usuario)
