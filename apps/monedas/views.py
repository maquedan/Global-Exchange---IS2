from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.usuarios.menu import tiene_rol

from .forms import MonedaForm
from .models import Moneda


def es_administrador(usuario):
    """Indica si el usuario autenticado posee el rol administrador."""
    return tiene_rol(usuario, "administrador")


def requiere_administrador(vista):
    """Restringe una vista a usuarios con el rol administrador."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_administrador(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_administrador
def lista(request):
    """Muestra las monedas actualmente admitidas para operar."""
    monedas = Moneda.objects.filter(activo=True)
    return render(request, "monedas/lista.html", {"monedas": monedas})


@login_required
@requiere_administrador
def inactivas(request):
    """Muestra las monedas que no están admitidas actualmente."""
    monedas = Moneda.objects.filter(activo=False)
    return render(request, "monedas/inactivas.html", {"monedas": monedas})


@login_required
@requiere_administrador
def crear(request):
    """Registra una nueva moneda admitida."""
    if request.method == "POST":
        formulario = MonedaForm(request.POST)

        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Moneda registrada correctamente.")
            return redirect("monedas:lista")
    else:
        formulario = MonedaForm()

    return render(
        request,
        "monedas/formulario.html",
        {"formulario": formulario, "accion": "Registrar"},
    )


@login_required
@requiere_administrador
def editar(request, pk):
    """Modifica los datos descriptivos de una moneda."""
    moneda = get_object_or_404(Moneda, pk=pk)

    if request.method == "POST":
        formulario = MonedaForm(request.POST, instance=moneda)

        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Moneda actualizada correctamente.")
            return redirect("monedas:lista")
    else:
        formulario = MonedaForm(instance=moneda)

    return render(
        request,
        "monedas/formulario.html",
        {"formulario": formulario, "accion": "Modificar"},
    )


@login_required
@requiere_administrador
@require_POST
def desactivar(request, pk):
    """Deja una moneda fuera de operación."""
    moneda = get_object_or_404(Moneda, pk=pk)
    moneda.desactivar()
    messages.success(request, f"{moneda.codigo} fue desactivada correctamente.")
    return redirect("monedas:lista")


@login_required
@requiere_administrador
@require_POST
def activar(request, pk):
    """Vuelve a admitir una moneda para operar."""
    moneda = get_object_or_404(Moneda, pk=pk)
    moneda.activar()
    messages.success(request, f"{moneda.codigo} fue activada correctamente.")
    return redirect("monedas:inactivas")