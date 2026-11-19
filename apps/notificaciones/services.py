"""Avisos a los clientes: cambios de tasa (RF033) y de estado (RF034).

Las dos funciones públicas se registran con `transaction.on_commit` para
no avisar de algo que termine revirtiéndose, y ninguna de las dos puede
tumbar la operación que las disparó.
"""
import logging

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction

from .models import Notificacion

logger = logging.getLogger(__name__)


def _destinatarios(tasa):
    """Usuarios activos con rol `usuario_cliente` y al menos un cliente activo.

    Un usuario puede estar asociado a varios clientes (y por error, dos veces
    al mismo); `distinct()` evita notificarlo repetido.
    """
    User = get_user_model()
    return User.objects.filter(
        is_active=True,
        groups__name="usuario_cliente",
        asociaciones_clientes__cliente__activo=True,
    ).distinct()


def _construir_mensaje(tasa, compra_anterior, venta_anterior):
    par = f"{tasa.moneda_origen.codigo}/{tasa.moneda_destino.codigo}"
    mensaje = (
        f"La tasa {par} cambió: compra {tasa.tasa_compra}, venta {tasa.tasa_venta}."
    )
    if compra_anterior is not None and venta_anterior is not None:
        mensaje += f" Antes: compra {compra_anterior}, venta {venta_anterior}."
    return mensaje


def notificar_cambio_de_tasa(tasa, *, compra_anterior=None, venta_anterior=None):
    """Avisa a los clientes que una tasa de cambio tiene valores nuevos.

    Se registra con `transaction.on_commit` para no avisar de un cambio que
    termine revertido (por ejemplo, si el resto de la vista falla después de
    llamar a esta función). Un fallo al enviar el correo no debe impedir que
    la tasa quede guardada ni que la notificación interna exista: se captura
    la excepción y se sigue con el resto de los destinatarios.
    """

    def _avisar():
        mensaje = _construir_mensaje(tasa, compra_anterior, venta_anterior)
        for usuario in _destinatarios(tasa):
            Notificacion.objects.create(
                usuario=usuario,
                tipo=Notificacion.Tipo.CAMBIO_TASA,
                mensaje=mensaje,
                tasa=tasa,
            )
            if usuario.email:
                try:
                    send_mail(
                        "Cambio en una tasa de cambio",
                        mensaje,
                        None,
                        [usuario.email],
                    )
                except Exception:
                    logger.exception(
                        "No se pudo enviar el correo de cambio de tasa a %s",
                        usuario.email,
                    )

    transaction.on_commit(_avisar)


# ---------------------------------------------------------------------------
# Cambios de estado de una operación (RF034 — GEG9-76)
# ---------------------------------------------------------------------------

# Qué transición genera qué tipo de aviso. Un estado que no esté acá no
# notifica: así el nacimiento de la operación (PENDIENTE) no manda nada, que
# sería avisarle a alguien de algo que acaba de hacer él mismo.
TIPO_POR_ESTADO = {
    "CONFIRMADA": Notificacion.Tipo.OPERACION_CONFIRMADA,
    "CANCELADA": Notificacion.Tipo.OPERACION_CANCELADA,
    "ANULADA": Notificacion.Tipo.OPERACION_ANULADA,
}


def formatear_monto(valor, codigo_moneda):
    """Único lugar donde se formatea un importe para un aviso.

    Está separado a propósito: cuando GEG9-82 defina el formato de montos del
    proyecto, se cambia acá y vale para todos los mensajes. Hoy usa el
    formato actual, con separador de miles y sin decimales para el guaraní,
    que no los tiene.
    """
    if codigo_moneda == "PYG":
        return f"{valor:,.0f} {codigo_moneda}".replace(",", ".")
    return f"{valor:,.2f} {codigo_moneda}"


def _descripcion_operacion(operacion):
    """"Compra #12 de 100,00 USD" — qué operación es, en una línea."""
    from apps.conversiones.models import CompraDivisa

    if isinstance(operacion, CompraDivisa):
        monto = formatear_monto(operacion.total_a_pagar, operacion.moneda_pagada.codigo)
        return f"Compra #{operacion.pk} de {monto}"

    monto = formatear_monto(
        operacion.monto_entregado, operacion.moneda_entregada.codigo
    )
    return f"Venta #{operacion.pk} de {monto}"


def _usuarios_del_cliente(cliente):
    """Usuarios activos asociados a ESE cliente, y solo a ese.

    A diferencia de `_destinatarios` (RF033), que avisa a todos los clientes
    porque una tasa le interesa a cualquiera, acá el aviso es de una
    operación concreta: nadie debe enterarse de operaciones ajenas.

    Puede devolver vacío: una operación iniciada en la terminal de
    autoservicio puede ser de un cliente sin ningún usuario con cuenta. Eso
    no es un error, simplemente no hay a quién avisarle.
    """
    User = get_user_model()
    return User.objects.filter(
        is_active=True,
        asociaciones_clientes__cliente=cliente,
    ).distinct()


def _mensaje_de_cambio(operacion, estado_anterior, estado_nuevo, motivo):
    etiquetas = dict(type(operacion).Estado.choices)
    desde = etiquetas.get(estado_anterior, estado_anterior)
    hasta = etiquetas.get(estado_nuevo, estado_nuevo)

    mensaje = f"{_descripcion_operacion(operacion)}: {desde} → {hasta}."
    if motivo:
        mensaje = f"{mensaje} {motivo}"
    return mensaje[:500]


def notificar_cambio_de_estado(cambio):
    """Avisa a los usuarios del cliente que su operación cambió de estado.

    Recibe el `CambioEstado` ya creado (RF023), que es lo que ata el aviso a
    la transición concreta: la unicidad sobre (usuario, cambio_estado) hace
    que registrar dos veces el mismo cambio no genere dos avisos.

    No notifica la creación de la operación: `estado_anterior` vacío
    significa que recién se creó, y eso no es un cambio.
    """
    if not cambio.estado_anterior:
        return

    tipo = TIPO_POR_ESTADO.get(cambio.estado_nuevo)
    if tipo is None:
        return

    operacion = cambio.compra or cambio.venta
    if operacion is None:
        return

    def _avisar():
        mensaje = _mensaje_de_cambio(
            operacion, cambio.estado_anterior, cambio.estado_nuevo, cambio.motivo
        )
        for usuario in _usuarios_del_cliente(operacion.cliente):
            # get_or_create y no create: si el aviso ya existe, no se duplica.
            Notificacion.objects.get_or_create(
                usuario=usuario,
                cambio_estado=cambio,
                defaults={"tipo": tipo, "mensaje": mensaje},
            )

    transaction.on_commit(_avisar)
