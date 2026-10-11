# CHIA — Conversaciones con Inteligencia Artificial

Registro del uso de IA como herramienta de apoyo durante el **Sprint 4** del
proyecto Global Exchange (Grupo 9, FP-UNA).

- **Modalidad de trabajo:** se utilizó como asistente de consulta y de
  programación. Las decisiones de diseño, cambios de código, comandos y
  verificaciones fueron realizados y validados por la integrante en el entorno
  real del proyecto.

---

## 1. Leyda Fleitas — RF023, Trazabilidad de Estados (GEG9-37)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

### 1.1. «¿Cómo registro un historial sin romper lo que ya hay (RF030, RF051, 114 pruebas)?»

**Lo que aprendimos.** Las compras y ventas ya tenían 6 funciones en
`services.py` que asignan `.estado` directamente (`iniciar_*`,
`expirar_*_si_corresponde`, `confirmar_pago_*`, `cancelar_*`), y RF030
(historial) ya depende de que `estado` siga valiendo lo mismo que antes
(`CONFIRMADA`). Tocar el campo en sí, o renombrarlo, iba a romper ambas cosas.

**Decisión.** Agregar el registro **al lado** del campo existente, no en
reemplazo: un modelo nuevo `CambioEstado` con una fila por cada transición, y
una única función central `registrar_cambio_estado()` que todas las funciones
de `services.py` llaman justo después de guardar el nuevo estado. El campo
`estado` de `CompraDivisa`/`VentaDivisa` no cambia de significado en ningún
momento.

### 1.2. «El ERS dice "pagada", el código dice CONFIRMADA. ¿Renombro la constante?»

**Lo que aprendimos.** Renombrar `CONFIRMADA` a `PAGADA` en el código iba a
tocar el historial (RF030), los templates de comprobante y las pruebas de
RF018/RF051 — mucho riesgo para un cambio que es puramente de vocabulario.

**Decisión.** Dejar la constante `CONFIRMADA` igual (valor en la base de
datos, comparaciones en el código) y cambiar únicamente la etiqueta visible
del `TextChoices`, de `"Confirmada"` a `"Pagada"`. Como `historial.html` y
ahora la línea de tiempo usan `get_estado_display()`, el cambio de vocabulario
llega solo, sin tocar un `if` en ningún lado.

### 1.3. «¿Cómo relaciono un `CambioEstado` con una compra O una venta, sin duplicar el modelo?»

**Lo que aprendimos.** `CompraDivisa` y `VentaDivisa` no comparten ninguna
clase base (es el patrón que ya traía el proyecto), así que no hay un tipo
común al que apuntar con una sola FK.

**Decisión.** Dos FK nullable (`compra`, `venta`) en el mismo modelo, con un
`CheckConstraint` que exige que se complete exactamente una. La función
`registrar_cambio_estado()` decide sola cuál de las dos llenar, mirando el
tipo de la operación que recibe (`isinstance(operacion, CompraDivisa)`).

### 1.4. «¿De dónde saco el "estado anterior" si ya cambié `.estado` en memoria antes de guardar?»

**Lo que aprendimos.** El patrón existente en `services.py` es: pisar
`compra.estado` con el valor nuevo y recién después `.save()`. Si
`registrar_cambio_estado()` leyera `compra.estado` en ese momento, ya sería
el valor nuevo — nunca podría saber cuál era el anterior.

**Decisión.** Capturar `estado_anterior = compra.estado` como variable local
**antes** de pisarlo, en cada uno de los 10 puntos donde esto pasa (2 en
`iniciar_*`, 2 en `expirar_*_si_corresponde`, 4 en `confirmar_pago_*` —dos
ramas cada una—, 2 en `cancelar_*`), y pasar ambos valores explícitos a
`registrar_cambio_estado()`. Para la primera transición de cada operación
(recién creada), se pasa `""` como estado anterior: significa "todavía no
existía".

### 1.5. «¿Cómo pruebo una migración de datos con pytest, si ya corrió antes de que arranquen las pruebas?»

