"""Proveedor real: dLocal, en modo sandbox (RF022 — GEG9-36).

Referencia oficial usada para esto (docs.dlocal.com): firma de la petición
("Generate a signature"), creación de pago ("Integrate checkout" / Create
payment), consulta ("Retrieve a payment") y reembolsos ("Refunds").
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone as _timezone

import requests
from django.conf import settings

from .base import ProveedorPago

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 15

# Los nombres de estado de dLocal no son los nuestros (Pago.Estado). AUTHORIZED
# y VERIFIED cuentan como aprobados para nuestro flujo; CANCELLED como
# rechazado (la documentación no distingue más para lo que necesitamos acá).
_MAPA_ESTADOS = {
    "PAID": "APROBADO",
    "AUTHORIZED": "APROBADO",
    "VERIFIED": "APROBADO",
    "REJECTED": "RECHAZADO",
    "CANCELLED": "RECHAZADO",
    "PENDING": "PENDIENTE",
}

_MAPA_ESTADOS_REEMBOLSO = {
    "SUCCESS": "REEMBOLSADO",
    "PENDING": "PENDIENTE",
    "REJECTED": "RECHAZADO",
}


class DLocalNoConfigurado(Exception):
    """Faltan las credenciales de dLocal en el entorno (RF022 — GEG9-36)."""


class DLocalErrorDeRed(Exception):
    """La pasarela no respondió (timeout o caída de red)."""


def _credenciales():
    x_login = getattr(settings, "DLOCAL_X_LOGIN", "")
    x_trans_key = getattr(settings, "DLOCAL_X_TRANS_KEY", "")
    secret_key = getattr(settings, "DLOCAL_SECRET_KEY", "")
    if not (x_login and x_trans_key and secret_key):
        raise DLocalNoConfigurado(
            "Faltan las credenciales de dLocal (DLOCAL_X_LOGIN, "
            "DLOCAL_X_TRANS_KEY, DLOCAL_SECRET_KEY). Completalas en el .env "
            "o usá PAGO_PROVEEDOR=simulado mientras tanto."
        )
    return x_login, x_trans_key, secret_key


def _firmar(x_login, x_date, cuerpo, secret_key):
    """HMAC-SHA256 de x_login + x_date + cuerpo, concatenados sin separadores.

    El cuerpo tiene que ser EXACTAMENTE la misma cadena de bytes que se
    manda en la petición — por eso se serializa una sola vez y se reutiliza,
    en vez de volver a convertir el dict a JSON al armar los encabezados.
    """
    mensaje = f"{x_login}{x_date}{cuerpo}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), mensaje, hashlib.sha256).hexdigest()


def _fecha_dlocal():
    """Formato exacto que pide dLocal: ISO 8601 con milisegundos y sufijo Z
    (igual que `new Date().toISOString()` en JS) — ejemplo real de su
    documentación: ``2018-07-12T13:46:28.629Z``. Un "+0000" en vez de "Z" lo
    rechaza con "Invalid parameter, param: X-Date" (se comprobó en sandbox).
    """
    ahora = datetime.now(_timezone.utc)
    return ahora.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _encabezados(x_login, x_trans_key, secret_key, cuerpo):
    x_date = _fecha_dlocal()
    firma = _firmar(x_login, x_date, cuerpo, secret_key)
    return {
        "X-Date": x_date,
        "X-Login": x_login,
        "X-Trans-Key": x_trans_key,
        "X-Version": "2.1",
        "User-Agent": "GlobalExchange/1.0",
        "Content-Type": "application/json",
        "Authorization": f"V2-HMAC-SHA256, Signature: {firma}",
    }


class DLocalProveedor(ProveedorPago):
    def __init__(self):
        self.base_url = getattr(settings, "DLOCAL_BASE_URL", "https://sandbox.dlocal.com")

    def _post(self, ruta, cuerpo_dict):
        x_login, x_trans_key, secret_key = _credenciales()
        cuerpo = json.dumps(cuerpo_dict, separators=(",", ":"))
        encabezados = _encabezados(x_login, x_trans_key, secret_key, cuerpo)
        try:
            respuesta = requests.post(
                f"{self.base_url}{ruta}",
                data=cuerpo,
                headers=encabezados,
                timeout=TIMEOUT_SEGUNDOS,
            )
        except requests.RequestException as error:
            logger.exception("Error de red llamando a dLocal (%s)", ruta)
            raise DLocalErrorDeRed(str(error)) from error
        return respuesta.json()

    def _get(self, ruta):
        x_login, x_trans_key, secret_key = _credenciales()
        encabezados = _encabezados(x_login, x_trans_key, secret_key, "")
        try:
            respuesta = requests.get(
                f"{self.base_url}{ruta}", headers=encabezados, timeout=TIMEOUT_SEGUNDOS
            )
        except requests.RequestException as error:
            logger.exception("Error de red llamando a dLocal (%s)", ruta)
            raise DLocalErrorDeRed(str(error)) from error
        return respuesta.json()

    def crear_pago(self, *, order_id, monto, moneda, compra, callback_url):
        _credenciales()  # falla rápido y claro si faltan, antes de tocar nada más

        cliente = compra.cliente
        documento = (cliente.documento or cliente.ruc or "").strip()
        cuerpo = {
            "amount": int(monto) if moneda == "PYG" else float(monto),
            "currency": moneda,
            "country": "PY",
            "payment_method_flow": "REDIRECT",
            "payer": {
                "name": str(cliente),
                "email": cliente.email,
                "document": documento[:20],
            },
            "order_id": order_id,
            # A dónde vuelve el navegador del cliente después de pagar. Sin
            # esto, dLocal deja al cliente varado en su propia pantalla de
            # éxito/rechazo, sin forma de volver a Global Exchange —
            # comprobado probando contra el sandbox real.
            "callback_url": callback_url,
        }
        notification_url = getattr(settings, "DLOCAL_NOTIFICATION_URL", "")
        if notification_url:
            cuerpo["notification_url"] = notification_url

        datos = self._post("/payments", cuerpo)
        return {
            "id_externo": datos.get("id", ""),
            "redirect_url": datos.get("redirect_url", ""),
            "estado": _MAPA_ESTADOS.get(datos.get("status"), "PENDIENTE"),
            "respuesta_cruda": datos,
        }

    def consultar_pago(self, id_externo):
        datos = self._get(f"/payments/{id_externo}")
        return {
            "estado": _MAPA_ESTADOS.get(datos.get("status"), "PENDIENTE"),
            "respuesta_cruda": datos,
        }

    def reembolsar(self, id_externo, monto, moneda):
        cuerpo = {
            "payment_id": id_externo,
            "amount": int(monto) if moneda == "PYG" else float(monto),
            "currency": moneda,
        }
        datos = self._post("/refunds", cuerpo)
        return {
            "estado": _MAPA_ESTADOS_REEMBOLSO.get(datos.get("status"), "PENDIENTE"),
            "respuesta_cruda": datos,
        }
