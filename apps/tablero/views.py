"""Tablero de control del administrador (RF038 — GEG9-67)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.usuarios.menu import tiene_rol

from .services import PERIODO_POR_DEFECTO, metricas


def requiere_administrador(vista):
    """Solo el administrador entra; cualquier otro rol recibe 403.

    Es el mismo decorador que ya repiten `cajas`, `clientes`, `comisiones`,
    `conversiones`, `facturacion`, `horarios`, `monedas` y `pagos`. Se
    mantiene la convención del proyecto en vez de mover la función a un
    módulo común: hacerlo acá dejaría dos formas distintas de proteger una
    vista hasta que se migren las otras ocho, y eso es peor que la copia.

    El bloqueo vive en la vista, no en el menú: esconder la opción es
    comodidad, y no sirve de nada contra alguien que escribe la dirección.
    """

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_administrador
def panel(request):
    """Consolida las métricas del negocio en una sola pantalla.

    El período llega por la dirección (``?periodo=hoy``). No se valida acá:
    `metricas` descarta lo que no reconoce y usa el valor por omisión, así
    que una dirección manipulada no rompe nada.
    """
    return render(
        request,
        "tablero/panel.html",
        {"tablero": metricas(request.GET.get("periodo", PERIODO_POR_DEFECTO))},
    )
