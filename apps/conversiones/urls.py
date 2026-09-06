from django.urls import path

from . import views

app_name = "conversiones"

urlpatterns = [
    path("simular/", views.simular, name="simular"),
]
