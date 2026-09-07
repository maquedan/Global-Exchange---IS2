from django.urls import path

from . import views

app_name = "tasa_cambios"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nueva/", views.crear, name="crear"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/desactivar/", views.desactivar, name="desactivar"),
    path("<int:pk>/activar/", views.activar, name="activar"),
]