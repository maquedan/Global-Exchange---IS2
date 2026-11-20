from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.usuarios.menu import tiene_rol

from .forms import RangoHorarioForm
from .models import RangoHorario


def requiere_administrador(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_administrador
def lista(request):
    return render(request, "horarios/lista.html", {"rangos": RangoHorario.objects.all()})


@login_required
@requiere_administrador
def crear(request):
    formulario = RangoHorarioForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Rango horario configurado correctamente.")
        return redirect("horarios:lista")
    return render(request, "horarios/formulario.html", {"formulario": formulario, "accion": "Configurar"})


@login_required
@requiere_administrador
def editar(request, pk):
    rango = get_object_or_404(RangoHorario, pk=pk)
    formulario = RangoHorarioForm(request.POST or None, instance=rango)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Rango horario actualizado correctamente.")
        return redirect("horarios:lista")
    return render(request, "horarios/formulario.html", {"formulario": formulario, "accion": "Actualizar"})


@login_required
@requiere_administrador
def eliminar(request, pk):
    if request.method != "POST":
        raise PermissionDenied
    get_object_or_404(RangoHorario, pk=pk).delete()
    messages.success(request, "Rango horario eliminado correctamente.")
    return redirect("horarios:lista")
