"""Deja el menú principal disponible en TODAS las plantillas.

Sin esto tendríamos que pasar el menú a mano en cada vista.
Se registra en la lista "context_processors" de config/settings/base.py.
"""
from django.contrib.auth.models import AnonymousUser

from .menu import construir_menu
from .services import clientes_del_usuario


def menu_principal(request):
    usuario = getattr(request, "user", None) or AnonymousUser()
    contexto = {"menu_principal": construir_menu(usuario)}

    # Cliente con el que se está operando, para mostrarlo en la barra
    # superior (RF008). Lo resuelve el middleware en cada request.
    contexto["cliente_activo"] = getattr(request, "cliente_activo", None)

    # ¿Tiene sentido ofrecerle cambiar de cliente? Solo si tiene más de uno:
    # con uno solo la pantalla de selección no tendría nada que elegir.
    contexto["puede_cambiar_cliente"] = (
        usuario.is_authenticated and clientes_del_usuario(usuario).count() > 1
    )

    # Contador de notificaciones no leídas para el badge del menú (RF033).
    contexto["notificaciones_no_leidas"] = 0
    if usuario.is_authenticated:
        from apps.notificaciones.models import Notificacion

        contexto["notificaciones_no_leidas"] = Notificacion.objects.filter(
            usuario=usuario, leida=False
        ).count()

    return contexto
