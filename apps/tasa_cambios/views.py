from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.notificaciones.services import notificar_cambio_de_tasa
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
            tasa = formulario.save()
            # Es una tasa nueva: siempre hay un cambio que avisar (RF033).
            notificar_cambio_de_tasa(tasa)
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
        tasa_compra_anterior = tasa.tasa_compra
        tasa_venta_anterior = tasa.tasa_venta
        formulario = TasaCambioForm(request.POST, instance=tasa)
        if formulario.is_valid():
            cambiaron_los_valores = (
                formulario.cleaned_data["tasa_compra"] != tasa_compra_anterior
                or formulario.cleaned_data["tasa_venta"] != tasa_venta_anterior
            )
            formulario.save()
            # Solo avisamos si de verdad cambió compra/venta — no por activar,
            # desactivar o tocar solo la fecha de vigencia (RF033).
            if cambiaron_los_valores:
                notificar_cambio_de_tasa(
                    tasa,
                    compra_anterior=tasa_compra_anterior,
                    venta_anterior=tasa_venta_anterior,
                )
            messages.success(request, "Tasa de cambio actualizada correctamente.")
            return redirect("tasa_cambios:lista")
    else:
        formulario = TasaCambioForm(instance=tasa)

    return render(
        request,
        "tasa_cambios/formulario.html",
        {"formulario": formulario, "accion": "Modificar"},
    )


@login_required
@requiere_gestion_tasas
@require_POST
def desactivar(request, pk):
    """Deja una tasa de cambio fuera de vigencia."""
    tasa = get_object_or_404(TasaCambio, pk=pk)
    tasa.desactivar()
    messages.success(request, "Tasa de cambio desactivada correctamente.")
    return redirect("tasa_cambios:lista")


@login_required
@requiere_gestion_tasas
@require_POST
def activar(request, pk):
    """Vuelve a poner una tasa de cambio en vigencia."""
    tasa = get_object_or_404(TasaCambio, pk=pk)
    try:
        tasa.activar()
    except ValidationError as error:
        messages.error(request, error.message)
        return redirect("tasa_cambios:lista")

    messages.success(request, "Tasa de cambio activada correctamente.")
    return redirect("tasa_cambios:lista")
from django.shortcuts import render

# Create your views here.
