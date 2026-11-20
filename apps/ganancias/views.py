from datetime import date
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render

from apps.usuarios.menu import tiene_rol

from .services import resumen_ganancias


def requiere_acceso_ganancias(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador", "analista_cambiario"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


def _fecha(valor):
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _contexto(request):
    fecha_desde = _fecha(request.GET.get("fecha_desde", ""))
    fecha_hasta = _fecha(request.GET.get("fecha_hasta", ""))
    resumen = resumen_ganancias(fecha_desde, fecha_hasta)
    return {
        "resumen": resumen,
        "fecha_desde": request.GET.get("fecha_desde", ""),
        "fecha_hasta": request.GET.get("fecha_hasta", ""),
    }


@login_required
@requiere_acceso_ganancias
def panel(request):
    return render(request, "ganancias/panel.html", _contexto(request))


@login_required
@requiere_acceso_ganancias
def datos(request):
    return JsonResponse(_contexto(request)["resumen"])
