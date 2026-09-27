from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.menu import tiene_rol

from .forms import CompraDivisaForm, SimulacionConversionForm, construir_resultado
from .models import CompraDivisa
from .services import CompraNoDisponible, confirmar_compra


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


@login_required
@requiere_cliente
def comprar(request):
    """Confirma una compra con los valores vigentes al enviar el formulario."""
    formulario = CompraDivisaForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        try:
            compra = confirmar_compra(
                cliente_id=datos["cliente"].pk,
                moneda_pagada=datos["moneda_pagada"],
                moneda_adquirida=datos["moneda_adquirida"],
                monto_pagado=datos["monto_pagado"],
            )
        except CompraNoDisponible as error:
            formulario.add_error(None, str(error))
        else:
            messages.success(request, "La compra de divisas fue confirmada correctamente.")
            return redirect("conversiones:comprobante_compra", pk=compra.pk)

    return render(request, "conversiones/comprar.html", {"formulario": formulario})


@login_required
@requiere_cliente
def comprobante_compra(request, pk):
    """Muestra el comprobante solo al usuario asociado al cliente de la compra."""
    compra = get_object_or_404(
        CompraDivisa.objects.select_related(
            "cliente", "moneda_pagada", "moneda_adquirida"
        ),
        pk=pk,
        cliente__asociaciones_usuarios__usuario=request.user,
    )
    return render(request, "conversiones/comprobante_compra.html", {"compra": compra})
