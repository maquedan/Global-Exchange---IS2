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

## Leyda Fleitas — RF026, Generación Automática de Facturas (GEG9-50)

| Campo | Valor |
|---|---|
| **Fecha y hora** | martes 27 de octubre de 2026, 11:42:35 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/facturacion/tests/test_facturacion.py` |
| **Comando** | `docker compose exec web pytest apps/facturacion -v` |
| **Resultado** | **29 passed** en 4.18s |

```text
$ date
Tue Oct 27 11:42:35 -03 2026

$ docker compose exec web pytest apps/facturacion -v
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 29 items

apps/facturacion/tests/test_facturacion.py ............................. [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 29 passed, 1 warning in 4.18s =========================
```

Ninguna prueba toca la red: el cliente de la API de Factura Segura se
reemplaza por dobles que cumplen la misma interfaz (`ClienteFacturacion`),
igual que se hizo con la pasarela de pago en RF022.

Cubre los siete casos pedidos por la historia, más los de borde que
aparecieron al implementarla:

- **Emisión automática:** al confirmar una compra y al confirmar una venta se
  crea la `Factura` y queda `GENERADA` con un CDC de 44 dígitos.
- **RNF011 (la facturación nunca bloquea la operación):** con un rechazo de
  la API la operación sigue `CONFIRMADA` y la factura queda en `ERROR`; con
  una excepción totalmente inesperada también sigue `CONFIRMADA` y la factura
  queda `PENDIENTE`, es decir reintentable y no perdida.
- **Timeout:** la factura queda `A_VERIFICAR` y **no se reenvía sola** — se
  verifica que en el segundo intento no se llama a la API, aunque el cliente
  ya responda bien.
- **Comando de reintento:** reintenta las `ERROR` y deja las `A_VERIFICAR`
  como están.
- **Una factura por operación:** emitir dos veces devuelve la misma y no
  vuelve a llamar a la API; la base rechaza una segunda factura para la misma
  operación y también una factura sin operación (`CheckConstraint`).
- **Numeración:** no se repite y es consecutiva; arranca en el primer número
  del rango autorizado por la cátedra (`0000489`); al agotarse el rango la
  factura queda en `ERROR` sin llamar a la API; y el reintento **reusa el
  mismo número**, para no dejar huecos en la secuencia del SIFEN.
- **Armado del DE:** conversión del monto a guaraníes (y una operación ya en
  guaraníes que no se convierte); un solo ítem por el total, con IVA 10% y
  `cUniMed` 77; receptor persona física como consumidor final con cédula y
  sin DV; receptor persona jurídica como contribuyente con RUC y DV
  separados; las dos actividades económicas del emisor, cada una con su
  descripción; y las dos cifras (guaraníes y moneda original) en `dInfAdic`.
- **Errores claros antes de llamar a la API:** cliente sin correo (que
  Factura Segura exige), RUC jurídico sin dígito verificador, actividad
  económica mal escrita, falta del token y datos del emisor todavía en los
  valores de prueba.
- **Secretos:** el token no aparece en los logs ni en el JSON que se guarda
  en la base, y tampoco la cabecera `Authentication-Token`.

También se corrió la suite completa del proyecto: **228 passed**, sin
regresiones en RF018, RF019, RF022, RF023 ni RF051. Las decisiones que el
ticket pedía proponer y no asumir (qué monto se factura, el tratamiento del
IVA, la moneda, el DV del receptor y los datos del emisor) están
documentadas en `docs/chia-sprint5.md`, sección 2.

---

## Leyda Fleitas — RF010, Restricción de Operaciones (GEG9-20)

| Campo | Valor |
|---|---|
| **Fecha y hora** | miércoles 28 de octubre de 2026, 13:38:19 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/usuarios/tests/test_restriccion_operaciones.py` |
| **Comando** | `docker compose exec web pytest apps/usuarios/tests/test_restriccion_operaciones.py -v` |
| **Resultado** | **37 passed** en 2.62s |

```text
$ date
Wed Oct 28 13:38:19 -03 2026

$ docker compose exec web pytest apps/usuarios/tests/test_restriccion_operaciones.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0
django: version: 6.1.1, settings: config.settings.dev (from env)
rootdir: /app
configfile: pytest.ini
plugins: django-4.14.0
collected 37 items

apps/usuarios/tests/test_restriccion_operaciones.py .................... [ 54%]
.................                                                        [100%]

=============================== warnings summary ===============================
../usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394
  /usr/local/lib/python3.12/site-packages/pytest_django/plugin.py:394: RemovedInDjango70Warning: The EMAIL_BACKEND setting is deprecated. Migrate to MAILERS before Django 7.0.
    dj_settings.DATABASES  # noqa: B018

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 37 passed, 1 warning in 2.62s =========================
```

Cubre los ocho casos pedidos por la historia. El criterio de diseño es que
**ocultar botones no es seguridad**: cada vista de operación se prueba con GET
y con POST, simulando a alguien que escribe la URL a mano o manda el
formulario por fuera de la interfaz.

- **Consulta sigue funcionando:** las 6 URLs de consulta (cotizaciones, datos
  JSON, panel, pantalla de restricción, simulación y notificaciones)
  responden `200` para un usuario sin ningún cliente asociado. La simulación
  (RF017) se prueba además con POST, verificando que no registra ninguna
  operación: es sólo cálculo.
- **Operación bloqueada:** prueba **parametrizada sobre las 17 URLs de
  operación**, con GET y con POST. Todas devuelven `302` a
  `/sin-cliente/`. Esa lista hace de red: una vista de operación nueva que se
  olvide de proteger se nota al agregarla.
- **No queda rastro:** después de intentar una compra (mandando además el id
  de un cliente ajeno en el POST) y el registro de una cuenta, se verifica
  que no existe **ningún** `CompraDivisa`, `VentaDivisa`, `Pago` ni
  `CuentaPago`.
- **Con cliente opera normal:** la compra se crea y queda a nombre del
  cliente asociado.
- **Cliente desactivado (RF003):** no puede iniciar una operación **ni
  confirmar una que ya estaba pendiente**. Este segundo caso era un hueco
  real antes de esta historia.
- **Defensa en profundidad:** `iniciar_compra`, `iniciar_venta` e
  `iniciar_pago` fallan con `ClienteNoHabilitado` llamados directamente, sin
  pasar por ninguna vista. Antes creaban la operación o el pago de otro
  cliente con sólo pasarles el id.
- **Menú:** sin cliente no aparecen *Comprar divisas*, *Vender divisas*, *Mis
  medios de pago* ni *Historial*; con cliente sí. Las de consulta siempre.
- **Administrador y analista no son bloqueados** por esta regla: sus
  pantallas se rigen por su propio control de rol (RF011).

También se corrió la suite completa del proyecto: **265 passed** (eran 228),
sin regresiones. Se adaptaron 6 pruebas existentes de RF008, RF018 y RF022
porque tres servicios ahora exigen `usuario=`; una de ellas quedó más fuerte
que antes (detalle en `docs/chia-sprint5.md`, sección 3.7).

La tabla completa de las 28 URLs relevadas, con lo que respondía cada una
antes y después del cambio, está en `docs/chia-sprint5.md` sección 3.1.

---

## Fabrizio Cardozo — RF053, Visualización de Facturas (GEG9-54)

| Campo | Valor |
|---|---|
| **Fecha y hora** | jueves 29 de octubre de 2026, 01:46:39 (-03, hora de Paraguay) |
| **Artefacto probado** | `apps/facturacion/tests/test_visualizacion.py` |
| **Comando** | `.venv/bin/python -m pytest apps/facturacion/tests/test_visualizacion.py -q` |
| **Resultado** | **6 passed** |

```text
$ .venv/bin/python -m pytest apps/facturacion/tests/test_visualizacion.py -q
......                                      [100%]
6 passed
```

También se ejecutó:

```text
$ .venv/bin/python manage.py check
System check identified no issues (0 silenced).
```

Las seis pruebas cubren el listado y detalle de facturas, separación de datos
entre clientes, acceso completo del administrador, filtros por número y estado
fiscal, visibilidad del menú por rol, RUC de persona jurídica y uso del
documento como RUC para persona física. Las advertencias mostradas por pytest
corresponden a compatibilidad futura de `EMAIL_BACKEND` y a permisos de
`.pytest_cache`; no representan fallos.

<!--
Próxima persona: copiá desde acá el bloque de arriba (## Nombre — Historia),
completá con tu propia ejecución, y pegá tu sección debajo de esta línea.
-->
