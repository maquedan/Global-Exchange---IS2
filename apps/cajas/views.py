from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.usuarios.menu import tiene_rol

from .forms import (
    ConteoInventarioBilletesForm,
    DenominacionBilleteForm,
    MovimientoCajaForm,
    SucursalForm,
)
from .models import Caja, ConteoInventarioBilletes, DenominacionBillete, Sucursal
from .services import (
    MovimientoNoPermitido,
    registrar_conteo_inventario,
    registrar_movimiento,
)


def requiere_administrador(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


def _render_detalle(
    request,
    sucursal,
    *,
    formulario=None,
    formulario_conteo=None,
    formulario_denominacion=None,
):
    caja = sucursal.caja
    movimientos = Paginator(
        caja.movimientos.select_related(
            "moneda", "cajero", "realizado_por"
        ).prefetch_related("detalle_billetes__denominacion"),
        50,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "cajas/detalle.html",
        {
            "sucursal": sucursal,
            "saldos": caja.saldos.select_related("moneda"),
            "fondos": caja.fondos_cajeros.select_related("cajero", "moneda"),
            "inventario_caja": caja.inventario_billetes.select_related(
                "denominacion__moneda"
            ),
            "inventario_cajeros": caja.inventario_billetes_cajeros.select_related(
                "cajero", "denominacion__moneda"
            ),
            "denominaciones": DenominacionBillete.objects.filter(
                moneda__activo=True
            ).select_related("moneda"),
            "conteos": ConteoInventarioBilletes.objects.filter(caja=caja)
            .select_related("moneda", "cajero", "realizado_por")
            .prefetch_related("detalle_billetes__denominacion")
            .order_by("-creado_en", "-pk")[:50],
            "movimientos": movimientos,
            "page_obj": movimientos,
            "formulario": formulario or MovimientoCajaForm(caja=caja, prefix="mov"),
            "formulario_conteo": formulario_conteo
            or ConteoInventarioBilletesForm(caja=caja, prefix="conteo"),
            "formulario_denominacion": formulario_denominacion
            or DenominacionBilleteForm(prefix="denominacion"),
        },
    )


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
    sucursal = get_object_or_404(Sucursal, pk=pk)
    return _render_detalle(request, sucursal)


@login_required
@requiere_administrador
@require_POST
def registrar_movimiento_view(request, pk):
    caja = get_object_or_404(Caja.objects.select_related("sucursal"), sucursal_id=pk)
    formulario = MovimientoCajaForm(request.POST, caja=caja, prefix="mov")
    if not formulario.is_valid():
        return _render_detalle(request, caja.sucursal, formulario=formulario)

    datos = formulario.cleaned_data
    try:
        registrar_movimiento(
            caja_id=caja.pk,
            tipo=datos["tipo"],
            moneda_id=datos["moneda"].pk,
            cajero_id=datos["cajero"].pk if datos["cajero"] else None,
            realizado_por=request.user,
            nota=datos["nota"],
            billetes=datos["billetes"],
        )
    except (MovimientoNoPermitido, ValidationError) as error:
        formulario.add_error(None, str(error))
        return _render_detalle(request, caja.sucursal, formulario=formulario)

    messages.success(request, "Movimiento de caja registrado correctamente.")
    return redirect("cajas:detalle", pk=caja.sucursal_id)


@login_required
@requiere_administrador
@require_POST
def registrar_denominacion_view(request, pk):
    sucursal = get_object_or_404(Sucursal, pk=pk)
    formulario = DenominacionBilleteForm(
        request.POST, prefix="denominacion"
    )
    if formulario.is_valid():
        formulario.save()
        messages.success(request, "Denominación de billete registrada correctamente.")
        return redirect("cajas:detalle", pk=sucursal.pk)
    return _render_detalle(
        request, sucursal, formulario_denominacion=formulario
    )


@login_required
@requiere_administrador
@require_POST
def registrar_conteo_view(request, pk):
    caja = get_object_or_404(Caja.objects.select_related("sucursal"), sucursal_id=pk)
    formulario = ConteoInventarioBilletesForm(
        request.POST, caja=caja, prefix="conteo"
    )
    if not formulario.is_valid():
        return _render_detalle(request, caja.sucursal, formulario_conteo=formulario)

    datos = formulario.cleaned_data
    try:
        registrar_conteo_inventario(
            caja_id=caja.pk,
            moneda_id=datos["moneda"].pk,
            cajero_id=datos["cajero"].pk if datos["cajero"] else None,
            realizado_por=request.user,
            billetes=datos["billetes"],
        )
    except (MovimientoNoPermitido, ValidationError) as error:
        formulario.add_error(None, str(error))
        return _render_detalle(request, caja.sucursal, formulario_conteo=formulario)

    messages.success(
        request, "Conteo de inventario registrado y reconciliado correctamente."
    )
    return redirect("cajas:detalle", pk=caja.sucursal_id)
