from django.contrib import admin

from .models import PermisoRol, PermisoSistema


@admin.register(PermisoSistema)
class PermisoSistemaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "descripcion")
    search_fields = ("codigo", "nombre")


@admin.register(PermisoRol)
class PermisoRolAdmin(admin.ModelAdmin):
    list_display = ("rol", "permiso")
    list_filter = ("rol",)
    search_fields = ("rol", "permiso__codigo")
