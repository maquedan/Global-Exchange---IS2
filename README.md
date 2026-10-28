# Global Exchange

Plataforma digital de cambio de divisas. Proyecto Django + PostgreSQL +
Keycloak, orquestado con Docker Compose.

## Requisitos

- Docker Desktop o Docker Engine con Docker Compose v2.
- Bash, Python 3 y `curl` para ejecutar los scripts de despliegue.

## Desarrollo

Desde la raíz del repositorio, ejecutá un solo comando:

```bash
./scripts/deploy.sh dev
```

La primera ejecución crea `.env` a partir de `.env.example` y genera
credenciales aleatorias locales. Luego construye Django, levanta PostgreSQL,
Keycloak y Mailpit, espera las bases de datos y el realm de Keycloak, sincroniza
los secretos OIDC, aplica migraciones, recoge los archivos estáticos y arranca
la aplicación. `.env` está excluido de Git; no lo compartas ni lo subas.

Accesos locales:

- Aplicación: http://localhost:8000
- Administración de Django: http://localhost:8000/admin
- Keycloak: http://localhost:8080
- Mailpit: http://localhost:8025

La contraseña generada para el administrador inicial de Keycloak se guarda en
`KC_ADMIN_PASSWORD` dentro de `.env`. Para crear un superusuario de Django:

```bash
docker compose exec web python manage.py createsuperuser
```

Para apagar los servicios sin borrar los datos persistidos:

```bash
docker compose down
```

## Producción

1. Copiá la plantilla local y completá dominios y credenciales:

   ```bash
   cp .env.prod.example .env.prod
   ```

   Reemplazá todos los valores `REEMPLAZAR`, en particular las contraseñas de
   las bases de datos, `KC_ADMIN_PASSWORD` y `SECRET_KEY`. Usá secretos
   aleatorios y URL-encodeá la contraseña PostgreSQL en `DATABASE_URL`.
   Configurá y aprobá también la cotización inicial USD/PYG y los porcentajes
   de comisión en las variables `INITIAL_*`; el despliegue no inventa valores
   financieros para producción.
   Configurá los dominios reales en `APP_PUBLIC_URL`, `SITE_BASE_URL`,
   `KEYCLOAK_PUBLIC_URL`, `KEYCLOAK_SERVER_URL` y `DJANGO_ALLOWED_HOSTS`.
   `.env.prod` está excluido de Git.

2. Desplegá con un solo comando:

   ```bash
   ./scripts/deploy.sh prod
   ```

   El script valida la configuración, construye la imagen, espera ambas bases
   de datos, inicia Keycloak, sincroniza las credenciales OIDC, aplica las
   migraciones, recoge los estáticos y carga los datos iniciales mínimos antes
   de arrancar Django con Gunicorn y Nginx.

Por defecto, Nginx publica la aplicación en el puerto 80 y Keycloak en el 8080.
Configurá TLS en un proxy o balanceador antes de exponer el servicio a Internet.
Para aplicar cambios de configuración, actualizá `.env.prod` y volvé a ejecutar
`./scripts/deploy.sh prod`.

## Datos iniciales

El despliegue carga datos con `python manage.py cargar_datos_iniciales` y un
perfil explícito. Para ejecutarlo manualmente:

```bash
docker compose exec web python manage.py cargar_datos_iniciales --profile demo
docker compose --env-file .env.prod -f docker-compose.prod.yml exec web \
  python manage.py cargar_datos_iniciales --profile minimal
```

La carga es idempotente: usa claves naturales y solo completa registros
ausentes; no actualiza tasas ni comisiones que ya existan ni borra datos.

- `demo` (desarrollo): monedas admitidas para la demostración, tasas ficticias
  USD/PYG y otras divisas frente a PYG, comisiones de ejemplo para las tres
  categorías, grupos de roles de Django, clientes ficticios y una caja demo
  con saldos e inventario en cero. No se crean usuarios ni contraseñas demo.
- `minimal` (producción): monedas USD y PYG, una tasa inicial USD/PYG, las tres
  categorías con sus comisiones y grupos de roles. Los valores financieros se
  deben revisar y definir en `.env.prod` (`INITIAL_USD_PYG_*` y
  `INITIAL_COMMISSION_*`). No se cargan clientes ni sucursales/cajas demo.

Al ejecutar de nuevo el comando no se duplican datos ni se sobrescriben
configuraciones existentes. Las tasas de demostración no representan precios
de mercado; en producción, confirmá la cotización y las comisiones antes de
habilitar operaciones.

## Scripts de Keycloak dentro de Docker

Con los servicios levantados, los scripts se ejecutan como contenedores
temporales. En desarrollo, `.env` ya está disponible dentro del contenedor:

```bash
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/sincronizar_secret.py
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/configurar_smtp.py
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/configurar_smtp.py --mailpit
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/configurar_smtp.py --probar tu@correo.com
```

`deploy.sh` ya ejecuta `sincronizar_secret.py` automáticamente durante el
despliegue.

## Tailwind CSS

El CSS se compila localmente con Tailwind CSS v4 y se guarda en
`static/css/app.css`. Para regenerarlo al editar las plantillas:

```bash
npm install
npm run dev
```

Antes de crear una imagen o desplegar a producción, generá el CSS minificado:

```bash
npm run build
```

El CSS compilado se incluye en el repositorio y Django lo recoge mediante
`collectstatic`.

## Documentación

La guía paso a paso también está en la
[documentación Sphinx](docs/sphinx/deployment.rst). Para regenerar el sitio:

```bash
docker compose exec web sphinx-build -b html docs/sphinx docs/sphinx/_build
```

## Estructura

```text
config/        Configuración Django (base/dev/prod)
apps/          Aplicaciones por módulo
docs/          Guías de proyecto y documentación Sphinx
scripts/       Automatización de despliegue y tareas de Keycloak
```

## Flujo de trabajo Git

Ver [docs/gitflow.md](docs/gitflow.md) (metodología Git Flow).
