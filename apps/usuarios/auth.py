"""Autenticación contra Keycloak (GEG9-24).

mozilla-django-oidc ya resuelve el "baile" de OpenID Connect: manda al usuario
a Keycloak, recibe el código, lo canjea por tokens y crea la sesión de Django.
Lo que NO hace solo es traer los **roles**. Eso lo agregamos acá.
"""
import base64
import json
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import Group
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

logger = logging.getLogger(__name__)


def _leer_payload_del_token(token):
    """Devuelve el contenido (payload) de un JWT como diccionario.

    Un JWT son 3 partes separadas por puntos: cabecera.payload.firma
    Solo nos interesa la del medio, que viene en Base64.

    No verificamos la firma a propósito: este token nos lo entregó Keycloak
    directamente en la respuesta del token endpoint (servidor a servidor,
    sin pasar por el navegador), así que no hay forma de que alguien lo haya
    alterado en el camino. La librería ya verificó el id_token por su lado.
    """
    try:
        payload = token.split(".")[1]
        # Base64 necesita que el largo sea múltiplo de 4; Keycloak recorta el
        # relleno "=" y hay que devolvérselo.
        relleno = "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload + relleno))
    except Exception:
        logger.warning("No se pudo leer el payload del token de Keycloak")
        return {}


class KeycloakOIDCBackend(OIDCAuthenticationBackend):
    """Backend de login que sincroniza los roles del realm con Grupos de Django."""

    def get_userinfo(self, access_token, id_token, payload):
        """Arma los datos del usuario SIN llamar a /userinfo.

        Por defecto la librería consulta el endpoint /userinfo de Keycloak.
        Eso trae dos problemas:

        1. Los ROLES no vienen ahí. Keycloak los manda dentro del access_token,
           en realm_access.roles.
        2. Si Django llama a Keycloak por un hostname distinto del que figura
           como emisor del token (típico en Docker: "keycloak" por dentro,
           "localhost" para el navegador), Keycloak responde 401 porque el
           emisor no le coincide.

        No hace falta esa llamada: el id_token ya trae el correo y el nombre, y
        la librería YA lo verificó contra las claves públicas de Keycloak antes
        de pasárnoslo en "payload". Es lo que OpenID Connect prevé para este
        caso, y de paso nos ahorramos una consulta de red por cada login.
        """
        claims = dict(payload)  # id_token verificado: sub, email, given_name...
        contenido = _leer_payload_del_token(access_token)
        claims["roles"] = contenido.get("realm_access", {}).get("roles", [])
        return claims

    def create_user(self, claims):
        """Se ejecuta la PRIMERA vez que alguien entra desde Keycloak."""
        usuario = super().create_user(claims)
        return self._sincronizar(usuario, claims)

    def update_user(self, usuario, claims):
        """Se ejecuta en CADA login siguiente: refresca datos y roles."""
        return self._sincronizar(usuario, claims)

    # ------------------------------------------------------------------
    def _sincronizar(self, usuario, claims):
        """Copia nombre, correo y roles de Keycloak al usuario de Django.

        Keycloak es la única fuente de verdad: si allá le sacaron un rol,
        acá se lo sacamos también.
        """
        usuario.email = claims.get("email", "") or usuario.email
        usuario.first_name = claims.get("given_name", "") or usuario.first_name
        usuario.last_name = claims.get("family_name", "") or usuario.last_name

        # Por defecto la librería le pone un nombre de usuario ilegible (un
        # hash del correo). Usamos el de Keycloak si todavía está libre.
        nombre_keycloak = claims.get("preferred_username")
        if nombre_keycloak and nombre_keycloak != usuario.username:
            ya_usado = (
                self.UserModel.objects.filter(username=nombre_keycloak)
                .exclude(pk=usuario.pk)
                .exists()
            )
            if not ya_usado:
                usuario.username = nombre_keycloak

        # Keycloak es el catálogo de roles. Ignoramos únicamente sus roles
        # técnicos; cualquier rol creado desde RF011 se sincroniza también.
        roles_keycloak = set(claims.get("roles", []))
        internos = set(settings.ROLES_KEYCLOAK_INTERNOS)
        internos.add(f"default-roles-{settings.KEYCLOAK_REALM}")
        roles = sorted(roles_keycloak - internos)

        # El administrador entra al /admin de Django.
        usuario.is_staff = settings.ROL_ADMINISTRADOR in roles
        usuario.is_superuser = settings.ROL_ADMINISTRADOR in roles
        usuario.save()

        # set() reemplaza los grupos: agrega los nuevos y quita los que ya no.
        grupos = [Group.objects.get_or_create(name=rol)[0] for rol in roles]
        usuario.groups.set(grupos)

        logger.info("Login de %s con roles %s", usuario.username, roles or "(ninguno)")
        return usuario


def cerrar_sesion_en_keycloak(request):
    """URL a la que redirigir para cerrar sesión también en Keycloak.

    Sin esto, al hacer logout se borra la sesión de Django pero la de Keycloak
    sigue viva: apretás "Iniciar sesión" y entra solo, sin pedir contraseña.
    """
    parametros = {"post_logout_redirect_uri": request.build_absolute_uri("/")}

    id_token = request.session.get("oidc_id_token")
    if id_token:
        parametros["id_token_hint"] = id_token
    else:
        parametros["client_id"] = settings.OIDC_RP_CLIENT_ID

    return f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?{urlencode(parametros)}"
