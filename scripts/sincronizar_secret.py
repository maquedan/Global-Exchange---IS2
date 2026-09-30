#!/usr/bin/env python3
"""Sincroniza secretos y callback de OIDC con Keycloak y el archivo env.

¿Por qué hace falta? El realm que está en el repo
(keycloak/realm-global-exchange.json) NO trae el client secret: no se guardan
secretos en Git. Entonces, cuando Keycloak importa el realm por primera vez,
genera un secret nuevo y al azar. Este script lo lee y lo escribe en tu .env.

Uso:   python3 scripts/sincronizar_secret.py
    ENV_FILE=.env.prod python3 scripts/sincronizar_secret.py

Si APP_PUBLIC_URL está definida, actualiza en Keycloak el callback y el origen
permitidos para esa URL pública.

Solo usa la biblioteca estándar de Python: no hace falta instalar nada ni
entrar al contenedor.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KEYCLOAK = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
REALM = os.environ.get("KEYCLOAK_REALM", "global-exchange")
CLIENT_ID = os.environ.get("OIDC_RP_CLIENT_ID", "global-exchange-web")
ADMIN_CLIENT_ID = os.environ.get("KEYCLOAK_ADMIN_CLIENT_ID", "global-exchange-admin")
ADMIN_USER = os.environ.get("KC_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("KC_ADMIN_PASSWORD", "admin")
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = Path(os.environ.get("ENV_FILE", str(RAIZ / ".env")))


def token_de_admin():
    datos = urllib.parse.urlencode({
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASS,
        "grant_type": "password",
    }).encode()
    url = f"{KEYCLOAK}/realms/master/protocol/openid-connect/token"
    with urllib.request.urlopen(url, datos, timeout=15) as r:
        return json.load(r)["access_token"]


def solicitar(ruta, token, metodo="GET", datos=None):
    req = urllib.request.Request(
        f"{KEYCLOAK}/admin/realms/{ruta}", data=datos, method=metodo
    )
    req.add_header("Authorization", f"Bearer {token}")
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        cuerpo = r.read()
        return json.loads(cuerpo) if cuerpo else None


def consultar(ruta, token):
    return solicitar(ruta, token)


def asegurar_cliente_administracion(token):
    """Crea el cliente RF011 en realms ya importados antes de esta historia."""
    clientes = consultar(f"{REALM}/clients?clientId={ADMIN_CLIENT_ID}", token)
    if clientes:
        cliente = clientes[0]
    else:
        configuracion = {
            "clientId": ADMIN_CLIENT_ID,
            "name": "Global Exchange (administración interna)",
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "clientAuthenticatorType": "client-secret",
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": True,
        }
        solicitar(f"{REALM}/clients", token, "POST", json.dumps(configuracion).encode())
        cliente = consultar(f"{REALM}/clients?clientId={ADMIN_CLIENT_ID}", token)[0]
        print(f"Cliente '{ADMIN_CLIENT_ID}' creado para RF011.")

    # El service account recibe solo los permisos que requiere RF011.
    cuenta = consultar(f"{REALM}/clients/{cliente['id']}/service-account-user", token)
    gestor = consultar(f"{REALM}/clients?clientId=realm-management", token)[0]
    roles = consultar(f"{REALM}/clients/{gestor['id']}/roles", token)
    requeridos = {"manage-realm", "view-realm", "query-users", "view-users", "manage-users"}
    asignados = consultar(
        f"{REALM}/users/{cuenta['id']}/role-mappings/clients/{gestor['id']}",
        token,
    )
    nombres_asignados = {rol["name"] for rol in asignados}
    asignar = [
        rol for rol in roles
        if rol["name"] in requeridos and rol["name"] not in nombres_asignados
    ]
    if not asignar:
        return cliente
    solicitar(
        f"{REALM}/users/{cuenta['id']}/role-mappings/clients/{gestor['id']}",
        token, "POST", json.dumps(asignar).encode(),
    )
    print(f"Cliente '{ADMIN_CLIENT_ID}' autorizado para RF011.")
    return cliente


def configurar_callback_web(token):
    if not APP_PUBLIC_URL:
        return

    url = urllib.parse.urlsplit(APP_PUBLIC_URL)
    if (url.scheme not in {"http", "https"} or not url.netloc
            or url.path not in {"", "/"} or url.query or url.fragment
            or url.username or url.password):
        sys.exit("APP_PUBLIC_URL debe ser un origen http(s), sin ruta ni credenciales.")

    clientes = consultar(f"{REALM}/clients?clientId={CLIENT_ID}", token)
    if not clientes:
        sys.exit(f"No existe el client '{CLIENT_ID}' en el realm '{REALM}'.")

    cliente = consultar(f"{REALM}/clients/{clientes[0]['id']}", token)
    redirect_uri = f"{APP_PUBLIC_URL}/oidc/callback/"
    redirect_uris = cliente.get("redirectUris", [])
    if redirect_uri not in redirect_uris:
        redirect_uris.append(redirect_uri)
    cliente["redirectUris"] = redirect_uris

    web_origins = cliente.get("webOrigins", [])
    if APP_PUBLIC_URL not in web_origins:
        web_origins.append(APP_PUBLIC_URL)
    cliente["webOrigins"] = web_origins

    attributes = cliente.setdefault("attributes", {})
    logout_uris = [
        uri.strip()
        for uri in re.split(r"\s*##\s*|\s+", attributes.get("post.logout.redirect.uris", ""))
        if uri.strip()
    ]
    logout_uri = f"{APP_PUBLIC_URL}/"
    if logout_uri not in logout_uris:
        logout_uris.append(logout_uri)
    attributes["post.logout.redirect.uris"] = "##".join(logout_uris)
    solicitar(
        f"{REALM}/clients/{cliente['id']}",
        token,
        "PUT",
        json.dumps(cliente).encode(),
    )
    print(f"Callback OIDC configurado para {APP_PUBLIC_URL}.")


def main():
    try:
        token = token_de_admin()
    except urllib.error.URLError as e:
        sys.exit(f"No pude conectarme a Keycloak en {KEYCLOAK}\n  ({e})\n"
                 f"¿Está levantado?  docker compose up -d keycloak")

    def secret_de(client_id):
        clientes = consultar(f"{REALM}/clients?clientId={client_id}", token)
        if not clientes:
            sys.exit(f"No existe el client '{client_id}' en el realm '{REALM}'.")
        return consultar(f"{REALM}/clients/{clientes[0]['id']}/client-secret", token)["value"]

    secret = secret_de(CLIENT_ID)
    asegurar_cliente_administracion(token)
    secret_admin = secret_de(ADMIN_CLIENT_ID)
    configurar_callback_web(token)

    if not ARCHIVO_ENV.exists():
        sys.exit(f"No encuentro {ARCHIVO_ENV}. Copiá .env.example a .env primero.")

    contenido = ARCHIVO_ENV.read_text()
    nuevo = contenido
    for clave, valor in (("OIDC_RP_CLIENT_SECRET", secret),
                         ("KEYCLOAK_ADMIN_CLIENT_SECRET", secret_admin)):
        linea = f"{clave}={valor}"
        if re.search(rf"^{clave}=.*$", nuevo, re.M):
            nuevo = re.sub(rf"^{clave}=.*$", linea, nuevo, flags=re.M)
        else:
            nuevo = nuevo.rstrip("\n") + f"\n{linea}\n"

    if nuevo == contenido:
        print(f"El .env ya tenía el secret correcto ({secret[:4]}...). Nada que hacer.")
        return

    ARCHIVO_ENV.write_text(nuevo)
    print("Listo: secretos de OIDC y administración RF011 actualizados.")
    print("Reiniciá Django para que lo tome:  docker compose restart web")


if __name__ == "__main__":
    main()
