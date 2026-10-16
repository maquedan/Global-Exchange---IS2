from django.urls import path

from . import views

app_name = "cajas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("historial/", views.historial_movimientos, name="historial_movimientos"),
    path("arqueo/", views.arqueo_view, name="arqueo"),
    path("diferencias/", views.registrar_diferencia_view, name="diferencias"),
    path("diferencias/<int:pk>/ajustar/", views.autorizar_ajuste_view, name="autorizar_ajuste"),
    path("sucursales/<int:pk>/", views.detalle, name="detalle"),
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
    path("mis-existencias/", views.mis_existencias, name="mis_existencias"),
]
