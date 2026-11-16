"""Deja el menú principal disponible en TODAS las plantillas.

Sin esto tendríamos que pasar el menú a mano en cada vista.
Se registra en la lista "context_processors" de config/settings/base.py.
"""
from django.contrib.auth.models import AnonymousUser

from .menu import construir_menu
from .services import clientes_del_usuario


def menu_principal(request):
    usuario = getattr(request, "user", None) or AnonymousUser()

    # Cliente con el que se está operando, para mostrarlo en la barra
    # superior (RF008). Lo resuelve el middleware en cada request.
    cliente_activo = getattr(request, "cliente_activo", None)

    # Cuántos clientes activos tiene asociados. Una sola consulta, porque de
    # este número salen tres cosas distintas.
    cantidad_clientes = (
        clientes_del_usuario(usuario).count() if usuario.is_authenticated else 0
    )

    contexto = {
        "cliente_activo": cliente_activo,
        # Quien no tiene ningún cliente no ve las opciones de operar (RF010).
        # Ojo: se mira la cantidad, no `cliente_activo`. Quien tiene varios y
        # todavía no eligió sí las ve, porque al tocarlas el middleware lo
        # lleva a elegir; ocultárselas lo dejaría encerrado.
        "menu_principal": construir_menu(usuario, puede_operar=cantidad_clientes > 0),
        # ¿Tiene sentido ofrecerle cambiar de cliente? Solo si tiene más de
        # uno: con uno solo la pantalla de selección no tendría qué elegir.
        "puede_cambiar_cliente": cantidad_clientes > 1,
        # Tiene clientes pero todavía no eligió: hay que ofrecerle el acceso
        # a la pantalla de selección en la barra superior.
        "debe_elegir_cliente": cliente_activo is None and cantidad_clientes > 0,
    }

    # Contador de notificaciones no leídas para el badge del menú (RF033).
    contexto["notificaciones_no_leidas"] = 0
    if usuario.is_authenticated:
        from apps.notificaciones.models import Notificacion

        contexto["notificaciones_no_leidas"] = Notificacion.objects.filter(
            usuario=usuario, leida=False
        ).count()

    return contexto
