from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render

from apps.usuarios.menu import tiene_rol

from .forms import AsociacionUsuarioClienteForm, ClienteForm
from .models import AsociacionUsuarioCliente, Cliente


def es_administrador(usuario):
    """Indica si el usuario autenticado posee el rol administrador."""
    return tiene_rol(usuario, "administrador")


def requiere_administrador(vista):
    """Restringe una vista a usuarios con el rol administrador."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_administrador(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


@login_required
@requiere_administrador
def lista(request):
    """Muestra los clientes activos registrados para RF001 — GEG9-11."""
    clientes = Cliente.objects.filter(activo=True)

    termino = (request.GET.get("q") or "").strip()
    categoria = request.GET.get("categoria") or ""
    tipo = request.GET.get("tipo") or ""

    if termino:
        clientes = clientes.filter(
            models.Q(nombres__icontains=termino)
            | models.Q(apellidos__icontains=termino)
            | models.Q(razon_social__icontains=termino)
            | models.Q(documento__icontains=termino)
            | models.Q(ruc__icontains=termino)
            | models.Q(email__icontains=termino)
        )

    if categoria:
        clientes = clientes.filter(categoria=categoria)

    if tipo:
        clientes = clientes.filter(tipo=tipo)

    return render(
        request,
        "clientes/lista.html",
        {
            "clientes": clientes,
            "filtros": {
                "q": termino,
                "categoria": categoria,
                "tipo": tipo,
            },
        },
    )


@login_required
@requiere_administrador
def eliminados(request):
    """Muestra los clientes que fueron dados de baja lógicamente."""
    clientes = Cliente.objects.filter(activo=False)
    return render(request, "clientes/eliminados.html", {"clientes": clientes})


@login_required
@requiere_administrador
def activar(request, pk):
    """Rehabilita un cliente que había sido dado de baja."""
    cliente = get_object_or_404(Cliente, pk=pk)
    cliente.activar()
    messages.success(request, f"Cliente {cliente} activado correctamente.")
    return redirect("clientes:eliminados")


@login_required
@requiere_administrador
def crear(request):
    """Registra un nuevo cliente persona física o jurídica."""
    if request.method == "POST":
        formulario = ClienteForm(request.POST)

        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Cliente registrado correctamente.")
            return redirect("clientes:lista")
    else:
        formulario = ClienteForm()

    return render(
        request,
        "clientes/formulario.html",
        {"formulario": formulario, "accion": "Registrar"},
    )


@login_required
@requiere_administrador
def editar(request, pk):
    """Modifica los datos de un cliente existente."""
    cliente = get_object_or_404(Cliente, pk=pk)

    if request.method == "POST":
        formulario = ClienteForm(request.POST, instance=cliente)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Cliente actualizado correctamente.")
            return redirect("clientes:lista")
    else:
        formulario = ClienteForm(instance=cliente)

    return render(
        request,
        "clientes/formulario.html",
        {"formulario": formulario, "accion": "Modificar"},
    )


@login_required
@requiere_administrador
def eliminar(request, pk):
    """Desactiva lógicamente un cliente."""
    cliente = Cliente.objects.get(pk=pk)
    cliente.desactivar()
    messages.success(request, f"Cliente {cliente} dado de baja lógicamente.")
    return redirect("clientes:lista")


@login_required
@requiere_administrador
def asociaciones(request):
    """Consulta y administra las asociaciones de RF007 — GEG9-17."""
    usuario_id = request.GET.get("usuario")

    if request.method == "POST":
        formulario = AsociacionUsuarioClienteForm(request.POST)
        if formulario.is_valid():
            usuario = formulario.cleaned_data["usuario"]
            clientes = formulario.cleaned_data["clientes"]
            ids_clientes = set(clientes.values_list("pk", flat=True))

            AsociacionUsuarioCliente.objects.filter(usuario=usuario).exclude(
                cliente_id__in=ids_clientes,
            ).delete()
            existentes = set(
                AsociacionUsuarioCliente.objects.filter(usuario=usuario).values_list(
                    "cliente_id",
                    flat=True,
                ),
            )
            AsociacionUsuarioCliente.objects.bulk_create(
                [
                    AsociacionUsuarioCliente(usuario=usuario, cliente=cliente)
                    for cliente in clientes
                    if cliente.pk not in existentes
                ],
            )
            messages.success(request, "Asociaciones actualizadas correctamente.")
            return redirect(f"{request.path}?usuario={usuario.pk}")
    else:
        inicial = {}
        if usuario_id:
            asociaciones_usuario = AsociacionUsuarioCliente.objects.filter(
                usuario_id=usuario_id,
            )
            inicial = {
                "usuario": usuario_id,
                "clientes": asociaciones_usuario.values_list("cliente_id", flat=True),
            }
        formulario = AsociacionUsuarioClienteForm(initial=inicial)

    asociaciones_existentes = AsociacionUsuarioCliente.objects.select_related(
        "usuario",
        "cliente",
    )
    return render(
        request,
        "clientes/asociaciones.html",
        {
            "formulario": formulario,
            "asociaciones": asociaciones_existentes,
        },
    )
