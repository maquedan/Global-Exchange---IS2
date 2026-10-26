from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path("elegir-cliente/", views.seleccionar_cliente, name="seleccionar_cliente"),
    path("administracion/roles-permisos/", views.roles_permisos, name="roles_permisos"),
]
