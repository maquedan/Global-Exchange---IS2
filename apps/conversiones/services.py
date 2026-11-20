import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.cajas.models import Caja, MovimientoCaja, SaldoCaja
from apps.cajas.services import (
    MovimientoNoPermitido,
    proponer_billetes_entrega,
    registrar_movimiento,
)
from apps.clientes.models import Cliente
from apps.comisiones.models import ComisionCategoria
from apps.cuentas.models import CuentaPago
from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.services import cliente_habilitado_para

from .models import CambioEstado, CompraDivisa, VentaDivisa


logger = logging.getLogger(__name__)

DOS_DECIMALES = Decimal("0.01")

# Tiempo que un cliente tiene para confirmar el pago antes de que la operación
# pendiente se cancele sola: una cotización vieja no debería quedar disponible
# para confirmar indefinidamente (RF051 — GEG9-51).
MINUTOS_EXPIRACION_PENDIENTE = 15

def usuario_es_terminal(usuario):
    """Indica si el usuario autenticado corresponde a una terminal."""
    return bool(
        usuario
        and usuario.is_authenticated
        and usuario.groups.filter(name="terminal").exists()
    )


def _vencio_el_plazo(operacion):
    limite = operacion.creado_en + timedelta(minutes=MINUTOS_EXPIRACION_PENDIENTE)
    return timezone.now() > limite


def registrar_cambio_estado(operacion, estado_anterior, estado_nuevo, *, motivo="", usuario=None):
    """Deja constancia de una transición de estado (RF023 — GEG9-37).

    `estado_anterior` vacío significa que la operación recién se crea (todavía
    no tenía ningún estado previo). Todo cambio de `.estado` en este archivo
    debe pasar por acá, para que el historial quede completo.
    """
    campo_operacion = "compra" if isinstance(operacion, CompraDivisa) else "venta"
    cambio = CambioEstado.objects.create(
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        motivo=motivo,
        usuario=usuario,
        **{campo_operacion: operacion},
    )
    _avisar_del_cambio(cambio)
    return cambio


def _avisar_del_cambio(cambio):
    """Notifica a los usuarios del cliente que la operación cambió (RF034).

    El import va adentro porque `apps.notificaciones` importa los modelos de
    esta app: a nivel de módulo sería circular (mismo motivo que `_facturar`).

    El `except` amplio es deliberado y es lo que pide el ERS: un fallo al
    avisar **nunca** debe deshacer ni bloquear el cambio de estado. El aviso
    es un efecto secundario; la transición es el hecho.

    Quien decide a quién avisar —y si corresponde avisar— es el servicio de
    notificaciones: acá no se filtra nada, para que este punto siga siendo
    el único enganche.
    """
    from apps.notificaciones.services import notificar_cambio_de_estado

    try:
        notificar_cambio_de_estado(cambio)
    except Exception:
        logger.exception(
            "No se pudo notificar el cambio de estado %s; la operación sigue igual",
            cambio.pk,
        )


def _facturar(operacion):
    """Agenda la emisión de la factura electrónica de la operación (RF026).

    El import va acá adentro y no arriba porque `apps.facturacion` importa
    los modelos de esta app: hacerlo a nivel de módulo sería circular.

    `programar_emision` usa `transaction.on_commit`, así que la factura se
    emite recién cuando la confirmación quedó guardada, y un fallo de la
    facturación nunca revierte la operación.
    """
    from apps.facturacion.services import programar_emision

    programar_emision(operacion)


def calcular_conversion(monto, tasa, tipo_operacion):
    """Calcula el resultado de una simulacion de conversion."""
    monto = Decimal(monto)
    tasa = Decimal(tasa)

    if tipo_operacion == "compra":
        resultado = monto * tasa
    elif tipo_operacion == "venta":
        resultado = monto / tasa
    else:
        raise ValueError("El tipo de operacion no es valido.")

    return resultado.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def calcular_comision(monto, porcentaje):
    """Calcula y redondea la comisión aplicable al importe base."""
    return (Decimal(monto) * Decimal(porcentaje) / Decimal("100")).quantize(
        DOS_DECIMALES,
        rounding=ROUND_HALF_UP,
    )


class CompraNoDisponible(Exception):
    """La compra no puede iniciarse con la configuración vigente."""


class CompraNoConfirmable(Exception):
    """La compra pendiente no puede confirmarse ni cancelarse por acción del cliente."""


