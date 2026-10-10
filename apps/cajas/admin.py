from django.contrib import admin

from .models import (
    Caja,
    ConteoInventarioBilletes,
    DenominacionBillete,
    DetalleConteoInventarioBilletes,
    DetalleMovimientoBillete,
    FondoCajero,
    InventarioBilleteCaja,
    InventarioBilleteCajero,
    MovimientoCaja,
    SaldoCaja,
    Sucursal,
)


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


@admin.register(DenominacionBillete)
class DenominacionBilleteAdmin(admin.ModelAdmin):
    list_display = ("moneda", "valor")
    list_filter = ("moneda",)
    ordering = ("moneda__codigo", "-valor")


@admin.register(InventarioBilleteCaja)
class InventarioBilleteCajaAdmin(SoloLecturaAdmin):
    list_display = ("caja", "denominacion", "cantidad")
    list_filter = ("denominacion__moneda", "caja__sucursal")
    readonly_fields = ("caja", "denominacion", "cantidad")


@admin.register(InventarioBilleteCajero)
class InventarioBilleteCajeroAdmin(SoloLecturaAdmin):
    list_display = ("caja", "cajero", "denominacion", "cantidad")
    list_filter = ("denominacion__moneda", "caja__sucursal")
    readonly_fields = ("caja", "cajero", "denominacion", "cantidad")


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


@admin.register(DetalleMovimientoBillete)
class DetalleMovimientoBilleteAdmin(SoloLecturaAdmin):
    list_display = ("movimiento", "denominacion", "cantidad")
    list_filter = ("denominacion__moneda",)
    readonly_fields = ("movimiento", "denominacion", "cantidad")


@admin.register(ConteoInventarioBilletes)
class ConteoInventarioBilletesAdmin(SoloLecturaAdmin):
    list_display = ("creado_en", "caja", "moneda", "cajero", "importe_total", "realizado_por")
    list_filter = ("moneda", "caja__sucursal")
    readonly_fields = tuple(field.name for field in ConteoInventarioBilletes._meta.fields)


@admin.register(DetalleConteoInventarioBilletes)
class DetalleConteoInventarioBilletesAdmin(SoloLecturaAdmin):
    list_display = ("conteo", "denominacion", "cantidad")
    list_filter = ("denominacion__moneda",)
    readonly_fields = ("conteo", "denominacion", "cantidad")
