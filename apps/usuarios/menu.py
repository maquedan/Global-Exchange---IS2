"""Menú principal según el rol del usuario (GEG9-25).

El menú se define UNA sola vez acá y se arma solo para cada usuario según
los roles que trajo de Keycloak.
"""
from django.urls import NoReverseMatch, reverse

# "roles" vacío = lo ve cualquier usuario que haya iniciado sesión.
# "necesita_cliente": la opción opera en nombre de un cliente, así que no
# se le muestra a quien no tiene ninguno asociado (RF010 — GEG9-20).
# "url" es el NOMBRE de la ruta (el name= de urls.py), no la dirección.
MENU_PRINCIPAL = [
    {"texto": "Panel", "url": "usuarios:panel", "roles": []},
    {"texto": "Cotizaciones", "url": "tasas:panel", "roles": []},
    {
        "texto": "Clientes",
        "url": "clientes:lista",
        "roles": ["administrador", "analista_cambiario"],
    },
        {
        "texto": "Monedas",
        "url": "monedas:lista",
        "roles": ["administrador"],
    },
    {
        "texto": "Tasas de cambio",
        "url": "tasa_cambios:lista",
        "roles": ["administrador", "analista_cambiario"],
    },
    {
        "texto": "Roles y permisos",
        "url": "usuarios:roles_permisos",
        "roles": ["administrador"],
    },
    {
        "texto": "Mis medios de pago",
        "necesita_cliente": True,
        "url": "cuentas:lista",
        "roles": ["usuario_cliente"],
    },
    {
        "texto": "Simular conversion",
        "url": "conversiones:simular",
        "roles": ["usuario_cliente"],
    },
    {
        "texto": "Comprar divisas",
        "necesita_cliente": True,
        "url": "conversiones:comprar",
        "roles": ["usuario_cliente"],
    },
    {
        "texto": "Vender divisas",
        "necesita_cliente": True,
        "url": "conversiones:vender",
        "roles": ["usuario_cliente"],
    },
    {
        "texto": "Comisiones",
        "url": "comisiones:lista",
        "roles": ["administrador"],
    },
    {
        "texto": "Caja principal",
        "url": "cajas:lista",
        "roles": ["administrador"],
    },
    {
        "texto": "Historial de caja",
        "url": "cajas:historial_movimientos",
        "roles": ["administrador"],
    },
    {
        "texto": "Arqueo de caja",
        "url": "cajas:arqueo",
        "roles": ["cajero"],
    },
    {
        "texto": "Diferencias de caja",
        "url": "cajas:diferencias",
        "roles": ["administrador"],
    },
    {
        "texto": "Mis existencias",
        "url": "cajas:mis_existencias",
        "roles": ["cajero"],
    },
    {
    "texto": "Historial de transacciones",
        "necesita_cliente": True,
    "url": "conversiones:historial",
    "roles": ["usuario_cliente"],
    },
    {
        "texto": "Notificaciones",
        "url": "notificaciones:lista",
        "roles": ["usuario_cliente"],
    },
    {
        "texto": "Mis facturas",
        "necesita_cliente": True,
        "url": "facturacion:lista",
        "roles": ["usuario_cliente"],
    },
    {
        "texto": "Facturas",
        "url": "facturacion:lista",
        "roles": ["administrador"],
    },
]


def roles_de(usuario):
    """Roles del usuario. En Django los guardamos como Grupos."""
    if not usuario.is_authenticated:
        return set()
    return set(usuario.groups.values_list("name", flat=True))


def tiene_rol(usuario, *roles):
    """¿El usuario tiene AL MENOS uno de estos roles?"""
    return bool(roles_de(usuario) & set(roles))


def tiene_permiso(usuario, codigo):
    """Indica si alguno de los roles del usuario habilita una funcionalidad.

    Las vistas nuevas pueden usar esta función para proteger una capacidad sin
    codificar roles concretos: el administrador cambia el vínculo en RF011.
    """
    if not usuario.is_authenticated:
        return False
    from .models import PermisoRol

    return PermisoRol.objects.filter(rol__in=roles_de(usuario), permiso__codigo=codigo).exists()


def construir_menu(usuario, cliente_activo=None):
    """Devuelve solo las opciones que este usuario puede ver.

    `cliente_activo` es el cliente con el que está operando (RF008). Si es
    `None`, se ocultan las opciones marcadas con `necesita_cliente`: son las
    que operan en nombre de un cliente y llevarían a un bloqueo (RF010).
    Ocultarlas es solo comodidad — el bloqueo de verdad está en las vistas.
    """
    if not usuario.is_authenticated:
        return []

    mis_roles = roles_de(usuario)
    visibles = []

    for opcion in MENU_PRINCIPAL:
        # 1) ¿Tiene el rol necesario?
        if opcion["roles"] and not (mis_roles & set(opcion["roles"])):
            continue
        # 2) ¿Opera en nombre de un cliente, y no tiene ninguno?
        if opcion.get("necesita_cliente") and cliente_activo is None:
            continue
        # 3) ¿La ruta ya existe? Todavía no programamos el CRUD de Clientes,
        #    así que esa opción se saltea sola. Cuando creemos
        #    apps/clientes/urls.py va a aparecer en el menú sin tocar nada acá.
        try:
            direccion = reverse(opcion["url"])
        except NoReverseMatch:
            continue
        visibles.append({"texto": opcion["texto"], "url": direccion})

    return visibles
