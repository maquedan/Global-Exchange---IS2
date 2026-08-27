"""Ambiente de PRODUCCIÓN."""
from .base import *  # noqa

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# Seguridad (activar SSL_REDIRECT cuando haya HTTPS real)
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("DJANGO_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("DJANGO_COOKIE_SECURE", default=False)
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=0)
X_FRAME_OPTIONS = "DENY"

# Email real (verificación de correo)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
