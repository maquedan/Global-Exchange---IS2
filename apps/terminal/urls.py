from django.urls import path

from . import views

app_name = "terminal"

urlpatterns = [
    path("", views.inicio_terminal, name="inicio"),
    path("reiniciar/", views.reiniciar_terminal, name="reiniciar"),
]