**Lo que aprendimos.** Las pruebas corren sobre una base de datos de pruebas
que ya tiene todas las migraciones aplicadas al momento de empezar — no hay
forma de "ver" el estado intermedio de una migración con pytest.

**Decisión.** Verificar la migración de datos a mano, con
`manage.py migrate` y una consulta por shell contra la base de desarrollo
real (que sí tenía compras/ventas viejas cargadas de probar RF051), en vez de
con una prueba automática. Quedó registrado en la sección de verificaciones.

## 1.6. Verificaciones realizadas

- Migración `0005_alter_..._and_more` generada con `makemigrations` y
  completada a mano con una migración de datos (`RunPython`) que crea el
  historial inicial de las compras/ventas que ya existían.
- Verificado a mano contra la base de desarrollo real: 5 compras ya cargadas
  (de pruebas de RF051) quedaron cada una con exactamente 1 `CambioEstado`,
  con la fecha histórica correcta (`confirmado_en`/`cancelado_en`/`creado_en`
  según corresponda), no la fecha de hoy.
- Suite completa del proyecto ejecutada tras el cambio: **124 pruebas
  aprobadas** (eran 114 antes de esta historia), sin romper ninguna prueba
  existente de Compra, Venta ni Historial.
- `python manage.py check` sin errores.
- **Corrección sobre la marcha:** el ticket sugería registrar `CambioEstado`
  en el admin de Django como solo lectura (no era un criterio de aceptación,
  solo una sugerencia de implementación). El equipo tiene prohibido usar el
  admin de Django en este proyecto, así que no se registró — la trazabilidad
  se consulta desde la línea de tiempo en los comprobantes, que sí es un
  criterio de aceptación y ya está cubierta.
- Documentación técnica incorporada a Sphinx en `docs/sphinx/conversiones.rst`
  (el modelo `CambioEstado` y la función `registrar_cambio_estado` aparecen
  solos, por `automodule`).
- La evidencia completa de pytest está en
  `docs/evidencia_pruebas_unitarias_sprint4.md`.

---

## 2. Leyda Fleitas — RF033, Alertas de Tasas (GEG9-38)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

### 2.1. «¿Señal `post_save` o llamar al servicio desde la vista?»

**Lo que aprendimos.** Una señal `post_save` en `TasaCambio` dispararía al
cargar el fixture `tasas_demo.json` con `loaddata` — cada integrante que
levanta el entorno terminaría generando decenas de notificaciones y correos
de prueba sin haber hecho nada.

**Decisión.** Llamar a `notificar_cambio_de_tasa()` explícitamente desde las
vistas `crear` y `editar` de `tasa_cambios`, no desde una señal. Es menos
"mágico", se puede probar con un `client.post()` normal, y `loaddata` queda
inmune porque nunca pasa por esas vistas. El costo conocido (documentado):
un cambio hecho a mano contra la base de datos no notificaría a nadie — no
es un caso que ocurra en el flujo normal de la aplicación.

### 2.2. «¿Cómo evito notificar un cambio que después falla y no llega a guardarse?»

**Lo que aprendimos.** Si se crea la `Notificacion` (y se manda el correo)
inmediatamente después de `formulario.save()`, pero más adelante en la misma
vista algo falla y la transacción se revierte, igual quedaría un correo
mandado avisando un cambio que nunca se guardó.

**Decisión.** Envolver el cuerpo de `notificar_cambio_de_tasa()` en
`transaction.on_commit()`. Así se ejecuta recién cuando la transacción que lo
rodea termina de confirmarse — nunca antes.

### 2.3. «Con `on_commit`, ¿cómo pruebo que la notificación se creó, si pytest-django envuelve cada prueba en una transacción que se revierte?»

**Lo que aprendimos.** `@pytest.mark.django_db` normal envuelve toda la
prueba en una transacción para después deshacerla, y `transaction.on_commit`
nunca llega a "confirmarse" en ese contexto — los callbacks registrados
simplemente no se ejecutan, y la prueba fallaría buscando una notificación
que nunca se creó.

