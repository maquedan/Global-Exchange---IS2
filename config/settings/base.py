"""Configuración común a todos los ambientes."""
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(DJANGO_DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="clave-insegura-solo-dev")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "mozilla_django_oidc",
    # Apps del proyecto
    "apps.clientes",
    "apps.usuarios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.usuarios.context_processors.menu_principal",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ===== Autenticación con Keycloak (OIDC) =====
# Backend propio (apps/usuarios/auth.py): además de iniciar sesión, copia los
# roles del realm de Keycloak a los Grupos de Django.
AUTHENTICATION_BACKENDS = (
    "apps.usuarios.auth.KeycloakOIDCBackend",
    "django.contrib.auth.backends.ModelBackend",
)

# Keycloak se alcanza por DOS caminos distintos y a veces con nombres distintos:
#  - KEYCLOAK_SERVER_URL: lo abre el NAVEGADOR (pantalla de login y de logout).
#  - KEYCLOAK_INTERNAL_URL: lo llama DJANGO por detrás (canjear el código por
#    tokens, pedir los datos del usuario, bajar las claves públicas).
# Corriendo todo en tu máquina son iguales (localhost:8080). Dentro de Docker,
# el navegador sigue usando localhost:8080 pero Django tiene que usar
# http://keycloak:8080, que es el nombre del servicio en docker-compose.
KEYCLOAK_SERVER_URL = env("KEYCLOAK_SERVER_URL", default="http://localhost:8080")

# ¿Estamos adentro de un contenedor? El archivo /.dockerenv solo existe ahí.
# Si es así, Django tiene que llamar a Keycloak por el nombre del servicio de
# docker-compose; si no, por localhost. Así el proyecto anda igual corriendo
# con "docker compose up" que con "python manage.py runserver".
CORRIENDO_EN_DOCKER = Path("/.dockerenv").exists()
KEYCLOAK_INTERNAL_URL = env(
    "KEYCLOAK_INTERNAL_URL",
    default="http://keycloak:8080" if CORRIENDO_EN_DOCKER else KEYCLOAK_SERVER_URL,
)
KEYCLOAK_REALM = env("KEYCLOAK_REALM", default="global-exchange")

_OIDC = f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect"
_OIDC_INTERNO = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect"

OIDC_RP_CLIENT_ID = env("OIDC_RP_CLIENT_ID", default="global-exchange-web")
OIDC_RP_CLIENT_SECRET = env("OIDC_RP_CLIENT_SECRET", default="")
OIDC_RP_SIGN_ALGO = "RS256"
# Pedimos estos datos del usuario a Keycloak: correo, nombre y apellido.
OIDC_RP_SCOPES = "openid email profile"

# Los ve el navegador:
OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_OIDC}/auth"
OIDC_OP_LOGOUT_ENDPOINT = f"{_OIDC}/logout"
# Los llama Django por detrás:
OIDC_OP_TOKEN_ENDPOINT = f"{_OIDC_INTERNO}/token"
OIDC_OP_USER_ENDPOINT = f"{_OIDC_INTERNO}/userinfo"
OIDC_OP_JWKS_ENDPOINT = f"{_OIDC_INTERNO}/certs"

# Al cerrar sesión no alcanza con salir de Django: también hay que salir de
# Keycloak, si no volver a entrar es automático y parece que el logout falló.
OIDC_OP_LOGOUT_URL_METHOD = "apps.usuarios.auth.cerrar_sesion_en_keycloak"
# Guarda el id_token en la sesión; Keycloak lo pide para cerrar sesión.
OIDC_STORE_ID_TOKEN = True

# Crear el usuario en Django la primera vez que entra desde Keycloak.
OIDC_CREATE_USER = True

# A dónde manda Django a quien no inició sesión y entra a una vista protegida.
LOGIN_URL = "/oidc/authenticate/"
LOGIN_REDIRECT_URL = "/panel/"
LOGOUT_REDIRECT_URL = "/"

# ===== Roles del realm de Keycloak =====
# Roles internos que nunca se copian a Grupos de Django. Los demás roles del
# realm se sincronizan dinámicamente: así un rol creado desde RF011 queda
# disponible en la aplicación en el siguiente inicio de sesión.
ROLES_KEYCLOAK = ["administrador", "analista_cambiario", "usuario_cliente"]
ROLES_KEYCLOAK_INTERNOS = ["offline_access", "uma_authorization"]
ROL_ADMINISTRADOR = "administrador"

# Cliente de servicio usado exclusivamente por el panel RF011 para administrar
# el realm mediante la API de Keycloak. Su secreto no se versiona: el script
# scripts/sincronizar_secret.py lo carga en .env al preparar el ambiente.
KEYCLOAK_ADMIN_CLIENT_ID = env("KEYCLOAK_ADMIN_CLIENT_ID", default="global-exchange-admin")
KEYCLOAK_ADMIN_CLIENT_SECRET = env("KEYCLOAK_ADMIN_CLIENT_SECRET", default="")

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Asuncion"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# Archivos estáticos propios del proyecto (incluye el CSS compilado por Tailwind).
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
