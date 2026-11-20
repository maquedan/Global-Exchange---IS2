from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cajas.models import Caja
from apps.cajas.services import proponer_billetes_entrega
from apps.pagos.models import Pago
from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.auditoria import registrar_auditoria
from apps.usuarios.menu import tiene_rol
from apps.usuarios.models import RegistroAuditoria
from apps.usuarios.services import requiere_cliente_activo
from apps.horarios.services import FueraDeHorarioOperativo

from .forms import (
    AnularCompraForm,
    ConciliacionForm,
    AnularVentaForm,
    CompraDivisaForm,
    EntregaEfectivoVentaForm,
    SimulacionConversionForm,
    VentaDivisaForm,
    construir_resultado,
    RecepcionEfectivoCompraForm,
    ReporteTransaccionesForm,
)

from .models import CompraDivisa, VentaDivisa

from .services import (
    AnulacionCompraNoPermitida,
    ConciliacionNoPermitida,
    compras_pendientes_de_conciliar,
    conciliar_compra,
    MINUTOS_EXPIRACION_PENDIENTE,
    AnulacionVentaNoPermitida,
    CompraNoConfirmable,
    CompraNoDisponible,
    VentaNoConfirmable,
    VentaNoDisponible,
    cancelar_compra,
    cancelar_venta,
    anular_compra,
    anular_venta,
    confirmar_pago_compra,
    confirmar_pago_venta,
    expirar_compra_si_corresponde,
    expirar_venta_si_corresponde,
    iniciar_compra,
    iniciar_venta,
    confirmar_pago_compra_efectivo,
)


