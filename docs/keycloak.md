# Keycloak — Global Exchange (GEG9-16, GEG9-21, GEG9-24)

Autenticación con Keycloak: autorregistro con verificación por correo, login
para todos los roles, y roles sincronizados con Django.

## Cómo levantar todo

```bash
docker compose up -d
python3 scripts/sincronizar_secret.py     # copia el client secret al .env
docker compose restart web
docker compose exec web python manage.py migrate
```

| Servicio | URL | Para qué |
|---|---|---|
| Aplicación Django | http://localhost:8000 | la app |
| Keycloak (admin) | http://localhost:8080 | `admin` / `admin` |
| Mailpit | http://localhost:8025 | leer los correos de verificación |

## Por qué NO se pierde la configuración

Keycloak guarda todo en `keycloak-db`, un PostgreSQL con el volumen
`keycloak_pgdata`. Los datos sobreviven a `docker compose down`.

Además, `keycloak/realm-global-exchange.json` tiene el realm entero versionado
en Git (roles, client, autorregistro, SMTP, usuarios de prueba). Con
`--import-realm`, quien clone el repo levanta todo ya configurado.

> El archivo **no** incluye el client secret: los secretos no van a Git. Por eso
> hace falta `scripts/sincronizar_secret.py` la primera vez.

Para empezar de cero (borra usuarios y sesiones, reimporta el realm):

```bash
docker compose down -v && docker compose up -d
python3 scripts/sincronizar_secret.py && docker compose restart web
```

## Usuarios de prueba (uno por rol)

| Usuario | Clave | Rol | Qué ve en el menú |
|---|---|---|---|
| `admin.demo` | `Demo1234!` | `administrador` | Panel, Administración |
| `analista.demo` | `Demo1234!` | `analista_cambiario` | Panel |
| `cliente.demo` | `Demo1234!` | `usuario_cliente` | Panel |

> La opción **Clientes** aparece sola en el menú de `administrador` y
> `analista_cambiario` cuando se implemente el CRUD (GEG9-11): el menú
> saltea las rutas que todavía no existen.

## Demostración

### 1. Login para todos los roles

Entrar a http://localhost:8000 → *Iniciar sesión* → probar con cada usuario.
El panel muestra el rol que trajo de Keycloak y **el menú cambia** según el rol.

Cerrar sesión entre prueba y prueba: el logout también cierra la sesión en
Keycloak, así que vuelve a pedir contraseña.

### 2. Creación de usuario y roles en Keycloak

En http://localhost:8080 (`admin`/`admin`), realm **global-exchange**:

- **Realm roles** → los tres roles del sistema.
- **Users → Add user** → completar, *Credentials* → poner contraseña
  (*Temporary: Off*), *Role mapping → Assign role* → elegir el rol.
- Entrar a http://localhost:8000 con ese usuario: Django lo crea solo y le
  asigna el grupo correspondiente.

Para mostrar que Keycloak manda: sacarle el rol en Keycloak, volver a entrar en
Django, y el menú cambia. Django **no** guarda roles por su cuenta.

### 3. Autorregistro con verificación por correo

1. http://localhost:8000 → *Iniciar sesión* → **Register**.
2. Completar el formulario y enviar.
3. Keycloak manda el correo de verificación y muestra
   *"You need to verify your email address"*.
4. Abrir **http://localhost:8025** (Mailpit): ahí está el correo.
5. Clic en el enlace de verificación → queda verificado y entra a la app.

Está activado en el realm con `registrationAllowed: true` y `verifyEmail: true`.

## Configuración del correo (SMTP)

En desarrollo el realm apunta a **Mailpit**, un servidor SMTP falso que corre en
Docker y muestra los correos en una web. No hace falta cuenta de Gmail y nada
sale a internet.

Está en *Realm settings → Email*:

| Campo | Valor |
|---|---|
| From | `no-reply@globalexchange.local` |
| Host | `mailpit` |
| Port | `1025` |
| Authentication / SSL / StartTLS | apagados |

### Para producción (Gmail)

En *Realm settings → Email*, con una **contraseña de aplicación** de Google
(no la contraseña normal de la cuenta; requiere verificación en dos pasos):

| Campo | Valor |
|---|---|
| Host | `smtp.gmail.com` |
| Port | `587` |
| StartTLS | activado |
| Authentication | activado, usuario = el correo, clave = la contraseña de aplicación |

## Notas técnicas

**`KC_HOSTNAME: http://localhost:8080`** — fija el emisor de los tokens. Sin
esto, Keycloak arma el emisor con el hostname por el que le entra cada consulta:
el navegador le habla por `localhost` y Django por `keycloak`, y rechaza tokens
legítimos con 401.

**Roles** — Keycloak no los manda en `/userinfo`, van dentro del `access_token`
en `realm_access.roles`. `apps/usuarios/auth.py` los lee de ahí y los copia a
Grupos de Django en cada login, reemplazando los anteriores.

**Dos URLs para Keycloak** — `KEYCLOAK_SERVER_URL` es la que abre el navegador
(siempre `localhost`); `KEYCLOAK_INTERNAL_URL` es la que usa Django por dentro
(`keycloak` en Docker). Son caminos distintos al mismo servidor.
