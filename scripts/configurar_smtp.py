#!/usr/bin/env python3
"""Configura el servidor de correo (SMTP) de Keycloak a partir del .env.

Keycloak es quien manda los correos de verificación del autorregistro, así que
la configuración va en el realm, no en Django. Este script la aplica leyendo el
.env, para que la contraseña quede en un solo lugar y nunca llegue a Git.

Uso:
    python3 scripts/configurar_smtp.py              aplica lo que dice el .env
    python3 scripts/configurar_smtp.py --mailpit    vuelve al buzón falso (desarrollo)
    python3 scripts/configurar_smtp.py --probar tu@correo.com
                                                    manda un correo de prueba real

Si EMAIL_HOST está vacío, usa Mailpit (http://localhost:8025), que atrapa los
correos sin mandarlos a internet. Solo la biblioteca estándar de Python.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def leer_env():
    """Lee el .env como un diccionario simple."""
    valores = {}
    archivo = RAIZ / ".env"
    if not archivo.exists():
        sys.exit("No encuentro el .env. Copiá .env.example a .env primero.")
    for linea in archivo.read_text().splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


ENV = leer_env()
KEYCLOAK = ENV.get("KEYCLOAK_SERVER_URL", "http://localhost:8080")
REALM = ENV.get("KEYCLOAK_REALM", "global-exchange")
ADMIN_USER = ENV.get("KC_ADMIN_USER", "admin")
ADMIN_PASS = ENV.get("KC_ADMIN_PASSWORD", "admin")

SMTP_MAILPIT = {
    "host": "mailpit", "port": "1025",
    "from": "no-reply@globalexchange.local", "fromDisplayName": "Global Exchange",
    "ssl": "false", "starttls": "false", "auth": "false",
}


def smtp_del_env():
    """Arma la configuración de Keycloak con los datos del .env."""
    host = ENV.get("EMAIL_HOST", "")
    if not host:
        return None

    remitente = ENV.get("EMAIL_FROM") or ENV.get("EMAIL_HOST_USER")
    if not remitente:
        sys.exit("Falta EMAIL_FROM (o EMAIL_HOST_USER) en el .env: es el remitente.")

    puerto = ENV.get("EMAIL_PORT", "587")
    usuario = ENV.get("EMAIL_HOST_USER", "")
    clave = ENV.get("EMAIL_HOST_PASSWORD", "")

    config = {
        "host": host,
        "port": puerto,
        "from": remitente,
        "fromDisplayName": ENV.get("EMAIL_FROM_NAME", "Global Exchange"),
        # El puerto 465 usa SSL desde el principio; el 587 arranca en claro y
        # sube a cifrado con STARTTLS. Es la convención de todos los proveedores.
        "ssl": "true" if puerto == "465" else "false",
        "starttls": "false" if puerto == "465" else "true",
        "auth": "true" if usuario else "false",
    }
    if usuario:
        config["user"] = usuario
        config["password"] = clave
    return config


# ------------------------------------------------------------ API de Keycloak
def token():
    datos = urllib.parse.urlencode({
        "client_id": "admin-cli", "username": ADMIN_USER,
        "password": ADMIN_PASS, "grant_type": "password",
    }).encode()
    url = f"{KEYCLOAK}/realms/master/protocol/openid-connect/token"
    try:
        with urllib.request.urlopen(url, datos, timeout=15) as r:
            return json.load(r)["access_token"]
    except urllib.error.URLError as e:
        sys.exit(f"No pude conectarme a Keycloak en {KEYCLOAK} ({e}).\n"
                 f"¿Está levantado?  docker compose up -d keycloak")


def pedir(metodo, ruta, cuerpo=None):
    b = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(f"{KEYCLOAK}/admin/realms/{ruta}", data=b, method=metodo)
    req.add_header("Authorization", f"Bearer {token()}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read().decode()
            return r.status, (json.loads(t) if t.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def aplicar(config, etiqueta):
    _, realm = pedir("GET", REALM)
    if not isinstance(realm, dict):
        sys.exit(f"No pude leer el realm '{REALM}': {realm}")
    realm["smtpServer"] = config
    estado, respuesta = pedir("PUT", REALM, realm)
    if estado >= 400:
        sys.exit(f"Keycloak rechazó la configuración (HTTP {estado}): {respuesta}")
    print(f"SMTP configurado: {etiqueta}")
    print(f"  servidor  : {config['host']}:{config['port']}")
    print(f"  remitente : {config['from']}")
    print(f"  cifrado   : {'SSL' if config['ssl'] == 'true' else 'STARTTLS' if config['starttls'] == 'true' else 'ninguno'}")
    print(f"  usuario   : {config.get('user', '(sin autenticación)')}")


def probar(destino):
    """Manda un correo real a esa dirección para probar que el SMTP anda.

    Crea un usuario descartable, le pide a Keycloak que le mande el correo, y
    lo borra. Así se prueba el camino completo sin ensuciar el realm.
    """
    usuario = f"prueba-smtp-{uuid.uuid4().hex[:8]}"
    estado, _ = pedir("POST", f"{REALM}/users", {
        "username": usuario, "email": destino,
        "firstName": "Prueba", "lastName": "SMTP", "enabled": True,
    })
    if estado == 409:
        sys.exit(
            f"Ya existe un usuario con el correo {destino} en el realm.\n"
            "Keycloak no permite dos cuentas con la misma direccion.\n\n"
            "Probá con una variante del mismo correo, que llega a la misma\n"
            f"bandeja pero Keycloak toma como distinta:\n"
            f"  python3 scripts/configurar_smtp.py --probar tucuenta+prueba@gmail.com"
        )
    if estado >= 400:
        sys.exit(f"No pude crear el usuario de prueba (HTTP {estado}).")

    _, us = pedir("GET", f"{REALM}/users?username={usuario}&exact=true")
    uid = us[0]["id"]
    try:
        estado, respuesta = pedir("PUT", f"{REALM}/users/{uid}/execute-actions-email",
                                  ["VERIFY_EMAIL"])
        if estado < 400:
            print(f"Correo enviado a {destino}. Revisá la bandeja (y la carpeta de spam).")
        else:
            print(f"Keycloak no pudo enviarlo (HTTP {estado}).")
            print(f"  {respuesta}")
            print("\nCausas habituales:")
            print("  - Gmail: falta la contraseña de aplicación (la normal no sirve).")
            print("  - Puerto o cifrado equivocados (587 = STARTTLS, 465 = SSL).")
            print("  - El remitente no coincide con la cuenta autenticada.")
            print("  - Revisá el detalle:  docker compose logs --tail 40 keycloak")
    finally:
        pedir("DELETE", f"{REALM}/users/{uid}")


def main():
    args = sys.argv[1:]

    if "--mailpit" in args:
        aplicar(SMTP_MAILPIT, "Mailpit (buzón falso de desarrollo)")
        print("\nLos correos NO salen a internet: se leen en http://localhost:8025")
        return

    if "--probar" in args:
        i = args.index("--probar")
        if i + 1 >= len(args):
            sys.exit("Uso: python3 scripts/configurar_smtp.py --probar tu@correo.com")
        probar(args[i + 1])
        return

    config = smtp_del_env()
    if config is None:
        aplicar(SMTP_MAILPIT, "Mailpit (EMAIL_HOST está vacío en el .env)")
        print("\nPara mandar correos reales, completá EMAIL_HOST y compañía en el .env.")
        return

    aplicar(config, "servidor real")
    print(f"\nProbalo:  python3 scripts/configurar_smtp.py --probar tu@correo.com")


if __name__ == "__main__":
    main()