def requiere_cliente(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "usuario_cliente"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


def requiere_cajero(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "cajero"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


def requiere_administrador(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


def requiere_administracion(vista):
    """Permite consultar reportes a administración y al analista cambiario."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador", "analista_cambiario"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_cliente
def simular(request):
    formulario = SimulacionConversionForm(request.POST or None)
    contexto = {"formulario": formulario}

    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        tasa = (
            TasaCambio.objects.filter(
                moneda_origen=datos["moneda_origen"],
                moneda_destino=datos["moneda_destino"],
                activo=True,
            )
            .order_by("-vigente_desde")
            .first()
        )
        if tasa is None:
            formulario.add_error(
                None,
                "No existe una tasa activa para el par de monedas seleccionado.",
            )
        else:
            contexto["resultado"] = construir_resultado(formulario, tasa)

    return render(request, "conversiones/simular.html", contexto)


@login_required
@requiere_cliente
@requiere_cliente_activo
def comprar(request):
    """Inicia una compra con los valores vigentes al enviar el formulario.

    Queda pendiente de confirmación (RF051): recién se efectiviza cuando el
    cliente confirma el pago en la pantalla siguiente.

    Si viene con datos por query string (el botón "Repetir esta operación" de
    una compra cancelada), se usan para pre-llenar el formulario.
    """
    formulario = CompraDivisaForm(request.POST or None, initial=request.GET or None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            compra = iniciar_compra(
                usuario=request.user,
                cliente_id=request.cliente_activo.pk,
                moneda_pagada=datos["moneda_pagada"],
                moneda_adquirida=datos["moneda_adquirida"],
                monto_pagado=datos["monto_pagado"],
            )
        except (CompraNoDisponible, FueraDeHorarioOperativo) as error:
            formulario.add_error(None, str(error))
        else:
            return redirect("conversiones:comprobante_compra", pk=compra.pk)

    return render(request, "conversiones/comprar.html", {"formulario": formulario})


@login_required
def comprobante_compra(request, pk):
    """Muestra el estado de la compra (pendiente, confirmada o cancelada)."""
    es_administrador = tiene_rol(request.user, "administrador")
    filtros = {"pk": pk}
    if not es_administrador:
        if not tiene_rol(request.user, "usuario_cliente"):
            raise PermissionDenied
        filtros["cliente__asociaciones_usuarios__usuario"] = request.user

    compra = get_object_or_404(
        CompraDivisa.objects.select_related(
            "cliente", "moneda_pagada", "moneda_adquirida"
        ).prefetch_related("cambios_estado__usuario", "pagos", "facturas"),
        **filtros,
    )
    if not es_administrador:
        compra = expirar_compra_si_corresponde(compra)

    pagos = list(compra.pagos.all())
    pago_aprobado = next(
        (pago for pago in pagos if pago.estado == Pago.Estado.APROBADO),
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
    hay_pago_sin_resolver = any(
        pago.estado in (Pago.Estado.PENDIENTE, Pago.Estado.REQUIERE_REVISION)
        and pago is not pago_en_revision
        for pago in pagos
    )
    return render(
        request,
        "conversiones/comprobante_compra.html",
        {
            "compra": compra,
            "minutos_expiracion": MINUTOS_EXPIRACION_PENDIENTE,
            "es_administrador": es_administrador,
            "requiere_reembolso_manual": (
                pago_aprobado is None
                or pago_aprobado.proveedor == "manual"
                or pago_en_revision is not None
            ),
            "reembolso_en_revision": pago_en_revision is not None,
            "anulacion_bloqueada": hay_pago_sin_resolver,
        },
    )


def _es_del_cliente_activo(request, modelo, pk):
    """¿Esa operación pertenece al cliente con el que se está operando?

    El servicio ya verifica que la operación sea de **algún** cliente del
    usuario. Esto es más estricto: tiene que ser del cliente **activo**
    (RF009 — GEG9-19). Sin esto, alguien asociado a dos clientes podía
    cambiar de cliente y seguir confirmando o cancelando las operaciones del
    anterior — justo lo que la conmutación no debe permitir: lo que se elige
    en la barra superior delimita sobre qué se puede actuar.

    No se aplica a `confirmar_venta_view`: esa es del cajero (RF058), que
    opera sin cliente activo.
    """
    return modelo.objects.filter(pk=pk, cliente=request.cliente_activo).exists()


@login_required
@requiere_cliente
@requiere_cliente_activo
def confirmar_compra_view(request, pk):
    """Confirma el pago de una compra pendiente (RF051 — GEG9-51)."""
    if request.method != "POST":
        return redirect("conversiones:comprobante_compra", pk=pk)
    if not _es_del_cliente_activo(request, CompraDivisa, pk):
        raise PermissionDenied

    try:
        compra = confirmar_pago_compra(pk=pk, usuario=request.user)
    except CompraNoConfirmable as error:
        raise PermissionDenied from error
    except FueraDeHorarioOperativo as error:
        messages.error(request, str(error))
        return redirect("conversiones:comprobante_compra", pk=pk)

    if compra.estado == CompraDivisa.Estado.CANCELADA:
        messages.error(
            request,
            "La cotización cambió mientras revisabas la operación, así que se "
            "canceló: no se te cobró con una tasa distinta a la que aceptaste.",
        )
    else:
        messages.success(request, "La compra de divisas fue confirmada correctamente.")

    return redirect("conversiones:comprobante_compra", pk=compra.pk)


@login_required
@requiere_cliente
@requiere_cliente_activo
def cancelar_compra_view(request, pk):
    """Cancela una compra pendiente por decisión del cliente (RF051)."""
    if request.method != "POST":
        return redirect("conversiones:comprobante_compra", pk=pk)
    if not _es_del_cliente_activo(request, CompraDivisa, pk):
        raise PermissionDenied

    try:
        compra = cancelar_compra(pk=pk, usuario=request.user)
    except CompraNoConfirmable as error:
        raise PermissionDenied from error

    messages.success(request, "Cancelaste la operación.")
    return redirect("conversiones:comprobante_compra", pk=compra.pk)


@login_required
@requiere_cajero
def compras_pendientes_view(request):
    """Lista las compras pendientes de cobro en efectivo (RF057)."""
    compras = (
        CompraDivisa.objects.filter(
            estado=CompraDivisa.Estado.PENDIENTE,
            espera_transferencia=False,
        )
        .select_related(
            "cliente",
            "moneda_pagada",
            "moneda_adquirida",
        )
        .order_by("creado_en", "pk")
    )

    return render(
        request,
        "conversiones/compras_pendientes.html",
        {"compras": compras},
    )


@login_required
@requiere_cajero
def confirmar_compra_efectivo_view(request, pk):
    """Permite al cajero recibir efectivo y confirmar una compra (RF057)."""
    compra = get_object_or_404(
        CompraDivisa.objects.select_related(
            "cliente",
            "moneda_pagada",
            "moneda_adquirida",
        ),
        pk=pk,
    )

    compra = expirar_compra_si_corresponde(compra)

    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        messages.info(
            request,
            "Esta compra ya fue procesada, cancelada o vencida.",
        )
        return redirect("conversiones:compras_pendientes")

    formulario = RecepcionEfectivoCompraForm(
        request.POST if request.method == "POST" else None,
        moneda_recibida=compra.moneda_pagada,
        importe_esperado=compra.total_a_pagar,
    )

    if request.method == "POST" and formulario.is_valid():
        try:
            compra = confirmar_pago_compra_efectivo(
                pk=compra.pk,
                usuario=request.user,
                billetes_recibidos=formulario.cleaned_data["billetes_recibidos"],
            )
        except CompraNoConfirmable as error:
            raise PermissionDenied from error
        except (CompraNoDisponible, FueraDeHorarioOperativo) as error:
            formulario.add_error(None, str(error))
        else:
            if compra.estado == CompraDivisa.Estado.CANCELADA:
                messages.error(
                    request,
                    "La cotización cambió o venció antes de recibir el efectivo; "
                    "la compra fue cancelada.",
                )
            else:
                messages.success(
                    request,
                    "La compra fue confirmada y el efectivo recibido quedó "
                    "registrado en el fondo del cajero.",
                )

            return redirect("conversiones:compras_pendientes")

    return render(
        request,
        "conversiones/recibir_efectivo_compra.html",
        {
            "compra": compra,
            "formulario": formulario,
        },
    )


@login_required
@requiere_cliente
@requiere_cliente_activo
def vender(request):
    """Inicia una venta que queda pendiente de entrega en efectivo.

    Queda pendiente de confirmación (RF051), igual que una compra.

    Si viene con datos por query string (el botón "Repetir esta operación" de
    una venta cancelada), se usan para pre-llenar el formulario.
    """
    formulario = VentaDivisaForm(
        request.POST or None, initial=request.GET or None
    )
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            venta = iniciar_venta(
                usuario=request.user,
                cliente_id=request.cliente_activo.pk,
                moneda_entregada=datos["moneda_entregada"],
                moneda_acreditada=datos["moneda_acreditada"],
                monto_entregado=datos["monto_entregado"],
            )
        except (VentaNoDisponible, FueraDeHorarioOperativo) as error:
            formulario.add_error(None, str(error))
        else:
            return redirect("conversiones:comprobante_venta", pk=venta.pk)

    return render(request, "conversiones/vender.html", {"formulario": formulario})


@login_required
def comprobante_venta(request, pk):
    """Muestra el estado de la venta (pendiente, confirmada o cancelada)."""
    puede_consultar = tiene_rol(request.user, "cajero", "administrador")
    es_cajero = tiene_rol(request.user, "cajero")
    filtros = {"pk": pk}
    if not puede_consultar:
        if not tiene_rol(request.user, "usuario_cliente"):
            raise PermissionDenied
        filtros["cliente__asociaciones_usuarios__usuario"] = request.user

    venta = get_object_or_404(
        VentaDivisa.objects.select_related(
            "cliente",
            "moneda_entregada",
            "moneda_acreditada",
            "cuenta_destino",
            "movimiento_efectivo_recibido__moneda",
            "movimiento_efectivo_entregado__moneda",
            "movimiento_efectivo_recibido__movimiento_reversion__moneda",
            "movimiento_efectivo_entregado__movimiento_reversion__moneda",
        ).prefetch_related(
            "movimiento_efectivo_recibido__detalle_billetes__denominacion",
            "movimiento_efectivo_entregado__detalle_billetes__denominacion",
            "movimiento_efectivo_recibido__movimiento_reversion__detalle_billetes__denominacion",
            "movimiento_efectivo_entregado__movimiento_reversion__detalle_billetes__denominacion",
        ),
        **filtros,
    )
    venta = expirar_venta_si_corresponde(venta)
    return render(
        request,
        "conversiones/comprobante_venta.html",
        {
            "venta": venta,
            "minutos_expiracion": MINUTOS_EXPIRACION_PENDIENTE,
            "es_cajero": es_cajero,
            "es_administrador": tiene_rol(request.user, "administrador"),
            "puede_cancelar": (
                not puede_consultar
                and tiene_rol(request.user, "usuario_cliente")
            ),
        },
    )


@login_required
@requiere_cajero
def ventas_pendientes_view(request):
    ventas = (
        VentaDivisa.objects.filter(estado=VentaDivisa.Estado.PENDIENTE)
        .select_related("cliente", "moneda_entregada", "moneda_acreditada")
        .order_by("creado_en", "pk")
    )
    return render(request, "conversiones/ventas_pendientes.html", {"ventas": ventas})


@login_required
@requiere_administrador
def ventas_administracion_view(request):
    """Lista las ventas para que administración pueda consultar y anular."""
    ventas = (
        VentaDivisa.objects.select_related(
            "cliente",
            "moneda_entregada",
            "moneda_acreditada",
        )
        .order_by("-creado_en", "-pk")
    )
    pagina = Paginator(ventas, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "conversiones/ventas_administracion.html",
        {"ventas": pagina, "ventas_page_obj": pagina},
    )


@login_required
@requiere_administrador
def compras_administracion_view(request):
    """Lista compras para que administración pueda consultar y anular."""
    compras = (
        CompraDivisa.objects.select_related(
            "cliente",
            "moneda_pagada",
            "moneda_adquirida",
        )
        .order_by("-creado_en", "-pk")
    )
    pagina = Paginator(compras, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "conversiones/compras_administracion.html",
        {"compras": pagina, "compras_page_obj": pagina},
    )


@login_required
@requiere_cajero
def confirmar_venta_view(request, pk):
    """Permite al cajero revisar el desglose y confirmar la entrega (RF058)."""
    venta = get_object_or_404(
        VentaDivisa.objects.select_related(
            "cliente", "moneda_entregada", "moneda_acreditada", "cuenta_destino"
        ),
        pk=pk,
    )
    venta = expirar_venta_si_corresponde(venta)
    if venta.estado != VentaDivisa.Estado.PENDIENTE:
        return redirect("conversiones:comprobante_venta", pk=venta.pk)

    caja = Caja.objects.filter(sucursal__activa=True).first()
    propuesta = (
        proponer_billetes_entrega(
            caja=caja,
            moneda=venta.moneda_acreditada,
            importe=venta.monto_acreditado,
            cajero=request.user,
        )
        if caja is not None
        else {
            "billetes": {},
            "disponible": venta.monto_acreditado * 0,
            "faltante": venta.monto_acreditado,
            "importe_entrega": None,
            "excedente": None,
        }
    )
    formulario = EntregaEfectivoVentaForm(
        request.POST if request.method == "POST" else None,
        moneda_recibida=venta.moneda_entregada,
        importe_recibido=venta.monto_entregado,
        moneda_entregada=venta.moneda_acreditada,
        importe_entregado=propuesta["importe_entrega"] or venta.monto_acreditado,
        billetes_entregados_iniciales=propuesta["billetes"],
    )
    if request.method == "POST" and formulario.is_valid():
        try:
            venta = confirmar_pago_venta(
                pk=venta.pk,
                usuario=request.user,
                billetes_recibidos=formulario.cleaned_data["billetes_recibidos"],
                billetes_entregados=formulario.cleaned_data["billetes_entregados"],
            )
        except VentaNoConfirmable as error:
            raise PermissionDenied from error
        except VentaNoDisponible as error:
            formulario.add_error(None, str(error))
        else:
            if venta.estado == VentaDivisa.Estado.CANCELADA:
                messages.error(
                    request,
                    "La cotización cambió o venció mientras se preparaba la "
                    "entrega; la venta se canceló y no se retiró efectivo.",
                )
            else:
                messages.success(
                    request,
                    "La venta fue confirmada. La divisa recibida y el efectivo "
                    "entregado quedaron registrados en el fondo del cajero.",
                )
            return redirect("conversiones:comprobante_venta", pk=venta.pk)

    return render(
        request,
        "conversiones/entregar_efectivo_venta.html",
        {
            "venta": venta,
            "caja": caja,
            "formulario": formulario,
            "disponible": propuesta["disponible"],
            "faltante": propuesta["faltante"],
            "importe_entrega": propuesta["importe_entrega"],
            "excedente": propuesta["excedente"],
        },
    )


@login_required
@requiere_cliente
@requiere_cliente_activo
def cancelar_venta_view(request, pk):
    """Cancela una venta pendiente por decisión del cliente (RF051)."""
    if request.method != "POST":
        return redirect("conversiones:comprobante_venta", pk=pk)
    if not _es_del_cliente_activo(request, VentaDivisa, pk):
        raise PermissionDenied

    try:
        venta = cancelar_venta(pk=pk, usuario=request.user)
    except VentaNoConfirmable as error:
        raise PermissionDenied from error

    messages.success(request, "Cancelaste la operación.")
    return redirect("conversiones:comprobante_venta", pk=venta.pk)


@login_required
@require_POST
def anular_venta_view(request, pk):
    """Permite al administrador anular una venta y revertir sus movimientos."""
    if not tiene_rol(request.user, "administrador"):
        raise PermissionDenied

    formulario = AnularVentaForm(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Indicá un motivo válido para anular la venta.")
        return redirect("conversiones:comprobante_venta", pk=pk)

    try:
        venta = anular_venta(
            pk=pk,
            usuario=request.user,
            motivo=formulario.cleaned_data["motivo"],
        )
    except AnulacionVentaNoPermitida as error:
        messages.error(request, str(error))
        return redirect("conversiones:comprobante_venta", pk=pk)

    registrar_auditoria(
        request.user,
        RegistroAuditoria.Accion.VENTA_ANULADA,
        f"Venta #{venta.pk}; cliente #{venta.cliente_id}; "
        f"motivo: {formulario.cleaned_data['motivo']}.",
    )
    messages.success(
        request,
        "La venta fue anulada y se registraron los movimientos inversos.",
    )
    return redirect("conversiones:comprobante_venta", pk=venta.pk)


@login_required
@require_POST
def anular_compra_view(request, pk):
    """Reembolsa y anula una compra pagada, solo por decisión administrativa."""
    if not tiene_rol(request.user, "administrador"):
        raise PermissionDenied

    formulario = AnularCompraForm(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Indicá un motivo válido para anular la compra.")
        return redirect("conversiones:comprobante_compra", pk=pk)

    try:
        compra, reembolso_completado = anular_compra(
            pk=pk,
            usuario=request.user,
            motivo=formulario.cleaned_data["motivo"],
            confirmar_reembolso_manual=formulario.cleaned_data[
                "confirmar_reembolso_manual"
            ],
        )
    except AnulacionCompraNoPermitida as error:
        messages.error(request, str(error))
        return redirect("conversiones:comprobante_compra", pk=pk)

    if not reembolso_completado:
        pago = compra.pagos.order_by("-creado_en", "-pk").first()
        estado_reembolso = (
            pago.respuesta_cruda.get("reembolso_anulacion", {}).get("estado")
            if pago
            else "REQUIERE_REVISION"
        )
        messages.error(
            request,
            "El reembolso no fue confirmado por el proveedor "
            f"(estado: {estado_reembolso}). La compra sigue pagada.",
        )
        return redirect("conversiones:comprobante_compra", pk=compra.pk)

    registrar_auditoria(
        request.user,
        RegistroAuditoria.Accion.COMPRA_ANULADA,
        f"Compra #{compra.pk}; cliente #{compra.cliente_id}; "
        f"motivo: {formulario.cleaned_data['motivo']}.",
    )
    messages.success(
        request,
        "La compra fue reembolsada y anulada correctamente.",
    )
    return redirect("conversiones:comprobante_compra", pk=compra.pk)


@login_required
@requiere_cliente
@requiere_cliente_activo
def historial(request):
    """Transacciones confirmadas del cliente activo, en modo consulta.

    Antes de RF008 mezclaba las de todos los clientes asociados; ahora
    muestra solo las del cliente con el que se está operando.
    """

    compras = (
        CompraDivisa.objects.filter(
            cliente=request.cliente_activo,
            estado=CompraDivisa.Estado.CONFIRMADA,
        )
        .select_related(
            "cliente",
            "moneda_pagada",
            "moneda_adquirida",
        )
        .distinct()
    )

    ventas = (
        VentaDivisa.objects.filter(
            cliente=request.cliente_activo,
            estado=VentaDivisa.Estado.CONFIRMADA,
        )
        .select_related(
            "cliente",
            "moneda_entregada",
            "moneda_acreditada",
            "cuenta_destino",
        )
        .distinct()
    )

    transacciones = []

    for compra in compras:
        transacciones.append(
            {
                "id": compra.pk,
                "tipo": "Compra",
                "fecha": compra.confirmado_en,
                "cliente": compra.cliente,
                "origen": compra.moneda_pagada,
                "destino": compra.moneda_adquirida,
                "monto_origen": compra.total_a_pagar,
                "monto_final": compra.monto_recibido,
                "comision": compra.monto_comision,
                "moneda_comision": compra.moneda_pagada,
                "porcentaje_comision": compra.porcentaje_comision,
                "tasa": compra.tasa_aplicada,
                "estado": compra.get_estado_display(),
            }
        )

    for venta in ventas:
        transacciones.append(
            {
                "id": venta.pk,
                "tipo": "Venta",
                "fecha": venta.confirmado_en,
                "cliente": venta.cliente,
                "origen": venta.moneda_entregada,
                "destino": venta.moneda_acreditada,
                "monto_origen": venta.monto_entregado,
                "monto_final": venta.monto_acreditado,
                "comision": venta.monto_comision,
                "moneda_comision": venta.moneda_acreditada,
                "porcentaje_comision": venta.porcentaje_comision,
                "tasa": venta.tasa_aplicada,
                "estado": venta.get_estado_display(),
            }
        )

    transacciones.sort(key=lambda transaccion: transaccion["fecha"], reverse=True)

    return render(
        request,
        "conversiones/historial.html",
        {"transacciones": transacciones},
    )


@login_required
@requiere_administracion
def reporte_transacciones(request):
    """Reporte global de compras y ventas para auditoría (RF030 — GEG9-66).

    Se mantiene separado de ``historial``, que representa únicamente al
    cliente activo y solo muestra operaciones confirmadas.
    """
    formulario = ReporteTransaccionesForm(request.GET or None)
    compras = CompraDivisa.objects.select_related(
        "cliente", "moneda_pagada", "moneda_adquirida"
    )
    ventas = VentaDivisa.objects.select_related(
        "cliente", "moneda_entregada", "moneda_acreditada"
    )

    if formulario.is_valid():
        datos = formulario.cleaned_data
        if datos["cliente"]:
            compras = compras.filter(cliente=datos["cliente"])
            ventas = ventas.filter(cliente=datos["cliente"])
        if datos["moneda"]:
            compras = compras.filter(
                Q(moneda_pagada=datos["moneda"])
                | Q(moneda_adquirida=datos["moneda"])
            )
            ventas = ventas.filter(
                Q(moneda_entregada=datos["moneda"])
                | Q(moneda_acreditada=datos["moneda"])
            )
        if datos["estado"]:
            compras = compras.filter(estado=datos["estado"])
            ventas = ventas.filter(estado=datos["estado"])
        if datos["fecha_desde"]:
            compras = compras.filter(creado_en__date__gte=datos["fecha_desde"])
            ventas = ventas.filter(creado_en__date__gte=datos["fecha_desde"])
        if datos["fecha_hasta"]:
            compras = compras.filter(creado_en__date__lte=datos["fecha_hasta"])
            ventas = ventas.filter(creado_en__date__lte=datos["fecha_hasta"])

        tipo = datos["tipo_operacion"]
        if tipo == "compra":
            ventas = ventas.none()
        elif tipo == "venta":
            compras = compras.none()

    transacciones = []
    for compra in compras:
        transacciones.append(
            {
                "id": compra.pk,
                "tipo": "Compra",
                "tipo_codigo": "compra",
                "fecha": compra.creado_en,
                "cliente": compra.cliente,
                "origen": compra.moneda_pagada,
                "destino": compra.moneda_adquirida,
                "monto_origen": compra.total_a_pagar,
                "monto_final": compra.monto_recibido,
                "comision": compra.monto_comision,
                "moneda_comision": compra.moneda_pagada,
                "porcentaje_comision": compra.porcentaje_comision,
                "tasa": compra.tasa_aplicada,
                "estado": compra.get_estado_display(),
            }
        )
    for venta in ventas:
        transacciones.append(
            {
                "id": venta.pk,
                "tipo": "Venta",
                "tipo_codigo": "venta",
                "fecha": venta.creado_en,
                "cliente": venta.cliente,
                "origen": venta.moneda_entregada,
                "destino": venta.moneda_acreditada,
                "monto_origen": venta.monto_entregado,
                "monto_final": venta.monto_acreditado,
                "comision": venta.monto_comision,
                "moneda_comision": venta.moneda_acreditada,
                "porcentaje_comision": venta.porcentaje_comision,
                "tasa": venta.tasa_aplicada,
                "estado": venta.get_estado_display(),
            }
        )

    transacciones.sort(key=lambda transaccion: transaccion["fecha"], reverse=True)
    return render(
        request,
        "conversiones/reporte_transacciones.html",
        {"formulario": formulario, "transacciones": transacciones},
    )

@login_required
@requiere_administrador
def conciliaciones(request):
    """Compras esperando que se verifique una transferencia (RF025 — GEG9-75)."""
    pendientes = compras_pendientes_de_conciliar()
    return render(
        request,
        "conversiones/conciliaciones.html",
        {"compras": pendientes},
    )


@login_required
@requiere_administrador
def conciliar(request, pk):
    """Marca una compra como pagada tras verificar la transferencia (RF025).

    El control de acceso está por duplicado a propósito: el decorador corta
    el GET y el POST, y el servicio vuelve a verificar el rol por su cuenta,
    para que no se pueda conciliar por otra vía que no sea esta vista.
    """
    compra = get_object_or_404(
        CompraDivisa.objects.select_related(
            "cliente", "moneda_pagada", "moneda_adquirida"
        ),
        pk=pk,
    )
    formulario = ConciliacionForm(request.POST or None)

    if request.method == "POST" and formulario.is_valid():
        try:
            with transaction.atomic():
                conciliada = conciliar_compra(
                    pk=compra.pk,
                    usuario=request.user,
                    referencia=formulario.cleaned_data["referencia"],
                    observacion=formulario.cleaned_data["observacion"],
                )
                if conciliada.estado == CompraDivisa.Estado.CONFIRMADA:
                    registrar_auditoria(
                        request.user,
                        RegistroAuditoria.Accion.COMPRA_CONCILIADA,
                        f"Compra #{conciliada.pk}; referencia "
                        f"{formulario.cleaned_data['referencia']}.",
                    )
        except (ConciliacionNoPermitida, FueraDeHorarioOperativo) as error:
            formulario.add_error(None, str(error))
        else:
            if conciliada.estado != CompraDivisa.Estado.CONFIRMADA:
                # RF051: la cotización cambió, así que se canceló en vez de
                # confirmarse. La cancelación ya quedó guardada.
                messages.error(
                    request,
                    f"La cotización cambió desde que se inició la operación "
                    f"#{compra.pk}, así que se canceló en vez de confirmarse. "
                    "No se le cobró nada al cliente: hay que devolverle la "
                    "transferencia o iniciar una operación nueva.",
                )
            else:
                messages.success(
                    request,
                    f"La operación #{compra.pk} quedó confirmada como pagada.",
                )
            return redirect("conversiones:conciliaciones")

    return render(
        request,
        "conversiones/conciliar.html",
        {"compra": compra, "formulario": formulario},
    )
