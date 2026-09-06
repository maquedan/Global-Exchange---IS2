from django.urls import path

from . import views

app_name = "monedas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nueva/", views.crear, name="crear"),
    path("inactivas/", views.inactivas, name="inactivas"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/desactivar/", views.desactivar, name="desactivar"),
    path("<int:pk>/activar/", views.activar, name="activar"),
]