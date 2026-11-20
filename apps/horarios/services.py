from django.utils import timezone

from .models import RangoHorario


MENSAJE_FUERA_DE_HORARIO = (
    "Las operaciones de compra y venta no están disponibles fuera del horario "
    "operativo. La consulta de tasas y la simulación siguen disponibles."
)


class FueraDeHorarioOperativo(Exception):
    """Se intentó iniciar o confirmar una operación fuera del horario."""


def horario_operativo_abierto(instante=None):
    """Indica si el instante está dentro de alguno de los rangos configurados.

    Sin configuración todavía, se conserva la operación abierta para permitir
    la puesta en marcha del sistema. En cuanto existe un rango, los días y
    horarios no configurados quedan cerrados.
    """
    instante = instante or timezone.localtime()
    rangos = RangoHorario.objects.filter(dia=instante.weekday())
    if not RangoHorario.objects.exists():
        return True
    hora = instante.time()
    return rangos.filter(hora_desde__lte=hora, hora_hasta__gt=hora).exists()


def exigir_horario_operativo(instante=None):
    if not horario_operativo_abierto(instante):
        raise FueraDeHorarioOperativo(MENSAJE_FUERA_DE_HORARIO)
