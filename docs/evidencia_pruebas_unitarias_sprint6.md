# Constancia de ejecución de pruebas unitarias (PUN)

Registro de ejecuciones reales de las pruebas unitarias realizadas durante el
**Sprint 6** del proyecto Global Exchange.

Cada sección incluye la fecha y hora del sistema, los artefactos probados, el
comando ejecutado, la salida de pytest y los casos cubiertos.

## Ryuto Maehara - RF013, Control de sesiones y cierre por inactividad

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