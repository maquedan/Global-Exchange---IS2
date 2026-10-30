from django.urls import path

from . import views

app_name = "terminal"

urlpatterns = [
    path("", views.inicio_terminal, name="inicio"),
    path("identificar/", views.identificar_cliente_terminal, name="identificar"),
    path("operacion/", views.seleccionar_operacion_terminal, name="seleccionar_operacion"),
    path("datos-operacion/", views.datos_operacion_terminal, name="datos_operacion"),
    path("simulacion/", views.simulacion_terminal, name="simulacion"),
    path("confirmar/", views.confirmar_operacion_terminal, name="confirmar_operacion"),
    path("operacion-pendiente/", views.operacion_pendiente_terminal, name="operacion_pendiente"),
    path("reiniciar/", views.reiniciar_terminal, name="reiniciar"),
]