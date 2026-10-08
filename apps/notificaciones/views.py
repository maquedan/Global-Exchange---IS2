from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.usuarios.menu import tiene_rol

from .models import Notificacion


def requiere_cliente(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "usuario_cliente"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_cliente
def lista(request):
    """Notificaciones del usuario logueado, más nuevas primero."""
    notificaciones = Notificacion.objects.filter(usuario=request.user)
    return render(request, "notificaciones/lista.html", {"notificaciones": notificaciones})


@login_required
@requiere_cliente
@require_POST
def marcar_leida(request, pk):
    """Marca como leída una notificación propia (RF033 — GEG9-38)."""
    notificacion = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    notificacion.leida = True
    notificacion.save(update_fields=["leida"])
    return redirect("notificaciones:lista")
