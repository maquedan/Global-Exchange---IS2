"""Cliente simulado de facturación (RF026 — GEG9-50).

No toca la red: sirve para desarrollo, para las pruebas automáticas y para la
demo mientras la autorización de la API de Factura Segura no esté lista.

No calcula impuestos ni totales: `calcular_de` devuelve el DE tal como se lo
pasaron. Inventar los campos que calcularía el SIFEN daría una falsa
sensación de que la factura está bien armada, y acá no hay forma de
verificarlo. El CDC que devuelve `generar_de` arranca con ``99`` justamente
para que se vea de entrada que es simulado: un CDC real arranca con el tipo
de documento (``01`` para una factura).
"""
import uuid

from .base import ClienteFacturacion

PREFIJO_CDC_SIMULADO = "99"


class FacturaSimuladaCliente(ClienteFacturacion):
    def calcular_de(self, de):
        return dict(de)

    def generar_de(self, de):
        cdc = _cdc_simulado()
        return {
            "cdc": cdc,
            "operation_id": str(uuid.uuid4()),
            "respuesta": {
                "code": 0,
                "description": "OK (cliente simulado, no se llamó a Factura Segura)",
                "results": [{"CDC": cdc}],
                "simulado": True,
            },
        }


def _cdc_simulado():
    """CDC de 44 dígitos, con el prefijo que lo delata como simulado."""
    relleno = f"{uuid.uuid4().int:042d}"[-42:]
    return PREFIJO_CDC_SIMULADO + relleno
