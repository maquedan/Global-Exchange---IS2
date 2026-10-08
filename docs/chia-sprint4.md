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
