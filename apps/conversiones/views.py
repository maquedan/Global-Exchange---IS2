from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.menu import tiene_rol

from .forms import SimulacionConversionForm, construir_resultado


def requiere_cliente(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "usuario_cliente"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_cliente
def simular(request):
    formulario = SimulacionConversionForm(request.POST or None)
    contexto = {"formulario": formulario}

    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        tasa = (
            TasaCambio.objects.filter(
                moneda_origen=datos["moneda_origen"],
                moneda_destino=datos["moneda_destino"],
                activo=True,
            )
            .order_by("-vigente_desde")
            .first()
        )
        if tasa is None:
            formulario.add_error(
                None,
                "No existe una tasa activa para el par de monedas seleccionado.",
            )
        else:
            contexto["resultado"] = construir_resultado(formulario, tasa)

    return render(request, "conversiones/simular.html", contexto)
