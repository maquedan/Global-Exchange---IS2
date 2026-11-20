from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.usuarios.auditoria import registrar_auditoria
from apps.usuarios.menu import tiene_rol
from apps.usuarios.models import RegistroAuditoria

from .forms import ComisionCategoriaForm
from .models import ComisionCategoria


def es_administrador(usuario):
    """Indica si el usuario autenticado tiene el rol administrador."""
    return tiene_rol(usuario, "administrador")


def requiere_administrador(vista):
    """Restringe la configuración de comisiones al rol administrador."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_administrador(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_administrador
def lista(request):
    """Muestra las comisiones configuradas por categoría de cliente."""
    comisiones = ComisionCategoria.objects.all()
    return render(
        request,
        "comisiones/lista.html",
        {"comisiones": comisiones},
    )


@login_required
@requiere_administrador
def crear(request):
    """Registra el porcentaje de comisión para una categoría."""
    if request.method == "POST":
        formulario = ComisionCategoriaForm(request.POST)

        if formulario.is_valid():
            with transaction.atomic():
                comision = formulario.save()
                registrar_auditoria(
                    request.user,
                    RegistroAuditoria.Accion.COMISION_CREADA,
                    f"Categoría {comision.get_categoria_display()}; "
                    f"comisión {comision.porcentaje} %.",
                )
            messages.success(request, "Comisión configurada correctamente.")
            return redirect("comisiones:lista")
    else:
        formulario = ComisionCategoriaForm()

    return render(
        request,
        "comisiones/formulario.html",
        {"formulario": formulario, "accion": "Configurar"},
    )


@login_required
@requiere_administrador
def editar(request, pk):
    """Actualiza el porcentaje de una comisión existente."""
    comision = get_object_or_404(ComisionCategoria, pk=pk)

    if request.method == "POST":
        formulario = ComisionCategoriaForm(request.POST, instance=comision)

        if formulario.is_valid():
            porcentaje_anterior = comision.porcentaje
            categoria_anterior = comision.categoria
            with transaction.atomic():
                comision = formulario.save()
                if (
                    comision.porcentaje != porcentaje_anterior
                    or comision.categoria != categoria_anterior
                ):
                    registrar_auditoria(
                        request.user,
                        RegistroAuditoria.Accion.COMISION_MODIFICADA,
                        f"Categoría {categoria_anterior} → {comision.categoria}; "
                        f"comisión {porcentaje_anterior} % → {comision.porcentaje} %.",
                    )
            messages.success(request, "Comisión actualizada correctamente.")
            return redirect("comisiones:lista")
    else:
        formulario = ComisionCategoriaForm(instance=comision)

    return render(
        request,
        "comisiones/formulario.html",
        {"formulario": formulario, "accion": "Actualizar"},
    )