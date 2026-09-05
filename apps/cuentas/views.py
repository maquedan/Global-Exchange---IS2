from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.usuarios.menu import tiene_rol

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


def _cuenta_del_usuario(request, pk):
    """Trae una cuenta SOLO si es de un cliente asociado al usuario logueado."""
    return get_object_or_404(
        CuentaPago,
        pk=pk,
        cliente__asociaciones_usuarios__usuario=request.user,
    )


@login_required
@requiere_cliente
def lista(request):
    cuentas = CuentaPago.objects.filter(
        cliente__asociaciones_usuarios__usuario=request.user,
        activa=True,
    ).select_related("cliente")
    return render(request, "cuentas/lista.html", {"cuentas": cuentas})


@login_required
@requiere_cliente
def crear(request):
    if request.method == "POST":
        formulario = CuentaPagoForm(request.POST, usuario=request.user)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Cuenta de pago registrada correctamente.")
            return redirect("cuentas:lista")
    else:
        formulario = CuentaPagoForm(usuario=request.user)

    return render(
        request,
        "cuentas/formulario.html",
        {"formulario": formulario, "accion": "Registrar"},
    )


@login_required
@requiere_cliente
def editar(request, pk):
    cuenta = _cuenta_del_usuario(request, pk)

    if request.method == "POST":
        formulario = CuentaPagoForm(request.POST, instance=cuenta, usuario=request.user)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Cuenta de pago actualizada correctamente.")
            return redirect("cuentas:lista")
    else:
        formulario = CuentaPagoForm(instance=cuenta, usuario=request.user)

    return render(
        request,
        "cuentas/formulario.html",
        {"formulario": formulario, "accion": "Modificar"},
    )


@login_required
@requiere_cliente
def eliminar(request, pk):
    cuenta = _cuenta_del_usuario(request, pk)
    cuenta.desactivar()
    messages.success(request, "Cuenta de pago eliminada correctamente.")
    return redirect("cuentas:lista")