@transaction.atomic
def iniciar_compra(*, usuario, cliente_id, moneda_pagada, moneda_adquirida, monto_pagado, desde_terminal=False):
    """Congela la tasa y comisión vigentes y deja la compra en estado PENDIENTE.

    El monto ingresado es la base de conversión. La comisión se cobra aparte y
    forma parte del total a pagar. La operación recién queda CONFIRMADA cuando
    el cliente confirma el pago en `confirmar_pago_compra` (RF051).

    `usuario` es obligatorio desde RF010 (GEG9-20): el servicio comprueba por
    su cuenta que esa persona pueda operar en nombre del cliente, en vez de
    confiar en que la vista ya lo verificó.
    """
    if desde_terminal:
        if not usuario_es_terminal(usuario):
            raise CompraNoDisponible(
                "Solo una terminal autorizada puede iniciar esta operación."
            )
    else:
        cliente_habilitado_para(usuario, cliente_id)


    cliente = Cliente.objects.select_for_update().filter(pk=cliente_id, activo=True).first()
    if cliente is None:
        raise CompraNoDisponible("El cliente ya no está habilitado para operar.")

    tasa = (
        TasaCambio.objects.select_for_update()
        .filter(
            moneda_origen=moneda_pagada,
            moneda_destino=moneda_adquirida,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )
    if tasa is None:
        raise CompraNoDisponible("No existe una tasa vigente para el par seleccionado.")

    comision = (
        ComisionCategoria.objects.select_for_update()
        .filter(categoria=cliente.categoria)
        .first()
    )
    if comision is None:
        raise CompraNoDisponible(
            "No existe una comisión configurada para la categoría del cliente."
        )

    monto_pagado = Decimal(monto_pagado).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
    monto_comision = calcular_comision(monto_pagado, comision.porcentaje)
    total_a_pagar = monto_pagado + monto_comision
    monto_recibido = calcular_conversion(monto_pagado, tasa.tasa_compra, "compra")

    compra = CompraDivisa.objects.create(
        cliente=cliente,
        moneda_pagada=moneda_pagada,
        moneda_adquirida=moneda_adquirida,
        tasa_cambio=tasa,
        monto_pagado=monto_pagado,
        porcentaje_comision=comision.porcentaje,
        monto_comision=monto_comision,
        total_a_pagar=total_a_pagar,
        tasa_aplicada=tasa.tasa_compra,
        monto_recibido=monto_recibido,
    )
    registrar_cambio_estado(compra, "", compra.estado)
    return compra


@transaction.atomic
def expirar_compra_si_corresponde(compra):
    """Cancela una compra pendiente si superó el tiempo límite para confirmar.

    Se llama tanto al mostrarla como al intentar confirmarla o cancelarla, para
    que una cotización vieja nunca quede disponible para pagar (RF051).

    Excepción: si el cliente eligió pagar por transferencia bancaria, la
    compra **no se vence** (RF025 — GEG9-75). Verificar una transferencia
    lleva horas o días, y con los 15 minutos de siempre la operación se
    cancelaría antes de que el administrador llegara a conciliarla. La
    protección de RF051 no se pierde: al conciliar se revalida la tasa, y si
    cambió la operación se cancela igual.
    """
    if compra.espera_transferencia:
        return compra

    if compra.estado == CompraDivisa.Estado.PENDIENTE and _vencio_el_plazo(compra):
        estado_anterior = compra.estado
        compra.estado = CompraDivisa.Estado.CANCELADA
        compra.motivo_cancelacion = CompraDivisa.MotivoCancelacion.EXPIRADA
        compra.cancelado_en = timezone.now()
        compra.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
        registrar_cambio_estado(
            compra, estado_anterior, compra.estado,
            motivo="Se venció el tiempo para confirmar.",
        )
    return compra


@transaction.atomic
def confirmar_pago_compra(*, pk, usuario):
    """Confirma el pago de una compra pendiente, si la cotización no cambió.

    Si la tasa activa para el par ya no es la que se congeló al iniciar la
    compra, la operación se cancela sola: el cliente no debe pagar una tasa
    distinta a la que aceptó (RF051 — GEG9-51).
    """
    compra = (
        CompraDivisa.objects.select_for_update()
        # cliente__activo: si al cliente lo dieron de baja (RF003) con la
        # operación pendiente, tampoco se puede confirmar ni cancelar
        # (RF010 — GEG9-20).
        .filter(
            pk=pk,
            cliente__asociaciones_usuarios__usuario=usuario,
            cliente__activo=True,
        )
        .first()
    )
    if compra is None:
        raise CompraNoConfirmable("La operación no existe o no te pertenece.")
    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        raise CompraNoConfirmable("Esta operación ya fue confirmada o cancelada.")

    return _confirmar_compra_pendiente(compra, usuario=usuario)


@transaction.atomic
def confirmar_pago_compra_efectivo(*, pk, usuario, billetes_recibidos):
    """Confirma una compra cobrando efectivo por denominación (RF057).

    El cajero recibe el efectivo exacto de la compra. El ingreso queda
    registrado en su fondo, con detalle de billetes, y la compra se confirma
    únicamente si la cotización congelada sigue vigente.
    """
    if (
        not usuario
        or not usuario.is_authenticated
        or not usuario.groups.filter(name="cajero").exists()
    ):
        raise CompraNoConfirmable(
            "Solo un cajero puede recibir efectivo de una compra."
        )

    compra = (
        CompraDivisa.objects.select_for_update()
        .filter(
            pk=pk,
            cliente__activo=True,
        )
        .first()
    )

    if compra is None:
        raise CompraNoConfirmable("La compra no existe o el cliente está inactivo.")

    if compra.espera_transferencia:
        raise CompraNoDisponible(
            "Esta compra espera la conciliación de una transferencia y no puede "
            "cobrarse en efectivo."
        )

    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        raise CompraNoConfirmable(
            "Esta compra ya fue confirmada o cancelada."
        )

    compra = expirar_compra_si_corresponde(compra)

    if compra.estado == CompraDivisa.Estado.CANCELADA:
        return compra

    tasa_vigente = (
        TasaCambio.objects.filter(
            moneda_origen=compra.moneda_pagada,
            moneda_destino=compra.moneda_adquirida,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )

    if tasa_vigente is None or tasa_vigente.pk != compra.tasa_cambio_id:
        estado_anterior = compra.estado
        compra.estado = CompraDivisa.Estado.CANCELADA
        compra.motivo_cancelacion = CompraDivisa.MotivoCancelacion.CAMBIO_COTIZACION
        compra.cancelado_en = timezone.now()
        compra.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])

        registrar_cambio_estado(
            compra,
            estado_anterior,
            compra.estado,
            motivo="La cotización cambió antes de recibir el efectivo.",
            usuario=usuario,
        )
        return compra

    caja = (
        Caja.objects.select_for_update()
        .filter(sucursal__activa=True)
        .select_related("sucursal")
        .first()
    )

    if caja is None:
        raise CompraNoDisponible(
            "No hay una caja activa configurada para recibir el efectivo."
        )

    try:
        movimiento = registrar_movimiento(
            caja_id=caja.pk,
            tipo=MovimientoCaja.Tipo.INGRESO_CAJERO,
            moneda_id=compra.moneda_pagada_id,
            realizado_por=usuario,
            cajero_id=usuario.pk,
            nota=f"Efectivo recibido del cliente por compra #{compra.pk}",
            billetes=billetes_recibidos,
        )
    except MovimientoNoPermitido as error:
        raise CompraNoDisponible(str(error)) from error

    if movimiento.importe != compra.total_a_pagar:
        raise CompraNoDisponible(
            "El desglose recibido debe sumar exactamente "
            f"{compra.total_a_pagar:.2f} {compra.moneda_pagada.codigo}."
        )

    estado_anterior = compra.estado
    compra.estado = CompraDivisa.Estado.CONFIRMADA
    compra.confirmado_en = timezone.now()
    compra.movimiento_efectivo_recibido = movimiento
    compra.save(
        update_fields=[
            "estado",
            "confirmado_en",
            "movimiento_efectivo_recibido",
        ]
    )

    registrar_cambio_estado(
        compra,
        estado_anterior,
        compra.estado,
        usuario=usuario,
    )
    _facturar(compra)

    return compra


