# Constancia de ejecución de pruebas unitarias (PUN)

Registro compartido de ejecuciones reales de las pruebas unitarias realizadas
durante el **Sprint 4** del proyecto Global Exchange.

Cada integrante agrega una sección por historia implementada, incluyendo la
fecha y hora del sistema, el artefacto probado, el comando ejecutado, la salida
real de la terminal y un resumen de los casos cubiertos.

> La evidencia se conserva tal como fue obtenida en la terminal, sin editar ni recortar la salida de pytest.

---

## Leyda Fleitas — RF023, Trazabilidad de Estados (GEG9-37)

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 8 de octubre de 2026, 14:32:09 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/conversiones/tests/test_conversiones.py` |
| **Comando** | `docker compose exec web pytest apps/conversiones/ -v` |
| **Resultado** | **40 passed** en 3.53s |

```text
$ date
Thu Oct  8 14:32:09 -03 2026

$ docker compose exec web pytest apps/conversiones/ -v
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 40 items

apps/conversiones/tests/test_conversiones.py ........................... [ 67%]
.............                                                            [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 40 passed, 1 warning in 3.53s =========================
```

Suma 10 pruebas nuevas de RF023 a las 30 que ya existían de RF018/RF019/RF030/
RF051: que iniciar una compra o venta registre la transición "nada → pendiente",
que confirmar el pago registre "pendiente → pagada" con el usuario que confirmó,
que cada uno de los tres motivos de cancelación (cliente, cambio de cotización,
vencimiento del plazo) quede con su propio texto, que el `CheckConstraint`
rechace un `CambioEstado` sin ninguna operación o con las dos a la vez, que la
línea de tiempo aparezca en el comprobante, y que un usuario que no es dueño de
la operación no pueda verla (404). También se corrió la suite completa del
proyecto: **124 passed**, sin regresiones en Compra, Venta ni Historial de
divisas.

---

## Leyda Fleitas — RF033, Alertas de Tasas (GEG9-38)

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 8 de octubre de 2026, 15:13:00 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/notificaciones/tests/test_notificaciones.py` |
| **Comando** | `docker compose exec web pytest apps/notificaciones/ -v` |
| **Resultado** | **9 passed** en 1.38s |

```text
$ date
Thu Oct  8 15:13:00 -03 2026

$ docker compose exec web pytest apps/notificaciones/ -v
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 9 items

apps/notificaciones/tests/test_notificaciones.py .........               [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 9 passed, 1 warning in 1.38s =========================
```

Cubre: que cambiar `tasa_compra` notifique solo a clientes asociados y
activos (nada para administradores, analistas, clientes sin asociación o con
cliente inactivo); que editar sin cambiar los valores de tasa no notifique;
que activar/desactivar tampoco notifiquen; que un usuario sin email reciba
igual la notificación interna sin romper nada; que un error simulado del
backend de correo (mockeado con `unittest.mock.patch`) no impida guardar la
tasa ni crear la notificación; que un usuario solo vea y marque como leídas
sus propias notificaciones; que el contador del menú cuente solo las no
leídas; y que cargar el fixture `tasas_demo` con `loaddata` no genere ninguna
notificación. También se corrió la suite completa del proyecto: **133
passed**, sin regresiones.

---

## Ryuto Maehara — Cajas

| Campo | Valor |
|---|---|
| **Fecha y hora** | viernes 9 de octubre de 2026, 23:17:05 (-03, hora de Paraguay) |
| **Artefactos probados** | `apps/cajas/tests/test_cajas.py`, `apps/usuarios/tests/test_menu.py` y suite completa (`apps/`) |
| **Comandos** | `docker compose exec web pytest apps/cajas/tests/test_cajas.py apps/usuarios/tests/test_menu.py -v`; `docker compose exec web pytest -v` |
| **Resultado** | **22 passed** en las pruebas enfocadas y **145 passed** en la suite completa; ambas ejecuciones reportaron 1 warning |

```text
$ date
Fri Oct  9 23:17:05 -03 2026

$ docker compose exec web pytest apps/cajas/tests/test_cajas.py apps/usuarios/tests/test_menu.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.15, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.2, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 22 items

apps/cajas/tests/test_cajas.py ...........                               [ 50%]
apps/usuarios/tests/test_menu.py ...........                             [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango2028Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 2028.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 22 passed, 1 warning in 5.76s =========================
```

La suite enfocada cubre la gestión de sucursales y cajas, permisos por rol,
registro y validación de ingresos/asignaciones/devoluciones, saldos e historial
de movimientos, y visibilidad del menú según el rol. A continuación se conserva
la salida completa de la suite de regresión:

```text
$ date
Fri Oct  9 23:16:31 -03 2026

$ docker compose exec web pytest -v
============================= test session starts ==============================
platform linux -- Python 3.12.15, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.2, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
testpaths: apps
plugins: django-4.14.0
collected 145 items

apps/cajas/tests/test_cajas.py ...........                               [  7%]
apps/clientes/tests/test_clientes.py ...............                     [ 17%]
apps/comisiones/tests/test_comisiones.py ......                          [ 22%]
apps/conversiones/tests/test_conversiones.py ........................... [ 40%]
..........                                                               [ 47%]
apps/cuentas/tests/test_cuentas.py ..........                            [ 54%]
apps/monedas/tests/test_monedas.py .......                               [ 59%]
apps/notificaciones/tests/test_notificaciones.py .........               [ 65%]
apps/tasa_cambios/tests.py ........                                      [ 71%]
apps/tasas/tests/test_tasas.py ...........                               [ 78%]
apps/usuarios/tests/test_auth.py .....                                   [ 82%]
apps/usuarios/tests/test_menu.py ..........                              [ 88%]
apps/usuarios/tests/test_roles_permisos.py ....                          [ 91%]
apps/conversiones/tests/test_conversiones.py ...                         [ 93%]
apps/usuarios/tests/test_auth.py ........                                [ 99%]
apps/usuarios/tests/test_menu.py .                                       [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango2028Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 2028.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 145 passed, 1 warning in 20.81s ========================
```

La suite completa pasó sin fallos. En ambas ejecuciones se informó el mismo
aviso deprecado de `EMAIL_BACKEND` en pytest-django. Las pruebas cubren las
operaciones de backend y los permisos relacionados con Cajas; no verifican
directamente el comportamiento JavaScript que muestra u oculta el campo de
cajero en el formulario de GEG9-39.

<!--
Próxima persona: copiá desde acá el bloque de arriba (## Nombre — Historia),
completá con tu propia ejecución, y pegá tu sección debajo de esta línea.
-->
