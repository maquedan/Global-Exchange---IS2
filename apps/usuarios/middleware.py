"""Middleware del cliente activo (RF008 — GEG9-18).

Hace dos cosas en cada request, para no repetir lo mismo en cada vista:

1. Deja `request.cliente_activo` disponible en todas partes (vistas,
   plantillas vía el context processor). Es `None` si el usuario no tiene
   clientes asociados, o si tiene varios y todavía no eligió.
2. Manda a la pantalla de selección a quien quiera **operar** sin haber
   elegido.

Sobre el punto 2: se redirige solo en las rutas que de verdad operan en
nombre de un cliente (comprar, vender, medios de pago, pagos), no en toda
la aplicación. Un administrador o analista puede estar asociado a clientes
y aun así entrar a las pantallas de administración sin que se le pida
elegir uno: esas pantallas no operan en nombre de nadie.
"""
from django.shortcuts import redirect
from django.urls import reverse

from .services import cliente_activo_de, clientes_del_usuario

# Rutas que operan en nombre de un cliente y por lo tanto necesitan uno
# elegido. El resto de la aplicación (consultas, administración, login)
# funciona igual sin elegir.
PREFIJOS_QUE_NECESITAN_CLIENTE = (
    "/conversiones/",
    "/cuentas/",
    "/pagos/",
)


class ClienteActivoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.cliente_activo = cliente_activo_de(request)

        if self._hay_que_pedir_seleccion(request):
            destino = reverse("usuarios:seleccionar_cliente")
            return redirect(f"{destino}?siguiente={request.path}")

        return self.get_response(request)

    def _hay_que_pedir_seleccion(self, request):
        if request.cliente_activo is not None:
            return False

        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated:
            return False

        if not request.path.startswith(PREFIJOS_QUE_NECESITAN_CLIENTE):
            return False

        # Sin ningún cliente asociado no hay nada para elegir: mandarlo a la
        # pantalla de selección sería dejarlo en un callejón sin salida. Ese
        # caso lo corta `requiere_cliente_activo` con un mensaje claro.
        return clientes_del_usuario(usuario).exists()
