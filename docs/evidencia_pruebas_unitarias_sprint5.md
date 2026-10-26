# Constancia de ejecución de pruebas unitarias (PUN)

Registro compartido de ejecuciones reales de las pruebas unitarias
realizadas durante el **Sprint 5** del proyecto Global Exchange.

Cada integrante agrega una sección por historia implementada, incluyendo la
fecha y hora del sistema, el artefacto probado, el comando ejecutado, la
salida real de la terminal y un resumen de los casos cubiertos.

> La evidencia se conserva tal como fue obtenida en la terminal, sin editar ni recortar la salida de pytest.

---

## Leyda Fleitas — RF008, Selección de Cliente Activo (GEG9-18)

| Campo | Valor |
|---|---|
| **Fecha y hora** | lunes 26 de octubre de 2026, 14:24:30 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/usuarios/tests/test_cliente_activo.py` |
| **Comando** | `docker compose exec web pytest apps/usuarios/tests/test_cliente_activo.py -v` |
| **Resultado** | **10 passed** en 3.40s |

```text
$ date
Mon Oct 26 14:24:30 -03 2026

$ docker compose exec web pytest apps/usuarios/tests/test_cliente_activo.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 10 items

apps/usuarios/tests/test_cliente_activo.py ..........                    [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 10 passed, 1 warning in 3.40s =========================
```

Cubre los seis casos pedidos por la historia, más tres de borde: usuario con
un solo cliente (queda seleccionado solo, sin pantalla extra); usuario con
dos o más (lo redirige a elegir y no puede operar sin elegir); intento de
elegir un cliente que no es suyo (rechazado, no se guarda nada en la
sesión); elección válida (queda guardada en la sesión); cliente activo dado
de baja con RF003 (pasa automáticamente al que queda activo); cliente activo
desvinculado del usuario (se limpia la elección y se vuelve a pedir);
usuario sin clientes (no rompe, `cliente_activo` es `None` y no puede
operar, pero tampoco se lo bloquea del resto de la aplicación); la compra se
registra a nombre del cliente activo y no de otro; y las pantallas de
consulta (panel, cotizaciones) no piden elegir cliente.

También se corrió la suite completa del proyecto: **199 passed**, sin
regresiones en RF018, RF019, RF020, RF030 ni RF051. Tres pruebas existentes
se adaptaron al comportamiento nuevo —el formulario ya no tiene desplegable
de cliente— y una de ellas destapó un bug propio: al sacar `cliente` del
formulario de medios de pago, Django dejaba de validar la restricción de
cuenta duplicada y el error salía crudo contra la base (detalle en
`docs/chia-sprint5.md`, sección 1.5).

---

<!--
Próxima persona: copiá desde acá el bloque de arriba (## Nombre — Historia),
completá con tu propia ejecución, y pegá tu sección debajo de esta línea.
-->
