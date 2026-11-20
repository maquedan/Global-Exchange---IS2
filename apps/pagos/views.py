from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.conversiones.models import CompraDivisa
from apps.usuarios.menu import tiene_rol
from apps.usuarios.services import requiere_cliente_para_operar

from .models import Pago
from .models import MetodoPago
from .services import (
    CODIGO_TRANSFERENCIA,
    MetodoPagoNoDisponible,
    OperacionNoDisponibleParaPago,
    cambiar_estado_metodo,
    exigir_metodo_habilitado,
    metodos_habilitados,
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


def requiere_administrador(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_cliente
@requiere_cliente_para_operar
def elegir_pago(request, compra_pk):
    """Pantalla "Elegí cómo pagar" para una compra pendiente (RF022 — GEG9-36)."""
    compra = get_object_or_404(
        CompraDivisa,
        pk=compra_pk,
        cliente__asociaciones_usuarios__usuario=request.user,
    )

    if request.method == "POST":
        try:
            pago = iniciar_pago(compra.pk, usuario=request.user)
        except (OperacionNoDisponibleParaPago, MetodoPagoNoDisponible) as error:
            messages.error(request, str(error))
            return redirect("conversiones:comprobante_compra", pk=compra.pk)

        if pago.redirect_url:
            return redirect(pago.redirect_url)
        return redirect("pagos:esperando", pk=pago.pk)

    # Los métodos ya no están escritos en la plantilla: salen de la base, así
    # que el administrador puede habilitarlos o deshabilitarlos sin desplegar
    # (RF035 — GEG9-77).
    return render(
        request,
        "pagos/elegir_pago.html",
        {"compra": compra, "metodos": metodos_habilitados()},
    )


@login_required
@requiere_cliente
@requiere_cliente_para_operar
def esperando(request, pk):
    """"Esperando confirmación del pago" + botones del proveedor Simulado."""
    pago = get_object_or_404(
        Pago, pk=pk, compra__cliente__asociaciones_usuarios__usuario=request.user
    )
    return render(request, "pagos/esperando.html", {"pago": pago})


@login_required
@requiere_cliente
@requiere_cliente_para_operar
@require_POST
def esperar_transferencia(request, compra_pk):
    """El cliente elige pagar por transferencia bancaria (RF025 — GEG9-75).

    No cobra nada: deja la compra marcada para que **no se venza** a los 15
    minutos y aparezca en la pantalla de conciliación del administrador, que
    la confirmará cuando verifique la transferencia.
    """
    compra = get_object_or_404(
        CompraDivisa,
        pk=compra_pk,
        cliente__asociaciones_usuarios__usuario=request.user,
    )

    if compra.estado != CompraDivisa.Estado.PENDIENTE:
        messages.error(request, "Esta operación ya no está pendiente de pago.")
        return redirect("conversiones:comprobante_compra", pk=compra.pk)

    # RF035: igual que la tarjeta, elegir transferencia exige que el método
    # esté habilitado, aunque se fuerce el POST.
    try:
        exigir_metodo_habilitado(CODIGO_TRANSFERENCIA)
    except MetodoPagoNoDisponible as error:
        messages.error(request, str(error))
        return redirect("conversiones:comprobante_compra", pk=compra.pk)

    if not compra.espera_transferencia:
        compra.espera_transferencia = True
        compra.save(update_fields=["espera_transferencia"])

    messages.success(
        request,
        "Anotamos que vas a pagar por transferencia. La operación queda "
        "reservada sin vencimiento hasta que verifiquemos el pago.",
    )
    return redirect("conversiones:comprobante_compra", pk=compra.pk)


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

    Por lo mismo queda **deliberadamente afuera** de la restricción de RF010
    (GEG9-20): no es una vista que use una persona, es el punto de retorno de
    la pasarela. Pedirle cliente activo rompería el cobro.
    """
    pago = get_object_or_404(Pago, pk=pk)
    usuario = request.user if request.user.is_authenticated else None
    pago = confirmar_pago(pago, usuario=usuario)
    return redirect("conversiones:comprobante_compra", pk=pago.compra_id)


@login_required
@requiere_cliente
@requiere_cliente_para_operar
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
@requiere_cliente_para_operar
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


@login_required
@requiere_administrador
def metodos(request):
    """Métodos de pago y su estado, para el administrador (RF035 — GEG9-77)."""
    return render(
        request,
        "pagos/metodos.html",
        {
            "metodos": MetodoPago.objects.prefetch_related("cambios__usuario"),
        },
    )


@login_required
@requiere_administrador
@require_POST
def cambiar_metodo(request, codigo):
    """Habilita o deshabilita un método.

    El control de acceso está por duplicado a propósito: el decorador corta
    el POST, y el servicio no tiene forma de ser llamado sin pasar por acá
    desde la web. Solo POST, con CSRF: cambiar configuración del negocio no
    puede hacerse con un GET.
    """
    habilitado = request.POST.get("habilitado") == "1"
    try:
        metodo = cambiar_estado_metodo(
            codigo=codigo, habilitado=habilitado, usuario=request.user
        )
    except MetodoPagoNoDisponible as error:
        messages.error(request, str(error))
    else:
        estado = "habilitado" if metodo.habilitado else "deshabilitado"
        messages.success(request, f"{metodo.nombre} quedó {estado}.")
    return redirect("pagos:metodos")
