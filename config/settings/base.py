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
    "apps.cuentas",
    "apps.monedas",
    "apps.tasa_cambios",
    "apps.tasas",
    "apps.conversiones",
    "apps.comisiones",
    "apps.notificaciones",
    "apps.cajas",
    "apps.pagos",
    "apps.facturacion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Deja request.cliente_activo y manda a elegir antes de operar (RF008).
    # Va después del de autenticación: necesita request.user ya resuelto.
    "apps.usuarios.middleware.ClienteActivoMiddleware",
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
ROLES_KEYCLOAK = ["administrador", "analista_cambiario", "usuario_cliente", "cajero"]
ROLES_KEYCLOAK_INTERNOS = ["offline_access", "uma_authorization"]
ROL_ADMINISTRADOR = "administrador"

# Cliente de servicio usado exclusivamente por el panel RF011 para administrar
# el realm mediante la API de Keycloak. Su secreto no se versiona: el script
# scripts/sincronizar_secret.py lo carga en .env al preparar el ambiente.
KEYCLOAK_ADMIN_CLIENT_ID = env("KEYCLOAK_ADMIN_CLIENT_ID", default="global-exchange-admin")
KEYCLOAK_ADMIN_CLIENT_SECRET = env("KEYCLOAK_ADMIN_CLIENT_SECRET", default="")

# ===== Pasarela de pago (RF022 — GEG9-36) =====
# "dlocal" llama de verdad al sandbox de dLocal; "simulado" no toca la red
# (demos y tests). Si falta alguna credencial con PAGO_PROVEEDOR=dlocal, el
# proveedor lo avisa con un error claro al iniciar el pago, no con un
# traceback — ver apps/pagos/proveedores/dlocal.py.
PAGO_PROVEEDOR = env("PAGO_PROVEEDOR", default="simulado")
DLOCAL_X_LOGIN = env("DLOCAL_X_LOGIN", default="")
DLOCAL_X_TRANS_KEY = env("DLOCAL_X_TRANS_KEY", default="")
DLOCAL_SECRET_KEY = env("DLOCAL_SECRET_KEY", default="")
DLOCAL_BASE_URL = env("DLOCAL_BASE_URL", default="https://sandbox.dlocal.com")
# Para armar el callback_url absoluto al que dLocal devuelve al cliente
# después de pagar (apps/pagos/views.retorno). En Docker, el navegador
# siempre entra por localhost, nunca por el nombre interno del servicio.
SITE_BASE_URL = env("SITE_BASE_URL", default="http://localhost:8000")

# ===== Facturación electrónica (RF026 — GEG9-50) =====
# "facturasegura" llama de verdad al ambiente de pruebas de Factura Segura;
# "simulado" no toca la red (desarrollo, demo y tests).
# El `or` está en todas estas lecturas por el mismo motivo: una clave presente
# pero vacía (como queda al copiar .env.example) devuelve "" y no el default.
FACTURACION_PROVEEDOR = env("FACTURACION_PROVEEDOR", default="") or "simulado"
FACTURASEGURA_BASE_URL = (
    env("FACTURASEGURA_BASE_URL", default="")
    or "https://apitest.facturasegura.com.py/misife00/v1/esi"
)
# El token se genera una vez por ambiente y va SOLO en el .env, nunca acá.
FACTURASEGURA_TOKEN = env("FACTURASEGURA_TOKEN", default="")

# Numeración del documento. La secuencia de `dNumDoc` la lleva el modelo
# `SecuenciaFactura`, una por establecimiento + punto de expedición.
FACTURACION_ESTABLECIMIENTO = env("FACTURACION_ESTABLECIMIENTO", default="") or "001"
FACTURACION_PUNTO_EXPEDICION = env("FACTURACION_PUNTO_EXPEDICION", default="") or "001"
# Rango de números que la cátedra autorizó para este punto de expedición. La
# numeración arranca en DESDE (no en 1) y no pasa de HASTA: un `dNumDoc` fuera
# del rango lo rechaza el SIFEN. HASTA en 0 significa "sin límite".
#
# No se usa `env.int()`: esa función revienta con ValueError si la variable
# está presente pero vacía, y en .env.example estas dos claves van sin valor
# justamente para que cada uno complete el rango que le autorizaron. Quien
# copiara el .env.example tal cual no podía ni levantar Django.
def _entero_opcional(nombre):
    valor = env(nombre, default="").strip()
    return int(valor) if valor else 0


