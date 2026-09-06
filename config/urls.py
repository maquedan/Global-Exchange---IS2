from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Autenticación con Keycloak: /oidc/authenticate/, /oidc/callback/, /oidc/logout/
    path("oidc/", include("mozilla_django_oidc.urls")),
    # Apps del proyecto
    path("", include("apps.usuarios.urls")),
    path("clientes/", include("apps.clientes.urls")),  # Registro de Clientes - GEG9-11
    path("cuentas/", include("apps.cuentas.urls")),  # Registro de Cuentas de Pago - GEG9-30
    path("monedas/", include("apps.monedas.urls")), # Administración de Monedas - GEG9-26
    path("tasas-cambio/", include("apps.tasa_cambios.urls")),
    path("tasas/", include("apps.tasas.urls")),  # Visualización de Tasas - GEG9-28
    path("conversiones/", include("apps.conversiones.urls")),
]