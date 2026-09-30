# Global Exchange

Plataforma digital de cambio de divisas. Proyecto Django + Keycloak.

## Requisitos
- Docker Desktop instalado.

## Ambientes

Este proyecto tiene dos ambientes montados con Docker:
- **Desarrollo** (`docker-compose.yml`): Django con `runserver`, PostgreSQL y Keycloak en modo `start-dev`.
- **Producción** (`docker-compose.prod.yml`): Django con `gunicorn`, PostgreSQL y Keycloak en modo `start`.

## Puesta en marcha (desarrollo)

1. Copiar el archivo de variables y ajustarlo:
   ```bash
   cp .env.example .env
   ```
2. Levantar los servicios:
   ```bash
   docker compose up --build
   ```
3. En otra terminal, aplicar las migraciones y crear un superusuario:
   ```bash
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```

## Tailwind CSS

El CSS de la interfaz se compila localmente con Tailwind CSS v4 y se guarda en
`static/css/app.css`. No se usa React, Vite ni CDN.

Para regenerarlo al editar las plantillas, en otra terminal ejecutá:

```bash
npm install
npm run dev
```

Antes de crear una imagen o desplegar a producción, generá el CSS minificado:

```bash
npm run build
```

El archivo ya compilado se incluye en el repositorio y Django lo recoge desde
`static/` mediante `collectstatic`.

## Accesos
- Aplicación Django: http://localhost:8000
- Admin de Django: http://localhost:8000/admin
- Consola de Keycloak: http://localhost:8080  (usuario: `admin` / clave: `admin`)

## Producción
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```
(Requiere un archivo `.env.prod` con las variables de producción.)
Sincronizá el callback OIDC y los secretos del realm, y recargá Django:
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm --no-deps \
   -v "$PWD/.env.prod:/app/.env.prod" \
   -e ENV_FILE=/app/.env.prod \
   -e KEYCLOAK_URL=http://keycloak:8080 \
   web python scripts/sincronizar_secret.py
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate web nginx
```
La aplicación queda disponible en la URL de `APP_PUBLIC_URL` a través de Nginx.

## Estructura
```
config/        Configuración del proyecto (settings base/dev/prod)
apps/          Apps por módulo (clientes, usuarios, ...)
docs/          Documentación (gitflow, CHIA, etc.)
```

## Flujo de trabajo Git
Ver `docs/gitflow.md` (metodología Git Flow).
