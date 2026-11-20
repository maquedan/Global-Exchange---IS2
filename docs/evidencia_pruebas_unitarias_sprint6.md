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