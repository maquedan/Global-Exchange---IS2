# CHIA — Conversaciones con Inteligencia Artificial

Registro del uso de IA como herramienta de apoyo durante el **Sprint 6** del
proyecto Global Exchange (Grupo 9, FP-UNA).

- **Modalidad de trabajo:** se utilizó como apoyo para relevar el código,
  implementar cambios puntuales y ejecutar pruebas en el entorno local del
  proyecto. Se documentan las decisiones y verificaciones de esta conversación;
  no se incluyen secretos ni credenciales.

## 1. Ryuto Maehara - RF013, Control de sesiones por inactividad y cierre voluntario

### 1.1. «¿Por qué `DJANGO_SESSION_IDLE_TIMEOUT=30` no cerraba la sesión?»

**Lo que aprendimos.** El contenedor sí había cargado `SESSION_COOKIE_AGE=30`
y `SESSION_SAVE_EVERY_REQUEST=True`. La caducidad del lado servidor impedía
usar una sesión vencida en la siguiente solicitud, pero no podía actualizar
una página que seguía abierta en el navegador. Hacía falta un temporizador en
la interfaz para que el vencimiento tuviera un efecto visible.

**Decisión.** Mantener la expiración de Django como control del lado servidor
y agregar un temporizador para las páginas autenticadas. El plazo se expone
desde la sesión al template y se usa para enviar un `POST` de cierre, con
protección CSRF.

### 1.2. «¿Por qué al volver a cargar la página seguía dentro de la cuenta?»

**Lo que aprendimos.** El cierre estándar de `mozilla-django-oidc` cierra la
sesión de Keycloak solo si la solicitud todavía identifica al usuario como
autenticado en Django. Cuando el temporizador enviaba el cierre en el mismo
instante en que caducaba Django, Keycloak no recibía el `id_token_hint`; su
sesión SSO seguía activa y el siguiente login autenticaba al usuario de nuevo.
Además, sin ese token Keycloak podía pedir confirmación en una pantalla
intermedia.

**Decisión.** Agregar una ruta de cierre por inactividad que obtiene la URL de
cierre de Keycloak y cierra Django incluso si la sesión local ya venció. El
temporizador se adelanta hasta dos segundos (o el 10 % del plazo, si es menor)
para enviar el `id_token_hint` antes de que Django elimine la sesión. Si la
sesión ya venció, se usa el `client_id` como alternativa.

### 1.3. «¿Cómo se configura y se comprueba el plazo?»

- `DJANGO_SESSION_IDLE_TIMEOUT` se interpreta en segundos y tiene un valor
  predeterminado de 900 (15 minutos); se documentó en los ejemplos de entorno.
- El contenedor local se verificó con un valor efectivo de 30 segundos. Si se
  cambia `.env`, hay que reiniciar el servicio `web` para que el proceso vuelva
  a leer la configuración.
- La prueba manual en navegador confirmó que, tras la inactividad, el flujo
  termina en Keycloak y muestra la pantalla de inicio de sesión, no la cuenta
  autenticada.

### 1.4. Verificaciones realizadas

- 103 pruebas de `apps/usuarios/tests` aprobadas, incluidas las de expiración,
  renovación con actividad, cierre voluntario y cierre por inactividad con la
  sesión Django ya vencida.
- `python manage.py check` sin errores y `git diff --check` limpio.

## 2. Menú — Ocultar opciones de historial y diferencias de caja

**Consulta:** quitar «Historial de caja» y «Diferencias de caja» de la barra
de navegación.

**Decisión.** Eliminar únicamente esas dos opciones del menú principal; las
rutas y funcionalidades de caja se mantienen disponibles. Se agregó una
prueba que confirma que ambas etiquetas no aparecen para el rol administrador.

**Verificación.** Las 13 pruebas de `apps/usuarios/tests/test_menu.py`
aprobaron.

## 3. Ryuto Maehara - RF024, Gestión de Anulaciones

### 3.1. «¿La anulación debe incluir compras y se puede reembolsar?»

