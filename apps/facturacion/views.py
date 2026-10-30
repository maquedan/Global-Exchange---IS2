"""Consulta de facturas electrónicas (RF053 — GEG9-54)."""
from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.usuarios.menu import tiene_rol

from .models import Factura
from .services import consultar_estado_fiscal, reintentar_factura


def requiere_consulta_facturas(vista):
    """Permite consultar facturas solamente a clientes y administradores."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "usuario_cliente", "administrador"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


def requiere_administrador(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)
    return envoltura


def requiere_cliente_activo_si_no_es_administrador(vista):
    """Pide un cliente activo solo a quien consulta como cliente.

    Un administrador no opera en nombre de un cliente y debe poder ver el
    padrón completo incluso si no tiene asociaciones de clientes.
    """

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "administrador") and request.cliente_activo is None:
            return redirect("usuarios:sin_cliente")
        return vista(request, *args, **kwargs)

    return envoltura


def facturas_visibles_para(request):
    """Queryset base con la separación de datos aplicada en la base.

    Un administrador puede consultar todo. Un cliente queda limitado al
    cliente activo de su sesión; nunca se acepta un cliente recibido por URL.
    """
    facturas = Factura.objects.select_related(
        "compra__cliente",
        "compra__moneda_pagada",
        "compra__moneda_adquirida",
        "venta__cliente",
        "venta__moneda_entregada",
        "venta__moneda_acreditada",
    )
    if tiene_rol(request.user, "administrador"):
        return facturas

    cliente = request.cliente_activo
    return facturas.filter(Q(compra__cliente=cliente) | Q(venta__cliente=cliente))


def _fecha(valor, nombre, request):
    """Convierte un filtro ISO a fecha sin romper la pantalla si es inválido."""
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        messages.warning(request, f"La fecha '{nombre}' no es válida y se ignoró.")
        return None


@login_required
@requiere_consulta_facturas
@requiere_cliente_activo_si_no_es_administrador
def lista(request):
    """Listado filtrable de facturas visibles para el rol actual."""
    facturas = facturas_visibles_para(request)
    numero = request.GET.get("numero", "").strip()
    estado_fiscal = request.GET.get("estado_fiscal", "")
    tipo = request.GET.get("tipo", "")
    fecha_desde = _fecha(request.GET.get("fecha_desde", ""), "desde", request)
    fecha_hasta = _fecha(request.GET.get("fecha_hasta", ""), "hasta", request)

    if numero:
        facturas = facturas.filter(numero__icontains=numero)
    if estado_fiscal == "SIN_CONSULTAR":
        facturas = facturas.filter(estado_fiscal="")
    elif estado_fiscal:
        facturas = facturas.filter(estado_fiscal=estado_fiscal)
    if tipo == "compra":
        facturas = facturas.filter(compra__isnull=False)
    elif tipo == "venta":
        facturas = facturas.filter(venta__isnull=False)
    if fecha_desde:
        facturas = facturas.filter(creada_en__date__gte=fecha_desde)
    if fecha_hasta:
        facturas = facturas.filter(creada_en__date__lte=fecha_hasta)

    estados_fiscales = (
        facturas.exclude(estado_fiscal="")
        .order_by("estado_fiscal")
        .values_list("estado_fiscal", flat=True)
        .distinct()
    )
    return render(
        request,
        "facturacion/lista.html",
        {
            "facturas": facturas,
            "estados_fiscales": estados_fiscales,
            "filtros": request.GET,
            "es_administrador": tiene_rol(request.user, "administrador"),
        },
    )


@login_required
@requiere_consulta_facturas
@requiere_cliente_activo_si_no_es_administrador
def detalle(request, pk):
    """Detalle de una factura, usando el mismo queryset protegido del listado."""
    factura = get_object_or_404(facturas_visibles_para(request), pk=pk)
    return render(
        request,
        "facturacion/detalle.html",
        {
            "factura": factura,
            "es_administrador": tiene_rol(request.user, "administrador"),
        },
    )


@login_required
@requiere_administrador
@require_POST
def actualizar_estado(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    try:
        consultar_estado_fiscal(factura)
        messages.success(request, f"Estado fiscal actualizado para {factura.numero_completo}.")
    except Exception as error:
        messages.error(request, f"No se pudo consultar el estado fiscal: {error}")
    return redirect("facturacion:detalle", pk=pk)


@login_required
@requiere_administrador
@require_POST
def reintentar(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    try:
        reintentar_factura(factura)
        messages.success(request, f"Se reintentó la factura {factura.numero_completo}.")
    except Exception as error:
        messages.error(request, f"No se pudo reintentar la factura: {error}")
    return redirect("facturacion:detalle", pk=pk)
