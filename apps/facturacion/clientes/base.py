"""Interfaz que debe cumplir cualquier cliente de facturación (RF026 — GEG9-50).

`apps.facturacion.services` solo conoce esta interfaz, nunca a Factura Segura
directamente: así se puede trabajar y hacer la demo con el cliente simulado
mientras la autorización de la API no esté lista, sin tocar la lógica de
negocio. Mismo patrón adaptador que `apps.pagos.proveedores`.
"""


class ClienteFacturacion:
    def calcular_de(self, de):
        """Pide los campos numéricos calculados según el SIFEN.

        Recibe el DE resumido y devuelve el DE completo, listo para
        `generar_de`. No genera ningún documento.
        """
        raise NotImplementedError

    def generar_de(self, de):
        """Genera y firma el documento electrónico.

        Devuelve ``{"cdc": str, "operation_id": str, "respuesta": dict}``.
        El CDC confirma la generación en Factura Segura, **no** la aprobación
        del SIFEN: eso se consulta después (RF028).
        """
        raise NotImplementedError


class FacturacionNoConfigurada(Exception):
    """Falta configuración obligatoria para emitir (token, RUC, timbrado...)."""


class FacturaRechazada(Exception):
    """Factura Segura respondió con `code` negativo: el DE no se generó.

    Reintentable: el documento no existe del otro lado, así que se puede
    volver a mandar con el mismo número una vez corregido el problema.
    """

    def __init__(self, mensaje, *, code=None, operation_id="", respuesta=None):
        super().__init__(mensaje)
        self.code = code
        self.operation_id = operation_id
        self.respuesta = respuesta or {}


class EmisionSinConfirmar(Exception):
    """Se cortó la comunicación y no sabemos si el documento se generó.

    La petición es síncrona: ante un timeout o un corte de red el servidor
    pudo haberla procesado igual, y sin el CDC no hay forma de consultarlo.
    **Nunca** se reintenta sola — la factura queda `A_VERIFICAR`.
    """
