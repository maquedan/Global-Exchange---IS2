from django.urls import path

from . import views

app_name = "pagos"

urlpatterns = [
    path("elegir/<int:compra_pk>/", views.elegir_pago, name="elegir_pago"),
    path(
        "elegir/<int:compra_pk>/transferencia/",
        views.esperar_transferencia,
        name="esperar_transferencia",
    ),
    path("<int:pk>/esperando/", views.esperando, name="esperando"),
    path("<int:pk>/retorno/", views.retorno, name="retorno"),
    path("<int:pk>/simulado/aprobar/", views.simulado_aprobar, name="simulado_aprobar"),
    path("<int:pk>/simulado/rechazar/", views.simulado_rechazar, name="simulado_rechazar"),
]
