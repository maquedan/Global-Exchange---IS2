"""Deja el menú principal disponible en TODAS las plantillas.

Sin esto tendríamos que pasar el menú a mano en cada vista.
Se registra en la lista "context_processors" de config/settings/base.py.
"""
from django.contrib.auth.models import AnonymousUser

from .menu import construir_menu


def menu_principal(request):
    usuario = getattr(request, "user", None) or AnonymousUser()
    return {"menu_principal": construir_menu(usuario)}
