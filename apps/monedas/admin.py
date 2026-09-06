from django.contrib import admin

from .models import Moneda


@admin.register(Moneda)
class MonedaAdmin(admin.ModelAdmin):
    """Administración técnica de monedas para RF014."""

    list_display = (
        "codigo",
        "nombre",
        "simbolo",
        "activo",
        "actualizado_en",
    )
    list_filter = ("activo",)
    search_fields = ("codigo", "nombre", "simbolo")
    readonly_fields = ("creado_en", "actualizado_en")