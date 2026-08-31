"""Adaptador pequeño y testeable para la API administrativa de Keycloak."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class KeycloakAdminError(Exception):
    """Error seguro para mostrar al administrador sin filtrar secretos."""


class KeycloakAdmin:
    """Gestiona roles y sus asignaciones usando un cliente de servicio."""

    def __init__(self):
        self.base_url = settings.KEYCLOAK_INTERNAL_URL.rstrip("/")
        self.realm = settings.KEYCLOAK_REALM

    def _token(self):
        secret = settings.KEYCLOAK_ADMIN_CLIENT_SECRET
        if not secret:
            raise KeycloakAdminError("Falta configurar KEYCLOAK_ADMIN_CLIENT_SECRET.")
        datos = urlencode({
            "grant_type": "client_credentials",
            "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
            "client_secret": secret,
        }).encode()
        respuesta = self._request(
            f"{self.base_url}/realms/{quote(self.realm)}/protocol/openid-connect/token",
            method="POST",
            data=datos,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            autenticado=False,
        )
        return respuesta["access_token"]

    def _request(self, url, *, method="GET", data=None, headers=None, autenticado=True):
        headers = dict(headers or {})
        if autenticado:
            headers["Authorization"] = f"Bearer {self._token()}"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=10) as response:
                cuerpo = response.read()
                return json.loads(cuerpo) if cuerpo else None
        except (HTTPError, URLError, KeyError, json.JSONDecodeError) as error:
            raise KeycloakAdminError("No se pudo completar la operación en Keycloak.") from error

    @property
    def _admin_url(self):
        return f"{self.base_url}/admin/realms/{quote(self.realm)}"

    def listar_roles(self):
        roles = self._request(f"{self._admin_url}/roles")
        internos = set(settings.ROLES_KEYCLOAK_INTERNOS)
        internos.add(f"default-roles-{self.realm}")
        return sorted((r for r in roles if r["name"] not in internos), key=lambda r: r["name"])

    def crear_rol(self, nombre, descripcion=""):
        self._request(
            f"{self._admin_url}/roles", method="POST",
            data=json.dumps({"name": nombre, "description": descripcion}).encode(),
            headers={"Content-Type": "application/json"},
        )

    def eliminar_rol(self, nombre):
        self._request(f"{self._admin_url}/roles/{quote(nombre, safe='')}", method="DELETE")

    def listar_usuarios(self):
        usuarios = self._request(f"{self._admin_url}/users?max=100")
        return sorted(usuarios, key=lambda u: u.get("username", ""))

    def roles_de_usuario(self, usuario_id):
        return self._request(f"{self._admin_url}/users/{quote(usuario_id, safe='')}/role-mappings/realm")

    def establecer_roles_usuario(self, usuario_id, nombres):
        actuales = self.roles_de_usuario(usuario_id)
        roles = {rol["name"]: rol for rol in self.listar_roles()}
        actuales_app = [rol for rol in actuales if rol["name"] in roles]
        deseados = [roles[nombre] for nombre in nombres if nombre in roles]
        if actuales_app:
            self._request(
                f"{self._admin_url}/users/{quote(usuario_id, safe='')}/role-mappings/realm",
                method="DELETE", data=json.dumps(actuales_app).encode(),
                headers={"Content-Type": "application/json"},
            )
        if deseados:
            self._request(
                f"{self._admin_url}/users/{quote(usuario_id, safe='')}/role-mappings/realm",
                method="POST", data=json.dumps(deseados).encode(),
                headers={"Content-Type": "application/json"},
            )
