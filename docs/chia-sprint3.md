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
