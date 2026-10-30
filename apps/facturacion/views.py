"""Consulta de facturas electrónicas (RF053 — GEG9-54)."""
from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.views.decorators.http import require_POST

from apps.usuarios.menu import tiene_rol

from .models import Factura
from .documentos import crear_pdf_texto
from .services import cliente_configurado, consultar_estado_fiscal, reintentar_factura


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


def facturas_filtradas(request):
    """Aplica los filtros del listado a las facturas autorizadas."""
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

    return facturas


def _filtros_contexto(facturas, request):
    estados_fiscales = (
        facturas.exclude(estado_fiscal="")
        .order_by("estado_fiscal")
        .values_list("estado_fiscal", flat=True)
        .distinct()
    )
    return {
        "facturas": facturas,
        "estados_fiscales": estados_fiscales,
        "filtros": request.GET,
        "es_administrador": tiene_rol(request.user, "administrador"),
    }


@login_required
@requiere_consulta_facturas
@requiere_cliente_activo_si_no_es_administrador
def lista(request):
    """Listado filtrable de facturas visibles para el rol actual."""
    return render(
        request,
        "facturacion/lista.html",
        _filtros_contexto(facturas_filtradas(request), request),
    )


def _descargar_factura(request, pk, formato):
    factura = get_object_or_404(facturas_visibles_para(request), pk=pk)
    if not factura.cdc:
        return HttpResponse("La factura todavía no tiene CDC.", status=409)
    _, cliente = cliente_configurado()
    contenido = cliente.descargar_documento(factura.cdc, formato)
    tipo = "application/pdf" if formato == "pdf" else "application/xml"
    extension = "pdf" if formato == "pdf" else "xml"
    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta["Content-Disposition"] = f'attachment; filename="factura-{factura.numero_completo}.{extension}"'
    return respuesta


@login_required
@requiere_consulta_facturas
@requiere_cliente_activo_si_no_es_administrador
def descargar_pdf(request, pk):
    return _descargar_factura(request, pk, "pdf")


@login_required
@requiere_consulta_facturas
@requiere_cliente_activo_si_no_es_administrador
def descargar_xml(request, pk):
    return _descargar_factura(request, pk, "xml")


def _filas_exportacion(facturas):
    return [[f.numero_completo, f.generada_en or f.creada_en, f.operacion.cliente,
             f.monto, f.moneda, f.estado_fiscal or "Sin consultar"] for f in facturas]


@login_required
@requiere_consulta_facturas
@requiere_cliente_activo_si_no_es_administrador
def exportar_historial(request, formato):
    facturas = facturas_filtradas(request)
    filas = _filas_exportacion(facturas)
    encabezados = ["Factura", "Fecha", "Cliente", "Monto", "Moneda", "Estado fiscal"]
    if formato == "excel":
        import html
        filas_html = "".join("<Row>" + "".join(f"<Cell><Data ss:Type=\"String\">{html.escape(str(v))}</Data></Cell>" for v in fila) + "</Row>" for fila in filas)
        cuerpo = "<?xml version=\"1.0\"?><Workbook xmlns=\"urn:schemas-microsoft-com:office:spreadsheet\" xmlns:ss=\"urn:schemas-microsoft-com:office:spreadsheet\"><Worksheet ss:Name=\"Facturación\"><Table><Row>" + "".join(f"<Cell><Data ss:Type=\"String\">{h}</Data></Cell>" for h in encabezados) + "</Row>" + filas_html + "</Table></Worksheet></Workbook>"
        respuesta = HttpResponse(cuerpo, content_type="application/vnd.ms-excel")
        respuesta["Content-Disposition"] = 'attachment; filename="historial-facturacion.xls"'
        return respuesta
    if formato == "pdf":
        texto = "Historial de facturación\n" + "\n".join(" | ".join(str(v) for v in fila) for fila in filas)
        contenido = _pdf_texto(texto)
        respuesta = HttpResponse(contenido, content_type="application/pdf")
        respuesta["Content-Disposition"] = 'attachment; filename="historial-facturacion.pdf"'
        return respuesta
    return HttpResponse("Formato no soportado.", status=404)


def _pdf_texto(texto):
    return crear_pdf_texto(texto)


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
