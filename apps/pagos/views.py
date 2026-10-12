from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.conversiones.models import CompraDivisa
from apps.usuarios.menu import tiene_rol

from .models import Pago
from .services import (
    OperacionNoDisponibleParaPago,
    confirmar_pago,
    iniciar_pago,
    resolver_pago_simulado,
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
def elegir_pago(request, compra_pk):
    """Pantalla "Elegí cómo pagar" para una compra pendiente (RF022 — GEG9-36)."""
    compra = get_object_or_404(
        CompraDivisa,
        pk=compra_pk,
        cliente__asociaciones_usuarios__usuario=request.user,
    )

    if request.method == "POST":
        try:
            pago = iniciar_pago(compra.pk)
        except OperacionNoDisponibleParaPago as error:
            messages.error(request, str(error))
            return redirect("conversiones:comprobante_compra", pk=compra.pk)

        if pago.redirect_url:
            return redirect(pago.redirect_url)
        return redirect("pagos:esperando", pk=pago.pk)

    return render(request, "pagos/elegir_pago.html", {"compra": compra})


@login_required
@requiere_cliente
def esperando(request, pk):
    """"Esperando confirmación del pago" + botones del proveedor Simulado."""
    pago = get_object_or_404(
        Pago, pk=pk, compra__cliente__asociaciones_usuarios__usuario=request.user
    )
    return render(request, "pagos/esperando.html", {"pago": pago})


@csrf_exempt
def retorno(request, pk):
    """A donde vuelve el navegador del cliente desde dLocal.

    dLocal manda esto como un POST (no un link que el cliente clickea), así
    que no trae el token CSRF de nuestro sitio — no puede tenerlo, es
    externo — y por el mismo motivo tampoco hay garantía de que llegue la
    cookie de sesión (los navegadores no siempre la mandan en un POST entre
    sitios). Por eso esta vista no exige login ni dueño: de todas formas
    **nunca confía en nada de la URL o el cuerpo del POST** — siempre vuelve
    a consultar el estado real del pago en la pasarela antes de confirmar
    nada (RF022 — GEG9-36).
    """
    pago = get_object_or_404(Pago, pk=pk)
    usuario = request.user if request.user.is_authenticated else None
    pago = confirmar_pago(pago, usuario=usuario)
    return redirect("conversiones:comprobante_compra", pk=pago.compra_id)


@login_required
@requiere_cliente
@require_POST
def simulado_aprobar(request, pk):
    pago = get_object_or_404(
        Pago, pk=pk, compra__cliente__asociaciones_usuarios__usuario=request.user
    )
    try:
        resolver_pago_simulado(pago, aprobar=True, usuario=request.user)
    except OperacionNoDisponibleParaPago as error:
        messages.error(request, str(error))
    return redirect("conversiones:comprobante_compra", pk=pago.compra_id)


@login_required
@requiere_cliente
@require_POST
def simulado_rechazar(request, pk):
    pago = get_object_or_404(
        Pago, pk=pk, compra__cliente__asociaciones_usuarios__usuario=request.user
    )
    try:
        resolver_pago_simulado(pago, aprobar=False, usuario=request.user)
    except OperacionNoDisponibleParaPago as error:
        messages.error(request, str(error))
    return redirect("conversiones:comprobante_compra", pk=pago.compra_id)
