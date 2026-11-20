"""Aplica parámetros de sesión modificables sin reiniciar Django."""
from django.conf import settings

from .models import ConfiguracionSeguridad


class ConfiguracionSesionMiddleware:
    """Renueva el vencimiento con el valor vigente en cada solicitud autenticada."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated:
            configuracion = ConfiguracionSeguridad.objects.filter(pk=1).first()
            tiempo_segundos = (
                configuracion.tiempo_inactividad_minutos * 60
                if configuracion
                else settings.SESSION_COOKIE_AGE
            )
            request.session.set_expiry(tiempo_segundos)

        return self.get_response(request)