**Decisión.** Usar el fixture `django_capture_on_commit_callbacks` de
pytest-django, con `execute=True`, envolviendo la llamada a la vista. Permite
probar el comportamiento real de producción sin tener que usar transacciones
reales de verdad (`transaction=True`), que son más lentas.

### 2.4. «¿Cómo calculo "clientes asociados y activos" sin duplicar lógica?»

**Lo que aprendimos.** Un usuario puede estar asociado a varios clientes, y
el requisito es "con AL MENOS un cliente activo", no "con todos sus clientes
activos".

**Decisión.** Un solo filtro:
`User.objects.filter(is_active=True, groups__name="usuario_cliente",
asociaciones_clientes__cliente__activo=True).distinct()` — el `distinct()`
evita contar dos veces a quien tiene más de un cliente activo asociado.

## 2.5. Verificaciones realizadas

- Migración inicial de `apps.notificaciones` generada y aplicada.
- Suite completa del proyecto ejecutada tras el cambio: **133 pruebas
  aprobadas** (eran 124 antes de esta historia).
- Casos nuevos cubiertos: notifica solo a clientes asociados y activos (no a
  administradores, analistas ni clientes sin asociación ni con cliente
  inactivo); editar sin cambiar `tasa_compra`/`tasa_venta` no notifica;
  activar/desactivar no notifican; un usuario sin email recibe igual la
  notificación interna sin que falle nada; un error simulado del backend de
  correo no impide guardar la tasa ni crear la notificación; un usuario solo
  ve y marca como leídas sus propias notificaciones (404 si intenta la ajena);
  el contador del menú cuenta solo las no leídas; cargar `tasas_demo` con
  `loaddata` no genera ninguna notificación.
- `python manage.py check` sin errores.
- Documentación técnica incorporada a Sphinx en
  `docs/sphinx/notificaciones.rst`.
- **Corrección sobre la marcha:** igual que con RF023, el ticket pedía un
  admin de solo lectura para `Notificacion`. No se registró — el equipo tiene
  prohibido usar el admin de Django en este proyecto.

---

## 3. Ryuto Maehara - RF041 — Cajas, fondos y rol cajero

**Herramienta:** Copilot SDK en VS Code.

**Consulta.** Se revisó si RF041 estaba implementado y cómo administrar las
cajas de sucursales y el efectivo asignado a cajeros.

**Resumen.** La aplicación permite crear sucursales con su caja, registrar
ingresos y retiros, asignar fondos a cajeros y registrar devoluciones. Los
saldos por moneda y el historial de movimientos se consultan desde el detalle
de cada caja. El rol `cajero` se administra en Keycloak; el rol identifica al
usuario y no requiere una app separada. En esta implementación, los movimientos
los registra el administrador.

**Cambios realizados.** Se agregó `cajero` a la configuración inicial del
realm y a la configuración de roles de la aplicación, junto con el usuario de
prueba `cajero.demo`. También se ajustó el formulario de movimientos para
mostrar el campo cajero únicamente en asignaciones y devoluciones.

**Incidente de autenticación.** Tras reiniciar Docker, Keycloak rechazaba el
secreto OIDC del cliente web. Se ejecutó `scripts/sincronizar_secret.py` para
actualizar los secretos locales y se reinició Django; la aplicación volvió a
responder correctamente.

**Verificaciones.** El archivo del realm pasó la validación JSON y las 11
pruebas del módulo de cajas pasaron tras el cambio del formulario dinámico.

---

## 4. Leyda Fleitas — RF022, Pago con pasarela real en modo prueba (GEG9-36)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

### 4.1. «Stripe o dLocal, y por qué»

**Lo que aprendimos.** Stripe no permite registrarse desde Paraguay. dLocal
sí, y además está pensado específicamente para Latinoamérica — tiene
cobertura nativa de Paraguay con tarjetas y medios de pago locales.

**Decisión.** dLocal en modo sandbox, con credenciales de prueba generadas
por el propio equipo (no las da la cátedra).

### 4.2. «¿Qué pasa si `moneda_pagada` no es ninguna que dLocal sepa cobrar en Paraguay?»

