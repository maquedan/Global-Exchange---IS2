from django.urls import path

from . import views

app_name = "conversiones"

urlpatterns = [
    path("simular/", views.simular, name="simular"),
    path("comprar/", views.comprar, name="comprar"),
    path(
        "compras-administracion/",
        views.compras_administracion_view,
        name="compras_administracion",
    ),
    path("compras/<int:pk>/", views.comprobante_compra, name="comprobante_compra"),
    path("compras/<int:pk>/confirmar/", views.confirmar_compra_view, name="confirmar_compra"),
    path("compras/<int:pk>/cancelar/", views.cancelar_compra_view, name="cancelar_compra"),
    path("compras/<int:pk>/anular/", views.anular_compra_view, name="anular_compra"),
    path(
        "compras-pendientes/",
        views.compras_pendientes_view,
        name="compras_pendientes",
    ),
    path(
        "compras/<int:pk>/recibir-efectivo/",
        views.confirmar_compra_efectivo_view,
        name="confirmar_compra_efectivo",
    ),
    path("vender/", views.vender, name="vender"),
    path(
        "ventas-administracion/",
        views.ventas_administracion_view,
        name="ventas_administracion",
    ),
    path("ventas/<int:pk>/", views.comprobante_venta, name="comprobante_venta"),
    path("ventas-pendientes/", views.ventas_pendientes_view, name="ventas_pendientes"),
    path(
        "ventas/<int:pk>/entregar-efectivo/",
        views.confirmar_venta_view,
        name="confirmar_venta",
    ),
    path("ventas/<int:pk>/cancelar/", views.cancelar_venta_view, name="cancelar_venta"),
    path("ventas/<int:pk>/anular/", views.anular_venta_view, name="anular_venta"),
    path("historial/", views.historial, name="historial"),
    path(
        "reporte-transacciones/",
        views.reporte_transacciones,
        name="reporte_transacciones",
    ),
    path("conciliaciones/", views.conciliaciones, name="conciliaciones"),
    path("conciliaciones/<int:pk>/", views.conciliar, name="conciliar"),
]
