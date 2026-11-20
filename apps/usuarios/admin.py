from django.contrib import admin

from .menu import tiene_rol
from .models import PermisoRol, PermisoSistema, RegistroAuditoria


@admin.register(PermisoSistema)
class PermisoSistemaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "descripcion")
    search_fields = ("codigo", "nombre")


@admin.register(PermisoRol)
class PermisoRolAdmin(admin.ModelAdmin):
    list_display = ("rol", "permiso")
    list_filter = ("rol",)
    search_fields = ("rol", "permiso__codigo")


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "usuario_nombre", "accion", "detalles")
    list_filter = ("accion", "creado_en")
    search_fields = ("usuario_nombre", "detalles")
    readonly_fields = ("usuario", "usuario_nombre", "accion", "detalles", "creado_en")

    def has_view_permission(self, request, obj=None):
        return tiene_rol(request.user, "administrador")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
