# Constancia de ejecución de pruebas unitarias (PUN)

Registro compartido de ejecuciones reales de las pruebas unitarias realizadas
durante el **Sprint 3** del proyecto Global Exchange.

Cada integrante agrega una sección por historia implementada, incluyendo la
fecha y hora del sistema, el artefacto probado, el comando ejecutado, la salida
real de la terminal y un resumen de los casos cubiertos.

> La evidencia se conserva tal como fue obtenida en la terminal, sin editar ni recortar la salida de pytest.

---

## Daniela Gonzalez — RF052, Configuración de Comisiones por Categoría (GEG9-35)

| Campo | Valor |
|---|---|
| **Fecha y hora** | miércoles 16 de septiembre de 2026, 22:15:31 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/comisiones/tests/test_comisiones.py` |
| **Comando** | `docker compose exec web pytest apps/comisiones/ -v` |
| **Resultado** | **6 passed** en 5.95s |

```text
$ date
Wed Sep 16 22:15:31 -03 2026

$ docker compose exec web pytest apps/comisiones/ -v
============================================= test session starts ==============================================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 6 items                                                                                              

apps/comisiones/tests/test_comisiones.py ......                                                          [100%]

=============================================== warnings summary ===============================================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================================= 6 passed, 1 warning in 5.95s =========================================
```

Las pruebas verifican el acceso exclusivo del administrador, visualización del
listado, registro de una comisión, prevención de configuraciones duplicadas por
categoría, validación del porcentaje máximo y actualización del porcentaje sin
permitir modificar la categoría.

---

## Fabrizio Cardozo — RF018, Compra de Divisas (GEG9-31)

| Campo | Valor |
|---|---|
| **Fecha y hora** | domingo 27 de septiembre de 2026, 17:39:41 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/conversiones/tests/test_conversiones.py` |
| **Comando** | `docker compose exec web pytest apps/conversiones/tests/test_conversiones.py -v` |
| **Resultado** | **10 passed** en 0.42s |

```text
$ date
Sun Sep 27 17:39:41 -03 2026

$ docker compose exec web pytest apps/conversiones/tests/test_conversiones.py -v
================================================= test session starts =================================================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 10 items

apps/conversiones/tests/test_conversiones.py ..........                                                         [100%]

================================================== warnings summary ===================================================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
/usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
============================================ 10 passed, 1 warning in 0.42s ============================================
```

Las pruebas de RF018 cubren el cálculo y redondeo de comisión, confirmación y
persistencia de la compra con la tasa y comisión aplicadas, ausencia de
comisión, exclusión de tasas futuras y la restricción de que un usuario solo
puede operar para clientes asociados.

---

<!--
Próxima persona: copiá desde acá el bloque de arriba (## Nombre — Historia),
completá con tu propia ejecución, y pegá tu sección debajo de esta línea.
-->
