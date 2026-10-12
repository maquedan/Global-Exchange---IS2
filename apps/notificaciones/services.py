"""Notificación a clientes ante cambios de tasa (RF033 — GEG9-38)."""
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
