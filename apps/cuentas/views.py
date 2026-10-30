from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.usuarios.menu import tiene_rol
from apps.usuarios.services import requiere_cliente_activo

from .forms import CuentaPagoForm
from .models import CuentaPago


def requiere_cliente(vista):
    """Restringe una vista a usuarios con el rol usuario_cliente."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "usuario_cliente"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


def _cuenta_del_cliente_activo(request, pk):
    """Trae una cuenta SOLO si es del cliente con el que se está operando."""
    return get_object_or_404(CuentaPago, pk=pk, cliente=request.cliente_activo)


@login_required
@requiere_cliente
@requiere_cliente_activo
def lista(request):
    cuentas = CuentaPago.objects.filter(
        cliente=request.cliente_activo,
        activa=True,
    ).select_related("cliente")
    return render(request, "cuentas/lista.html", {"cuentas": cuentas})


@login_required
@requiere_cliente
@requiere_cliente_activo
def crear(request):
    formulario = CuentaPagoForm(request.POST or None, cliente=request.cliente_activo)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Cuenta de pago registrada correctamente.")
        return redirect("cuentas:lista")

    return render(
        request,
        "cuentas/formulario.html",
        {"formulario": formulario, "accion": "Registrar"},
    )


@login_required
@requiere_cliente
@requiere_cliente_activo
def editar(request, pk):
    cuenta = _cuenta_del_cliente_activo(request, pk)

    formulario = CuentaPagoForm(request.POST or None, instance=cuenta)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Cuenta de pago actualizada correctamente.")
        return redirect("cuentas:lista")

    return render(
        request,
        "cuentas/formulario.html",
        {"formulario": formulario, "accion": "Modificar"},
    )


@login_required
@requiere_cliente
@requiere_cliente_activo
def eliminar(request, pk):
    cuenta = _cuenta_del_cliente_activo(request, pk)
    cuenta.desactivar()
    messages.success(request, "Cuenta de pago eliminada correctamente.")
    return redirect("cuentas:lista")
