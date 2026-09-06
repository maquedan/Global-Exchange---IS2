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

## Daniela — RF014, Administración de Monedas (GEG9-26)

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

## [TU NOMBRE] — [Tu historia, ej: RF015, Actualización de Tasas (GEG9-27)]

| Campo | Valor |
|---|---|
| **Fecha y hora** | [pegar la salida de `date`] |
| **Comando** | `docker compose exec web pytest apps/[TU_APP]/ -v` |
| **Resultado** | **[N] passed** en [X]s |

```
[pegar acá TODA la salida de la terminal: el "date" y el "pytest -v" completos]
```

[uno o dos renglones explicando qué prueban tus tests]

---

<!--
Próxima persona: copiá desde acá el bloque de arriba (## Nombre — Historia),
completá con tu propia ejecución, y pegá tu sección debajo de esta línea.
-->
