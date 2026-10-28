#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  echo "Uso: $0 dev|prod" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage

case "$1" in
  dev)
    ENV_FILE=".env"
    seed_profile="demo"
    if [[ ! -f "$ENV_FILE" ]]; then
      cp .env.example "$ENV_FILE"
    fi
    python3 - <<'PY'
from pathlib import Path
import secrets

path = Path(".env")
lines = path.read_text().splitlines()
values = {}
for line in lines:
    stripped = line.strip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        key, value = stripped.split("=", 1)
        values[key] = value

defaults = {
    "POSTGRES_DB": "globalexchange",
    "POSTGRES_USER": "postgres",
    "KEYCLOAK_DB_NAME": "keycloak",
    "KEYCLOAK_DB_USER": "keycloak",
    "KC_ADMIN_USER": "admin",
}
for key, value in defaults.items():
    if not values.get(key):
        values[key] = value

for key in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "KEYCLOAK_DB_PASSWORD", "KC_ADMIN_PASSWORD"):
    if not values.get(key) or values[key] == "GENERATE_ON_DEPLOY":
        values[key] = secrets.token_urlsafe(36)

if not values.get("DATABASE_URL") or values["DATABASE_URL"] == "GENERATE_ON_DEPLOY":
    values["DATABASE_URL"] = (
        f"postgres://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@db:5432/{values['POSTGRES_DB']}"
    )

keys_to_write = set(defaults) | {
    "DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "KEYCLOAK_DB_PASSWORD",
    "KC_ADMIN_PASSWORD", "DATABASE_URL",
}
written = set()
result = []
for line in lines:
    stripped = line.strip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        key = stripped.split("=", 1)[0]
        if key in keys_to_write:
            result.append(f"{key}={values[key]}")
            written.add(key)
            continue
    result.append(line)
for key in keys_to_write - written:
    result.append(f"{key}={values[key]}")
path.write_text("\n".join(result) + "\n")
PY
    compose=(docker compose --env-file "$ENV_FILE")
    ;;
  prod)
    ENV_FILE=".env.prod"
    seed_profile="minimal"
    if [[ ! -f "$ENV_FILE" ]]; then
      echo "No existe .env.prod. Copiá .env.prod.example, completá sus valores y volvé a ejecutar." >&2
      exit 1
    fi
    python3 - <<'PY'
from pathlib import Path
import sys

values = {}
for line in Path(".env.prod").read_text().splitlines():
    stripped = line.strip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        key, value = stripped.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")

required = (
    "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "DATABASE_URL",
    "KEYCLOAK_DB_NAME", "KEYCLOAK_DB_USER", "KEYCLOAK_DB_PASSWORD",
    "KC_ADMIN_USER", "KC_ADMIN_PASSWORD", "SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS", "APP_PUBLIC_URL", "SITE_BASE_URL",
    "KEYCLOAK_PUBLIC_URL", "KEYCLOAK_SERVER_URL", "KEYCLOAK_INTERNAL_URL",
    "INITIAL_USD_PYG_BUY_RATE", "INITIAL_USD_PYG_SELL_RATE",
    "INITIAL_COMMISSION_MINORISTA", "INITIAL_COMMISSION_CORPORATIVO",
    "INITIAL_COMMISSION_VIP",
)
missing = [
    key for key in required
    if not values.get(key) or "REEMPLAZAR" in values[key] or "tu-dominio.com" in values[key]
]
if missing:
    print("Configurá estos valores en .env.prod antes de desplegar: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)
PY
    compose=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)
    ;;
  *)
    usage
    ;;
esac

"${compose[@]}" config --quiet
"${compose[@]}" build web
"${compose[@]}" up -d --wait db keycloak-db

if [[ "$1" == "dev" ]]; then
  "${compose[@]}" up -d mailpit keycloak
else
  "${compose[@]}" up -d keycloak
fi

keycloak_ready=0
for ((attempt = 1; attempt <= 60; attempt++)); do
  if curl --silent --fail --output /dev/null \
    http://localhost:8080/realms/global-exchange/.well-known/openid-configuration; then
    keycloak_ready=1
    break
  fi
  sleep 2
done
if [[ "$keycloak_ready" -ne 1 ]]; then
  echo "El realm global-exchange de Keycloak no estuvo listo en 120 segundos." >&2
  exit 1
fi

if [[ "$1" == "prod" ]]; then
  "${compose[@]}" run --rm --no-deps \
    -v "$ROOT_DIR/.env.prod:/app/.env.prod" \
    -e ENV_FILE=/app/.env.prod \
    -e KEYCLOAK_URL=http://keycloak:8080 \
    web python scripts/sincronizar_secret.py
else
  "${compose[@]}" run --rm --no-deps \
    -e KEYCLOAK_URL=http://keycloak:8080 \
    web python scripts/sincronizar_secret.py
fi

"${compose[@]}" run --rm --no-deps web sh -c \
  "python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py cargar_datos_iniciales --profile $seed_profile"

if [[ "$1" == "prod" ]]; then
  "${compose[@]}" up -d --wait web nginx
  echo "Producción desplegada. Revisá la URL configurada en APP_PUBLIC_URL."
else
  "${compose[@]}" up -d --wait web
  echo "Desarrollo desplegado: http://localhost:8000 (Django) y http://localhost:8080 (Keycloak)."
  echo "Las credenciales locales se guardaron en .env; no las subas al repositorio."
fi
