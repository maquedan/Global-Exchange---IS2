from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    """Administración de clientes para RF001 — GEG9-11."""

    list_display = (
        "tipo",
        "nombre_completo",
        "documento_o_ruc",
        "email",
        "telefono",
        "creado_en",
    )
    list_filter = ("tipo",)
    search_fields = (
        "nombres",
        "apellidos",
        "documento",
        "razon_social",
        "ruc",
        "email",
    )
    readonly_fields = ("creado_en",)

    @admin.display(description="Cliente")
    def nombre_completo(self, cliente):
        if cliente.tipo == Cliente.Tipo.FISICA:
            return f"{cliente.nombres} {cliente.apellidos}"
        return cliente.razon_social

    @admin.display(description="Documento / RUC")
    def documento_o_ruc(self, cliente):
        if cliente.tipo == Cliente.Tipo.FISICA:
            return cliente.documento
        return cliente.ruc