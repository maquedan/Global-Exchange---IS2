# Global Exchange — arquitectura y stack

## Resumen

Global Exchange es una aplicación web monolítica para administrar clientes,
monedas y cotizaciones, y ofrecer flujos de simulación y registro de operaciones
de cambio. El backend está implementado en Django; la interfaz se renderiza en
el servidor con plantillas Django y CSS compilado localmente con Tailwind CSS.
Keycloak brinda inicio de sesión OpenID Connect (OIDC) y administra los roles.

Este documento describe lo que está configurado en el repositorio. No presupone
integraciones bancarias, proveedores de cotizaciones ni servicios que todavía
no forman parte del código.

## Stack tecnológico

| Capa | Tecnología configurada | Uso |
|---|---|---|
| Lenguaje / runtime | Python 3.12 | Backend y herramientas de gestión |
| Framework web | Django `>=6.0,<6.2` | Aplicación monolítica, ORM, sesiones, formularios, vistas, plantillas y admin |
| Configuración | `django-environ` | Lectura de variables de entorno y configuración de base de datos |
| Base de datos de la aplicación | PostgreSQL 16 en Docker | Datos de negocio y tablas de Django; SQLite es el valor alternativo al ejecutar localmente sin `DATABASE_URL` |
| Driver PostgreSQL | Psycopg 3 (`psycopg[binary]`) | Conexión Django–PostgreSQL |
| Identidad | Keycloak 26 + OpenID Connect | Login, registro/verificación configurados en el realm y roles |
| Integración OIDC | `mozilla-django-oidc` y backend propio | Flujo de login/logout y sincronización de roles con grupos Django |
| Interfaz | Django Templates + HTML | Renderizado server-side; no es una SPA |
| CSS | Tailwind CSS 4.3, CLI de npm | Compila `assets/css/tailwind.css` a `static/css/app.css` |
| Servidor de desarrollo | Django `runserver` | Servicio `web` en el Compose de desarrollo |
| Servidor de aplicación | Gunicorn, WSGI | Servicio `web` en el Compose de producción |
| Proxy de producción | Nginx `stable-alpine` | Publica la aplicación y sirve los estáticos recolectados |
| Correo local | Mailpit | SMTP de desarrollo para correos del realm; interfaz web local |
| Contenedores | Docker / Docker Compose | Aplicación y servicios dependientes |
| Pruebas | pytest, pytest-django, Coverage.py | Pruebas automatizadas y medición de cobertura |
| Documentación de código | Sphinx | HTML generado desde docstrings |

Las dependencias Python se declaran con rangos en `requirements.txt`; el
frontend declara Tailwind y su CLI en `package.json` y fija el árbol resuelto
en `package-lock.json`.

## Vista de arquitectura

```text
Navegador
  ├── HTTP ──> Nginx (producción) ──> Gunicorn / Django
  │                                      ├── PostgreSQL de la aplicación
  │                                      └── Keycloak (OIDC / Admin API)
  │                                              └── PostgreSQL de Keycloak
  └── OIDC ──> Keycloak

Django sirve las páginas HTML; en producción Nginx también sirve /static/.
En desarrollo, Django usa runserver y Keycloak puede enviar correo de prueba
a Mailpit.
```

La comunicación de identidad tiene dos direcciones de Keycloak: el navegador
accede a `KEYCLOAK_SERVER_URL`, mientras Django usa `KEYCLOAK_INTERNAL_URL`
para canjear tokens y consultar claves o la API de administración. En Docker,
normalmente el navegador usa `localhost` y Django el nombre interno del servicio
`keycloak`.

## Aplicaciones y responsabilidades

Todas las aplicaciones de negocio viven bajo `apps/` y usan Django ORM, vistas,
formularios y URLs.

| App | Responsabilidad principal | Entidades / comportamiento |
|---|---|---|
| `usuarios` | Panel, autenticación, menú y administración de roles | Backend OIDC, grupos Django sincronizados desde roles Keycloak, `PermisoSistema` y `PermisoRol`, integración con la Admin API de Keycloak |
| `clientes` | Registro y administración de clientes | Personas físicas/jurídicas, categorías minorista/corporativo/VIP, baja lógica y asociación usuario–cliente |
| `cuentas` | Medios para acreditar fondos | Cuentas bancarias y billeteras electrónicas asociadas a un cliente |
| `monedas` | Catálogo de divisas | Código ISO de tres letras, nombre, símbolo y estado activo |
| `tasa_cambios` | Administración de pares y cotizaciones | Tasas de compra/venta, vigencia, historial y estado; restricción para una tasa activa por par |
| `tasas` | Consulta de cotizaciones e historial | Panel de pares, estadísticas y endpoint JSON autenticado para refresco periódico; no carga precios desde un proveedor externo |
| `conversiones` | Simulación, compra y venta | Cálculos `Decimal`, comisión, transacciones y comprobantes; las confirmaciones quedan persistidas en Django |
| `comisiones` | Configuración de comisión | Porcentaje por categoría de cliente, de 0 a 100 |

