from django.contrib import admin

from .models import Caja, FondoCajero, MovimientoCaja, SaldoCaja, Sucursal


class SoloLecturaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "direccion", "activa", "creada_en")
    list_filter = ("activa",)
    search_fields = ("nombre", "direccion")
    readonly_fields = ("creada_en",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        Caja.objects.get_or_create(sucursal=obj)


@admin.register(Caja)
class CajaAdmin(SoloLecturaAdmin):
    list_display = ("sucursal", "creada_en")
    readonly_fields = ("sucursal", "creada_en")


@admin.register(SaldoCaja)
class SaldoCajaAdmin(SoloLecturaAdmin):
    list_display = ("caja", "moneda", "saldo")
    readonly_fields = ("caja", "moneda", "saldo")


@admin.register(FondoCajero)
class FondoCajeroAdmin(SoloLecturaAdmin):
    list_display = ("caja", "cajero", "moneda", "saldo")
    readonly_fields = ("caja", "cajero", "moneda", "saldo")


@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(SoloLecturaAdmin):
    list_display = (
        "creado_en",
        "caja",
        "tipo",
        "moneda",
        "importe",
        "cajero",
        "realizado_por",
    )
    list_filter = ("tipo", "moneda", "caja__sucursal")
    search_fields = ("caja__sucursal__nombre", "cajero__username", "nota")
    readonly_fields = tuple(field.name for field in MovimientoCaja._meta.fields)
