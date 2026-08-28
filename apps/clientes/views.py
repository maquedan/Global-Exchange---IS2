from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from apps.usuarios.menu import tiene_rol

from .forms import ClienteForm
from .models import Cliente


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
    """Muestra los clientes registrados para RF001 — GEG9-11."""
    clientes = Cliente.objects.all()
    return render(request, "clientes/lista.html", {"clientes": clientes})


@login_required
@requiere_administrador
def crear(request):
    """Registra un nuevo cliente persona física o jurídica."""
    if request.method == "POST":
        formulario = ClienteForm(request.POST)

        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Cliente registrado correctamente.")
            return redirect("clientes:lista")
    else:
        formulario = ClienteForm()

    return render(
        request,
        "clientes/formulario.html",
        {"formulario": formulario},
    )