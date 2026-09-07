from django.contrib import admin

from .models import CuentaPago


@admin.register(CuentaPago)
class CuentaPagoAdmin(admin.ModelAdmin):
    list_display = ("cliente", "tipo", "entidad", "numero_cuenta", "titular", "activa", "creado_en")
    list_filter = ("tipo", "activa")
    search_fields = ("cliente__nombres", "cliente__razon_social", "entidad", "numero_cuenta", "titular")
    readonly_fields = ("creado_en",)
