# CHIA — Conversaciones con Inteligencia Artificial

Registro del uso de IA como herramienta de apoyo durante el **Sprint 1** del
proyecto Global Exchange (Grupo 9, FP-UNA).

- **Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.
- **Módulo documentado:** integración con Keycloak — login por roles (GEG9-24),
  autorregistro con verificación por correo (GEG9-16) y menú principal (GEG9-25).
- **Modalidad de trabajo:** se usó como asistente de consulta y de programación.
  El equipo definió qué construir, tomó las decisiones de diseño, ejecutó los
  comandos y verificó cada resultado contra el entorno real antes de darlo por
  bueno. El código propuesto por la IA se revisó y se ajustó antes de integrarlo.

Este documento está organizado por **consulta realizada**, indicando qué se
preguntó, qué se aprendió y qué se decidió a partir de eso.

---

## 1. Consultas sobre integración con Keycloak

### 1.1 «El login redirige a `http://keycloak:8080` y el navegador da `ERR_NAME_NOT_RESOLVED`»

**Lo que aprendimos.** `keycloak` es el nombre del servicio *dentro* de la red de
Docker. El navegador corre en Windows, fuera de Docker, y para él ese nombre no
existe. Keycloak se alcanza por **dos caminos distintos**:

| Camino | Quién lo usa | Valor |
|---|---|---|
| `KEYCLOAK_SERVER_URL` | El **navegador** (pantalla de login) | `localhost:8080` |
| `KEYCLOAK_INTERNAL_URL` | **Django**, por detrás | `keycloak:8080` |

**Decisión.** Separar ambas variables en la configuración, y detectar
automáticamente si el proceso corre dentro de un contenedor (comprobando si
existe `/.dockerenv`) para elegir el valor correcto.

### 1.2 «Edito el `.env` y Django sigue usando los valores viejos»

El síntoma era un `401 unauthorized_client: Invalid client credentials` al
iniciar sesión, con el *client secret* correcto en el archivo.

**Lo que aprendimos.** `docker-compose` lee `env_file` **una sola vez, al crear
el contenedor**; después esos valores quedan congelados. Y `django-environ` no
pisa variables que ya existen en el entorno, así que ignoraba el archivo
editado. Por eso un `docker compose restart` no alcanza: hace falta
`--force-recreate`.

**Decisión.** En desarrollo, dar prioridad al archivo `.env` sobre el entorno del
proceso, y documentar la diferencia entre `restart` y `--force-recreate`.

### 1.3 «El token se obtiene bien, pero `/userinfo` responde 401»

**Lo que aprendimos.** El token declara `iss: http://localhost:8080/...` (el
hostname que usó el navegador), pero Django consultaba `http://keycloak:8080/...`.
Keycloak compara el emisor del token contra el hostname por el que le entra la
consulta; como no coinciden, lo rechaza aunque el token sea válido.

También aprendimos que **esa consulta no es necesaria**: el `id_token` ya trae el
correo y el nombre, y la librería lo verifica contra las claves públicas de
Keycloak antes de entregarlo. OpenID Connect contempla justamente este caso.

**Decisión.** Armar los datos del usuario desde el `id_token` ya verificado, lo
que además ahorra una consulta de red por cada inicio de sesión. Como corrección
de fondo, se fijó `KC_HOSTNAME` para que el emisor sea estable.

### 1.4 «¿Por qué los roles no llegan a Django?»

**Lo que aprendimos.** Keycloak **no envía los roles del realm en `/userinfo`**.
Van dentro del `access_token`, en `realm_access.roles`.

**Decisión.** Leerlos de ahí y sincronizarlos con los **Grupos de Django** en
cada login, reemplazando los anteriores. Así, si en Keycloak se revoca un rol, en
Django desaparece también: Keycloak queda como única fuente de verdad, sin
duplicar la administración de permisos en dos lugares.

---

## 2. Consultas sobre el correo de verificación

### 2.1 «¿Por qué hace falta una cuenta de correo para la aplicación, si el usuario ya pone su propio correo al registrarse?»

Fue la consulta que más ayudó a entender el mecanismo.

**Lo que aprendimos.** Hay dos correos distintos en juego:

- El que escribe el usuario es el **destinatario**: a dónde llega el mensaje.
- La aplicación necesita además un **remitente**: desde dónde se envía.

Los servidores de correo no aceptan mensajes de desconocidos —si lo hicieran,
cualquiera podría enviar correos haciéndose pasar por un banco—. Antes de
aceptar el envío preguntan «¿quién sos?», y hay que responder con un usuario y
una contraseña. Esa es la cuenta de la aplicación.

Una sola cuenta sirve para todos los usuarios que se registren: no es una cuenta
por usuario.

### 2.2 «¿Se puede usar una API en vez de SMTP?»

