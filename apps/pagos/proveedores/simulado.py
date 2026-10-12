"""Proveedor sin red, para demos y tests (RF022 — GEG9-36).

Nunca llama a ningún servicio externo. El pago queda PENDIENTE al crearse;
el estado real lo decide la persona que usa la demo, con los botones
Aprobar/Rechazar de la pantalla de pago (ver `apps.pagos.views` y
`apps.pagos.services.resolver_pago_simulado`). `consultar_pago` solo refleja
lo que ya quedó guardado en el `Pago`.
"""
import uuid

from .base import ProveedorPago


class SimuladoProveedor(ProveedorPago):
    def crear_pago(self, *, order_id, monto, moneda, compra, callback_url):
        return {
            "id_externo": f"SIMULADO-{uuid.uuid4().hex[:12]}",
            "redirect_url": "",
            "estado": "PENDIENTE",
            "respuesta_cruda": {"proveedor": "simulado"},
        }

    def consultar_pago(self, id_externo):
        from apps.pagos.models import Pago

        pago = Pago.objects.filter(id_externo=id_externo).first()
        estado = pago.estado if pago else "PENDIENTE"
        return {"estado": estado, "respuesta_cruda": {"proveedor": "simulado"}}

    def reembolsar(self, id_externo, monto, moneda):
        return {"estado": "REEMBOLSADO", "respuesta_cruda": {"proveedor": "simulado"}}
