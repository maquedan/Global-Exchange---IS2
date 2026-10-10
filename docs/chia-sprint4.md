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
