from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

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
    denominacion_tiene_referencias,
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


def _contexto_sucursal(request, sucursal):
    caja = sucursal.caja
    movimientos = Paginator(
        caja.movimientos.select_related(
            "moneda", "cajero", "realizado_por"
        ).prefetch_related("detalle_billetes__denominacion"),
        50,
    ).get_page(request.GET.get("page"))
    return {
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
    }


def _render_detalle(request, sucursal):
    return render(
        request, "cajas/detalle.html", _contexto_sucursal(request, sucursal)
    )


def _render_movimiento(request, sucursal, formulario=None):
    caja = sucursal.caja
    return render(
        request,
        "cajas/movimiento_formulario.html",
        {
            "sucursal": sucursal,
            "formulario": formulario
            or MovimientoCajaForm(caja=caja, prefix="mov"),
        },
    )


def _render_denominacion(request, sucursal, formulario=None):
    denominaciones = DenominacionBillete.objects.filter(
        moneda__activo=True
    ).select_related("moneda")
    for denominacion in denominaciones:
        denominacion.en_uso = denominacion_tiene_referencias(denominacion)
    return render(
        request,
        "cajas/denominacion_formulario.html",
        {
            "sucursal": sucursal,
            "denominaciones": denominaciones,
            "formulario": formulario
            or DenominacionBilleteForm(prefix="denominacion"),
        },
    )


def _render_editar_denominacion(request, sucursal, denominacion, formulario=None):
    en_uso = denominacion_tiene_referencias(denominacion)
    return render(
        request,
        "cajas/denominacion_editar.html",
        {
            "sucursal": sucursal,
            "denominacion": denominacion,
            "en_uso": en_uso,
            "formulario": formulario
            or DenominacionBilleteForm(
                instance=denominacion, prefix="denominacion"
            ),
        },
    )


def _render_conteo(request, sucursal, formulario=None):
    caja = sucursal.caja
    return render(
        request,
        "cajas/conteo_formulario.html",
        {
            "sucursal": sucursal,
            "formulario": formulario
            or ConteoInventarioBilletesForm(caja=caja, prefix="conteo"),
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
@require_http_methods(["GET", "POST"])
def registrar_movimiento_view(request, pk):
    caja = get_object_or_404(Caja.objects.select_related("sucursal"), sucursal_id=pk)
    if request.method == "GET":
        return _render_movimiento(request, caja.sucursal)
    formulario = MovimientoCajaForm(request.POST, caja=caja, prefix="mov")
    if not formulario.is_valid():
        return _render_movimiento(request, caja.sucursal, formulario=formulario)

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
        return _render_movimiento(request, caja.sucursal, formulario=formulario)

    messages.success(request, "Movimiento de caja registrado correctamente.")
    return redirect("cajas:detalle", pk=caja.sucursal_id)


@login_required
@requiere_administrador
@require_http_methods(["GET", "POST"])
def registrar_denominacion_view(request, pk):
    sucursal = get_object_or_404(Sucursal, pk=pk)
    if request.method == "GET":
        return _render_denominacion(request, sucursal)
    formulario = DenominacionBilleteForm(
        request.POST, prefix="denominacion"
    )
    if formulario.is_valid():
        formulario.save()
        messages.success(request, "Denominación de billete registrada correctamente.")
        return redirect("cajas:detalle", pk=sucursal.pk)
    return _render_denominacion(request, sucursal, formulario)


@login_required
@requiere_administrador
@require_http_methods(["GET", "POST"])
def editar_denominacion_view(request, pk, denominacion_pk):
    sucursal = get_object_or_404(Sucursal, pk=pk)
    denominacion = get_object_or_404(DenominacionBillete, pk=denominacion_pk)
    if request.method == "GET":
        return _render_editar_denominacion(request, sucursal, denominacion)

    with transaction.atomic():
        denominacion = DenominacionBillete.objects.select_for_update().get(
            pk=denominacion.pk
        )
        formulario = DenominacionBilleteForm(
            request.POST, instance=denominacion, prefix="denominacion"
        )
        if denominacion_tiene_referencias(denominacion):
            formulario.add_error(
                None,
                "No se puede modificar una denominación que ya tiene inventario, "
                "movimientos o conteos asociados.",
            )
        elif formulario.is_valid():
            formulario.save()
            messages.success(request, "Denominación actualizada correctamente.")
            return redirect("cajas:registrar_denominacion", pk=sucursal.pk)

    return _render_editar_denominacion(
        request, sucursal, denominacion, formulario=formulario
    )


@login_required
@requiere_administrador
@require_http_methods(["POST"])
def eliminar_denominacion_view(request, pk, denominacion_pk):
    sucursal = get_object_or_404(Sucursal, pk=pk)
    with transaction.atomic():
        denominacion = get_object_or_404(
            DenominacionBillete.objects.select_for_update(), pk=denominacion_pk
        )
        if denominacion_tiene_referencias(denominacion):
            messages.error(
                request,
                "No se puede eliminar una denominación que ya tiene inventario, "
                "movimientos o conteos asociados.",
            )
        else:
            try:
                denominacion.delete()
            except ProtectedError:
                messages.error(
                    request,
                    "No se puede eliminar una denominación que ya está en uso.",
                )
            else:
                messages.success(request, "Denominación eliminada correctamente.")
    return redirect("cajas:registrar_denominacion", pk=sucursal.pk)


@login_required
@requiere_administrador
@require_http_methods(["GET", "POST"])
def registrar_conteo_view(request, pk):
    caja = get_object_or_404(Caja.objects.select_related("sucursal"), sucursal_id=pk)
    if request.method == "GET":
        return _render_conteo(request, caja.sucursal)
    formulario = ConteoInventarioBilletesForm(
        request.POST, caja=caja, prefix="conteo"
    )
    if not formulario.is_valid():
        return _render_conteo(request, caja.sucursal, formulario)

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
        return _render_conteo(request, caja.sucursal, formulario)

    messages.success(
        request, "Conteo de inventario registrado y reconciliado correctamente."
    )
    return redirect("cajas:detalle", pk=caja.sucursal_id)
