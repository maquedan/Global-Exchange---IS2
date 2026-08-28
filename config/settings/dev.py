"""Ambiente de DESARROLLO."""
from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["*"]

# En desarrollo los correos (verificación) se muestran en la consola
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# ===== En desarrollo, el archivo .env es el que manda =====
# django-environ NO pisa las variables que ya existen en el entorno del proceso.
# Adentro de Docker eso duele: docker-compose copia el .env cuando CREA el
# contenedor y esos valores quedan congelados ahí. Si después editás el .env
# (por ejemplo, pegás el client secret nuevo de Keycloak), Django sigue usando
# el viejo y el login falla con "Invalid client credentials".
# En desarrollo queremos siempre lo que dice el archivo, que es lo que editás.
def _leer_archivo_env(ruta):
    valores = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text().splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        # Algunos .env escriben los valores entre comillas: CLAVE="valor"
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


_DEL_ARCHIVO = _leer_archivo_env(BASE_DIR / ".env")

OIDC_RP_CLIENT_ID = _DEL_ARCHIVO.get("OIDC_RP_CLIENT_ID", OIDC_RP_CLIENT_ID)
OIDC_RP_CLIENT_SECRET = _DEL_ARCHIVO.get("OIDC_RP_CLIENT_SECRET", OIDC_RP_CLIENT_SECRET)
KEYCLOAK_SERVER_URL = _DEL_ARCHIVO.get("KEYCLOAK_SERVER_URL", KEYCLOAK_SERVER_URL)

# ===== El navegador NO está adentro de Docker =====
# La pantalla de login la abre el navegador, que corre en Windows. Desde ahí los
# nombres internos de Docker ("keycloak") no existen: da ERR_NAME_NOT_RESOLVED.
# En desarrollo Keycloak siempre se publica en el puerto 8080 de la máquina.
if CORRIENDO_EN_DOCKER and "//keycloak:" in KEYCLOAK_SERVER_URL:
    KEYCLOAK_SERVER_URL = KEYCLOAK_SERVER_URL.replace("//keycloak:", "//localhost:")

# Recalculamos las URLs que ve el navegador con los valores ya corregidos.
_OIDC_NAVEGADOR = f"{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect"
OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_OIDC_NAVEGADOR}/auth"
OIDC_OP_LOGOUT_ENDPOINT = f"{_OIDC_NAVEGADOR}/logout"
