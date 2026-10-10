from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.usuarios.menu import tiene_rol

from .forms import MovimientoCajaForm, SucursalForm
from .models import Caja, Sucursal
from .services import MovimientoNoPermitido, registrar_movimiento


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
    sucursales = Sucursal.objects.prefetch_related(
        "caja__saldos__moneda", "caja__fondos_cajeros__moneda"
    )
    return render(request, "cajas/lista.html", {"sucursales": sucursales})


@login_required
@requiere_administrador
def crear_sucursal(request):
    formulario = SucursalForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            sucursal = formulario.save()
            Caja.objects.create(sucursal=sucursal)
        messages.success(request, "Sucursal y caja creadas correctamente.")
        return redirect("cajas:lista")
    return render(
        request,
        "cajas/sucursal_formulario.html",
        {"formulario": formulario, "accion": "Registrar"},
    )


@login_required
@requiere_administrador
def editar_sucursal(request, pk):
    sucursal = get_object_or_404(Sucursal, pk=pk)
    formulario = SucursalForm(request.POST or None, instance=sucursal)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Sucursal actualizada correctamente.")
        return redirect("cajas:lista")
    return render(
        request,
        "cajas/sucursal_formulario.html",
        {"formulario": formulario, "accion": "Modificar"},
    )


@login_required
@requiere_administrador
def detalle(request, pk):
    sucursal = get_object_or_404(
        Sucursal.objects.prefetch_related(
            "caja__saldos__moneda",
            "caja__fondos_cajeros__cajero",
            "caja__fondos_cajeros__moneda",
            "caja__movimientos__moneda",
            "caja__movimientos__cajero",
            "caja__movimientos__realizado_por",
        ),
        pk=pk,
    )
    caja = sucursal.caja
    movimientos = Paginator(
        caja.movimientos.select_related("moneda", "cajero", "realizado_por"), 50
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "cajas/detalle.html",
        {
            "sucursal": sucursal,
            "saldos": caja.saldos.select_related("moneda"),
            "fondos": caja.fondos_cajeros.select_related("cajero", "moneda"),
            "movimientos": movimientos,
            "page_obj": movimientos,
            "formulario": MovimientoCajaForm(caja=caja),
        },
    )


@login_required
@requiere_administrador
@require_POST
def registrar_movimiento_view(request, pk):
    caja = get_object_or_404(Caja.objects.select_related("sucursal"), sucursal_id=pk)
    formulario = MovimientoCajaForm(request.POST, caja=caja)
    if not formulario.is_valid():
        movimientos = Paginator(
            caja.movimientos.select_related("moneda", "cajero", "realizado_por"), 50
        ).get_page(request.GET.get("page"))
        return render(
            request,
            "cajas/detalle.html",
            {
                "sucursal": caja.sucursal,
                "saldos": caja.saldos.select_related("moneda"),
                "fondos": caja.fondos_cajeros.select_related("cajero", "moneda"),
                "movimientos": movimientos,
                "page_obj": movimientos,
                "formulario": formulario,
            },
        )

    datos = formulario.cleaned_data
    try:
        registrar_movimiento(
            caja_id=caja.pk,
            tipo=datos["tipo"],
            moneda_id=datos["moneda"].pk,
            importe=datos["importe"],
            cajero_id=datos["cajero"].pk if datos["cajero"] else None,
            realizado_por=request.user,
            nota=datos["nota"],
        )
    except (MovimientoNoPermitido, ValidationError) as error:
        formulario.add_error(None, str(error))
        movimientos = Paginator(
            caja.movimientos.select_related("moneda", "cajero", "realizado_por"), 50
        ).get_page(request.GET.get("page"))
        return render(
            request,
            "cajas/detalle.html",
            {
                "sucursal": caja.sucursal,
                "saldos": caja.saldos.select_related("moneda"),
                "fondos": caja.fondos_cajeros.select_related("cajero", "moneda"),
                "movimientos": movimientos,
                "page_obj": movimientos,
                "formulario": formulario,
            },
        )

    messages.success(request, "Movimiento de caja registrado correctamente.")
    return redirect("cajas:detalle", pk=caja.sucursal_id)
