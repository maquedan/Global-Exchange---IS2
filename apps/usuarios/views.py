"""Vistas de autenticación y panel principal (GEG9-24, GEG9-25)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .keycloak_admin import KeycloakAdmin, KeycloakAdminError
from .menu import roles_de
from .models import PermisoRol, PermisoSistema


def inicio(request):
    """Página pública: solo el botón para iniciar sesión con Keycloak."""
    if request.user.is_authenticated:
        return redirect("usuarios:panel")
    return render(request, "usuarios/inicio.html")


@login_required
def panel(request):
    """Vista PROTEGIDA.

    El decorador @login_required es el que la protege: si entrás sin sesión,
    Django te manda a LOGIN_URL (= /oidc/authenticate/, o sea, a Keycloak) y
    después te trae de vuelta acá.
    """
    return render(
        request,
        "usuarios/panel.html",
        {"roles": sorted(roles_de(request.user))},
    )


def es_administrador(usuario):
    """Autoriza RF011 únicamente al rol administrador del realm."""
    return usuario.is_authenticated and "administrador" in roles_de(usuario)


@login_required
@user_passes_test(es_administrador)
@require_http_methods(["GET", "POST"])
def roles_permisos(request):
    """Panel RF011: roles en Keycloak y permisos funcionales en Django."""
    keycloak = KeycloakAdmin()
    try:
        if request.method == "POST":
            accion = request.POST.get("accion")
            if accion == "crear_rol":
                nombre = request.POST.get("nombre", "").strip()
                if not nombre:
                    messages.error(request, "El nombre del rol es obligatorio.")
                else:
                    keycloak.crear_rol(nombre, request.POST.get("descripcion", "").strip())
                    messages.success(request, f"Rol '{nombre}' creado en Keycloak.")
            elif accion == "eliminar_rol":
                nombre = request.POST.get("rol", "")
                keycloak.eliminar_rol(nombre)
                PermisoRol.objects.filter(rol=nombre).delete()
                messages.success(request, f"Rol '{nombre}' eliminado.")
            elif accion == "crear_permiso":
                codigo = request.POST.get("codigo", "").strip()
                nombre = request.POST.get("nombre_permiso", "").strip()
                if not codigo or not nombre:
                    messages.error(request, "Código y nombre del permiso son obligatorios.")
                elif PermisoSistema.objects.filter(codigo=codigo).exists():
                    messages.error(request, "Ya existe un permiso con ese código.")
                else:
                    PermisoSistema.objects.create(
                        codigo=codigo, nombre=nombre,
                        descripcion=request.POST.get("descripcion_permiso", "").strip(),
                    )
                    messages.success(request, f"Permiso '{codigo}' creado.")
            elif accion == "guardar_permisos":
                rol = request.POST.get("rol", "")
                permisos = PermisoSistema.objects.filter(pk__in=request.POST.getlist("permisos"))
                PermisoRol.objects.filter(rol=rol).delete()
                PermisoRol.objects.bulk_create([PermisoRol(rol=rol, permiso=p) for p in permisos])
                messages.success(request, f"Permisos de '{rol}' actualizados.")
            elif accion == "asignar_roles":
                keycloak.establecer_roles_usuario(
                    request.POST.get("usuario", ""), request.POST.getlist("roles")
                )
                messages.success(request, "Roles del usuario actualizados en Keycloak.")
            else:
                messages.error(request, "Acción no reconocida.")
            return redirect("usuarios:roles_permisos")

        roles = keycloak.listar_roles()
        permisos_por_rol = {
            rol["name"]: set(PermisoRol.objects.filter(rol=rol["name"]).values_list("permiso_id", flat=True))
            for rol in roles
        }
        return render(request, "usuarios/roles_permisos.html", {
            "roles": roles,
            "permisos": PermisoSistema.objects.all(),
            "permisos_por_rol": permisos_por_rol,
            "usuarios_keycloak": keycloak.listar_usuarios(),
        })
    except KeycloakAdminError as error:
        messages.error(request, str(error))
        return render(request, "usuarios/roles_permisos.html", {
            "roles": [], "permisos": PermisoSistema.objects.all(),
            "permisos_por_rol": {}, "usuarios_keycloak": [],
        }, status=503)
