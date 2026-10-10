from django.urls import path

from . import views

app_name = "cajas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("sucursales/nueva/", views.crear_sucursal, name="crear_sucursal"),
    path("sucursales/<int:pk>/", views.detalle, name="detalle"),
    path("sucursales/<int:pk>/editar/", views.editar_sucursal, name="editar_sucursal"),
    path(
        "sucursales/<int:pk>/movimientos/",
        views.registrar_movimiento_view,
        name="registrar_movimiento",
    ),
    path(
        "sucursales/<int:pk>/denominaciones/",
        views.registrar_denominacion_view,
        name="registrar_denominacion",
    ),
    path(
        "sucursales/<int:pk>/denominaciones/<int:denominacion_pk>/editar/",
        views.editar_denominacion_view,
        name="editar_denominacion",
    ),
    path(
        "sucursales/<int:pk>/denominaciones/<int:denominacion_pk>/eliminar/",
        views.eliminar_denominacion_view,
        name="eliminar_denominacion",
    ),
    path(
        "sucursales/<int:pk>/conteos/",
        views.registrar_conteo_view,
        name="registrar_conteo",
    ),
]
