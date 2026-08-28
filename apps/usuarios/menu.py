"""Menú principal según el rol del usuario (GEG9-25).

El menú se define UNA sola vez acá y se arma solo para cada usuario según
los roles que trajo de Keycloak.
"""
from django.urls import NoReverseMatch, reverse

# "roles" vacío = lo ve cualquier usuario que haya iniciado sesión.
# "url" es el NOMBRE de la ruta (el name= de urls.py), no la dirección.
MENU_PRINCIPAL = [
    {"texto": "Panel", "url": "usuarios:panel", "roles": []},
    {
        "texto": "Clientes",
        "url": "clientes:lista",
        "roles": ["administrador", "analista_cambiario"],
    },
    {"texto": "Administración", "url": "admin:index", "roles": ["administrador"]},
]


def roles_de(usuario):
    """Roles del usuario. En Django los guardamos como Grupos."""
    if not usuario.is_authenticated:
        return set()
    return set(usuario.groups.values_list("name", flat=True))


def tiene_rol(usuario, *roles):
    """¿El usuario tiene AL MENOS uno de estos roles?"""
    return bool(roles_de(usuario) & set(roles))


def construir_menu(usuario):
    """Devuelve solo las opciones que este usuario puede ver."""
    if not usuario.is_authenticated:
        return []

    mis_roles = roles_de(usuario)
    visibles = []

    for opcion in MENU_PRINCIPAL:
        # 1) ¿Tiene el rol necesario?
        if opcion["roles"] and not (mis_roles & set(opcion["roles"])):
            continue
        # 2) ¿La ruta ya existe? Todavía no programamos el CRUD de Clientes,
        #    así que esa opción se saltea sola. Cuando creemos
        #    apps/clientes/urls.py va a aparecer en el menú sin tocar nada acá.
        try:
            direccion = reverse(opcion["url"])
        except NoReverseMatch:
            continue
        visibles.append({"texto": opcion["texto"], "url": direccion})

    return visibles
