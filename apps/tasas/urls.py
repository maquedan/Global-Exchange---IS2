from django.urls import path

from . import views

app_name = "tasas"

urlpatterns = [
    path("", views.panel, name="panel"),
    path("datos/", views.datos_actuales, name="datos_actuales"),
]
