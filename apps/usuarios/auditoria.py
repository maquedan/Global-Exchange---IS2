from .models import RegistroAuditoria


def registrar_auditoria(usuario, accion, detalles=""):
    """Guarda el actor y una copia de su nombre para preservar el historial."""
    RegistroAuditoria.objects.create(
        usuario=usuario,
        usuario_nombre=usuario.get_username(),
        accion=accion,
        detalles=detalles,
    )
