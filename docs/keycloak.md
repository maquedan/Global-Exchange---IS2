# Keycloak — Global Exchange (GEG9-16, GEG9-21, GEG9-24, RF011)

Autenticación con Keycloak: autorregistro con verificación por correo, login
para todos los roles, y roles sincronizados con Django.

## Cómo levantar todo

```bash
docker compose up -d
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/sincronizar_secret.py
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
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/sincronizar_secret.py
docker compose restart web
```

## Usuarios de prueba

| Usuario | Clave | Rol | Qué ve en el menú |
|---|---|---|---|
| `admin.demo` | `Demo1234!` | `administrador` | Panel, Administración |
| `analista.demo` | `Demo1234!` | `analista_cambiario` | Panel |
| `cliente.demo` | `Demo1234!` | `usuario_cliente` | Panel |
| `cajero.demo` | `Demo1234!` | `cajero` | Panel |
| `nuevo.demo` | `Demo1234!` | `usuario_cliente` | Panel, Cotizaciones, Simular |

`nuevo.demo` es el usuario para probar **RF010 (GEG9-20)**: tiene el rol de
cliente pero **ningún cliente asociado**, igual que alguien que acaba de
registrarse. Sirve para comprobar que queda limitado a funciones de consulta:
no ve en el menú las opciones de operar, y si escribe a mano una URL de
operación lo manda a `/sin-cliente/`. **No le asocies ningún cliente**, o deja
de servir para esa prueba.

Los usuarios `cajero.demo` y `nuevo.demo` se crean al importar el realm por
primera vez. En un Keycloak ya existente el archivo del realm no se vuelve a
importar, así que hay dos caminos: crearlos a mano desde la consola de
Keycloak con estas credenciales y su rol, o rehacer el contenedor para que
importe el realm de nuevo:

```bash
# 1. Averiguá el nombre del volumen de Keycloak (el prefijo depende de la
#    carpeta donde esté clonado el proyecto):
docker volume ls | grep keycloak

# 2. Parar y borrar SOLO los contenedores de Keycloak:
docker compose stop keycloak keycloak-db
docker compose rm -f keycloak keycloak-db

# 3. Borrar SOLO el volumen de Keycloak, con el nombre del paso 1:
docker volume rm global-exchange---is2_keycloak_pgdata

# 4. Levantarlo de nuevo: ahí reimporta el realm.
docker compose up -d keycloak
```

> ⚠️ **No uses `docker compose down -v`**, ni siquiera nombrando los servicios
> de Keycloak. Ese `-v` borra **todos** los volúmenes declarados en el
> compose, incluido `pgdata`, que es la base de datos de la aplicación:
> perderías clientes, operaciones y facturas. Por eso los pasos de arriba
> nombran el volumen de Keycloak uno por uno.

> Al rehacer el volumen se pierden los usuarios y roles que hayas creado a
> mano desde la consola de Keycloak. Los que están en el archivo del realm
> (`admin.demo`, `cliente.demo`, etc.) vuelven solos.

> La opción **Clientes** aparece sola en el menú de `administrador` y
> `analista_cambiario` cuando se implemente el CRUD (GEG9-11): el menú
> saltea las rutas que todavía no existen.

## Administración dinámica de roles (RF011)

El menú del administrador incorpora **Roles y permisos**. La pantalla usa el
cliente técnico `global-exchange-admin` para crear/eliminar realm roles y
asignarlos a usuarios de Keycloak. Los permisos de funcionalidades se guardan
en Django y se vinculan a esos roles. La guía completa está en
[`rf011-roles-permisos.md`](rf011-roles-permisos.md).

Después de importar un realm nuevo, ejecutar nuevamente
`python3 scripts/sincronizar_secret.py`: ahora también incorpora
`KEYCLOAK_ADMIN_CLIENT_SECRET` en `.env`.

## Demostración

### 1. Login para todos los roles

Entrar a http://localhost:8000 → *Iniciar sesión* → probar con cada usuario.
El panel muestra el rol que trajo de Keycloak y **el menú cambia** según el rol.

Cerrar sesión entre prueba y prueba: el logout también cierra la sesión en
Keycloak, así que vuelve a pedir contraseña.

### 2. Creación de usuario y roles en Keycloak

En http://localhost:8080 (`admin`/`admin`), realm **global-exchange**:

- **Realm roles** → los cuatro roles del sistema (`administrador`,
  `analista_cambiario`, `usuario_cliente` y `cajero`).
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

### Para usuarios reales

Mailpit **no manda nada a internet**: si un usuario real se registra, no le
llega nada. Para que sí lleguen, hay que configurar un SMTP de verdad.

Las credenciales van en el `.env` (que no se versiona), y se aplican con:

```bash
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/configurar_smtp.py
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/configurar_smtp.py --probar tu@correo.com
docker compose run --rm --no-deps -e KEYCLOAK_URL=http://keycloak:8080 \
  web python scripts/configurar_smtp.py --mailpit
```

Si `EMAIL_HOST` está vacío, el script deja Mailpit. Las mismas variables las usa
Django en producción, así que las credenciales quedan en un solo lugar.

