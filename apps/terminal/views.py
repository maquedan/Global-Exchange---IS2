from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.usuarios.menu import tiene_rol


def requiere_terminal(vista):
    """Restringe las pantallas de autoservicio al perfil terminal."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "terminal"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_terminal
def inicio_terminal(request):
    """Pantalla inicial del modo terminal de autoservicio (GEG9-55 - RF054)."""
    return render(request, "terminal/inicio.html")


@login_required
@requiere_terminal
@require_POST
def reiniciar_terminal(request):
    """Limpia los datos temporales y vuelve al inicio de la terminal."""
    for clave in (
        "terminal_cliente_id",
        "terminal_tipo_operacion",
        "terminal_compra_id",
        "terminal_venta_id",
    ):
        request.session.pop(clave, None)

    return redirect("terminal:inicio")