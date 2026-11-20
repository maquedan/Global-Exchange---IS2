from datetime import date
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.http import HttpResponse
from django.shortcuts import render

from apps.usuarios.menu import tiene_rol

from .services import resumen_ganancias
from .forms import FiltrosGananciasForm
from apps.comun.exportaciones import crear_pdf_reporte, crear_xlsx, fecha_generacion


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
    formulario = FiltrosGananciasForm(request.GET or None)
    datos = formulario.cleaned_data if formulario.is_valid() else {}
    resumen = resumen_ganancias(datos.get("fecha_desde"), datos.get("fecha_hasta"), datos.get("moneda"), datos.get("estado"))
    return {
        "resumen": resumen,
        "formulario": formulario,
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


@login_required
@requiere_acceso_ganancias
def exportar(request, formato):
    resumen = _contexto(request)["resumen"]
    encabezados = ["Moneda", "Comisiones", "Diferencia de tasa", "Total"]
    filas = [[i["moneda"], i["comision"], i["diferencia_tasa"], i["total"]] for i in resumen["desglose"]]
    totales = {"Operaciones": resumen["operaciones"], "Comisiones": resumen["total"]["comision"], "Diferencia de tasa": resumen["total"]["diferencia_tasa"], "Ganancia total": resumen["total"]["total"], "Fecha de generación": fecha_generacion()}
    if formato == "excel":
        respuesta = HttpResponse(crear_xlsx("Ganancias", encabezados, filas, totales, {1, 2, 3}), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        respuesta["Content-Disposition"] = 'attachment; filename="reporte-ganancias.xlsx"'
        return respuesta
    if formato == "pdf":
        respuesta = HttpResponse(crear_pdf_reporte("Reporte de ganancias", encabezados, filas, totales), content_type="application/pdf")
        respuesta["Content-Disposition"] = 'attachment; filename="reporte-ganancias.pdf"'
        return respuesta
    return HttpResponse("Formato no soportado.", status=404)
