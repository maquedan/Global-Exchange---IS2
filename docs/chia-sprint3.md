# CHIA — Conversaciones con Inteligencia Artificial

Registro del uso de IA como herramienta de apoyo durante el **Sprint 3** del
proyecto Global Exchange (Grupo 9, FP-UNA).

- **Modalidad de trabajo:** se utilizó como asistente de consulta y de
  programación. Las decisiones de diseño, cambios de código, comandos y
  verificaciones fueron realizados y validados por la integrante en el entorno
  real del proyecto.

---

## 1. Daniela Gonzalez — RF052, Configuración de Comisiones por Categoría (GEG9-35)

**Herramienta:** Codex (OpenAI), integrado en VS Code sobre WSL2.

### 1.1. «¿Qué historia debe implementarse primero para no bloquear Compra y Venta?»

**Lo que aprendimos.** Las historias de Compra y Venta necesitan conocer el
porcentaje de comisión del cliente antes de confirmar una operación. En cambio,
el historial solo puede implementarse completamente cuando ya existan
transacciones registradas.

**Decisión.** Implementar primero RF052 como una app independiente,
`apps.comisiones`, para que RF018 y RF019 puedan consultar la comisión vigente
de Minorista, Corporativo o VIP.

### 1.2. «¿Cómo evitar que cada módulo tenga categorías diferentes?»

**Lo que aprendimos.** Duplicar las categorías en otra app puede causar datos
inconsistentes. Las categorías Minorista, Corporativo y VIP ya pertenecen al
modelo `Cliente`.

**Decisión.** Reutilizar `Cliente.Categoria.choices` para el campo `categoria`
de `ComisionCategoria`, en lugar de definir nuevas opciones.

### 1.3. «¿Por qué una categoría no puede tener dos configuraciones de comisión?»

**Lo que aprendimos.** Si una categoría tuviera dos porcentajes vigentes, Compra
y Venta no sabrían cuál aplicar.

**Decisión.** Definir `categoria` como única. Cada categoría posee una sola
configuración vigente, que el administrador puede actualizar cuando sea
necesario.

### 1.4. «¿Por qué no se elimina una configuración de comisión?»

**Lo que aprendimos.** Compra y Venta necesitan una comisión vigente para
calcular nuevas operaciones. Además, las transacciones futuras deben guardar el
porcentaje aplicado como dato histórico.

**Decisión.** No implementar eliminación. El administrador crea o actualiza el
porcentaje; RF018 y RF019 deberán guardar el porcentaje y monto de comisión
dentro de cada transacción confirmada.

## 1.5. Verificaciones realizadas

- Migración inicial de `apps.comisiones` generada y aplicada en PostgreSQL
  mediante Docker Compose.
- `python manage.py check` ejecutado sin errores.
- Flujo manual validado desde `/comisiones/`: creación de configuración,
  edición de porcentaje y rechazo de categorías duplicadas.
- Pruebas unitarias focalizadas ejecutadas con pytest; la salida completa se
  registra en `docs/evidencia_pruebas_unitarias_sprint3.md`.
- Documentación técnica de la app incorporada a Sphinx mediante
  `docs/sphinx/comisiones.rst`.

---

## 2. Fabrizio Cardozo — RF018, Compra de Divisas (GEG9-31)

**Herramienta:** Codex (OpenAI), integrado en VS Code sobre WSL2.

### 2.1. «¿Cómo se obtiene la tasa y comisión aplicables al confirmar?»

**Lo que aprendimos.** Una tasa futura no debe utilizarse antes de su fecha de
vigencia, y la comisión depende de la categoría del cliente (Minorista,
Corporativo o VIP).

**Decisión.** Al confirmar, buscar la tasa activa más reciente cuyo
`vigente_desde` sea menor o igual al momento actual, y la configuración de
comisión de la categoría del cliente. Si falta alguna de las dos, cancelar la
operación y mostrar un mensaje explicativo.

### 2.2. «¿Por qué se guardan la tasa y la comisión dentro de la compra?»

**Lo que aprendimos.** Las cotizaciones y los porcentajes de comisión pueden
cambiar después de una operación. Consultar siempre la configuración actual
alteraría el comprobante histórico.

**Decisión.** Crear el modelo `CompraDivisa` con el monto base, porcentaje y
monto de comisión, total a pagar, tasa aplicada y monto recibido. Esos valores
son una fotografía de la operación confirmada.

### 2.3. «¿Cómo se impide que un cliente opere para otra persona?»

**Lo que aprendimos.** El rol `usuario_cliente` no basta para autorizar una
operación: el usuario debe estar asociado al cliente seleccionado.

**Decisión.** Limitar el selector de clientes a las asociaciones activas del
usuario autenticado y restringir el comprobante al propietario de la compra.

## 2.4. Verificaciones realizadas

- Migración `0001_compra_divisa` generada para persistir las compras de
  divisas.
- Flujo disponible para el rol `usuario_cliente` en
  `/conversiones/comprar/`.
- Validación de monedas diferentes, cliente asociado, tasa vigente y comisión
  configurada para la categoría del cliente.
- Pruebas unitarias de RF018 y suite completa ejecutadas: **94 pruebas
  aprobadas**. La evidencia está registrada en
  `docs/evidencia_pruebas_unitarias_sprint3.md`.
- Documentación técnica incorporada a Sphinx en
  `docs/sphinx/conversiones.rst`.

---

## 3. Leyda Fleitas — RF051, Cancelación de Transacción por Cambio de Cotización (GEG9-51)


### 3.1. «Comprar/Vender ya confirman todo en un solo paso, ¿cómo se cancela algo que nunca queda pendiente?»

