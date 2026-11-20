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
        # Sin "necesita_cliente": el administrador no opera en nombre de un
        # cliente, y marcarla se la ocultaría por RF010 (GEG9-20).
        "texto": "Conciliar transferencias",
        "url": "conversiones:conciliaciones",
        "roles": ["administrador"],
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
        "texto": "Ventas y anulaciones",
        "url": "conversiones:ventas_administracion",
        "roles": ["administrador"],
    },
    {
        "texto": "Arqueo de caja",
        "url": "cajas:arqueo",
        "roles": ["cajero"],
    },
    {
        "texto": "Ventas pendientes",
        "url": "conversiones:ventas_pendientes",
        "roles": ["cajero"],
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


def construir_menu(usuario, puede_operar=False):
    """Devuelve solo las opciones que este usuario puede ver.

    `puede_operar` indica si el usuario tiene **al menos un cliente activo
    asociado**, no si ya eligió con cuál operar. La diferencia importa: quien
    tiene varios clientes y todavía no eligió sí debe ver las opciones de
    operar, porque al tocarlas el middleware de RF008 lo lleva a la pantalla
    de selección. Ocultárselas lo dejaría sin ninguna forma de llegar ahí.

    Las opciones marcadas con `necesita_cliente` se ocultan solo a quien no
    tiene ningún cliente (RF010). Es comodidad: el bloqueo de verdad está en
    las vistas.
    """
    if not usuario.is_authenticated:
        return []

    mis_roles = roles_de(usuario)

    if "terminal" in mis_roles:
        return [
            {"texto": "Panel", "url": reverse("usuarios:panel")},
            {"texto": "Terminal", "url": reverse("terminal:inicio")},
        ]

    visibles = []

    for opcion in MENU_PRINCIPAL:
        # 1) ¿Tiene el rol necesario?
        if opcion["roles"] and not (mis_roles & set(opcion["roles"])):
            continue
        # 2) ¿Opera en nombre de un cliente, y no tiene ninguno?
        if opcion.get("necesita_cliente") and not puede_operar:
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
