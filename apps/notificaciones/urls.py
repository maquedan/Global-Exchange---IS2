from django.urls import path

from . import views

app_name = "notificaciones"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/marcar-leida/", views.marcar_leida, name="marcar_leida"),
]
