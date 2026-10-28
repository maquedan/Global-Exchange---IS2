"""Cliente real de la API de Factura Segura, ambiente de pruebas (RF026 — GEG9-50).

Referencia: el documento "Protocolo de comunicación y operations del API
/misife00/v1/esi" de Factura Segura. Todas las operaciones son ``POST`` al
mismo recurso, con el cuerpo ``{"operation": ..., "params": {...}}`` y el
token en la cabecera ``Authentication-Token``.

El token se genera una vez por ambiente con usuario y contraseña
(``POST .../login?include_auth_token``, en el dominio raíz, no bajo
``/misife00``) y dura hasta que se cambie la contraseña. Acá no se pide: se
lee ya generado de ``FACTURASEGURA_TOKEN``. Nunca se escribe en logs ni se
guarda en la base junto con la petición.
"""
import logging

import requests
from django.conf import settings

from .base import (
    ClienteFacturacion,
    EmisionSinConfirmar,
    FacturaRechazada,
    FacturacionNoConfigurada,
)

logger = logging.getLogger(__name__)

# RNF001 pide que las operaciones no pasen de 5 segundos. La emisión corre en
# `transaction.on_commit`, es decir después de que la operación ya quedó
# confirmada y guardada, así que un timeout no la bloquea; igual el tiempo se
# mantiene corto para no demorar la respuesta al cliente.
TIMEOUT_SEGUNDOS = 5


# Valores de prueba que `config/settings/base.py` usa mientras no tengamos los
# datos reales del emisor. Mandarlos a la API de verdad sería emitir una
# factura con un RUC y un timbrado que no existen, así que el cliente real se
# niega antes de llamar.
VALORES_DE_PRUEBA = {
    "FACTURACION_EMISOR_RUC": "00000000",
    "FACTURACION_TIMBRADO": "00000000",
}


def _token():
    token = getattr(settings, "FACTURASEGURA_TOKEN", "")
    if not token:
        raise FacturacionNoConfigurada(
            "Falta FACTURASEGURA_TOKEN en el entorno. Completalo en el .env o "
            "usá FACTURACION_PROVEEDOR=simulado mientras tanto."
        )
    return token


def _verificar_emisor_real():
    for nombre, valor_de_prueba in VALORES_DE_PRUEBA.items():
        if getattr(settings, nombre, "") == valor_de_prueba:
            raise FacturacionNoConfigurada(
                f"{nombre} sigue con el valor de prueba ({valor_de_prueba}). "
                "Completá los datos reales del emisor en el .env antes de "
                "emitir contra Factura Segura, o usá "
                "FACTURACION_PROVEEDOR=simulado."
            )


class FacturaSeguraCliente(ClienteFacturacion):
    def __init__(self):
        self.base_url = getattr(
            settings,
            "FACTURASEGURA_BASE_URL",
            "https://apitest.facturasegura.com.py/misife00/v1/esi",
        )
        # Falla rápido y claro, antes de armar el DE y de tocar la red.
        _token()
        _verificar_emisor_real()

    def _ejecutar(self, operation, params):
        """Hace la llamada y valida la respuesta según el protocolo.

        `code` 0 o positivo es éxito; negativo es error, con el detalle en
        `description` y, si lo hubiere, en `results`.
        """
        cabeceras = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authentication-Token": _token(),
        }
        cuerpo = {"operation": operation, "params": params}

        try:
            respuesta = requests.post(
                self.base_url,
                json=cuerpo,
                headers=cabeceras,
                timeout=TIMEOUT_SEGUNDOS,
            )
        except requests.RequestException as error:
            # No se distingue timeout de corte de red a propósito: en los dos
            # casos el servidor pudo haber procesado la operación.
            logger.warning(
                "Se cortó la comunicación con Factura Segura en %s: %s",
                operation,
                error.__class__.__name__,
            )
            raise EmisionSinConfirmar(str(error)) from error

        # Se parsea aparte del POST: un cuerpo ilegible sí llegó y fue
        # respondido, así que es un rechazo, no una comunicación cortada.
        # (`JSONDecodeError` de requests hereda de `RequestException`, por eso
        # no puede quedar dentro del `try` de arriba.)
        try:
            datos = respuesta.json()
        except ValueError as error:
            logger.error(
                "Factura Segura devolvió una respuesta ilegible en %s (HTTP %s)",
                operation,
                respuesta.status_code,
            )
            raise FacturaRechazada(
                "Factura Segura devolvió una respuesta que no es JSON.",
                respuesta={"http_status": respuesta.status_code},
            ) from error

        operation_id = (datos.get("operation_info") or {}).get("id", "")
        code = datos.get("code")

        if code is None or code < 0:
            logger.error(
                "Factura Segura rechazó %s (code=%s, operation_id=%s)",
                operation,
                code,
                operation_id,
            )
            raise FacturaRechazada(
                datos.get("description") or "Factura Segura rechazó la petición.",
                code=code,
                operation_id=operation_id,
                respuesta=datos,
            )

        logger.info(
            "Factura Segura aceptó %s (operation_id=%s)", operation, operation_id
        )
        return datos

    def calcular_de(self, de):
        datos = self._ejecutar("calcular_de", {"DE": de})
        resultados = datos.get("results") or []
        if not resultados or "DE" not in resultados[0]:
            raise FacturaRechazada(
                "calcular_de no devolvió el DE calculado.",
                operation_id=(datos.get("operation_info") or {}).get("id", ""),
                respuesta=datos,
            )
        return resultados[0]["DE"]

    def generar_de(self, de):
        datos = self._ejecutar("generar_de", {"DE": de})
        resultados = datos.get("results") or []
        cdc = resultados[0].get("CDC", "") if resultados else ""
        operation_id = (datos.get("operation_info") or {}).get("id", "")

        if not cdc:
            # code era 0 pero no vino el CDC: no se puede dar por generada.
            raise FacturaRechazada(
                "generar_de respondió sin CDC.",
                operation_id=operation_id,
                respuesta=datos,
            )

        return {"cdc": cdc, "operation_id": operation_id, "respuesta": datos}
