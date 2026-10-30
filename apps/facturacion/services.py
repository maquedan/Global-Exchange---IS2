"""Emisión automática de facturas electrónicas (RF026 — GEG9-50).

`emitir_factura(operacion)` es la única puerta de entrada: las vistas, el
comando de reintento y el disparo automático al confirmarse una operación
pasan todos por acá.

Sobre la atomicidad: la reserva del número y la llamada a la API van en
transacciones separadas, a propósito. Si fueran una sola, el candado de
`SecuenciaFactura` quedaría tomado durante toda la llamada HTTP y ninguna
otra operación podría facturar mientras tanto. Como contrapartida, un número
reservado puede quedar sin usar un rato: por eso el reintento vuelve a usar
**la misma** `Factura` (y el mismo número) en vez de pedir uno nuevo, así la
secuencia no queda con huecos.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.conversiones.models import CompraDivisa

from .clientes.base import (
    EmisionSinConfirmar,
    FacturaRechazada,
    FacturacionNoConfigurada,
)
from .clientes.facturasegura import FacturaSeguraCliente
from .clientes.simulado import FacturaSimuladaCliente
from .de import DatosDeFacturacionIncompletos, armar_de, monto_facturable
from .models import Factura, SecuenciaFactura
from .models import HistorialEstadoFiscal

logger = logging.getLogger(__name__)

# Estados desde los que sí se puede reintentar: el documento no llegó a
# generarse del otro lado. `A_VERIFICAR` queda afuera a propósito.
ESTADOS_REINTENTABLES = (Factura.Estado.PENDIENTE, Factura.Estado.ERROR)
ESTADOS_FISCALES_FINALES = (Factura.EstadoFiscal.EMITIDA, Factura.EstadoFiscal.APROBADA)


def _instancia_cliente(nombre):
    if nombre == "facturasegura":
        return FacturaSeguraCliente()
    return FacturaSimuladaCliente()


def cliente_configurado():
    """Devuelve ``(nombre, instancia)`` del cliente de facturación en uso."""
    nombre = getattr(settings, "FACTURACION_PROVEEDOR", "simulado")
    return nombre, _instancia_cliente(nombre)


@transaction.atomic
def _reservar_factura(operacion):
    """Devuelve la `Factura` de la operación, creándola si todavía no existe.

    Toma el candado de la **operación** (no de la factura, que todavía puede
    no existir) para que dos confirmaciones simultáneas no creen dos
    facturas. La unicidad en la base es la red de contención final.
    """
    campo = "compra" if isinstance(operacion, CompraDivisa) else "venta"
    type(operacion).objects.select_for_update().get(pk=operacion.pk)

    factura = Factura.objects.filter(**{campo: operacion}).first()
    if factura is not None:
        return factura

    establecimiento = getattr(settings, "FACTURACION_ESTABLECIMIENTO", "001")
    punto_expedicion = getattr(settings, "FACTURACION_PUNTO_EXPEDICION", "001")
    monto_pyg, monto_origen, moneda_origen = monto_facturable(operacion)

    return Factura.objects.create(
        timbrado=getattr(settings, "FACTURACION_TIMBRADO", ""),
        establecimiento=establecimiento,
        punto_expedicion=punto_expedicion,
        numero=SecuenciaFactura.siguiente_numero(
            establecimiento,
            punto_expedicion,
            desde=getattr(settings, "FACTURACION_NUMERO_DESDE", 1),
        ),
        monto=monto_pyg,
        monto_origen=monto_origen,
        moneda_origen=moneda_origen,
        **{campo: operacion},
    )


def _numero_fuera_de_rango(factura):
    """Mensaje de error si el número quedó fuera del rango autorizado.

    La cátedra habilita un rango acotado de `dNumDoc` por punto de
    expedición. Si se agota, el SIFEN rechazaría el documento, así que la
    factura queda en `ERROR` sin llamar a la API.

    Cuando autoricen un rango nuevo, además de actualizar el `.env` hay que
    borrar las facturas que quedaron en este error: al reintentarlas se les
    asigna un número nuevo, dentro del rango nuevo.
    """
    hasta = getattr(settings, "FACTURACION_NUMERO_HASTA", 0)
    if not hasta or int(factura.numero) <= hasta:
        return None

    desde = getattr(settings, "FACTURACION_NUMERO_DESDE", 1)
    return (
        f"Se agotó el rango de numeración autorizado para "
        f"{factura.establecimiento}-{factura.punto_expedicion} "
        f"({desde:07d} a {hasta:07d}): el número {factura.numero} quedó afuera. "
        "Hay que pedir un rango nuevo a la cátedra."
    )


def _guardar_error(factura, estado, mensaje, *, operation_id="", respuesta=None):
    factura.estado = estado
    factura.mensaje_error = mensaje[:500]
    if operation_id:
        factura.operation_id = operation_id
    if respuesta is not None:
        factura.respuesta = respuesta
    factura.save(
        update_fields=[
            "estado",
            "mensaje_error",
            "operation_id",
            "respuesta",
            "intentos",
            "actualizada_en",
        ]
    )
    logger.warning(
        "Factura %s de la operación quedó en %s: %s",
        factura.numero_completo,
        estado,
        mensaje,
    )
    return factura


def emitir_factura(operacion):
    """Emite (o reintenta) la factura de una operación confirmada.

    Es idempotente: si la factura ya está `GENERADA` no vuelve a llamar a la
    API, y si quedó `A_VERIFICAR` tampoco — esa necesita que alguien revise a
    mano si el documento se generó o no.
    """
    factura = _reservar_factura(operacion)

    if factura.estado not in ESTADOS_REINTENTABLES:
        return factura

    # Una factura que ya tiene CDC pudo haber sido aceptada aunque la respuesta
    # original se haya perdido. Consultar antes de reenviar evita duplicados.
    if factura.cdc:
        try:
            consultar_estado_fiscal(factura)
        except Exception as error:
            return _guardar_error(factura, Factura.Estado.ERROR, f"No se pudo verificar antes de reenviar: {error}")
        factura.refresh_from_db()
        if factura.estado_fiscal in ESTADOS_FISCALES_FINALES:
            return factura

    fuera_de_rango = _numero_fuera_de_rango(factura)
    if fuera_de_rango is not None:
        return _guardar_error(factura, Factura.Estado.ERROR, fuera_de_rango)

    factura.intentos += 1

    try:
        # Instanciar el cliente real valida de entrada que estén el token y
        # los datos del emisor, antes de armar nada y sin tocar la red.
        _nombre, cliente = cliente_configurado()
        de = armar_de(operacion, factura=factura)
    except (FacturacionNoConfigurada, DatosDeFacturacionIncompletos) as error:
        return _guardar_error(factura, Factura.Estado.ERROR, str(error))

    # El DE se guarda antes de llamar: si la comunicación se corta, queda
    # registrado exactamente lo que se mandó. No contiene el token: ese va
    # solo en la cabecera de la petición.
    factura.peticion = de
    factura.save(update_fields=["peticion", "intentos", "actualizada_en"])

    try:
        de_calculado = cliente.calcular_de(de)
        resultado = cliente.generar_de(de_calculado)
    except EmisionSinConfirmar as error:
        return _guardar_error(
            factura,
            Factura.Estado.A_VERIFICAR,
            f"Se cortó la comunicación con Factura Segura; hay que verificar a "
            f"mano si el documento se generó. Detalle: {error}",
        )
    except FacturacionNoConfigurada as error:
        return _guardar_error(factura, Factura.Estado.ERROR, str(error))
    except FacturaRechazada as error:
        return _guardar_error(
            factura,
            Factura.Estado.ERROR,
            str(error),
            operation_id=error.operation_id,
            respuesta=error.respuesta,
        )

    factura.cdc = resultado["cdc"]
    factura.operation_id = resultado["operation_id"]
    factura.respuesta = resultado["respuesta"]
    factura.estado = Factura.Estado.GENERADA
    # Un reintento genera un documento nuevo: el rechazo consultado pertenece
    # al CDC anterior y no debe seguir apareciendo como estado del nuevo.
    factura.estado_fiscal = ""
    factura.motivo_rechazo = ""
    factura.mensaje_error = ""
    factura.generada_en = timezone.now()
    factura.save(
        update_fields=[
            "cdc",
            "operation_id",
            "respuesta",
            "estado",
            "estado_fiscal",
            "motivo_rechazo",
            "mensaje_error",
            "generada_en",
            "intentos",
            "actualizada_en",
        ]
    )
    logger.info(
        "Factura %s generada con CDC %s", factura.numero_completo, factura.cdc
    )
    return factura


def programar_emision(operacion):
    """Deja la emisión agendada para cuando la confirmación quede commiteada.

    Se usa `transaction.on_commit` por dos razones: no facturar una operación
    cuya confirmación termine revirtiéndose, y que un fallo de la facturación
    nunca deshaga ni bloquee esa confirmación (RNF011). De ahí el `except`
    amplio: la operación ya está confirmada y la factura queda registrada en
    `ERROR` o `A_VERIFICAR` para reintentarla con el comando
    `emitir_facturas_pendientes`.
    """

    def _emitir_sin_romper_la_operacion():
        try:
            emitir_factura(operacion)
        except Exception:
            logger.exception(
                "Falló la emisión automática de la factura de %s; la operación "
                "sigue confirmada",
                operacion,
            )

    transaction.on_commit(_emitir_sin_romper_la_operacion)


def consultar_estado_fiscal(factura):
    """Consulta SIFEN, guarda el estado y audita solo las transiciones."""
    if not factura.cdc:
        raise ValueError("La factura todavía no tiene CDC para consultar.")
    _nombre, cliente = cliente_configurado()
    resultado = cliente.consultar_estado(factura.cdc)
    estado = str(resultado.get("estado_fiscal", "")).upper()
    equivalencias = {"GENERADA": "EMITIDA", "EMITIDO": "EMITIDA", "APROBADO": "APROBADA", "RECHAZADO": "RECHAZADA"}
    estado = equivalencias.get(estado, estado)
    if estado not in Factura.EstadoFiscal.values:
        raise FacturaRechazada(f"Estado fiscal desconocido: {estado}", respuesta=resultado.get("respuesta"))

    anterior = factura.estado_fiscal
    motivo = (resultado.get("motivo") or "")[:500]
    factura.estado_fiscal = estado
    factura.motivo_rechazo = motivo if estado == Factura.EstadoFiscal.RECHAZADA else ""
    factura.estado_fiscal_consultado_en = timezone.now()
    factura.operation_id = resultado.get("operation_id") or factura.operation_id
    factura.respuesta = resultado.get("respuesta") or factura.respuesta
    factura.save(update_fields=["estado_fiscal", "motivo_rechazo", "estado_fiscal_consultado_en", "operation_id", "respuesta", "actualizada_en"])
    if anterior != estado:
        HistorialEstadoFiscal.objects.create(
            factura=factura,
            estado_anterior=anterior,
            estado_nuevo=estado,
            motivo=motivo,
            operation_id=resultado.get("operation_id", ""),
            respuesta=resultado.get("respuesta") or {},
        )
    return factura


def reintentar_factura(factura):
    """Reintenta una factura rechazada luego de consultar su estado real."""
    if factura.estado_fiscal != Factura.EstadoFiscal.RECHAZADA:
        raise ValueError("Solo se pueden reintentar facturas rechazadas por SIFEN.")
    factura.estado = Factura.Estado.PENDIENTE
    factura.save(update_fields=["estado", "actualizada_en"])
    return emitir_factura(factura.operacion)
