"""Filtros de presentación del módulo de usuarios."""
from django import template

register = template.Library()


@register.filter
def get_item(diccionario, clave):
    """Obtiene una clave de un diccionario sin romper si no existe."""
    return diccionario.get(clave, set())
