from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    # Autenticación con Keycloak
    path("oidc/", include("mozilla_django_oidc.urls")),
    # Apps del proyecto (se agregan en la Fase 2)
    # path("", include("apps.clientes.urls")),
]
