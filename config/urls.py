from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Autenticación con Keycloak: /oidc/authenticate/, /oidc/callback/, /oidc/logout/
    path("oidc/", include("mozilla_django_oidc.urls")),
    # Apps del proyecto
    path("", include("apps.usuarios.urls")),
    path("clientes/", include("apps.clientes.urls")),  # Registro de Clientes - GEG9-11
]