**Lo que aprendimos.** `confirmar_compra`/`confirmar_venta` creaban la
operación ya resuelta: no existía ningún momento intermedio entre que el
cliente ve la cotización y que la operación queda en firme. Sin un estado
"pendiente", no hay nada que cancelar.

**Decisión.** Partir el flujo en dos pasos: `iniciar_compra`/`iniciar_venta`
congelan la tasa y la comisión vigentes y crean la operación en estado
PENDIENTE; una acción posterior y explícita del cliente
(`confirmar_pago_compra`/`confirmar_pago_venta`) la pasa a CONFIRMADA.

### 3.2. «Si la tasa cambió entre que se inició y se confirmó, ¿qué tasa se cobra?»

**Lo que aprendimos.** Ninguna de las dos es correcta por sí sola: cobrar la
tasa vieja ignora que ya no está vigente, y cobrar la tasa nueva rompe la
promesa de la historia ("no verme afectado por una tasa distinta a la que
acepté"). La única opción consistente con lo pedido es no cobrar nada.

**Decisión.** Al confirmar, comparar la tasa activa actual para el par contra
la que quedó guardada en la operación. Si difieren, cancelar automáticamente
(`motivo_cancelacion = CAMBIO_COTIZACION`) en vez de confirmar con cualquiera
de las dos.

### 3.3. «¿Alcanza con la cancelación automática, o el cliente necesita poder cancelar él mismo?»

**Lo que aprendimos.** El texto de la historia pide explícitamente "quiero
**poder** cancelar", no solo que el sistema cancele solo. Son dos casos
distintos: cancelación automática (la tasa cambió) y cancelación manual (el
cliente se arrepiente antes de pagar, cambie o no la tasa).

**Decisión.** Agregar también un botón de cancelar manual sobre la operación
pendiente, con su propio motivo (`motivo_cancelacion = CLIENTE`), para
distinguirlo en el historial de una cancelación automática.

### 3.4. «¿Cómo migrar el campo `confirmado_en` sin perder las operaciones ya confirmadas de antes?»

**Lo que aprendimos.** El campo `confirmado_en` (con `auto_now_add`) en
realidad guardaba la fecha de **creación**, porque antes se creaba ya
confirmada. Al agregar el estado, ese significado deja de ser cierto.

**Decisión.** Renombrar `confirmado_en` a `creado_en` (conserva la fecha
original) y agregar un `confirmado_en` nuevo, vacío. Una migración de datos
marca las operaciones que ya existían como `CONFIRMADA`, con
`confirmado_en = creado_en`, para no reescribir su historial.

### 3.5. «Si nadie vuelve a confirmar, ¿la operación pendiente queda ahí para siempre?»

**Lo que aprendimos.** El chequeo de "¿cambió la tasa?" solo corre cuando
alguien hace clic en Confirmar. Si el cliente nunca vuelve a esa pantalla, la
operación queda PENDIENTE indefinidamente con una cotización cada vez más
vieja, sin que nadie la revise.

**Decisión.** Agregar un plazo de 15 minutos desde que se inicia la
operación. Se chequea (y se cancela sola si corresponde, con
`motivo_cancelacion = EXPIRADA`) en tres momentos: al confirmar, al cancelar
manualmente, y al simplemente abrir la pantalla de la operación — así una
pendiente vencida nunca se ve como si todavía se pudiera pagar.

### 3.6. «¿Cómo sabe el cliente cuánto tiempo le queda para confirmar?»

**Lo que aprendimos.** El aviso de "tenés 15 minutos" es un texto fijo: no le
dice al cliente si le quedan 14 minutos o 30 segundos. Y si se cancela por
cambio de cotización, hoy tiene que volver a completar todo el formulario de
cero para reintentar.

**Decisión.** Dos mejoras chicas sobre lo mismo, sin agregar dependencias:

- Un contador en JavaScript puro en la pantalla de revisión (mismo estilo que
  el reloj de RF016) que se actualiza cada segundo a partir de
  `creado_en + 15 minutos`, y recarga la página sola al llegar a cero para
  que el servidor aplique la cancelación real.
- Un botón "Repetir esta operación" en el comprobante (confirmada o
  cancelada) que arma la URL del formulario con los mismos datos por query
  string; la vista los usa como `initial` del formulario.

**Bug encontrado al probarlo.** El link de "Repetir" armaba mal la URL
(`monto_pagado=100,00` con coma) porque `{{ compra.monto_pagado }}` se
formatea con el idioma activo. Mismo bug que ya habíamos visto en RF016 —
se resolvió igual, con `stringformat:".2f"`.

## 3.7. Verificaciones realizadas

- Migración `0003_estado_pendiente_cancelacion` generada a mano (el
  autodetector de Django no sabe expresar un `RenameField` + migración de
  datos) y aplicada sin errores; `0004_alter_..._motivo_cancelacion` agregada
  después para el motivo `EXPIRADA`.
- Suite completa del proyecto ejecutada tras el cambio: **111 pruebas
  aprobadas**, sin romper ninguna prueba existente de Compra/Venta.
- Casos nuevos cubiertos: confirmación exitosa sin cambio de tasa,
  cancelación automática por cambio de cotización, cancelación manual,
  cancelación automática por vencimiento del plazo, pre-llenado del
  formulario desde el botón "Repetir", rechazo de confirmar/cancelar una
  operación que ya no está pendiente, y rechazo de confirmar la operación de
  otro cliente.
- Documentación registrada en `docs/evidencia_pruebas_unitarias_sprint3.md`.

---
