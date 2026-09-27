from django.urls import path

from . import views

app_name = "conversiones"

urlpatterns = [
    path("simular/", views.simular, name="simular"),
    path("comprar/", views.comprar, name="comprar"),
    path("compras/<int:pk>/", views.comprobante_compra, name="comprobante_compra"),
]
