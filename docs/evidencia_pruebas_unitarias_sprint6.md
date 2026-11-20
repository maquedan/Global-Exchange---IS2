# Constancia de ejecución de pruebas unitarias (PUN)

Registro de ejecuciones reales de las pruebas unitarias realizadas durante el
**Sprint 6** del proyecto Global Exchange.

Cada sección incluye la fecha y hora del sistema, los artefactos probados, el
comando ejecutado, la salida de pytest y los casos cubiertos.

## Leyda Fleitas — RF025, Conciliación Manual (GEG9-75)

| Campo | Valor |
|---|---|
| **Fecha y hora** | lunes 16 de noviembre de 2026, 10:26:24 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/conversiones/tests/test_conciliacion.py` |
| **Comando** | `docker compose exec web pytest apps/conversiones/tests/test_conciliacion.py -v` |
| **Resultado** | **16 passed** en 3.29s |

```text
$ date
Mon Nov 16 10:26:24 -03 2026

$ docker compose exec web pytest apps/conversiones/tests/test_conciliacion.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 16 items

apps/conversiones/tests/test_conciliacion.py ................            [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 16 passed, 1 warning in 3.29s =========================
```

Ninguna prueba llama a Factura Segura ni a dLocal: se agregó un
`conftest.py` en la raíz del proyecto con fixtures `autouse` que fuerzan los
proveedores simulados en **todas** las pruebas (el motivo está en
`docs/chia-sprint6.md`, sección 1.5).

Casos cubiertos:

- **Camino feliz:** conciliar deja la compra `CONFIRMADA`, con
  `confirmado_en` y con la factura electrónica `GENERADA` — o sea que la
  conciliación dispara RF026 por el mismo camino que un pago con tarjeta.
- **Trazabilidad (RF023):** el `CambioEstado` queda con el administrador como
  autor y con la referencia y la observación en el motivo.
- **Registro del cobro:** se crea un `Pago` con proveedor `manual`, estado
  `APROBADO`, la referencia en `id_externo`, el importe en la moneda de la
  operación y el usuario que concilió en `respuesta_cruda`.
- **Lo que no se puede conciliar:** una compra cancelada; dos veces seguidas
  (no duplica ni el pago, ni la factura, ni el cambio de estado); sin
  referencia.
- **RF051 sigue valiendo:** si la cotización cambió, la compra se cancela, no
  se registra ningún pago y la cancelación **queda guardada** — esto último
  fue un bug propio: lanzar la excepción dentro de la transacción la
  revertía.
- **El vencimiento:** una compra marcada para pagar por transferencia no se
  vence ni a los dos días y se puede conciliar; una normal con dos horas sí
  se cancela por `EXPIRADA`. La lista del administrador solo trae las que
  esperan transferencia.
- **Acceso:** el servicio rechaza a quien no tiene el rol `administrador`, y
  las dos vistas devuelven 403 con GET y con POST (parametrizado).
- **RNF011:** un fallo de la facturación no deshace la conciliación.

También se corrió la suite completa: **328 passed** (eran 312), sin
regresiones en las historias de los compañeros ni en las propias.

---

## Leyda Fleitas — RF012, Recuperación de Acceso (GEG9-22)

| Campo | Valor |
|---|---|
| **Fecha y hora** | lunes 16 de noviembre de 2026, 11:02:53 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/usuarios/tests/test_realm_keycloak.py` |
| **Comando** | `docker compose exec web pytest apps/usuarios/tests/test_realm_keycloak.py -v` |
| **Resultado** | **7 passed** en 0.11s |

```text
$ date
Mon Nov 16 11:02:53 -03 2026

$ docker compose exec web pytest apps/usuarios/tests/test_realm_keycloak.py -v
apps/usuarios/tests/test_realm_keycloak.py .......                       [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 7 passed, 1 warning in 0.11s =========================
```

Keycloak no se puede levantar dentro de pytest, así que las pruebas leen el
**archivo del realm versionado** y verifican que la configuración de la que
depende la recuperación esté efectivamente ahí y no librada a los valores por
defecto: recuperación habilitada, verificación de correo exigida, servidor
SMTP definido, **ningún usuario ni contraseña en el archivo**, vencimiento del
enlace fijado en 5 minutos, idioma español y que todos los usuarios de prueba
tengan dirección de correo.

El flujo en sí se recorrió **a mano contra el Keycloak real**, porque es lo
único que lo demuestra:

| Comprobación | Resultado |
|---|---|
| Pedido de recuperación → correo | Llega a Mailpit con asunto *"Reiniciar contraseña"* |
| Enlace → contraseña nueva → ingreso | Funciona |
| Reutilizar el mismo enlace | **Rechazado:** *"Action expired. Please continue with login now."* |
| Mensaje para usuario inexistente | **Idéntico** al de uno existente: no se puede enumerar correos |
| Correo sin verificar | Keycloak **manda el enlace igual** (ver `docs/chia-sprint6.md` 2.4) |

También se corrió la suite completa: **343 passed** (eran 336), sin
regresiones.

---

## Leyda Fleitas — RF009, Conmutación de Cliente en Sesión (GEG9-19)

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 16:55:24 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/usuarios/tests/test_conmutacion_cliente.py` |
| **Comando** | `docker compose exec web pytest apps/usuarios/tests/test_conmutacion_cliente.py -v` |
| **Resultado** | **13 passed** en 3.06s |

```text
$ date
Thu Nov 19 16:55:24 -03 2026

$ docker compose exec web pytest apps/usuarios/tests/test_conmutacion_cliente.py -v
apps/usuarios/tests/test_conmutacion_cliente.py .............            [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 13 passed, 1 warning in 3.06s =========================
```

RF008 dejó el mecanismo hecho, así que estas pruebas cubren lo propio de
RF009: **cambiar** de cliente estando ya operando con otro, y que ese cambio
no abra ninguna puerta. De las 10 pruebas que ya existían en
`test_cliente_activo.py`, ninguna probaba el cambio.

- **El cambio en sí:** se hace sin cerrar sesión (se verifica que la clave de
  sesión sea la misma antes y después); el encabezado pasa a mostrar el
  cliente nuevo y deja de mostrar el anterior; el enlace *Cambiar* aparece con
  dos clientes y desaparece cuando queda uno.
- **Redirección abierta (hallazgo de seguridad):** prueba parametrizada con
  cuatro variantes —URL absoluta, `//dominio`, otro dominio por `http` y
  `javascript:`— tanto por POST como por query string. Todas terminan en el
  panel. Antes de esta historia, la primera redirigía al sitio externo.
- **Volver a la pantalla de origen:** con una ruta interna válida, sí vuelve.
- **Que el cambio no abra puertas:** no se puede elegir un cliente ajeno
  mandando su id en el POST; y una compra pendiente del cliente anterior
  **deja de ser confirmable** tras cambiar de cliente, cosa que antes sí se
  podía.
- **Cliente desactivado:** si se desactiva el activo y queda otro, se pasa a
  ese solo; si se desactivan todos, se vuelve a pedir elegir.

También se corrió la suite completa: **356 passed** (eran 343), sin
regresiones. El detalle de los dos hallazgos está en `docs/chia-sprint6.md`,
secciones 3.1 y 3.2.

---

## Leyda Fleitas — RF016, Gráficos de Evolución de Tasas (GEG9-68)

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 17:15:10 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/tasas/tests/test_tasas.py` |
| **Comando** | `docker compose exec web pytest apps/tasas/ -v` |
| **Resultado** | **20 passed** en 42.96s |

```text
$ date
Thu Nov 19 17:15:10 -03 2026

$ docker compose exec web pytest apps/tasas/ -v
apps/tasas/tests/test_tasas.py ....................                      [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 20 passed, 1 warning in 42.96s ========================
```

El gráfico ya existía y cumple los seis criterios de la historia, así que
**no se cambió el gráfico ni se agregó ninguna librería**. Se sumaron las
**8 pruebas** que faltaban (de 12 a 20) y un aviso que corrige un problema de
información, no de funcionamiento.

**Lo que ya cumplía:** gráfico de evolución por par con líneas de compra y
venta, selector de período (7D / 1M / 3M / Todo), datos del historial real de
`TasaCambio`, acceso para cualquier rol autenticado —incluido el usuario sin
cliente asociado, ya cubierto por pruebas de RF008 y RF010—, y estados
razonables para un par sin historial o con una sola tasa.

**Lo que faltaba y se agregó:**

- **El aviso de rango sin datos.** Con los datos de demostración, todas las
  tasas tienen entre 74 y 101 días: al tocar **7D** no queda ningún punto en
  el rango y el gráfico caía a los dos más recientes **sin decirlo**, con el
  botón marcado como activo. Parecía dato de la última semana. Ahora aparece
  *"No hay registros en los últimos 7 días. Se muestran los 2 más recientes."*
- **Las pruebas del selector de período**, que no tenía ninguna: los cuatro
  rangos presentes; el filtrado es del lado del navegador (el historial
  completo viaja embebido, así que ningún botón recarga la página); cada punto
  lleva fecha, compra y venta, ordenados de más viejo a más nuevo; el JSON
  embebido es válido; las dos líneas del gráfico son compra y venta; el
  usuario sin cliente ve el panel; y el servidor no recorta el historial.

Durante el trabajo, las pruebas nuevas destaparon un error propio: el modelo
tiene una restricción de **una sola tasa activa por par**, y las primeras
versiones creaban varias activas del mismo par. Se corrigieron para armar el
historial con `activo=False` y dejar activa solo la última, que es lo que
ocurre en la realidad. Detalle en `docs/chia-sprint6.md`, sección 4.3.

---

## Leyda Fleitas — RF034, Alertas de Operación (GEG9-76)

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 17:56:10 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/notificaciones/tests/test_alertas_operacion.py` |
| **Comando** | `docker compose exec web pytest apps/notificaciones/ -v` |
| **Resultado** | **22 passed** en 9.83s |

```text
$ date
Thu Nov 19 17:56:10 -03 2026

$ docker compose exec web pytest apps/notificaciones/ -v
apps/notificaciones/tests/test_alertas_operacion.py ............         [ 54%]
apps/notificaciones/tests/test_notificaciones.py ..........              [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 22 passed, 1 warning in 9.83s =========================
```

Las 12 pruebas nuevas llaman a los **servicios de negocio de verdad**
—confirmar, cancelar, vencer, anular— y no al servicio de notificaciones
directamente: así verifican también que el enganche esté puesto en
`registrar_cambio_estado`, que es el único punto por donde pasan los once
cambios de estado del proyecto.

- **Cada transición avisa con su tipo:** confirmar genera
  `OPERACION_CONFIRMADA`; cancelar y vencer generan `OPERACION_CANCELADA` con
  el motivo dentro del mensaje; anular genera `OPERACION_ANULADA`.
- **Crear la operación no avisa:** `estado_anterior` vacío es el nacimiento,
  no un cambio.
- **Solo al dueño:** un usuario asociado a otro cliente no recibe nada, y
  todos los usuarios del cliente de la operación sí reciben.
- **Cliente sin usuarios no rompe:** es el caso de la terminal de
  autoservicio, donde el cliente puede no tener cuenta. No se crea ningún
  aviso y la operación sigue su curso.
- **Un fallo al avisar no deshace la confirmación:** se tumba el servicio de
  notificaciones a propósito y la compra queda `CONFIRMADA` igual.
- **Sin duplicados:** registrar el mismo cambio dos veces genera un solo
  aviso, garantizado por la restricción de unicidad en la base.
- **Se ve y se usa:** aparece en la lista, suma al contador del menú (que no
  filtra por tipo, así que los tipos nuevos entran solos) y se puede marcar
  como leída.
- **Formato de montos:** un único punto (`formatear_monto`), listo para
  cuando se integre GEG9-82.

También se corrió la suite completa: **377 passed** (eran 364), sin
regresiones. Las decisiones de diseño están en `docs/chia-sprint6.md`,
sección 5 — en particular por qué los destinatarios salen del cliente de la
operación y no de quien la disparó (5.2).

---

## Ryuto Maehara - RF013 y GEG9-23, Control de sesiones y simplificación del menú

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 20:18:53 (-03) |
| **Ambiente** | Docker Compose, servicio `web` |
| **Artefactos probados** | `apps/usuarios/tests/test_session_security.py`, `apps/usuarios/tests/test_menu.py` |
| **Comando** | `docker compose exec -T web pytest apps/usuarios/tests/test_session_security.py apps/usuarios/tests/test_menu.py -v` |
| **Resultado** | **19 passed**, 1 warning en 0.76s |

```text
$ docker compose exec -T web pytest apps/usuarios/tests/test_session_security.py apps/usuarios/tests/test_menu.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0
django: version: 6.1.3, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 19 items

apps/usuarios/tests/test_session_security.py ......                      [ 31%]
apps/usuarios/tests/test_menu.py .............                           [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango2028Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 2028.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 19 passed, 1 warning in 0.76s =========================
```

Las seis pruebas de sesiones verifican que una solicitud renueve el
vencimiento, que una sesión vencida exija autenticación, que las páginas
autenticadas incluyan el temporizador, que el cierre voluntario invalide la
sesión local, que el cierre por inactividad pueda cerrar Keycloak después de
vencer Django y que se envíe el `id_token_hint` cuando todavía está disponible.

Las trece pruebas del menú cubren la visibilidad de opciones según roles y
autenticación; incluyen una prueba que confirma que **Historial de caja** y
**Diferencias de caja** no se muestran al administrador. Las rutas de esas
funcionalidades no se eliminaron.

El único warning corresponde a la deprecación futura de `EMAIL_BACKEND`
informada por `pytest-django`; no produjo fallos.

---

## Ryuto Maehara - RF024, Gestión de Anulaciones

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 22:35 (-03) |
| **Ambiente** | Docker Compose, servicio `web` |
| **Artefactos probados** | `apps/conversiones/tests/test_conversiones.py`, `apps/pagos/tests/test_pagos.py`, `apps/usuarios/tests/test_menu.py` |
| **Comando** | `docker compose exec -T web python -m pytest -v apps/conversiones/tests/test_conversiones.py apps/pagos/tests/test_pagos.py apps/usuarios/tests/test_menu.py` |
| **Resultado** | **87 passed**, 1 warning en 1.86s |

```text
$ docker compose exec -T web python -m pytest -v apps/conversiones/tests/test_conversiones.py apps/pagos/tests/test_pagos.py apps/usuarios/tests/test_menu.py
============================= test session starts ==============================
platform linux -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0
django: version: 6.1.3, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 87 items

apps/conversiones/tests/test_conversiones.py ........................... [ 31%]
............................                                             [ 63%]
apps/pagos/tests/test_pagos.py ..............                            [ 79%]
apps/usuarios/tests/test_menu.py ............                            [ 93%]
apps/conversiones/tests/test_conversiones.py ...                         [ 96%]
apps/pagos/tests/test_pagos.py ..                                        [ 98%]
apps/usuarios/tests/test_menu.py .                                       [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango2028Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 2028.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 87 passed, 1 warning in 1.86s =========================
```

### Casos cubiertos

- **Anulación de ventas:** anulación administrativa con registro de la
  transición y movimientos de caja inversos; se verifica que una anulación no
  se aplique si no se puede revertir el efectivo y que un usuario no
  administrador no pueda anular.
- **Anulación de compras:** reembolso exitoso por el proveedor del pago y
  transición a `ANULADA`; devolución manual obligatoria para pagos manuales o
  compras sin un pago asociado; un reembolso pendiente o rechazado mantiene la
  compra pagada y requiere revisión antes de completar la anulación.
- **Pagos:** selección del proveedor original para el reembolso y rechazo del
  reembolso automático en proveedores manuales.
- **Autorización y menú:** solo el administrador puede listar/anular compras;
  las opciones de anulaciones de compras y ventas aparecen solo para el
  administrador.

También se ejecutaron estas verificaciones:

| Comando | Resultado |
|---|---|
| `docker compose exec -T web python manage.py makemigrations --check --dry-run` | No se detectaron cambios de modelo sin migración. |
| `docker compose exec -T web python manage.py check` | No se identificaron problemas de configuración. |
| `docker compose exec -T web python manage.py migrate conversiones` | Se aplicó `conversiones.0012_compradivisa_anulado_en`. |
| `git diff --check` | Sin errores de espacios o formato del diff. |

Se comprobó en el navegador el listado administrativo y el comprobante de una
compra de ejemplo. No se envió un reembolso real al proveedor dLocal; los casos
automatizados de reembolso usan proveedores simulados o mocks. El warning de
pytest es la deprecación futura de `EMAIL_BACKEND` y no produjo fallos.

---

## Ryuto Maehara - GEG9-78, Configuración de seguridad (RF036)

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 23:14:58 (-03) |
| **Ambiente** | Docker Compose, servicio `web` |
| **Artefactos probados** | `apps/usuarios/tests/test_configuracion_seguridad.py` |
| **Comando** | `docker compose exec -T web python -m pytest -v apps/usuarios/tests/test_configuracion_seguridad.py` |
| **Resultado** | **6 passed**, 1 warning en 0.84s |

```text
$ docker compose exec -T web python -m pytest -v apps/usuarios/tests/test_configuracion_seguridad.py
============================= test session starts ==============================
platform linux -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0
django: version: 6.1.3, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 6 items

apps/usuarios/tests/test_configuracion_seguridad.py ......               [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango2028Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 2028.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 6 passed, 1 warning in 0.84s =========================
```

### Casos cubiertos

- Un usuario con rol de cliente no puede acceder a la configuración; el acceso
  está limitado al administrador.
- El administrador puede cambiar el tiempo de inactividad y se auditan el
  usuario, la fecha y los valores anterior y nuevo.
- Se rechazan valores menores a 5 minutos, mayores a 480 minutos y entradas no
  numéricas; los intentos inválidos no generan registros de auditoría.
- El nuevo plazo se refleja en la expiración de una sesión autenticada sin
  reiniciar el sistema.

El warning corresponde a la deprecación futura de `EMAIL_BACKEND` informada
por `pytest-django`; no produjo fallos.

## Ryuto Maehara - GEG9-81, Registro de auditoría

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 23:32:00 (-03) |
| **Ambiente** | Docker Compose, servicio `web`, base PostgreSQL |
| **Artefactos probados** | `apps/usuarios/tests/test_auditoria.py`, `apps/clientes/tests/test_clientes.py`, `apps/comisiones/tests/test_comisiones.py`, `apps/tasa_cambios/tests.py`, `apps/conversiones/tests/test_conciliacion.py`, `apps/conversiones/tests/test_conversiones.py` |
| **Comando** | `docker compose exec -T web python -m pytest -v apps/usuarios/tests/test_auditoria.py apps/clientes/tests/test_clientes.py apps/comisiones/tests/test_comisiones.py apps/tasa_cambios/tests.py apps/conversiones/tests/test_conciliacion.py apps/conversiones/tests/test_conversiones.py` |
| **Resultado** | **110 passed**, 1 warning en 9.15s |

```text
$ docker compose exec -T web python -m pytest -v apps/usuarios/tests/test_auditoria.py apps/clientes/tests/test_clientes.py apps/comisiones/tests/test_comisiones.py apps/tasa_cambios/tests.py apps/conversiones/tests/test_conciliacion.py apps/conversiones/tests/test_conversiones.py
============================= test session starts ==============================
platform linux -- Python 3.12.16, pytest-9.2.0, pluggy-1.7.0
django: version: 6.1.3, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 110 items

apps/usuarios/tests/test_auditoria.py .....                              [  4%]
apps/clientes/tests/test_clientes.py ...............                     [ 18%]
apps/comisiones/tests/test_comisiones.py ......                          [ 23%]
apps/tasa_cambios/tests.py .........                                     [ 31%]
apps/conversiones/tests/test_conciliacion.py ................            [ 46%]
apps/conversiones/tests/test_conversiones.py ........................... [ 70%]
............................                                             [ 96%]
apps/conversiones/tests/test_conciliacion.py .                           [ 97%]
apps/conversiones/tests/test_conversiones.py ...                         [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango2028Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 2028.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 110 passed, 1 warning in 9.15s ========================
```

### Casos cubiertos

- **Acceso y consulta:** el rol administrador puede abrir la pantalla; un
  analista no puede acceder. Se verifican filtros por usuario, acción y fecha,
  así como el rechazo de solicitudes `POST`.
- **Solo lectura:** en Django Admin el registro no permite alta, edición ni
  borrado, y un usuario de tipo `staff` sin rol administrador no puede
  consultarlo.
- **Tasas, comisiones y clientes:** se comprueba el registro de altas de
  clientes y comisiones, la creación de tasas y la activación/desactivación de
  tasas. Un intento fallido de activación no genera un evento.
- **Anulaciones y conciliaciones:** las pruebas de las vistas verifican que las
  anulaciones de compra y venta y la conciliación exitosa generen sus acciones
  de auditoría asociadas al administrador.

### Verificaciones complementarias

| Comando | Resultado |
|---|---|
| `docker compose exec -T web python manage.py check` | No se identificaron problemas de configuración. |
| `docker compose exec -T web python manage.py makemigrations --check --dry-run` | No se detectaron cambios de modelo sin migración. |
| `docker compose exec -T web python manage.py showmigrations usuarios` | `0003_registroauditoria` aparece aplicada. |
| `docker compose exec -T web python manage.py migrate usuarios` | Se aplicó `usuarios.0003_registroauditoria` en la base activa. |
| `git diff --check` | Sin errores de espacios o formato del diff. |

Al abrir `/administracion/auditoria/` antes de aplicar la migración, la aplicación
respondía con `ProgrammingError` porque faltaba la tabla
`usuarios_registroauditoria`. Después de aplicar la migración se recargó la
misma página y se verificó que el título, los filtros y el mensaje de estado
vacío se mostraran correctamente. No había registros porque todavía no se
habían realizado operaciones auditables desde la activación; el registro no se
completa con operaciones históricas. El warning de pytest corresponde a la
deprecación futura de `EMAIL_BACKEND` y no produjo fallos.

---
---

## Leyda Fleitas — RF035, Configuración de Pagos (GEG9-77)

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 21:10:29 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/pagos/tests/test_metodos_pago.py` |
| **Comando** | `docker compose exec web pytest apps/pagos/tests/test_metodos_pago.py -v` |
| **Resultado** | **16 passed** en 4.45s |

```text
$ date
Thu Nov 19 21:10:29 -03 2026

$ docker compose exec web pytest apps/pagos/tests/test_metodos_pago.py -v
apps/pagos/tests/test_metodos_pago.py ................                   [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 16 passed, 1 warning in 4.45s =========================
```

- **La migración de datos** crea exactamente los dos métodos que ya
  funcionaban (tarjeta y transferencia), ambos habilitados. No se agregó
  billetera: no tiene código detrás y sería un botón que no hace nada.
- **Habilitar y deshabilitar** funciona en los dos sentidos, queda registro
  de **quién y cuándo**, el historial guarda **todos** los cambios —no solo
  el último— y no se registra un cambio que no ocurrió.
- **Un método deshabilitado** desaparece de la pantalla de pago y no se puede
  usar ni forzando el POST, ni por pasarela ni por transferencia.
- **Sin ningún método habilitado** la pantalla responde 200 con un mensaje
  claro; no hay error 500.
- **Lo que ya estaba en curso no se traba** (punto 5 del ERS, y el más fácil
  de incumplir sin darse cuenta): un pago por pasarela ya iniciado se
  confirma igual; una compra que espera transferencia se cancela igual; y la
  conciliación manual de RF025 sigue funcionando. El cliente ya transfirió el
  dinero: dejarlo trabado sería quedarse con su plata.
- **Acceso:** un usuario que no es administrador recibe 403 tanto por GET
  como por POST, y cambiar el estado exige POST con CSRF.

También se corrió la suite completa: **400 passed** (eran 384), sin
regresiones. Las decisiones están en `docs/chia-sprint6.md`, sección 11 — en
particular por qué la comprobación va solo al iniciar el pago (11.3).

---

## Leyda Fleitas — GEG9-82, Formato de Números y Montos

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 19 de noviembre de 2026, 21:38:52 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/comun/tests/test_formato.py` |
| **Comando** | `docker compose exec web pytest apps/comun/ -v` |
| **Resultado** | **42 passed** en 2.44s |

```text
$ date
Thu Nov 19 21:38:52 -03 2026

$ docker compose exec web pytest apps/comun/ -v
apps/comun/tests/test_formato.py ..........................................  [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 42 passed, 1 warning in 2.44s =========================
```

### El antes y el después

| Dónde | Antes | Después |
|---|---|---|
| Historial de transacciones | `712000.0` | **`712.000`** |
| Tasa aplicada | `7120.00` | **`7.120,00`** |
| Factura en guaraníes | `72980000` | **`72.980.000`** |
| Importe en dólares | `102.5` | **`102,50`** |
| Columnas de montos | a la izquierda | **a la derecha**, con cifras tabulares |
| Excel | todo texto, no se sumaba | **números alineados a la derecha** |

### Lo que cubren las pruebas

- **El formato:** enteros, decimales, **cero, negativos y números grandes**
  (hasta `999.999.999.999,99`), y el redondeo hacia arriba en el medio exacto.
- **Que no use float:** `Decimal("1.005")` redondea a `1,01`. En float daría
  `1,00`, porque 1.005 en binario es en realidad 1.00499999999999989…
- **Cada moneda con sus decimales:** PYG y JPY sin decimales, USD y EUR con
  dos. Sale del campo `decimales` de cada moneda, no de una lista en el
  código.
- **Las tasas conservan su precisión:** `0,000125` no se redondea a `0,00`.
- **Los formularios aceptan las dos formas** de escribir (`10.000` y `10000`,
  `1.234,56` y `1234.56`) y **el valor guardado no cambia**: sigue siendo el
  mismo `Decimal`. Se verifica además que siga validando el mínimo.
- **La alineación llega a las pantallas:** la clase está definida una sola vez
  y los encabezados numéricos del historial la llevan.
- **Las descargas:** el Excel lleva los importes como `ss:Type="Number"` con
  alineación derecha —antes iban como texto y ni se podían sumar— y el PDF
  rellena las columnas con espacios para alinearlas.
- **El gráfico de tasas** usa `Intl.NumberFormat("es-PY")`, el mismo formato
  sin reimplementarlo.

También se corrió la suite completa: **442 passed** (eran 400), sin
regresiones. Dos pruebas existentes de tasas se adaptaron porque verificaban
el atributo `step` del widget anterior.

Las decisiones están en `docs/chia-sprint6.md`, sección 12 — en particular
por qué se descartó `USE_THOUSAND_SEPARATOR` (12.1) y el riesgo de leer una
tasa de `7.120` como siete mil ciento veinte (12.3).

---

## Fabrizio Cardozo — RF031, Monitoreo de Ganancias en Tiempo Real (GEG9-64)

| Campo | Valor |
|---|---|
| **Fecha y hora** | Pendiente de ejecución en el entorno Docker |
| **Ambiente** | Docker Compose, servicio `web` |
| **Artefactos probados** | `apps/ganancias/tests/test_ganancias.py`, `apps/usuarios/tests/test_menu.py` |
| **Comando** | `docker compose exec -T web python -m pytest -v apps/ganancias/tests/test_ganancias.py apps/usuarios/tests/test_menu.py` |
| **Resultado** | Pendiente de ejecución |

### Casos cubiertos

- La ganancia suma la comisión y la diferencia entre la tasa de venta y la
  tasa de compra.
- Las operaciones canceladas no se incluyen en el resumen; el filtro utiliza
  únicamente operaciones confirmadas.
- El dashboard filtra por fecha de confirmación.
- Un usuario sin rol no puede acceder al dashboard.
- El rol `analista_cambiario` puede consultar el dashboard.
- La opción «Ganancias» aparece en el menú para administrador y analista
  cambiario.

La ejecución debe completarse en Docker antes de registrar una cantidad de
pruebas aprobadas. RF031 no requiere migraciones porque el cálculo utiliza los datos ya almacenados en `CompraDivisa` y `VentaDivisa`.

---

## Fabrizio Cardozo — RF030, Reporte de Transacciones para la Administración (GEG9-66)

| Campo | Valor |
|---|---|
| **Fecha y hora** | viernes 20 de noviembre de 2026, 02:14:13 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/conversiones/tests/test_reporte_transacciones.py` |
| **Comando** | `.venv/bin/pytest apps/conversiones/tests/test_reporte_transacciones.py -q` |
| **Resultado** | **6 passed** |

```text
$ .venv/bin/pytest apps/conversiones/tests/test_reporte_transacciones.py -q
......                                                                   [100%]
6 passed, 2 warnings
```

Casos cubiertos:

- El reporte lista compras y ventas, incluyendo estados pendientes y pagados.
- Los filtros combinan cliente, moneda, tipo, estado y rango inclusivo de
  fechas.
- La moneda se encuentra tanto en el origen como en el destino de la
  conversión.
- `administrador` y `analista_cambiario` pueden consultar; cliente y cajero
  reciben 403.
- El endpoint del reporte es independiente del historial restringido al
  cliente.

También se ejecutó la suite de conversiones: **95 passed**, y
`.venv/bin/python manage.py check` terminó sin errores. Las dos advertencias
corresponden a la deprecación de `EMAIL_BACKEND` de Django y a permisos
preexistentes de escritura de `.pytest_cache`.

---

## Daniela González — Corrección de comprobantes administrativos

| Campo | Valor |
|---|---|
| **Fecha y hora** | viernes 20 de noviembre de 2026, 03:50:48 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/conversiones/tests/test_conversiones.py` |
| **Comando** | `docker compose exec web pytest apps/conversiones/tests/test_conversiones.py -v` |
| **Resultado** | **66 passed**, 1 warning en 12.63s |

```text
$ date
Fri Nov 20 03:50:48 -03 2026

$ docker compose exec web pytest apps/conversiones/tests/test_conversiones.py -v
==================================== test session starts ====================================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.2, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 66 items                                                                          

apps/conversiones/tests/test_conversiones.py ........................................ [ 60%]
..........................                                                            [100%]

===================================== warnings summary ======================================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango2028Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 2028.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
============================== 66 passed, 1 warning in 12.63s ===============================
```

- El administrador ve «Volver a Compras y anulaciones» en un comprobante de
  compra y no ve acciones para repetirla.
- El administrador ve «Volver a Ventas y anulaciones» en un comprobante de
  venta y no ve acciones para repetirla.
- El cliente conserva el flujo de repetición y el cajero conserva su retorno 
  a ventas pendientes.

## Fabrizio Cardozo — RF037, Gestión de Horarios Operativos (GEG9-79)

| Campo | Valor |
|---|---|
| **Fecha y hora** | viernes 20 de noviembre de 2026, 04:42:25 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/horarios/tests/test_horarios.py` |
| **Comando** | `.venv/bin/pytest apps/horarios/tests/test_horarios.py -q` |
| **Resultado** | **6 passed** |

```text
$ .venv/bin/pytest apps/horarios/tests/test_horarios.py -q
......                                                                   [100%]
6 passed, 2 warnings
```

Casos cubiertos:

- Configuración de rangos por día, incluyendo apertura, cierre exacto y días
  sin rango.
- Rechazo de inicio de compra y venta fuera del horario, incluida la ruta de
  terminal, y rechazo de confirmación de venta fuera de horario.
- Acceso exclusivo del administrador a la configuración y validación de que
  la hora de inicio sea anterior a la hora de fin.
- La simulación continúa disponible fuera del horario operativo.

También se verificó `manage.py check`, `makemigrations --check` y que las
pruebas de conversiones y terminal pasaran sin regresiones. La suite completa se
intentó ejecutar; quedó un fallo preexistente en
`apps/notificaciones/tests/test_notificaciones.py::test_editar_sin_cambiar_los_valores_no_notifica`,
relacionado con una notificación al editar una tasa sin cambiar sus valores.

---

## Daniela González — Revisión del flujo crítico de compra/venta y terminal (GEG9-70)

| Campo | Valor |
|---|---|
| **Fecha y hora** | viernes 20 de noviembre de 2026, 05:00:53 (-03, hora de Paraguay) |
| **Artefactos probados** | `apps/conversiones/tests/test_conversiones.py`, `apps/terminal/tests/test_terminal.py`, `apps/cajas/tests/test_cajas.py`, `apps/pagos/tests/`, `apps/facturacion/tests/` |
| **Comando** | `docker compose exec web pytest apps/conversiones/tests/test_conversiones.py apps/terminal/tests/test_terminal.py apps/cajas/tests/test_cajas.py apps/pagos/tests apps/facturacion/tests -v` |
| **Resultado** | **199 passed**, 1 warning en 101.57s |

```text
$ docker compose exec web pytest apps/conversiones/tests/test_conversiones.py apps/terminal/tests/test_terminal.py apps/cajas/tests/test_cajas.py apps/pagos/tests apps/facturacion/tests -v
collected 199 items

================== 199 passed, 1 warning in 101.57s (0:01:41) ==================

$ docker compose exec web python manage.py check
System check identified no issues (0 silenced).
```

La ejecución cubre los flujos automatizados de simulación, tasa y comisión, confirmación, cancelación por cambio de cotización o vencimiento, efectivo, movimientos de caja, terminal, pagos y facturación controlada. El detalle de los casos, sus límites y los recorridos manuales documentados se encuentra en [`qa-sprint6.md`](qa-sprint6.md).

Las pruebas no llaman a dLocal ni a Factura Segura reales: esos proveedores se simulan o controlan dentro de la suite. La verificación contra servicios externos requiere credenciales y datos autorizados del ambiente correspondiente.

---
## Leyda Fleitas — RF038, Panel de Control Central (GEG9-67)

| Campo | Valor |
|---|---|
| **Fecha y hora** | viernes 20 de noviembre de 2026, 09:33:26 (-03, hora de Paraguay) |
| **Artefactos probados** | `apps/tablero/services.py`, `apps/tablero/views.py`, `templates/tablero/panel.html`, `apps/usuarios/menu.py` |
| **Comando** | `docker compose exec web pytest apps/tablero -v` |
| **Resultado** | **40 passed**, 1 warning en 3.75s |

```text
$ docker compose exec web pytest apps/tablero -v
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
collected 40 items

apps/tablero/tests/test_tablero.py .......................................  [100%]

======================== 40 passed, 1 warning in 3.75s =========================

$ docker compose exec web python manage.py check
System check identified no issues (0 silenced).

$ docker compose exec web sphinx-build -b html docs/sphinx docs/sphinx/_build
build succeeded.
```

### Suite completa del proyecto

```text
$ docker compose exec web pytest
530 passed, 1 warning in 80.07s (0:01:20)
```

Antes de esta rama la suite tenía una falla en
`apps/notificaciones/tests/test_notificaciones.py::test_editar_sin_cambiar_los_valores_no_notifica`,
registrada como preexistente en la evidencia de GEG9-81. Se rastreó su origen
y se arregló: el commit `8b816fb` había agregado `vigente_desde` a la
condición `cambiaron_los_valores` de `apps/tasa_cambios/views.py`, que RF033
usa para decidir si notificar, y el efecto era que cambiar solo la fecha de
vigencia de una tasa le notificaba a todos los clientes asociados.

El arreglo **separa la condición en dos**: `cambiaron_las_tasas` para la
notificación y `hubo_cambios` para la auditoría. **La auditoría no cambia** —
sigue registrando el cambio de fecha de vigencia. Se verificó con las 36
pruebas de `apps/usuarios/tests/test_auditoria.py`, `apps/tasa_cambios` y
`apps/notificaciones`, todas aprobadas.

Se agregó `test_cambiar_solo_la_vigencia_se_audita_pero_no_notifica`, que fija
las dos conductas en una sola prueba: cero notificaciones **y** un registro de
auditoría. En archivos separados, arreglar una rompiendo la otra seguiría
dando verde.

### Casos cubiertos

**Acceso exclusivo (criterio 1)**

| Caso | Esperado | Resultado |
|---|---|---|
| Rol `analista_cambiario` entra por URL directa | 403 | ✅ |
| Rol `usuario_cliente` entra por URL directa | 403 | ✅ |
| Rol `cajero` entra por URL directa | 403 | ✅ |
| Rol `terminal` entra por URL directa | 403 | ✅ |
| Usuario autenticado sin ningún rol | 403 | ✅ |
| Rol `administrador` | 200 | ✅ |
| Sin sesión | redirige a iniciar sesión | ✅ |
| Opción «Tablero» en el menú | solo el administrador la ve | ✅ |

**Métricas (criterio 2)**

| Caso | Esperado | Resultado |
|---|---|---|
| Conteos por estado, compras y ventas separadas | coinciden con los datos de prueba | ✅ |
| Fila de total | suma compras más ventas en cada estado | ✅ |
| Clientes activos e inactivos | 1 y 1 | ✅ |
| Clientes con distintos períodos | el mismo número: es el estado de hoy | ✅ |
| Saldos de caja | agrupados por moneda, con los decimales de cada una | ✅ |
| Diferencias de arqueo | cantidad y monto por moneda | ✅ |
| Sucursal | se informa la única que el modelo permite, sin contador | ✅ |
| Facturas | error de emisión y rechazo de SIFEN contados separados | ✅ |
| Ventas pendientes de entrega | no se filtran por período | ✅ |

**Dinero y ganancias (criterios 2 y 5)**

| Caso | Esperado | Resultado |
|---|---|---|
| Compra confirmada, una cancelada y una anulada | solo la confirmada suma | ✅ |
| La anulada lleva fecha de confirmación | tampoco suma: el filtro mira el estado | ✅ |
| Ganancias del tablero contra `resumen_ganancias()` | idénticas, no un recálculo | ✅ |
| Ganancias con período de 30 días | el mismo rango que el resto de la pantalla | ✅ |

**Filtro de período (criterio 3)**

| Caso | Esperado | Resultado |
|---|---|---|
| Tres operaciones a 0, 3 y 40 días | hoy 1, 7 días 2, 30 días 2, todo 3 | ✅ |
| «7 días» | incluye hoy y los seis anteriores, no el séptimo | ✅ |
| `?periodo=cualquier-cosa` | cae en el valor por omisión | ✅ |
| `?periodo=../../etc/passwd` | 200, sin error | ✅ |
| `?periodo=`, texto con comillas y punto y coma | valor por omisión, sin error | ✅ |

**Estado vacío (criterio 6)**

| Caso | Esperado | Resultado |
|---|---|---|
| Base sin datos | 200, todo en cero y listas vacías, sin error 500 | ✅ |

**Rendimiento (criterio 7, RNF001)**

| Caso | Esperado | Resultado |
|---|---|---|
| Servicio con 2 operaciones y después con 42 | **la misma cantidad de consultas** | ✅ |
| Cota del servicio | 12 consultas o menos | ✅ |
| Pantalla completa con 10 operaciones | 25 consultas o menos, incluyendo sesión, roles y menú | ✅ |

**Formato (criterio 8)**

| Caso | Esperado | Resultado |
|---|---|---|
| Cifras en la pantalla | `17.750,00`, `10.000,00`, `27.750,00` | ✅ |
| Formato de Django sin agrupar | `17750.00` y `17750,00` **no** aparecen | ✅ |

**Ganancia en guaraníes**

| Caso | Esperado | Resultado |
|---|---|---|
| Desglose con USD y PYG | cada moneda convertida y un total con unidad | ✅ |
| Cotización usada | la tasa de **compra** vigente, no la de venta | ✅ |
| Moneda sin tasa activa hacia el guaraní | queda fuera del total **y se la nombra** | ✅ |
| Moneda sin tasa activa | no se le inventa cotización | ✅ |
| Todo ya en guaraníes | no se muestra una columna de equivalencias repetida | ✅ |

**Gráfico de evolución**

| Caso | Esperado | Resultado |
|---|---|---|
| Suma de las barras | **idéntica al resumen de RF031** del período | ✅ |
| Período de 7 días | una barra por día, con los días sin ganancia en cero | ✅ |
| Período de 30 días | junta días, nunca más de 12 barras | ✅ |
| El doble de ganancia | dibuja el doble de alto | ✅ |
| Todas las barras | dentro del dibujo, sin alto ni posición negativos | ✅ |
| Sin operaciones | gráfico vacío, sin error | ✅ |
| Pantalla renderizada | muestra el total en guaraníes y el `<svg>` | ✅ |
| Coordenadas del SVG renderizado | con punto decimal, **nunca con coma** | ✅ |
| Barras renderizadas | al menos una con alto mayor que cero | ✅ |

### Lo que las pruebas no cubren

- **La apariencia.** Que la rejilla de tarjetas se acomode bien en el celular,
  que las columnas queden alineadas y que el gráfico se lea se verifica
  mirando la pantalla; las capturas acompañan esta evidencia.
- **La cotización elegida.** Las pruebas verifican que se use la tasa de
  compra vigente, no que ésa sea la cotización correcta para valuar: eso es
  una decisión de negocio, no algo que un test pueda demostrar.
- **El tiempo real de carga.** Las pruebas garantizan que el costo en
  consultas no crece con los datos, que es la causa de una pantalla lenta,
  pero no miden los 3 segundos de RNF001 contra un volumen de producción.

---
