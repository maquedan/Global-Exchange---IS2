from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.panel, name="panel"),
    path(
        "cerrar-sesion-inactiva/",
        views.cerrar_sesion_por_inactividad,
        name="cerrar_sesion_inactividad",
    ),
    path("elegir-cliente/", views.seleccionar_cliente, name="seleccionar_cliente"),
    path("sin-cliente/", views.sin_cliente, name="sin_cliente"),
    path("administracion/roles-permisos/", views.roles_permisos, name="roles_permisos"),
]
