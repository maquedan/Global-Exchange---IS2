# Constancia de ejecución de pruebas unitarias (PUN)

Registro compartido de ejecuciones reales de la suite de pruebas, con fecha y
hora del sistema. Cada integrante agrega su propia sección con la evidencia de
las pruebas que escribió, tal como salió en su terminal — sin editar ni
recortar la salida.

**Cómo sumar tu parte:** copiá el formato de la sección de abajo, corré
`date` seguido de `docker compose exec web pytest apps/<tu_app>/ -v`, y pegá
la salida completa tal cual.

---

## Leyda Fleitas — RF020, Cuentas y Billeteras de clientes (GEG9-30)

| Campo | Valor |
|---|---|
| **Fecha y hora** | sábado 5 de septiembre de 2026, 23:27:39 (-03, hora de Paraguay) |
| **Comando** | `docker compose exec web pytest apps/cuentas/ -v` |
| **Resultado** | **10 passed** en 14.45s |

```
$ date
Sat Sep  5 23:27:39 -03 2026

$ docker compose exec web pytest apps/cuentas/ -v
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 10 items

apps/cuentas/tests/test_cuentas.py ..........                            [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 10 passed, 1 warning in 14.45s =========================
```

Esas 10 pruebas cubren: permisos por rol, aislamiento entre clientes (nadie ve
ni edita cuentas ajenas), alta con validación de duplicados, edición, baja
lógica, y la regla de negocio del modelo (no se registran cuentas para
clientes inactivos). Ver [`apps/cuentas/tests/test_cuentas.py`](../apps/cuentas/tests/test_cuentas.py).

---

## Daniela Gonzalez — RF014, Administración de Monedas (GEG9-26)

| Campo | Valor |
|---|---|
| **Fecha y hora** | 5 de septiembre de 2026, 23:41 (-03, hora de Paraguay) |
| **Comando** | `docker compose exec web pytest apps/monedas/ -v` |
| **Resultado** | **6 passed** en 13.39s |

```
$ docker compose exec web pytest apps/monedas/ -v
================================== test session starts ==================================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 6 items

apps/monedas/tests/test_monedas.py ......                                         [100%]

=================================== warnings summary ====================================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
============================= 6 passed, 1 warning in 13.39s =============================
```

Esas 6 pruebas cubren la gestión de monedas admitidas para operar (RF014):
alta, que no se repita el código de una moneda, y que la administración quede
restringida al rol correspondiente.

---

## Ryuto Maehara — RF015, Actualización de Tasas (GEG9-27)

| Campo | Valor |
|---|---|
| **Fecha y hora** | domingo 6 de septiembre de 2026, 15:23:24 (-03, hora de Paraguay) |
| **Comando** | `docker compose exec web pytest apps/tasa_cambios/ -v` |
| **Resultado** | **4 passed** en 0.82s |

```
$ date
Sun Sep  6 15:23:24 -03 2026

$ docker compose exec web pytest apps/tasa_cambios/ -v
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 4 items

apps/tasa_cambios/tests.py ....                                          [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 4 passed, 1 warning in 0.82s =========================
```

Esas 4 pruebas cubren: que solo el rol `analista_cambiario` pueda crear tasas
de cambio, que `usuario_cliente` no pueda gestionarlas (403), que el
formulario rechace poner la misma moneda de origen y destino, y que no se
puedan tener dos tasas activas al mismo tiempo para el mismo par de monedas.

> **Nota técnica:** este archivo se llama `tests.py` (no `tests/test_*.py`
> como el resto del proyecto). El `pytest.ini` original solo buscaba
> `test_*.py`, así que estas 4 pruebas **no se ejecutaban** con
> `docker compose exec web pytest` hasta que se amplió el patrón a
> `python_files = test_*.py tests.py`. Ya está corregido.

---

<!--
Próxima persona: copiá desde acá el bloque de arriba (## Nombre — Historia),
completá con tu propia ejecución, y pegá tu sección debajo de esta línea.
-->
