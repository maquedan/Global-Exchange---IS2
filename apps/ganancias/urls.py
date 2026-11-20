from django.urls import path

from . import views

app_name = "ganancias"

urlpatterns = [
    path("", views.panel, name="panel"),
    path("datos/", views.datos, name="datos"),
]
