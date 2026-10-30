from django.urls import path

from . import views

app_name = "facturacion"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/actualizar-estado/", views.actualizar_estado, name="actualizar_estado"),
    path("<int:pk>/reintentar/", views.reintentar, name="reintentar"),
    path("<int:pk>/descargar/pdf/", views.descargar_pdf, name="descargar_pdf"),
    path("<int:pk>/descargar/xml/", views.descargar_xml, name="descargar_xml"),
    path("exportar/<str:formato>/", views.exportar_historial, name="exportar_historial"),
]