### Datos y relaciones principales

```text
Usuario Django ──< AsociaciónUsuarioCliente >── Cliente
                                                   ├──< CuentaPago
                                                   ├──< CompraDivisa
                                                   └──< VentaDivisa >── CuentaPago

Moneda ──< TasaCambio >── Moneda
                 ├──< CompraDivisa
                 └──< VentaDivisa

Cliente.categoria ──> ComisionCategoria
Grupo Django (rol Keycloak) ──< PermisoRol >── PermisoSistema
```

Las operaciones confirmadas guardan importes, tasa y porcentaje de comisión
aplicados como una fotografía histórica. Las referencias a cliente, monedas,
tasa y cuenta usan protección contra borrado en los registros de operación.

### Flujos de negocio relevantes

- **Login y autorización:** OIDC autentica en Keycloak; el backend propio usa
  los claims verificados del ID token y extrae roles del access token para
  sincronizarlos con grupos de Django en cada login. Las vistas protegen
  funciones mediante login y comprobaciones de rol. El menú se construye según
  esos roles.
- **Gestión de identidades:** el panel administrativo utiliza un cliente de
  servicio distinto para la Admin API de Keycloak. Los permisos funcionales y
  sus asociaciones con roles se almacenan localmente en Django.
- **Consulta de tasas:** se muestran las cotizaciones almacenadas y su historial.
  El frontend consulta `/tasas/datos/` periódicamente; esto refresca datos
  existentes, no constituye una fuente de precios en tiempo real.
- **Simulación:** el formulario usa las monedas y tasas registradas. El código
  multiplica por la tasa de compra para la operación `compra` y divide por la
  tasa de venta para `venta`, con redondeo a dos decimales.
- **Compra confirmada:** el servicio vuelve a validar cliente activo, tasa
  vigente y comisión dentro de una transacción atómica. Registra el importe
  base, comisión, total a pagar, tasa y monto recibido.
- **Venta confirmada:** valida cliente, cuenta destino, tasa y comisión, y
  registra el importe convertido, comisión y neto acreditado. La implementación
  actual usa `tasa_compra` en el cálculo de confirmación; confirmar la regla
  comercial antes de operar con dinero real.

Las confirmaciones son registros internos. En el repositorio no se ve conexión
con bancos, procesadores de pago, custodia de fondos ni un sistema externo de
liquidación.

## Rutas de la aplicación

| Prefijo | Función |
|---|---|
| `/` y `/panel/` | Inicio público y panel protegido |
| `/oidc/` | Inicio de autenticación, callback y logout de `mozilla-django-oidc` |
| `/admin/` | Django Admin |
| `/clientes/` | Clientes, bajas y asociaciones |
| `/cuentas/` | Medios de pago del usuario cliente |
| `/monedas/` | Catálogo de monedas |
| `/tasas-cambio/` | Administración de tasas |
| `/tasas/` y `/tasas/datos/` | Panel de tasas y datos JSON para refresco |
| `/conversiones/` | Simulación, compra, venta y comprobantes |
| `/comisiones/` | Configuración de comisiones |

No hay Django REST Framework ni una API pública general. El endpoint JSON de
tasas es una ruta de Django y requiere sesión iniciada.

## Ejecución y despliegue

### Desarrollo

`docker-compose.yml` configura:

- `web`: Django `runserver`, código montado desde el host, puerto `8000`.
- `db`: PostgreSQL 16 de la aplicación, puerto `5432`, volumen persistente.
- `keycloak-db`: PostgreSQL 16 separado para persistir realm, clientes, roles y
  usuarios.
- `keycloak`: Keycloak 26 en modo `start-dev`, realm importado desde
  `keycloak/realm-global-exchange.json`, puerto `8080`.
- `mailpit`: SMTP en `1025` e interfaz en `8025`.

Inicio habitual:

```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Direcciones de desarrollo: aplicación `http://localhost:8000`, Keycloak
`http://localhost:8080` y Mailpit `http://localhost:8025`.

Para compilar CSS fuera de Docker:

