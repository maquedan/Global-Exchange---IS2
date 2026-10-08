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

<!--
Próxima persona: copiá desde acá el bloque de arriba (## Nombre — Historia),
completá con tu propia ejecución, y pegá tu sección debajo de esta línea.
-->
