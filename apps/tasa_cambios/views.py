from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.usuarios.menu import tiene_rol

from .forms import TasaCambioForm
from .models import TasaCambio


def puede_gestionar_tasas(usuario):
    return tiene_rol(usuario, "administrador", "analista_cambiario")


def requiere_gestion_tasas(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not puede_gestionar_tasas(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_gestion_tasas
def lista(request):
    tasas = TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
    return render(request, "tasa_cambios/lista.html", {"tasas": tasas})


@login_required
@requiere_gestion_tasas
def crear(request):
    if request.method == "POST":
        formulario = TasaCambioForm(request.POST)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Tasa de cambio registrada correctamente.")
            return redirect("tasa_cambios:lista")
    else:
        formulario = TasaCambioForm()

    return render(
        request,
        "tasa_cambios/formulario.html",
        {"formulario": formulario, "accion": "Registrar"},
    )


@login_required
@requiere_gestion_tasas
def editar(request, pk):
    tasa = get_object_or_404(TasaCambio, pk=pk)

    if request.method == "POST":
        formulario = TasaCambioForm(request.POST, instance=tasa)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Tasa de cambio actualizada correctamente.")
            return redirect("tasa_cambios:lista")
    else:
        formulario = TasaCambioForm(instance=tasa)

    return render(
        request,
        "tasa_cambios/formulario.html",
        {"formulario": formulario, "accion": "Modificar"},
    )
from django.shortcuts import render

# Create your views here.
