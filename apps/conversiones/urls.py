from django.urls import path

from . import views

app_name = "conversiones"

urlpatterns = [
    path("simular/", views.simular, name="simular"),
    path("comprar/", views.comprar, name="comprar"),
    path("compras/<int:pk>/", views.comprobante_compra, name="comprobante_compra"),
    path("compras/<int:pk>/confirmar/", views.confirmar_compra_view, name="confirmar_compra"),
    path("compras/<int:pk>/cancelar/", views.cancelar_compra_view, name="cancelar_compra"),
    path("vender/", views.vender, name="vender"),
    path("ventas/<int:pk>/", views.comprobante_venta, name="comprobante_venta"),
    path("ventas/<int:pk>/confirmar/", views.confirmar_venta_view, name="confirmar_venta"),
    path("ventas/<int:pk>/cancelar/", views.cancelar_venta_view, name="cancelar_venta"),
    path("historial/", views.historial, name="historial"),
]
