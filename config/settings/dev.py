"""Ambiente de DESARROLLO."""
from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["*"]

# En desarrollo los correos (verificación) se muestran en la consola
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