**Lo que aprendimos.** La anulación de ventas ya registraba el motivo, el
administrador y la fecha, además de revertir los movimientos de efectivo
asociados. Las compras no tenían un flujo equivalente de anulación. Los pagos
electrónicos sí permiten solicitar el reembolso al proveedor original; una
transferencia conciliada requiere una devolución manual verificada por un
administrador.

**Decisión.** Incorporar la anulación de compras confirmadas, exigir un motivo y
registrar la transición a `ANULADA` con el actor y la fecha. Para pagos de
pasarela, anular solo si el proveedor confirma el reembolso. Para pagos manuales
o compras sin un pago asociado, exigir confirmación administrativa de que la
devolución ya se realizó. Si el proveedor deja el reembolso pendiente o lo
rechaza, mantener la compra pagada y dejar el pago para revisión; la anulación
se puede completar después de verificar manualmente la devolución.

### 3.2. «¿Cómo se accede y qué se muestra?»

- Se agregó «Compras y anulaciones» al menú del administrador y un listado de
  compras con acceso al comprobante y a la trazabilidad.
- El comprobante permite anular solo compras confirmadas; una compra anulada
  no se puede anular nuevamente.
- La migración agrega `anulado_en` a las compras. Las vistas de historial que
  filtran por estado confirmado dejan de incluir las compras anuladas.
- Se actualizaron las pruebas de menú y permisos para limitar las acciones al
  administrador.

### 3.3. Verificaciones y alcance

- Pasaron las pruebas focalizadas de conversiones, pagos y menú; también
  `python manage.py check`, `makemigrations --check --dry-run` y `git diff
  --check`.
- Se aplicó la migración `0012_compradivisa_anulado_en` y se verificó en el
  navegador el listado y el comprobante con compras de ejemplo. No se ejecutó
  un reembolso real de dLocal.
- Las compras actuales no generan movimientos de caja; por eso no hay un
  movimiento de efectivo de compra que este flujo pueda revertir. Si se agrega
  el pago de compras en efectivo, habrá que modelar ese movimiento.

## 4. Ryuto Maehara - GEG9-78, Configuración de seguridad (RF036)

### 4.1. «¿Cómo se configura el tiempo de inactividad?»

**Decisión.** Agregar la pantalla «Seguridad», visible y accesible solo para el
rol administrador. Allí se configura el tiempo máximo de inactividad entre 5
minutos y 8 horas. El valor se guarda en la base de datos y el middleware lo
aplica a las sesiones autenticadas en sus solicitudes, sin reiniciar Django.
Los cambios se registran con el usuario, la fecha y los valores anterior y
nuevo.

### 4.2. «¿Sigue siendo necesaria `DJANGO_SESSION_IDLE_TIMEOUT`?»

- La variable se expresa en segundos y sirve como valor inicial si todavía no
  existe una configuración guardada; `900` equivale a 15 minutos.
- Una vez creada la configuración en la base de datos, el valor guardado tiene
  prioridad. Cambiar `.env` no reemplaza el parámetro configurado en la
  pantalla.
- Las sesiones activas adoptan el nuevo plazo en su siguiente solicitud. Una
  pestaña abierta puede conservar su temporizador anterior hasta volver a
  cargar o hacer otra solicitud.

### 4.3. «¿Por qué aparecía `ProgrammingError` en `/panel/`?»

**Causa y resolución.** El código consultaba la tabla nueva de configuración,
pero la migración aún no se había aplicado en la base de datos del contenedor.
Se ejecutó `python manage.py migrate usuarios`; luego se verificó que el panel
y la pantalla de seguridad cargaran correctamente.

### 4.4. Verificaciones realizadas

- Las 460 pruebas del proyecto aprobaron con SQLite; `python manage.py check`
  y `makemigrations --check --dry-run` no detectaron problemas.
- Se verificó en el navegador el panel y la pantalla de seguridad después de
  aplicar la migración `0002_cambioconfiguracionseguridad_configuracionseguridad`.