FACTURACION_NUMERO_DESDE = _entero_opcional("FACTURACION_NUMERO_DESDE") or 1
FACTURACION_NUMERO_HASTA = _entero_opcional("FACTURACION_NUMERO_HASTA")

# OJO: los datos del emisor que siguen son VALORES DE PRUEBA, puestos para
# poder desarrollar, hacer la demo con el proveedor simulado y correr los
# tests. Los reales dependen del emisor que la cátedra asocie a nuestro
# usuario ESI de Factura Segura y todavía no los tenemos: hasta completarlos
# en el .env, la factura NO sirve ante el SIFEN. Con
# FACTURACION_PROVEEDOR=facturasegura el cliente real se niega a emitir
# mientras sigan en estos valores (ver apps/facturacion/clientes/).
#
# Se usa `or` porque en .env.example estas claves están sin valor: si alguien
# copia el archivo tal cual, `env` devuelve "" y no el default.
FACTURACION_TIMBRADO = env("FACTURACION_TIMBRADO", default="") or "00000000"
FACTURACION_TIMBRADO_INICIO = (
    env("FACTURACION_TIMBRADO_INICIO", default="") or "2026-01-01"
)
FACTURACION_EMISOR_RUC = env("FACTURACION_EMISOR_RUC", default="") or "00000000"
FACTURACION_EMISOR_DV = env("FACTURACION_EMISOR_DV", default="") or "0"
FACTURACION_EMISOR_TIPO_CONTRIBUYENTE = (
    env("FACTURACION_EMISOR_TIPO_CONTRIBUYENTE", default="") or "2"
)
FACTURACION_EMISOR_NOMBRE = (
    env("FACTURACION_EMISOR_NOMBRE", default="") or "GLOBAL EXCHANGE (DATOS DE PRUEBA)"
)
FACTURACION_EMISOR_DIRECCION = (
    env("FACTURACION_EMISOR_DIRECCION", default="") or "Sin definir"
)
FACTURACION_EMISOR_NUMERO_CASA = env("FACTURACION_EMISOR_NUMERO_CASA", default="") or "0"
FACTURACION_EMISOR_DEPARTAMENTO = (
    env("FACTURACION_EMISOR_DEPARTAMENTO", default="") or "1"
)
FACTURACION_EMISOR_DEPARTAMENTO_NOMBRE = (
    env("FACTURACION_EMISOR_DEPARTAMENTO_NOMBRE", default="") or "CAPITAL"
)
FACTURACION_EMISOR_CIUDAD = env("FACTURACION_EMISOR_CIUDAD", default="") or "1"
FACTURACION_EMISOR_CIUDAD_NOMBRE = (
    env("FACTURACION_EMISOR_CIUDAD_NOMBRE", default="") or "ASUNCION (DISTRITO)"
)
FACTURACION_EMISOR_TELEFONO = (
    env("FACTURACION_EMISOR_TELEFONO", default="") or "(021)000000"
)
FACTURACION_EMISOR_EMAIL = (
    env("FACTURACION_EMISOR_EMAIL", default="") or "facturacion@globalexchange.test"
)
# Actividades económicas del emisor (gActEco del SIFEN). Son varias, y cada
# código va con su descripción: se escriben como "codigo:descripcion",
# separadas por "|". Las reales las define el RUC del emisor.
FACTURACION_EMISOR_ACTIVIDADES = (
    env("FACTURACION_EMISOR_ACTIVIDADES", default="")
    or "66190:Otras actividades auxiliares de servicios financieros"
)

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Asuncion"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
# Archivos estáticos propios del proyecto (incluye el CSS compilado por Tailwind).
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