**Lo que aprendimos.** Keycloak solo envía correo por SMTP. Usar una API HTTP
exigiría programar una extensión en Java (un *SPI*) y compilarla dentro de la
imagen. Pero los servicios de correo transaccional (Brevo, SendGrid, Mailgun)
**también ofrecen SMTP**, así que se puede usar un servicio profesional sin
escribir código adicional.

### 2.3 «¿Qué código del proyecto hace el envío?»

**Lo que aprendimos.** Ninguno. No hay una sola llamada de envío de correo en
`apps/` ni en `config/`. **Django ni se entera** de que se envió un correo: lo
hace Keycloak con su propio código interno.

El recorrido real es:

```
Navegador → Django → Keycloak → (SMTP) → Gmail → bandeja del usuario
                         ↑
              acá ocurre el envío
```

Django solo aparece al principio (redirigir a Keycloak) y al final (recibir al
usuario ya verificado). Lo único que escribimos nosotras es la **configuración**:
qué servidor usar y con qué credenciales.

Aprendimos también que los ajustes `EMAIL_*` de Django en `prod.py` son para
correos que envíe *la aplicación* —hoy ninguno—, y no tienen relación con la
verificación de Keycloak. Se decidió que ambos lean las mismas variables del
`.env` para tener las credenciales en un solo lugar.

### 2.4 «¿Conviene crear un correo propio para la aplicación?»

**Lo que aprendimos.** Sí, por cuatro razones: el remitente lo ve el usuario final
y debe representar al sistema, no a una persona; la contraseña es compartida con
el equipo; si el proveedor bloquea la cuenta por envíos automáticos no afecta un
correo personal; y al terminar el proyecto se elimina sin más.

**Decisión.** Se creó una cuenta dedicada y se generó una *contraseña de
aplicación* de Google (Gmail rechaza la contraseña normal de la cuenta desde
2022, y exige verificación en dos pasos para generarla).

### 2.5 «¿Cómo probar el correo sin depender de internet?»

**Lo que aprendimos.** Existen servidores SMTP falsos como **Mailpit**, que
atrapan los correos y los muestran en una interfaz web sin enviarlos a ninguna
parte.

**Decisión.** Usar Mailpit como valor por defecto en desarrollo: el entorno
funciona al clonarlo, sin pedirle credenciales a nadie, y permite demostrar el
circuito completo sin depender de la conexión. Para usuarios reales se cambia con
un comando.

---

## 3. Consultas sobre persistencia y entorno

### 3.1 «¿Por qué se pierde la configuración de Keycloak?»

**Lo que aprendimos.** Keycloak guardaba todo en una base H2 **dentro del
contenedor**, sin volumen. Un `docker compose down` borraba el realm, el client,
los roles y los usuarios, y había que reconfigurar todo a mano.

**Decisión.** Dos capas de protección:

1. Base PostgreSQL propia con volumen, igual que en producción.
2. El realm versionado en Git, que se importa solo al arrancar. Quien clona el
   repositorio levanta el entorno ya configurado.

**Verificación.** Se borró el volumen de Keycloak a propósito y todo se
reconstruyó desde el repositorio. Un reinicio posterior de la máquina confirmó
que los datos ahora persisten.

### 3.2 «Keycloak no arranca y el log no dice por qué»

**Lo que aprendimos.** Keycloak sugiere reejecutar con `--verbose` para ver la
causa. Así apareció un `ModelDuplicateException`: el realm exportado desde la API
(67 KB, 116 claves) conservaba los roles de los clientes internos de Keycloak
(`realm-management`, `account`, `broker`), que Keycloak **crea solo** al armar un
realm nuevo. El import intentaba crearlos por segunda vez.

**Decisión.** Reemplazar el export automático por un realm escrito a mano de
2,4 KB con únicamente lo del proyecto, dejando que Keycloak complete el resto con
sus valores por defecto. Además de funcionar, ahora se puede leer y revisar.

### 3.3 «El comando `docker` se cuelga y no da ningún error»

**Lo que aprendimos a diagnosticar.** Revisando por capas: el motor `dockerd`
estaba vivo dentro de la distro `docker-desktop` con los contenedores corriendo,
y el proceso proxy dentro de Ubuntu respondía. Lo roto era el tramo entre
`/var/run/docker.sock` y el motor: por eso el cliente esperaba para siempre en
lugar de fallar.

**Decisión.** Terminar la máquina virtual de Docker, cerrar por la fuerza los
procesos de Docker Desktop en Windows y volver a abrirlo. Se adoptó la costumbre
de anteponer `timeout 15` a los comandos de Docker para que corten solos.

### 3.4 «¿Por qué no me funciona Docker?» (segunda vez)

