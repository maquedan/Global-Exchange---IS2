#!/usr/bin/env python3
"""Copia el client secret de Keycloak al archivo .env.

¿Por qué hace falta? El realm que está en el repo
(keycloak/realm-global-exchange.json) NO trae el client secret: no se guardan
secretos en Git. Entonces, cuando Keycloak importa el realm por primera vez,
genera un secret nuevo y al azar. Este script lo lee y lo escribe en tu .env.

Uso:   python3 scripts/sincronizar_secret.py

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
ADMIN_USER = os.environ.get("KC_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("KC_ADMIN_PASSWORD", "admin")

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = RAIZ / ".env"


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


def consultar(ruta, token):
    req = urllib.request.Request(f"{KEYCLOAK}/admin/realms/{ruta}")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def main():
    try:
        token = token_de_admin()
    except urllib.error.URLError as e:
        sys.exit(f"No pude conectarme a Keycloak en {KEYCLOAK}\n  ({e})\n"
                 f"¿Está levantado?  docker compose up -d keycloak")

    clientes = consultar(f"{REALM}/clients?clientId={CLIENT_ID}", token)
    if not clientes:
        sys.exit(f"No existe el client '{CLIENT_ID}' en el realm '{REALM}'.")

    secret = consultar(f"{REALM}/clients/{clientes[0]['id']}/client-secret", token)["value"]

    if not ARCHIVO_ENV.exists():
        sys.exit(f"No encuentro {ARCHIVO_ENV}. Copiá .env.example a .env primero.")

    contenido = ARCHIVO_ENV.read_text()
    linea = f"OIDC_RP_CLIENT_SECRET={secret}"
    if re.search(r"^OIDC_RP_CLIENT_SECRET=.*$", contenido, re.M):
        nuevo = re.sub(r"^OIDC_RP_CLIENT_SECRET=.*$", linea, contenido, flags=re.M)
    else:
        nuevo = contenido.rstrip("\n") + f"\n{linea}\n"

    if nuevo == contenido:
        print(f"El .env ya tenía el secret correcto ({secret[:4]}...). Nada que hacer.")
        return

    ARCHIVO_ENV.write_text(nuevo)
    print(f"Listo: OIDC_RP_CLIENT_SECRET actualizado ({secret[:4]}...).")
    print("Reiniciá Django para que lo tome:  docker compose restart web")


if __name__ == "__main__":
    main()
