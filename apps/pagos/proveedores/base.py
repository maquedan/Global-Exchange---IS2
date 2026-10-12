"""Interfaz que debe cumplir cualquier proveedor de pago (RF022 — GEG9-36).

`apps.pagos.services` solo conoce esta interfaz, nunca a dLocal ni al
proveedor simulado directamente: así se puede cambiar de pasarela (o sumar
una nueva) sin tocar la lógica de negocio ni las vistas. Patrón adaptador.
"""


class ProveedorPago:
    def crear_pago(self, *, order_id, monto, moneda, compra, callback_url):
        """Inicia un pago.

        `callback_url` es a dónde debe volver el navegador del cliente
        después de pagar (flujo REDIRECT) — un proveedor sin navegador
        externo de por medio (el Simulado) simplemente lo ignora.

        Devuelve ``{"id_externo": str, "redirect_url": str, "estado": str,
        "respuesta_cruda": dict}``. `estado` ya viene traducido a
        ``Pago.Estado`` (no al vocabulario propio de cada proveedor).
        """
        raise NotImplementedError

    def consultar_pago(self, id_externo):
        """Devuelve ``{"estado": str, "respuesta_cruda": dict}``."""
        raise NotImplementedError

    def reembolsar(self, id_externo, monto, moneda):
        """Devuelve ``{"estado": str, "respuesta_cruda": dict}``."""
        raise NotImplementedError
