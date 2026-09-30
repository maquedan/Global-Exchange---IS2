from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.menu import tiene_rol

from .forms import (
    CompraDivisaForm,
    SimulacionConversionForm,
    VentaDivisaForm,
    construir_resultado,
)
from .models import CompraDivisa, VentaDivisa
from .services import (
    MINUTOS_EXPIRACION_PENDIENTE,
    CompraNoConfirmable,
    CompraNoDisponible,
    VentaNoConfirmable,
    VentaNoDisponible,
    cancelar_compra,
    cancelar_venta,
    confirmar_pago_compra,
    confirmar_pago_venta,
    expirar_compra_si_corresponde,
    expirar_venta_si_corresponde,
    iniciar_compra,
    iniciar_venta,
)


def requiere_cliente(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "usuario_cliente"):
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
def comprar(request):
    """Inicia una compra con los valores vigentes al enviar el formulario.

    Queda pendiente de confirmación (RF051): recién se efectiviza cuando el
    cliente confirma el pago en la pantalla siguiente.

    Si viene con datos por query string (el botón "Repetir esta operación" de
    una compra cancelada), se usan para pre-llenar el formulario.
    """
    formulario = CompraDivisaForm(
        request.POST or None, usuario=request.user, initial=request.GET or None
    )
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            compra = iniciar_compra(
                cliente_id=datos["cliente"].pk,
                moneda_pagada=datos["moneda_pagada"],
                moneda_adquirida=datos["moneda_adquirida"],
                monto_pagado=datos["monto_pagado"],
            )
        except CompraNoDisponible as error:
            formulario.add_error(None, str(error))
        else:
            return redirect("conversiones:comprobante_compra", pk=compra.pk)

    return render(request, "conversiones/comprar.html", {"formulario": formulario})


@login_required
@requiere_cliente
def comprobante_compra(request, pk):
    """Muestra el estado de la compra (pendiente, confirmada o cancelada)."""
    compra = get_object_or_404(
        CompraDivisa.objects.select_related(
            "cliente", "moneda_pagada", "moneda_adquirida"
        ),
        pk=pk,
        cliente__asociaciones_usuarios__usuario=request.user,
    )
    compra = expirar_compra_si_corresponde(compra)
    return render(
        request,
        "conversiones/comprobante_compra.html",
        {"compra": compra, "minutos_expiracion": MINUTOS_EXPIRACION_PENDIENTE},
    )


@login_required
@requiere_cliente
def confirmar_compra_view(request, pk):
    """Confirma el pago de una compra pendiente (RF051 — GEG9-51)."""
    if request.method != "POST":
        return redirect("conversiones:comprobante_compra", pk=pk)

    try:
        compra = confirmar_pago_compra(pk=pk, usuario=request.user)
    except CompraNoConfirmable as error:
        raise PermissionDenied from error

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
def cancelar_compra_view(request, pk):
    """Cancela una compra pendiente por decisión del cliente (RF051)."""
    if request.method != "POST":
        return redirect("conversiones:comprobante_compra", pk=pk)

    try:
        compra = cancelar_compra(pk=pk, usuario=request.user)
    except CompraNoConfirmable as error:
        raise PermissionDenied from error

    messages.success(request, "Cancelaste la operación.")
    return redirect("conversiones:comprobante_compra", pk=compra.pk)


@login_required
@requiere_cliente
def vender(request):
    """Inicia una venta con la cuenta de acreditación elegida.

    Queda pendiente de confirmación (RF051), igual que una compra.

    Si viene con datos por query string (el botón "Repetir esta operación" de
    una venta cancelada), se usan para pre-llenar el formulario.
    """
    formulario = VentaDivisaForm(
        request.POST or None, usuario=request.user, initial=request.GET or None
    )
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            venta = iniciar_venta(
                cliente_id=datos["cliente"].pk,
                moneda_entregada=datos["moneda_entregada"],
                moneda_acreditada=datos["moneda_acreditada"],
                cuenta_destino=datos["cuenta_destino"],
                monto_entregado=datos["monto_entregado"],
            )
        except VentaNoDisponible as error:
            formulario.add_error(None, str(error))
        else:
            return redirect("conversiones:comprobante_venta", pk=venta.pk)

    return render(request, "conversiones/vender.html", {"formulario": formulario})


@login_required
@requiere_cliente
def comprobante_venta(request, pk):
    """Muestra el estado de la venta (pendiente, confirmada o cancelada)."""
    venta = get_object_or_404(
        VentaDivisa.objects.select_related(
            "cliente", "moneda_entregada", "moneda_acreditada", "cuenta_destino"
        ),
        pk=pk,
        cliente__asociaciones_usuarios__usuario=request.user,
    )
    venta = expirar_venta_si_corresponde(venta)
    return render(
        request,
        "conversiones/comprobante_venta.html",
        {"venta": venta, "minutos_expiracion": MINUTOS_EXPIRACION_PENDIENTE},
    )


@login_required
@requiere_cliente
def confirmar_venta_view(request, pk):
    """Confirma el pago de una venta pendiente (RF051 — GEG9-51)."""
    if request.method != "POST":
        return redirect("conversiones:comprobante_venta", pk=pk)

    try:
        venta = confirmar_pago_venta(pk=pk, usuario=request.user)
    except VentaNoConfirmable as error:
        raise PermissionDenied from error

    if venta.estado == VentaDivisa.Estado.CANCELADA:
        messages.error(
            request,
            "La cotización cambió mientras revisabas la operación, así que se "
            "canceló: no se te acreditó con una tasa distinta a la que aceptaste.",
        )
    else:
        messages.success(request, "La venta de divisas fue confirmada correctamente.")

    return redirect("conversiones:comprobante_venta", pk=venta.pk)


@login_required
@requiere_cliente
def cancelar_venta_view(request, pk):
    """Cancela una venta pendiente por decisión del cliente (RF051)."""
    if request.method != "POST":
        return redirect("conversiones:comprobante_venta", pk=pk)

    try:
        venta = cancelar_venta(pk=pk, usuario=request.user)
    except VentaNoConfirmable as error:
        raise PermissionDenied from error

    messages.success(request, "Cancelaste la operación.")
    return redirect("conversiones:comprobante_venta", pk=venta.pk)