```bash
npm ci
npm run dev       # modo watch durante desarrollo
npm run build     # salida minificada para despliegue
```

### Producción configurada

`docker-compose.prod.yml` levanta PostgreSQL separados para Django y Keycloak,
Keycloak en modo `start`, Django/Gunicorn y Nginx. La aplicación ejecuta
`collectstatic` al iniciar; Nginx publica el puerto `80`, sirve los estáticos y
redirige el resto del tráfico a Gunicorn en el puerto `8000` interno. Los
volúmenes nombrados conservan bases de datos y estáticos.

El despliegue espera un `.env.prod` local, no versionado:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

Las URLs públicas del cliente OIDC/realm deben coincidir con el dominio real y
el callback configurado. Nginx actualmente escucha HTTP en el puerto 80; no hay
configuración TLS/certificados en el repositorio. Antes de producción real se
debe terminar TLS y establecer explícitamente claves, contraseñas, hosts
permitidos, cookies seguras, redirección HTTPS y HSTS según el entorno.

### Configuración

La configuración común está en `config/settings/base.py`; `dev.py` y `prod.py`
ajustan el comportamiento por ambiente. Variables relevantes:

| Variable | Propósito |
|---|---|
| `DJANGO_SECRET_KEY` / `SECRET_KEY` | Clave secreta Django; no reutilizar valores de ejemplo en producción |
| `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Modo debug y hosts permitidos |
| `DATABASE_URL` | Conexión PostgreSQL; sin ella se usa SQLite local |
| `KEYCLOAK_SERVER_URL`, `KEYCLOAK_INTERNAL_URL`, `KEYCLOAK_REALM` | Direcciones, realm y nombre de Keycloak |
| `OIDC_RP_CLIENT_ID`, `OIDC_RP_CLIENT_SECRET` | Cliente web OIDC |
| `KEYCLOAK_ADMIN_CLIENT_ID`, `KEYCLOAK_ADMIN_CLIENT_SECRET` | Cliente de servicio de administración |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_FROM` | SMTP real para los correos de producción |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_COOKIE_SECURE`, `DJANGO_HSTS_SECONDS` | Opciones de seguridad de producción |

`.env` y `.env.prod` están excluidos de Git; usar `.env.example` como referencia
y mantener los secretos fuera del repositorio. El realm de desarrollo contiene
configuración y cuentas de demostración, por lo que no debe importarse sin
revisión a un entorno real.

## Calidad, pruebas y documentación

- Pruebas: `pytest` (configuración en `pytest.ini`; pruebas dentro de las apps).
- Cobertura: Coverage.py, configurado por `.coveragerc`.
- Chequeo Django: `python manage.py check`.
- Documentación de código: Sphinx, configuración y páginas en `docs/sphinx/`;
  generación con
  `sphinx-build -b html docs/sphinx docs/sphinx/_build`.
- Migraciones de base de datos: versionadas en `apps/*/migrations/`.

## Límites y pendientes observables en el repositorio

- No existe cliente de cotizaciones externo, tareas programadas, colas, Redis,
  Celery ni broker de mensajes. El panel utiliza las tasas que ya se cargaron
  en la base.
- La interfaz es server-rendered; no hay React, Vue, Vite ni CDN configurado.
- Hay vistas que intentan renderizar `conversiones/comprar.html`,
  `conversiones/vender.html`, `conversiones/comprobante_compra.html`,
  `conversiones/comprobante_venta.html` y plantillas bajo `comisiones/`, pero
  esos archivos no aparecen en el inventario versionado. Esos recorridos de
  interfaz requieren las plantillas correspondientes para completarse.
- `tiene_permiso()` y los modelos de permisos están implementados, pero las
  vistas de negocio revisadas autorizan por rol; no se observa una aplicación
  transversal de permisos funcionales en esas vistas.
- Las pruebas y chequeos deben ejecutarse en un entorno que tenga instaladas
  las dependencias Python declaradas en `requirements.txt`.

## Referencias del repositorio

- [README.md](./README.md): instalación y comandos de ejecución.
- [requirements.txt](./requirements.txt) y [package.json](./package.json):
  dependencias backend y frontend.
- [config/settings/](./config/settings/): configuración Django por ambiente.
- [docker-compose.yml](./docker-compose.yml) y
  [docker-compose.prod.yml](./docker-compose.prod.yml): servicios y despliegues.
- [keycloak/realm-global-exchange.json](./keycloak/realm-global-exchange.json):
  configuración versionada del realm.
- [apps/](./apps/) y [templates/](./templates/): módulos de negocio e interfaz.
