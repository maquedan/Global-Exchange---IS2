"""Cliente activo de la sesión (RF008 — GEG9-18).

Un usuario puede estar asociado a varios clientes (RF007). Antes de operar
tiene que elegir en nombre de cuál lo hace, y esa elección vive en la
**sesión**, nunca en la base: es una preferencia del momento, no un dato del
negocio.

Toda la lógica está acá para que las vistas solo llamen a funciones, y para
que RF009 (cambiar de cliente sin cerrar sesión) sea reutilizar lo mismo.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from apps.clientes.models import Cliente

# Clave bajo la que se guarda la elección en la sesión.
CLAVE_SESION = "cliente_activo_id"


class ClienteNoDisponible(Exception):
    """El cliente pedido no existe, no está activo o no es de este usuario."""


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
    que acá solo cae el usuario **sin ningún cliente asociado**. Ese caso lo
    resuelve RF010 (GEG9-20); por ahora no se lo deja operar, pero tampoco
    se rompe nada.
    """

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if getattr(request, "cliente_activo", None) is None:
            messages.error(
                request,
                "Todavía no tenés un cliente asociado para operar. "
                "Pedile a un administrador que te asocie uno.",
            )
            return redirect("usuarios:panel")
        return vista(request, *args, **kwargs)

    return envoltura