**Lo que aprendimos**, leyendo la documentación real antes de programar
(`docs.dlocal.com`, país Paraguay): dLocal ahí **solo** cobra en PYG (sin
decimales) o en USD —y esto último solo con tarjeta, vía
`currency_to_charge`—. El modelo de `CompraDivisa` ya permite EUR, BRL, ARS,
GBP y JPY como `moneda_pagada`, ninguna de las cuales dLocal puede cobrar
directamente ahí.

**Decisión** (confirmada con la responsable del proyecto antes de programar,
tal como pedía el ticket): si `moneda_pagada` no es PYG ni USD, convertir el
`total_a_pagar` a su equivalente en PYG usando `tasa_aplicada` —ya congelada
en la operación— y cobrar eso. Se implementó en una sola función,
`monto_para_pasarela(compra)`, para no repetir esta regla en varios lugares.

### 4.3. «¿La pasarela aplica también a Venta?»

**Lo que aprendimos.** En una Venta el cliente **entrega** divisas y
**recibe** PYG — no hay nada que cobrarle con tarjeta. Meter una pasarela de
pago ahí habría significado inventar qué cobrarle, algo que el ticket no
pedía.

**Decisión** (confirmada antes de programar): la pasarela (RF022) solo se
agrega al flujo de Compra. El "Confirmar pago" directo de Venta (RF051) no
cambia.

### 4.4. «Bug real encontrado probando contra el sandbox, no solo con mocks»

**Lo que aprendimos.** La documentación de la firma da un solo ejemplo
literal del encabezado `X-Date`: `2018-07-12T13:46:28.629Z` (como
`new Date().toISOString()` en JavaScript — milisegundos y sufijo `Z`). Se
implementó al principio con offset `+0000` en vez de `Z`, que es un formato
también válido de ISO 8601 pero no el que dLocal espera exactamente — y el
sandbox lo rechazó con `{"code": 5001, "message": "Invalid parameter",
"param": "X-Date"}`.

**Decisión.** Corregir el formato a sufijo `Z` y volver a probar contra el
sandbox real (no solo con el mock de las pruebas automáticas). Con esa
corrección, `crear_pago` y `consultar_pago` funcionaron de verdad contra
`https://sandbox.dlocal.com`, devolviendo un `redirect_url` real y un
`id` real de pago. Este bug nunca lo iban a encontrar las pruebas con mock
(ahí el "servidor falso" nunca valida el formato real del header) — por
eso el ticket pedía probar contra la documentación/sandbox antes de dar por
terminada la integración.

### 4.5. «¿Cómo confío en que el pago salió aprobado, si el cliente vuelve de la pasarela con la URL que quiera?»

**Lo que aprendimos.** Un cliente (o cualquiera) podría volver a la URL de
retorno con parámetros manipulados a mano, intentando simular un pago
aprobado sin haber pagado.

**Decisión.** La vista de retorno nunca mira los parámetros de la URL: vuelve
a preguntarle a la pasarela (`consultar_pago`) cuál es el estado real del
pago, y recién ahí decide. Es además idempotente — consultarlo dos veces no
confirma la compra dos veces (se verificó con una prueba que cuenta cuántas
veces se llamó al proveedor).

### 4.6. «¿Qué pasa si el pago sale aprobado pero la compra ya venció o cambió de cotización mientras tanto?»

**Lo que aprendimos.** Es un caso real de carrera: el cliente puede tardar en
pagar en la pasarela más de lo que dura la cotización congelada (15 minutos,
RF051), o el analista puede actualizar la tasa justo en el medio.

**Decisión.** Si el pago llega aprobado pero `confirmar_pago_compra` no la
deja CONFIRMADA (la cancela por cambio de cotización o por vencimiento), se
intenta reembolsar automáticamente. Si el reembolso en sí también falla, el
`Pago` queda en un estado nuevo, `REQUIERE_REVISION`, en vez de que el
usuario vea un error críptico o el dinero quede cobrado sin nada a cambio.

### 4.7. «¿Y si no hay credenciales de dLocal configuradas?»

