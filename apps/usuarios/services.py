"""Cliente activo de la sesión (RF008 — GEG9-18).

Un usuario puede estar asociado a varios clientes (RF007). Antes de operar
tiene que elegir en nombre de cuál lo hace, y esa elección vive en la
**sesión**, nunca en la base: es una preferencia del momento, no un dato del
negocio.

Toda la lógica está acá para que las vistas solo llamen a funciones, y para
que RF009 (cambiar de cliente sin cerrar sesión) sea reutilizar lo mismo.
"""
from functools import wraps

from django.shortcuts import redirect

from apps.clientes.models import Cliente

# Clave bajo la que se guarda la elección en la sesión.
CLAVE_SESION = "cliente_activo_id"


class ClienteNoDisponible(Exception):
    """El cliente pedido no existe, no está activo o no es de este usuario."""


class ClienteNoHabilitado(Exception):
    """El usuario no puede operar en nombre de ese cliente (RF010 — GEG9-20).

    Es la defensa en profundidad de la capa de servicios: las vistas ya
    bloquean con `requiere_cliente_para_operar`, pero un servicio tiene que
    poder negarse por su cuenta, sin depender de que lo llamen desde una
    vista bien decorada.
    """


def cliente_habilitado_para(usuario, cliente_id):
    """Devuelve el cliente si el usuario puede operar en su nombre.

    Exige las dos condiciones a la vez, que son las que `clientes_del_usuario`
    ya usa: que exista la asociación (RF007) y que el cliente esté activo
    (RF003). Levanta `ClienteNoHabilitado` si falta alguna.
    """
    cliente = clientes_del_usuario(usuario).filter(pk=cliente_id).first()
    if cliente is None:
        raise ClienteNoHabilitado(
            "No podés operar en nombre de ese cliente: o tu cuenta no está "
            "asociada a él, o el cliente fue dado de baja."
        )
    return cliente


def clientes_del_usuario(usuario):
    """Clientes activos asociados al usuario, para elegir con cuál operar."""
    if usuario is None or not usuario.is_authenticated:
        return Cliente.objects.none()
    return Cliente.objects.filter(
        asociaciones_usuarios__usuario=usuario,
        activo=True,
    ).distinct()


def elegir_cliente(request, cliente_id):
    """Guarda en la sesión el cliente con el que se va a operar.

    El id viene de un formulario, así que **nunca se confía en él**: se
    busca entre los clientes del propio usuario antes de guardarlo. Si no
    está entre ellos, se rechaza.
    """
    cliente = clientes_del_usuario(request.user).filter(pk=cliente_id).first()
    if cliente is None:
        raise ClienteNoDisponible("Ese cliente no está disponible para vos.")

    request.session[CLAVE_SESION] = cliente.pk
    return cliente


def olvidar_cliente(request):
    """Borra la elección. Lo usa RF009 para volver a pedirla."""
    request.session.pop(CLAVE_SESION, None)


def cliente_activo_de(request):
    """Cliente activo de esta sesión, revalidado contra la base en cada request.

    Devuelve `None` si el usuario no tiene ninguno asociado, o si tiene
    varios y todavía no eligió. Si el que estaba guardado ya no sirve
    (lo dieron de baja con RF003, o lo desvincularon), se limpia la
    elección para que se vuelva a pedir.

    Con un solo cliente asociado no se le pregunta nada a nadie: se elige
    solo.
    """
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return None

    disponibles = clientes_del_usuario(usuario)
    guardado_id = request.session.get(CLAVE_SESION)

    if guardado_id is not None:
        cliente = disponibles.filter(pk=guardado_id).first()
        if cliente is not None:
            return cliente
        olvidar_cliente(request)

    if disponibles.count() == 1:
        cliente = disponibles.first()
        request.session[CLAVE_SESION] = cliente.pk
        return cliente

    return None


def requiere_cliente_activo(vista):
    """Corta una vista operativa si no hay cliente activo.

    El middleware ya manda a elegir a quien tiene clientes y no eligió, así
    que acá solo cae el usuario **sin ningún cliente asociado**.

    Desde RF010 (GEG9-20) el bloqueo no vuelve al panel con un mensaje
    suelto: manda a la pantalla que explica qué sí puede hacer y cómo pedir
    la asociación. Es un alias de `requiere_cliente_para_operar`, que hace
    exactamente lo mismo; se conserva el nombre porque RF008 ya lo usa en
    varias vistas.
    """
    return requiere_cliente_para_operar(vista)


def requiere_cliente_para_operar(vista):
    """Deja operar solo a quien tenga un cliente habilitado (RF010 — GEG9-20).

    El ERS pide limitar al usuario no asociado a un cliente "únicamente a
    funciones de consulta". Esta es la parte de servidor de esa regla: corta
    tanto el GET como el POST, así que escribir la URL a mano o mandar el
    formulario por fuera no sirve de nada.

    Se apoya en `request.cliente_activo` (RF008), que ya es `None` tanto
    para el usuario sin clientes como para aquel cuyo cliente fue dado de
    baja, así que los dos casos quedan cubiertos con la misma pieza.

    Administradores y analistas no se ven afectados: no se aplica a las
    vistas de administración, que tienen su propio control de rol (RF011).
    """

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if getattr(request, "cliente_activo", None) is None:
            return redirect("usuarios:sin_cliente")
        return vista(request, *args, **kwargs)

    return envoltura