def _confirmar_compra_pendiente(compra, *, usuario, motivo=""):
    """Núcleo de la confirmación de una compra pendiente.

    Lo comparten las dos puertas de entrada, que solo se diferencian en el
    control de acceso: `confirmar_pago_compra` (el dueño, tras pagar) y
    `conciliar_compra` (un administrador que verificó una transferencia,
    RF025 — GEG9-75). Así la revalidación de tasa de RF051, la trazabilidad
    de RF023 y la facturación de RF026 son exactamente las mismas por los
    dos caminos, sin duplicar nada.

    `motivo` queda en el historial de estados: vacío en el pago normal, y con
    la referencia de la transferencia en la conciliación.
    """
    compra = expirar_compra_si_corresponde(compra)
    if compra.estado == CompraDivisa.Estado.CANCELADA:
        return compra

    tasa_vigente = (
        TasaCambio.objects.filter(
            moneda_origen=compra.moneda_pagada,
            moneda_destino=compra.moneda_adquirida,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )

    if tasa_vigente is None or tasa_vigente.pk != compra.tasa_cambio_id:
        estado_anterior = compra.estado
        compra.estado = CompraDivisa.Estado.CANCELADA
        compra.motivo_cancelacion = CompraDivisa.MotivoCancelacion.CAMBIO_COTIZACION
        compra.cancelado_en = timezone.now()
        compra.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
        registrar_cambio_estado(
            compra, estado_anterior, compra.estado,
            motivo="La cotización cambió antes de confirmar.", usuario=usuario,
        )
        return compra

    estado_anterior = compra.estado
    compra.estado = CompraDivisa.Estado.CONFIRMADA
    compra.confirmado_en = timezone.now()
    compra.save(update_fields=["estado", "confirmado_en"])
    registrar_cambio_estado(
        compra, estado_anterior, compra.estado, motivo=motivo, usuario=usuario
    )
    _facturar(compra)
    return compra


class ConciliacionNoPermitida(Exception):
    """La compra no se puede conciliar manualmente (RF025 — GEG9-75)."""


# Lo que se guarda en `Pago.proveedor` cuando el cobro no pasó por ninguna
# pasarela, sino por una transferencia que un administrador verificó a mano.
PROVEEDOR_MANUAL = "manual"

LARGO_MAXIMO_REFERENCIA = 100


def compras_pendientes_de_conciliar():
    """Compras que un administrador puede conciliar (RF025 — GEG9-75).

    Son las que siguen pendientes y el cliente marcó para pagar por
    transferencia. Las que esperan la pasarela no entran: esas las resuelve
    dLocal, no una verificación manual.
    """
    return (
        CompraDivisa.objects.filter(
            estado=CompraDivisa.Estado.PENDIENTE,
            espera_transferencia=True,
        )
        .select_related("cliente", "moneda_pagada", "moneda_adquirida")
        .order_by("creado_en")
    )


@transaction.atomic
def conciliar_compra(*, pk, usuario, referencia, observacion=""):
    """Marca como pagada una compra tras verificar una transferencia (RF025).

    Es la contraparte administrativa de `confirmar_pago_compra`: cambia el
    control de acceso —acá el rol `administrador`, no el dueño de la
    operación— pero la confirmación en sí pasa por el mismo núcleo, así que
    se revalida la tasa (RF051), se registra el cambio de estado (RF023) y
    se emite la factura (RF026) exactamente igual que en un pago normal.

    Es idempotente: una compra que ya no está pendiente se rechaza con un
    mensaje claro, sin tocar nada.

    Devuelve la compra. Si la cotización cambió, viene **CANCELADA** y sin
    pago registrado: hay que mirarle el estado, no alcanza con que no haya
    excepción.
    """
    if (
        not usuario
        or not usuario.is_authenticated
        or not usuario.groups.filter(name="administrador").exists()
    ):
        raise ConciliacionNoPermitida(
            "Solo un administrador puede conciliar una transferencia."
        )

    referencia = (referencia or "").strip()
    if not referencia:
        raise ConciliacionNoPermitida(
            "Indicá la referencia de la transferencia bancaria."
        )
    if len(referencia) > LARGO_MAXIMO_REFERENCIA:
        raise ConciliacionNoPermitida(
            f"La referencia no puede superar los {LARGO_MAXIMO_REFERENCIA} caracteres."
        )
    observacion = (observacion or "").strip()

    # Sin filtro de dueño: el administrador no está asociado al cliente.
    compra = CompraDivisa.objects.select_for_update().filter(pk=pk).first()
    if compra is None:
        raise ConciliacionNoPermitida("La operación no existe.")
    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        raise ConciliacionNoPermitida(
            f"Esta operación ya no está pendiente (está {compra.get_estado_display()}): "
            "no se puede conciliar."
        )

    motivo = f"Conciliación manual. Referencia: {referencia}."
    if observacion:
        motivo = f"{motivo} {observacion}"

    compra = _confirmar_compra_pendiente(compra, usuario=usuario, motivo=motivo[:255])

    if compra.estado != CompraDivisa.Estado.CONFIRMADA:
        # La revalidación de RF051 la canceló: la cotización ya no es la que
        # el cliente aceptó. No se registra ningún pago, y se **devuelve** la
        # compra en vez de lanzar: lanzar revertiría la cancelación, porque
        # todo esto corre dentro de una transacción. Quien llama mira el
        # estado para avisarle al administrador.
        return compra

    _registrar_pago_manual(compra, usuario=usuario, referencia=referencia,
                           observacion=observacion)
    return compra


def _registrar_pago_manual(compra, *, usuario, referencia, observacion):
    """Deja el cobro asentado como un `Pago` más, con proveedor "manual".

    El import va adentro porque `apps.pagos` importa esta app: a nivel de
    módulo sería circular (mismo motivo que `_facturar`).

    Se registra el importe tal como lo transfirió el cliente —el total en la
    moneda de la operación—, no el convertido para la pasarela: acá no hubo
    pasarela. Así el comprobante muestra la conciliación en el mismo bloque
    de "Pago" que un cobro con tarjeta, sin tocar ninguna plantilla.
    """
    import uuid

    from apps.pagos.models import Pago

    return Pago.objects.create(
        compra=compra,
        proveedor=PROVEEDOR_MANUAL,
        order_id=f"MAN-{compra.pk}-{uuid.uuid4().hex[:8]}",
        id_externo=referencia,
        monto=compra.total_a_pagar,
        moneda=compra.moneda_pagada.codigo,
        estado=Pago.Estado.APROBADO,
        respuesta_cruda={
            "conciliacion_manual": True,
            "referencia": referencia,
            "observacion": observacion,
            "conciliado_por": usuario.get_username(),
        },
    )


@transaction.atomic
def cancelar_compra(*, pk, usuario):
    """Cancela una compra pendiente por decisión del cliente."""
    compra = (
        CompraDivisa.objects.select_for_update()
        # cliente__activo: si al cliente lo dieron de baja (RF003) con la
        # operación pendiente, tampoco se puede confirmar ni cancelar
        # (RF010 — GEG9-20).
        .filter(
            pk=pk,
            cliente__asociaciones_usuarios__usuario=usuario,
            cliente__activo=True,
        )
        .first()
    )
    if compra is None:
        raise CompraNoConfirmable("La operación no existe o no te pertenece.")
    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        raise CompraNoConfirmable("Esta operación ya no se puede cancelar.")

    compra = expirar_compra_si_corresponde(compra)
    if compra.estado == CompraDivisa.Estado.CANCELADA:
        return compra

    estado_anterior = compra.estado
    compra.estado = CompraDivisa.Estado.CANCELADA
    compra.motivo_cancelacion = CompraDivisa.MotivoCancelacion.CLIENTE
    compra.cancelado_en = timezone.now()
    compra.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
    registrar_cambio_estado(
        compra, estado_anterior, compra.estado,
        motivo="Cancelada por el cliente.", usuario=usuario,
    )
    return compra


class AnulacionCompraNoPermitida(Exception):
    """La compra confirmada no se puede anular de forma segura."""


@transaction.atomic
def anular_compra(
    *, pk, usuario, motivo, confirmar_reembolso_manual=False
):
    """Anula una compra pagada tras confirmar su reembolso.

    Los pagos de pasarela se reembolsan con el proveedor que los procesó. Las
    transferencias conciliadas y las compras sin un Pago asociado requieren
    confirmación administrativa de que la devolución manual ya se realizó.
    """
    if (
        not usuario
        or not usuario.is_authenticated
        or not usuario.groups.filter(name="administrador").exists()
    ):
        raise AnulacionCompraNoPermitida(
            "Solo un administrador puede anular una compra confirmada."
        )

    motivo = (motivo or "").strip()
    if not motivo or len(motivo) > 255:
        raise AnulacionCompraNoPermitida(
            "Indicá un motivo de anulación de hasta 255 caracteres."
        )

    compra = CompraDivisa.objects.select_for_update().filter(pk=pk).first()
    if compra is None:
        raise AnulacionCompraNoPermitida("La compra no existe.")
    if compra.estado != CompraDivisa.Estado.CONFIRMADA:
        raise AnulacionCompraNoPermitida(
            "Solo se pueden anular compras que ya fueron confirmadas."
        )

    from apps.pagos.models import Pago

    pagos = list(
        Pago.objects.select_for_update()
        .filter(compra=compra)
        .order_by("-creado_en", "-pk")
    )
    pago_reembolsado = next(
        (pago for pago in pagos if pago.estado == Pago.Estado.REEMBOLSADO),
        None,
    )
    pago_en_revision = next(
        (
            pago
            for pago in pagos
            if pago.estado == Pago.Estado.REQUIERE_REVISION
            and "reembolso_anulacion" in pago.respuesta_cruda
        ),
        None,
    )
    pago_aprobado = next(
        (pago for pago in pagos if pago.estado == Pago.Estado.APROBADO),
        None,
    )
    if any(pago.estado == Pago.Estado.PENDIENTE for pago in pagos):
        raise AnulacionCompraNoPermitida(
            "La compra tiene un pago pendiente de resolución y no se puede "
            "anular todavía."
        )

    ahora = timezone.now()
    detalle_reembolso = None
    if pago_en_revision is not None:
        if not confirmar_reembolso_manual:
            raise AnulacionCompraNoPermitida(
                "El reembolso requiere revisión. Verificá la devolución con el "
                "proveedor antes de confirmarla manualmente."
            )
        pago_en_revision.estado = Pago.Estado.REEMBOLSADO
        detalle_reembolso = dict(
            pago_en_revision.respuesta_cruda["reembolso_anulacion"]
        )
        detalle_reembolso["resolucion_manual"] = {
            "estado": "REEMBOLSADO",
            "resuelto_por": usuario.get_username(),
            "resuelto_en": ahora.isoformat(),
            "motivo": motivo,
        }
        pago_en_revision.respuesta_cruda = {
            **pago_en_revision.respuesta_cruda,
            "reembolso_anulacion": detalle_reembolso,
        }
        pago_en_revision.save(
            update_fields=["estado", "respuesta_cruda", "actualizado_en"]
        )
    elif pago_reembolsado is not None:
        detalle_reembolso = pago_reembolsado.respuesta_cruda.get(
            "reembolso_anulacion"
        )
    elif pago_aprobado is not None and pago_aprobado.proveedor == "manual":
        if not confirmar_reembolso_manual:
            raise AnulacionCompraNoPermitida(
                "Confirmá que la transferencia ya fue devuelta antes de anular "
                "la compra."
            )
        pago_aprobado.estado = Pago.Estado.REEMBOLSADO
        detalle_reembolso = {
            "estado": "REEMBOLSADO",
            "proveedor": "manual",
            "confirmado_por": usuario.get_username(),
            "confirmado_en": ahora.isoformat(),
            "motivo": motivo,
        }
        pago_aprobado.respuesta_cruda = {
            **pago_aprobado.respuesta_cruda,
            "reembolso_anulacion": detalle_reembolso,
        }
        pago_aprobado.save(
            update_fields=["estado", "respuesta_cruda", "actualizado_en"]
        )
    elif pago_aprobado is not None:
        from apps.pagos.services import (
            ReembolsoPagoNoDisponible,
            solicitar_reembolso_pago,
        )

        try:
            resultado = solicitar_reembolso_pago(pago_aprobado)
        except ReembolsoPagoNoDisponible as error:
            raise AnulacionCompraNoPermitida(str(error)) from error

        detalle_reembolso = {
            "estado": resultado["estado"],
            "solicitado_por": usuario.get_username(),
            "solicitado_en": ahora.isoformat(),
            "motivo": motivo,
            "respuesta": resultado["respuesta_cruda"],
        }
        pago_aprobado.respuesta_cruda = {
            **pago_aprobado.respuesta_cruda,
            "reembolso_anulacion": detalle_reembolso,
        }
        if resultado["estado"] == Pago.Estado.REEMBOLSADO:
            pago_aprobado.estado = Pago.Estado.REEMBOLSADO
        else:
            pago_aprobado.estado = Pago.Estado.REQUIERE_REVISION
        pago_aprobado.save(
            update_fields=["estado", "respuesta_cruda", "actualizado_en"]
        )
        if resultado["estado"] != Pago.Estado.REEMBOLSADO:
            return compra, False
    else:
        pagos_pendientes = any(
            pago.estado
            in (Pago.Estado.PENDIENTE, Pago.Estado.REQUIERE_REVISION)
            for pago in pagos
        )
        if pagos_pendientes:
            raise AnulacionCompraNoPermitida(
                "La compra tiene un pago pendiente de resolución y no se puede "
                "anular todavía."
            )
        if not confirmar_reembolso_manual:
            raise AnulacionCompraNoPermitida(
                "No hay un pago registrado para esta compra. Confirmá que la "
                "devolución manual ya fue realizada antes de anularla."
            )

    if compra.movimiento_efectivo_recibido_id:
        movimiento = (
            MovimientoCaja.objects.select_for_update()
            .filter(pk=compra.movimiento_efectivo_recibido_id)
            .prefetch_related("detalle_billetes")
            .first()
        )
        if movimiento is None:
            raise AnulacionCompraNoPermitida(
                "No se encuentra el movimiento de efectivo de la compra."
            )
        if movimiento.tipo != MovimientoCaja.Tipo.INGRESO_CAJERO:
            raise AnulacionCompraNoPermitida(
                "El movimiento de efectivo de la compra no es un ingreso "
                "válido para revertir."
            )

        billetes = dict(
            movimiento.detalle_billetes.values_list(
                "denominacion_id", "cantidad"
            )
        )
        if not billetes:
            raise AnulacionCompraNoPermitida(
                "Falta el desglose de billetes del efectivo recibido."
            )

        try:
            registrar_movimiento(
                caja_id=movimiento.caja_id,
                tipo=MovimientoCaja.Tipo.RETIRO_CAJERO,
                moneda_id=movimiento.moneda_id,
                realizado_por=usuario,
                cajero_id=movimiento.cajero_id,
                nota=(
                    f"Anulación de compra #{compra.pk}; reversión del "
                    f"movimiento #{movimiento.pk}: {motivo}"
                ),
                billetes=billetes,
                reversion_de=movimiento,
            )
        except MovimientoNoPermitido as error:
            raise AnulacionCompraNoPermitida(
                f"No se puede completar la reversión de efectivo: {error}"
            ) from error

    estado_anterior = compra.estado
    compra.estado = CompraDivisa.Estado.ANULADA
    compra.anulado_en = ahora
    compra.save(update_fields=["estado", "anulado_en"])
    registrar_cambio_estado(
        compra,
        estado_anterior,
        compra.estado,
        motivo=motivo,
        usuario=usuario,
    )
    return compra, True


class VentaNoDisponible(Exception):
    """La venta no puede iniciarse con la configuración vigente."""


class VentaNoConfirmable(Exception):
    """La venta pendiente no puede confirmarse ni cancelarse por acción del cliente."""


class AnulacionVentaNoPermitida(Exception):
    """La venta confirmada no puede anularse de forma segura."""


@transaction.atomic
def iniciar_venta(
    *, usuario, cliente_id, moneda_entregada, moneda_acreditada,
    monto_entregado, cuenta_destino=None, desde_terminal=False
):
    """Congela la tasa y comisión y deja la venta PENDIENTE de entrega en efectivo.

    `usuario` es obligatorio desde RF010 (GEG9-20), igual que en
    `iniciar_compra`.
    """
    if desde_terminal:
        if not usuario_es_terminal(usuario):
            raise VentaNoDisponible(
                "Solo una terminal autorizada puede iniciar esta operación."
            )
    else:
        cliente_habilitado_para(usuario, cliente_id)

    cliente = Cliente.objects.select_for_update().filter(pk=cliente_id, activo=True).first()
    if cliente is None:
        raise VentaNoDisponible("El cliente ya no está habilitado para operar.")
    if moneda_entregada == moneda_acreditada:
        raise VentaNoDisponible("Las monedas deben ser diferentes.")

    cuenta = None
    if cuenta_destino is not None:
        cuenta = (
            CuentaPago.objects.select_for_update()
            .filter(pk=cuenta_destino.pk, cliente=cliente, activa=True)
            .first()
        )
        if cuenta is None:
            raise VentaNoDisponible(
                "La cuenta de destino no está activa o no pertenece al cliente."
            )

    tasa = (
        TasaCambio.objects.select_for_update()
        .filter(
            moneda_origen=moneda_entregada,
            moneda_destino=moneda_acreditada,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )
    if tasa is None:
        raise VentaNoDisponible("No existe una tasa vigente para el par seleccionado.")

    comision = (
        ComisionCategoria.objects.select_for_update()
        .filter(categoria=cliente.categoria)
        .first()
    )
    if comision is None:
        raise VentaNoDisponible(
            "No existe una comisión configurada para la categoría del cliente."
        )

    monto_entregado = Decimal(monto_entregado).quantize(
        DOS_DECIMALES, rounding=ROUND_HALF_UP
    )
    monto_convertido = calcular_conversion(monto_entregado, tasa.tasa_compra, "compra")
    monto_comision = calcular_comision(monto_convertido, comision.porcentaje)

    venta = VentaDivisa.objects.create(
        cliente=cliente,
        moneda_entregada=moneda_entregada,
        moneda_acreditada=moneda_acreditada,
        tasa_cambio=tasa,
        cuenta_destino=cuenta,
        monto_entregado=monto_entregado,
        porcentaje_comision=comision.porcentaje,
        monto_comision=monto_comision,
        monto_convertido=monto_convertido,
        monto_acreditado=monto_convertido - monto_comision,
        tasa_aplicada=tasa.tasa_compra,
    )
    registrar_cambio_estado(venta, "", venta.estado)
    return venta


@transaction.atomic
def expirar_venta_si_corresponde(venta):
    """Cancela una venta pendiente si superó el tiempo límite para confirmar."""
    if venta.estado == VentaDivisa.Estado.PENDIENTE and _vencio_el_plazo(venta):
        estado_anterior = venta.estado
        venta.estado = VentaDivisa.Estado.CANCELADA
        venta.motivo_cancelacion = VentaDivisa.MotivoCancelacion.EXPIRADA
        venta.cancelado_en = timezone.now()
        venta.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
        registrar_cambio_estado(
            venta, estado_anterior, venta.estado,
            motivo="Se venció el tiempo para confirmar.",
        )
    return venta


@transaction.atomic
def confirmar_pago_venta(
    *, pk, usuario, billetes_recibidos, billetes_entregados
):
    """Confirma una venta pendiente y entrega el neto en efectivo (RF058).

    Misma protección que `confirmar_pago_compra`: si la tasa activa para el
    par ya cambió respecto a la congelada al iniciar la venta, se cancela sola
    en vez de entregar un importe calculado con una tasa distinta (RF051).
    La divisa del cliente ingresa y el efectivo entregado sale del fondo del
    cajero, con ambos movimientos vinculados a la venta en la misma transacción.
    """
    if not usuario or not usuario.is_authenticated or not usuario.groups.filter(
        name="cajero"
    ).exists():
        raise VentaNoConfirmable("Solo un cajero puede entregar efectivo de una venta.")

    venta = (
        VentaDivisa.objects.select_for_update()
        .filter(
            pk=pk,
            cliente__activo=True,
        )
        .first()
    )
    if venta is None:
        raise VentaNoConfirmable("La operación no existe o no te pertenece.")
    if venta.estado != VentaDivisa.Estado.PENDIENTE:
        raise VentaNoConfirmable("Esta operación ya fue confirmada o cancelada.")

    venta = expirar_venta_si_corresponde(venta)
    if venta.estado == VentaDivisa.Estado.CANCELADA:
        return venta

    tasa_vigente = (
        TasaCambio.objects.filter(
            moneda_origen=venta.moneda_entregada,
            moneda_destino=venta.moneda_acreditada,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )

    if tasa_vigente is None or tasa_vigente.pk != venta.tasa_cambio_id:
        estado_anterior = venta.estado
        venta.estado = VentaDivisa.Estado.CANCELADA
        venta.motivo_cancelacion = VentaDivisa.MotivoCancelacion.CAMBIO_COTIZACION
        venta.cancelado_en = timezone.now()
        venta.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
        registrar_cambio_estado(
            venta, estado_anterior, venta.estado,
            motivo="La cotización cambió antes de confirmar.", usuario=usuario,
        )
        return venta

    caja = (
        Caja.objects.select_for_update()
        .filter(sucursal__activa=True)
        .select_related("sucursal")
        .first()
    )
    if caja is None:
        raise VentaNoDisponible("No hay una caja activa configurada para la entrega.")

    propuesta = proponer_billetes_entrega(
        caja=caja,
        moneda=venta.moneda_acreditada,
        importe=venta.monto_acreditado,
        cajero=usuario,
    )
    importe_minimo = propuesta["importe_entrega"]
    if importe_minimo is None:
        raise VentaNoDisponible(
            f"Faltan {propuesta['faltante']:.2f} {venta.moneda_acreditada.codigo} "
            "en el fondo del cajero para cubrir la entrega."
        )

    try:
        movimiento_recibido = registrar_movimiento(
            caja_id=caja.pk,
            tipo=MovimientoCaja.Tipo.INGRESO_CAJERO,
            moneda_id=venta.moneda_entregada_id,
            realizado_por=usuario,
            cajero_id=usuario.pk,
            nota=f"Divisa recibida del cliente por venta #{venta.pk}",
            billetes=billetes_recibidos,
        )
        movimiento_entregado = registrar_movimiento(
            caja_id=caja.pk,
            tipo=MovimientoCaja.Tipo.RETIRO_CAJERO,
            moneda_id=venta.moneda_acreditada_id,
            realizado_por=usuario,
            cajero_id=usuario.pk,
            nota=f"Efectivo entregado al cliente por venta #{venta.pk}",
            billetes=billetes_entregados,
        )
    except MovimientoNoPermitido as error:
        raise VentaNoDisponible(str(error)) from error

    if movimiento_recibido.importe != venta.monto_entregado:
        raise VentaNoDisponible(
            f"El desglose recibido debe sumar exactamente "
            f"{venta.monto_entregado:.2f} {venta.moneda_entregada.codigo}."
        )
    if movimiento_entregado.importe != importe_minimo:
        raise VentaNoDisponible(
            f"El desglose debe sumar el importe mínimo posible de "
            f"{importe_minimo:.2f} {venta.moneda_acreditada.codigo}."
        )

    estado_anterior = venta.estado
    venta.estado = VentaDivisa.Estado.CONFIRMADA
    venta.confirmado_en = timezone.now()
    venta.monto_efectivo_entregado = movimiento_entregado.importe
    venta.movimiento_efectivo_recibido = movimiento_recibido
    venta.movimiento_efectivo_entregado = movimiento_entregado
    venta.save(
        update_fields=[
            "estado",
            "confirmado_en",
            "monto_efectivo_entregado",
            "movimiento_efectivo_recibido",
            "movimiento_efectivo_entregado",
        ]
    )
    registrar_cambio_estado(venta, estado_anterior, venta.estado, usuario=usuario)
    _facturar(venta)
    return venta


@transaction.atomic
def cancelar_venta(*, pk, usuario):
    """Cancela una venta pendiente por decisión del cliente."""
    venta = (
        VentaDivisa.objects.select_for_update()
        # Ver el comentario en confirmar_pago_compra (RF010 — GEG9-20).
        .filter(
            pk=pk,
            cliente__asociaciones_usuarios__usuario=usuario,
            cliente__activo=True,
        )
        .first()
    )
    if venta is None:
        raise VentaNoConfirmable("La operación no existe o no te pertenece.")
    if venta.estado != VentaDivisa.Estado.PENDIENTE:
        raise VentaNoConfirmable("Esta operación ya no se puede cancelar.")

    venta = expirar_venta_si_corresponde(venta)
    if venta.estado == VentaDivisa.Estado.CANCELADA:
        return venta

    estado_anterior = venta.estado
    venta.estado = VentaDivisa.Estado.CANCELADA
    venta.motivo_cancelacion = VentaDivisa.MotivoCancelacion.CLIENTE
    venta.cancelado_en = timezone.now()
    venta.save(update_fields=["estado", "motivo_cancelacion", "cancelado_en"])
    registrar_cambio_estado(
        venta, estado_anterior, venta.estado,
        motivo="Cancelada por el cliente.", usuario=usuario,
    )
    return venta


@transaction.atomic
def anular_venta(*, pk, usuario, motivo):
    """Anula una venta confirmada y registra los movimientos inversos (RF059)."""
    if (
        not usuario
        or not usuario.is_authenticated
        or not usuario.groups.filter(name="administrador").exists()
    ):
        raise AnulacionVentaNoPermitida(
            "Solo un administrador puede anular una venta confirmada."
        )

    motivo = (motivo or "").strip()
    if not motivo or len(motivo) > 255:
        raise AnulacionVentaNoPermitida(
            "Indicá un motivo de anulación de hasta 255 caracteres."
        )

    venta = VentaDivisa.objects.select_for_update().filter(pk=pk).first()
    if venta is None:
        raise AnulacionVentaNoPermitida("La venta no existe.")
    if venta.estado != VentaDivisa.Estado.CONFIRMADA:
        raise AnulacionVentaNoPermitida(
            "Solo se pueden anular ventas que ya fueron confirmadas."
        )
    if not venta.movimiento_efectivo_recibido_id or not venta.movimiento_efectivo_entregado_id:
        raise AnulacionVentaNoPermitida(
            "La venta no tiene ambos movimientos de efectivo vinculados; "
            "no se puede revertir automáticamente."
        )

    movimientos = (
        MovimientoCaja.objects.select_for_update()
        .filter(
            pk__in=[
                venta.movimiento_efectivo_recibido_id,
                venta.movimiento_efectivo_entregado_id,
            ]
        )
        .prefetch_related("detalle_billetes")
    )
    movimientos_por_id = {movimiento.pk: movimiento for movimiento in movimientos}
    movimiento_recibido = movimientos_por_id.get(
        venta.movimiento_efectivo_recibido_id
    )
    movimiento_entregado = movimientos_por_id.get(
        venta.movimiento_efectivo_entregado_id
    )
    if movimiento_recibido is None or movimiento_entregado is None:
        raise AnulacionVentaNoPermitida(
            "No se encuentran los movimientos originales de la venta."
        )
    if (
        movimiento_recibido.tipo != MovimientoCaja.Tipo.INGRESO_CAJERO
        or movimiento_entregado.tipo != MovimientoCaja.Tipo.RETIRO_CAJERO
        or movimiento_recibido.caja_id != movimiento_entregado.caja_id
        or movimiento_recibido.cajero_id != movimiento_entregado.cajero_id
    ):
        raise AnulacionVentaNoPermitida(
            "Los movimientos originales no corresponden a una liquidación "
            "de efectivo válida."
        )

    movimientos_inversos = (
        (movimiento_recibido, MovimientoCaja.Tipo.RETIRO_CAJERO),
        (movimiento_entregado, MovimientoCaja.Tipo.INGRESO_CAJERO),
    )
    for original, tipo_inverso in movimientos_inversos:
        billetes = dict(
            original.detalle_billetes.values_list("denominacion_id", "cantidad")
        )
        if not billetes:
            raise AnulacionVentaNoPermitida(
                "Falta el desglose de billetes de un movimiento original."
            )
        try:
            registrar_movimiento(
                caja_id=original.caja_id,
                tipo=tipo_inverso,
                moneda_id=original.moneda_id,
                realizado_por=usuario,
                cajero_id=original.cajero_id,
                nota=(
                    f"Anulación de venta #{venta.pk}; reversión del movimiento "
                    f"#{original.pk}: {motivo}"
                ),
                billetes=billetes,
                reversion_de=original,
            )
        except MovimientoNoPermitido as error:
            raise AnulacionVentaNoPermitida(
                f"No se puede completar la reversión: {error}"
            ) from error

    estado_anterior = venta.estado
    venta.estado = VentaDivisa.Estado.ANULADA
    venta.anulado_en = timezone.now()
    venta.save(update_fields=["estado", "anulado_en"])
    registrar_cambio_estado(
        venta,
        estado_anterior,
        venta.estado,
        motivo=f"Anulada por administrador: {motivo}",
        usuario=usuario,
    )
    return venta