**Decisión.** `DLocalProveedor` chequea las tres credenciales **antes** de
tocar cualquier otro dato, y si falta alguna tira un error claro y explicado
(`DLocalNoConfigurado`), nunca un `AttributeError` críptico. Mientras tanto,
`PAGO_PROVEEDOR=simulado` (el valor por defecto) permite hacer una demo
completa sin red ni credenciales, con botones para aprobar/rechazar el pago
a mano.

**Corrección sobre la marcha:** igual que con RF023 y RF033, el ticket
pedía un admin de solo lectura para `Pago`. No se registró — el equipo tiene
prohibido usar el admin de Django en este proyecto.

## 4.8. Verificaciones realizadas

- Migración inicial de `apps.pagos` generada y aplicada.
- Suite completa del proyecto ejecutada tras el cambio: **170 pruebas
  aprobadas** (incluye las 2 agregadas en 4.9 para los bugs del
  `callback_url` y el CSRF).
- Casos nuevos cubiertos: pago aprobado confirma la compra, pago rechazado
  no la confirma, idempotencia (consultar dos veces no confirma dos veces),
  pago aprobado con cotización cambiada o con la operación vencida (no
  confirma, intenta reembolso), la firma HMAC concatena login+fecha+cuerpo
  exactamente como pide la documentación, el `CheckConstraint` de "una sola
  operación" en `Pago`, y que faltar las credenciales de dLocal da un error
  claro en vez de una excepción cruda.
- **Verificación real contra el sandbox de dLocal** (no solo mocks): se creó
  una compra real con `moneda_pagada=USD` y se llamó a `iniciar_pago` con
  `PAGO_PROVEEDOR=dlocal` de verdad. La primera llamada falló por el formato
  de `X-Date` (ver 4.4); corregido esto, `crear_pago` devolvió un
  `redirect_url` y un `id` reales de `sandbox.dlocal.com`, y `consultar_pago`
  contra ese mismo pago devolvió `PENDING` correctamente traducido a
  `PENDIENTE`.
- Documentación técnica incorporada a Sphinx en `docs/sphinx/pagos.rst`.

### 4.9. Dos bugs más, encontrados recién al probar la demo completa en el navegador (no con pytest)

**«El cliente queda varado en la pantalla de éxito de dLocal, sin volver a nuestra app»**

**Lo que aprendimos.** `crear_pago` nunca mandaba `callback_url` en el
pedido — sin eso, dLocal no tiene a dónde devolver al navegador después de
pagar. La documentación completa de ese campo está en una página aparte
("Configure callback URL"), no en la de "Integrate checkout" que se había
revisado antes de programar.

**Decisión.** Armar un `callback_url` absoluto (`SITE_BASE_URL` +
`reverse("pagos:retorno", ...)`) con el `pk` del `Pago` ya creado, y
mandarlo siempre en el pedido a dLocal. Se verificó contra el sandbox real
que dLocal lo acepta sin error.

**«Prohibido (403): La verificación CSRF ha fallado»**

**Lo que aprendimos.** dLocal no redirige al cliente con un link común: le
hace al navegador un **POST** al `callback_url`. Ese POST no trae (ni puede
traer) el token CSRF de nuestro sitio, y por el mismo motivo —un POST entre
sitios distintos— tampoco hay garantía de que el navegador mande la cookie
de sesión.

**Decisión.** Dos cambios en `retorno`: `@csrf_exempt` (no hace falta el
token porque de todas formas nunca se confía en nada de ese POST — siempre
se vuelve a consultar el estado real con `consultar_pago`), y dejar de
exigir login/dueño en esa vista puntual. Como `confirmar_pago_compra`
necesita un usuario asociado al cliente para encontrar la compra, si no hay
sesión se usa cualquiera de los usuarios ya asociados a ese cliente —no
hace falta que sea justo quien iba a pagar: la operación ya se validó como
legítima contra la pasarela antes de llegar a ese paso.

**Verificación.** Se agregaron dos pruebas que reproducen exactamente estos
dos escenarios (un `Client(enforce_csrf_checks=True)` real, y
`confirmar_pago(..., usuario=None)`), además de repetir la prueba manual
completa contra el sandbox real hasta llegar de vuelta al comprobante ya
confirmado.

---