**Lo que aprendimos.** No era Docker. Los contenedores tenían la política de
reinicio por defecto (`no`), así que al reiniciarse la máquina quedaban
detenidos y no había nada escuchando en los puertos.

**Decisión.** `restart: unless-stopped` en los cinco servicios, para que el
entorno vuelva solo.

---

## 4. Consultas sobre Git Flow

### 4.1 «¿Dónde se usan los tags?»

**Lo que aprendimos.** No van en las funcionalidades:

| | Cuándo | Dónde |
|---|---|---|
| Rama `feature/GEG9-XX` | Por cada historia | Sale de `develop` y vuelve a `develop` |
| **Tag de release** | Al **cerrar el sprint** | Sobre `main` |

### 4.2 «Hice merge en `main` en vez de `develop`, ¿cómo lo saco?»

**Lo que aprendimos.** Conviene **no deshacerlo**. Revertir un commit de merge
con `git revert -m 1` es una trampa conocida: Git queda registrando que esos
commits «ya se integraron y se revirtieron», y el merge real de fin de sprint no
traería nada. Reescribir la rama con `--force` rompería el historial que los
demás integrantes ya descargaron.

**Decisión.** Dejarlo. El contenido de `main` era idéntico al de `develop`, así
que el impacto real era nulo.

### 4.3 «¿Qué significa mover `develop` hacia atrás?»

**Lo que aprendimos.** Una rama en Git **no es una carpeta ni una copia de los
archivos: es una etiqueta que señala un commit**. Mover la etiqueta no borra
nada; los commits siguen existiendo mientras alguna rama los alcance. Por eso,
antes de mover `develop`, se crea la rama de la funcionalidad: para que los
commits nunca queden sin referencia.

También aprendimos la diferencia entre estar «adelante» (tener commits que el
remoto no tiene) y «atrás» (que el remoto tenga commits propios).

### 4.4 «¿Traigo las ramas de mis compañeros o subo solo la mía?»

**Lo que aprendimos.** Cada integrante integra su propia rama: quien escribió el
código es quien sabe si está terminado, y el historial debe reflejar quién
integró qué. Se verificó además que no hubiera archivos en común entre las ramas
para descartar conflictos.

### 4.5 «¿Es obligatorio hacer el merge ahora?»

**Lo que aprendimos.** El merge se hace cuando la historia está terminada, y
conviene hacerlo por **Pull Request** en lugar de por consola: deja registro de
revisión de código, que es parte del criterio de calidad. También se aprendió que
GitHub propone `main` por defecto como destino, y hay que cambiarlo a `develop`.

---

## 5. Consultas sobre los criterios de la entrega

### 5.1 «¿Qué es el PDO?»

**Lo que aprendimos.** Es documentación del código **generada por una
herramienta**, no escrita a mano. Se escriben los `"""docstrings"""` en el código
y Sphinx arma un sitio HTML navegable a partir de ellos.

**Decisión.** Configurar Sphinx una vez y regenerar la documentación al final,
cuando todas las historias estuvieran integradas. Configurarlo desde el principio
evitó dejarlo para último momento; generarlo al final aseguró que saliera
completo.

### 5.2 «¿Qué es el CHIA?»

Este documento.

---

## 6. Verificaciones realizadas

No se dio nada por bueno sin ejecutarlo contra el entorno real:

- **Login con los tres roles** (`administrador`, `analista_cambiario`,
  `usuario_cliente`), comprobando que el menú cambia según el rol.
- **Vista protegida:** sin sesión, `/panel/` redirige a Keycloak.
- **Cierre de sesión:** cierra la sesión en Django y también en Keycloak.
- **Autorregistro con correo real:** registro, correo recibido en la bandeja,
  enlace abierto, cuenta con `emailVerified: true` y acceso a la aplicación.
- **Persistencia:** se borró el volumen de Keycloak y el entorno se reconstruyó
  solo desde el repositorio.
- **Pruebas unitarias:** la suite completa del sprint en verde.
- **Revisión del proyecto:** `manage.py check` sin problemas y sin migraciones
  pendientes de generar.

---

## 7. Observaciones para los próximos sprints

1. **`is_superuser` para el rol `administrador`.** Quien tiene ese rol recibe
   `is_superuser = True`, lo que **saltea todas las verificaciones de permisos de
   Django**. Con ese usuario no se puede demostrar que los permisos finos
   funcionan. Conviene revisarlo al profundizar GEG9-21.

2. **Rotar el *client secret*.** El realm se recreó varias veces durante el
   desarrollo; conviene una rotación final antes de la entrega, y que cada
   integrante ejecute `scripts/sincronizar_secret.py`.

3. **`EMAIL_BACKEND` quedará obsoleto en Django 7.** Las pruebas muestran un
   aviso: el ajuste se reemplaza por `MAILERS`.