**Gmail** — necesita la verificación en dos pasos activada y una *contraseña de
aplicación* (Google rechaza la contraseña normal de la cuenta desde 2022):

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=tucuenta@gmail.com
EMAIL_HOST_PASSWORD=abcd efgh ijkl mnop     # la de 16 letras que da Google
EMAIL_FROM=tucuenta@gmail.com               # tiene que ser la misma cuenta
```

Se genera en cuenta de Google → *Seguridad* → *Verificación en 2 pasos* →
*Contraseñas de aplicaciones*. Límite: unos 500 correos por día.

**Alternativa sin usar un Gmail personal:** Brevo, Mailgun o SendGrid tienen
plan gratuito (Brevo: 300 correos/día). Cambian solo `EMAIL_HOST`, el usuario y
la clave; el resto queda igual.

> El puerto define el cifrado: **587 → STARTTLS**, **465 → SSL**. El script lo
> resuelve solo según el puerto que pongas.

## Notas técnicas

**`KC_HOSTNAME: http://localhost:8080`** — fija el emisor de los tokens. Sin
esto, Keycloak arma el emisor con el hostname por el que le entra cada consulta:
el navegador le habla por `localhost` y Django por `keycloak`, y rechaza tokens
legítimos con 401.

**Roles** — Keycloak no los manda en `/userinfo`, van dentro del `access_token`
en `realm_access.roles`. `apps/usuarios/auth.py` los lee de ahí y los copia a
Grupos de Django en cada login, reemplazando los anteriores.

El archivo de importación inicial define los cuatro roles. Keycloak solo importa
ese archivo al crear el realm; en un ambiente que ya tenga datos persistidos,
agrega `cajero` desde **Roles y permisos** en Global Exchange o desde
**Realm roles** en la consola de Keycloak. No es necesario recrear el realm.

**Dos URLs para Keycloak** — `KEYCLOAK_SERVER_URL` es la que abre el navegador
(siempre `localhost`); `KEYCLOAK_INTERNAL_URL` es la que usa Django por dentro
(`keycloak` en Docker). Son caminos distintos al mismo servidor.

## Recuperación de acceso (RF012 — GEG9-22)

La contraseña la gestiona **Keycloak**, no Django (RNF003). El flujo ya viene
en Keycloak y está habilitado con `resetPasswordAllowed: true`; lo que se
versionó en esta historia son los ajustes de los que depende.

### Cómo probarlo

1. Asegurate de que Keycloak le hable a **Mailpit**, el buzón falso que atrapa
   los correos sin mandarlos a internet:

   ```bash
   python3 scripts/configurar_smtp.py --mailpit
   ```

2. Abrí http://localhost:8000 → **Iniciar sesión**. En la pantalla de Keycloak,
   tocá **"¿Olvidaste tu contraseña?"**.
3. Escribí `cliente.demo` (o su correo) y enviá.
4. Abrí **http://localhost:8025**: ahí está el correo *"Reiniciar contraseña"*.
5. Seguí el enlace, definí la contraseña nueva y entrá a Global Exchange.

### Lo que se comprobó contra el servidor real

| Qué | Resultado |
|---|---|
| ¿El enlace se puede reutilizar? | **No.** Al reintentarlo: *"Action expired. Please continue with login now."* |
| ¿Cuánto dura? | **5 minutos** (`actionTokenGeneratedByUserLifespan`), fijado en el realm |
| ¿Se puede averiguar qué correos existen? | **No.** Usuario verificado, sin verificar e inexistente dan el **mismo** mensaje |
| ¿Manda el enlace si el correo NO está verificado? | **Sí, lo manda igual** |

### Sobre el correo sin verificar

El ERS dice "enviados al correo verificado", pero Keycloak manda el enlace
aunque el correo no esté verificado. Se comprobó pidiendo la recuperación para
un usuario con `emailVerified: false`: el correo llegó igual.

Keycloak no tiene una opción para condicionar el envío a que el correo esté
verificado; hacerlo requeriría un autenticador propio, que es justamente el
tipo de código que RNF003 evita. Lo que protege la cuenta es **`verifyEmail:
true`**: mientras el correo no esté verificado, Keycloak exige verificarlo
para poder usar la cuenta, así que cambiar la contraseña por sí solo no
alcanza para entrar.

> No está verificado en este relevamiento que Keycloak bloquee el ingreso
> después de restablecer con un correo sin verificar: es lo que indica la
> configuración, pero no se probó ese caso punta a punta.

### Usar un correo real en lugar de Mailpit

Para que los correos salgan de verdad, completá en el `.env` (nunca en el
repositorio):

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=la-cuenta@gmail.com
EMAIL_HOST_PASSWORD=la-contraseña-de-aplicación-de-16-letras
EMAIL_FROM=la-cuenta@gmail.com
```

y aplicalo con:

```bash
python3 scripts/configurar_smtp.py
```

Gmail exige verificación en dos pasos y una **contraseña de aplicación**: no
acepta la contraseña normal de la cuenta.

> ⚠️ **El archivo del realm y el Keycloak que corre se desincronizan.** El
> realm se importa **solo en el primer arranque** del contenedor; después,
> cualquier cambio hecho a mano o con `configurar_smtp.py` vive únicamente en
> el servidor. Durante esta historia el archivo decía Mailpit y el servidor
> apuntaba a Gmail, y por eso los correos de prueba no aparecían por ningún
> lado. Si algo no coincide con lo que esperás, comparalo con:
>
> ```bash
> docker compose exec web python manage.py shell -c "
> from apps.usuarios.keycloak_admin import KeycloakAdmin
> kc = KeycloakAdmin(); print(kc._request(kc._admin_url).get('smtpServer'))"
> ```
