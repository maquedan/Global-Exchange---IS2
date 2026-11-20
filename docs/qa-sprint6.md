# QA – Sprint 6

**Historias QA incluidas:** GEG9-70

## Propósito

Este documento reúne la evidencia de calidad funcional, técnica y de permisos del Sprint 6. Complementa la constancia de pruebas unitarias y diferencia lo que fue verificado automáticamente de los recorridos realizados mediante la interfaz.

No se considera validada una integración externa real únicamente porque las pruebas automatizadas utilicen proveedores simulados.

---

## GEG9-70 – Revisión del flujo crítico de compra, venta y terminal

### Ejecución automatizada

Fecha y hora: viernes 20 de noviembre de 2026, 05:00:53 (-03, hora de
Paraguay).

Se ejecutó la siguiente batería desde el entorno Docker Compose:

```bash
docker compose exec web pytest \
  apps/conversiones/tests/test_conversiones.py \
  apps/terminal/tests/test_terminal.py \
  apps/cajas/tests/test_cajas.py \
  apps/pagos/tests \
  apps/facturacion/tests \
  -v
```

**Resultado:** `199 passed, 1 warning in 101.57s (0:01:41)`.

También se ejecutó:

```bash
docker compose exec web python manage.py check
```

**Resultado:** `System check identified no issues (0 silenced).`

La advertencia de pytest corresponde a la futura deprecación de
`EMAIL_BACKEND` por Django; no representa un fallo de los flujos verificados.

### Compra y venta de divisas

Se verificaron la simulación de compra y venta, el cálculo de tasa y comisión, el congelamiento de los valores aplicados, la confirmación con cotización vigente y la protección para que un cliente no confirme ni consulte una operación ajena.

**Resultado:** Aprobado.

### Cancelación por cotización o vencimiento

Se verificó que compras y ventas pendientes se cancelen cuando cambia la cotización antes de confirmar o cuando expira el plazo permitido. También se comprueba la trazabilidad del estado y el motivo de cancelación.

**Resultado:** Aprobado.

### Compra con recepción de efectivo

Se verificó que el cajero ingrese billetes por denominación, que el total deba coincidir con el monto a cobrar, que un desglose incorrecto impida confirmar y que una compra confirmada aumente las existencias y registre su movimiento de caja. La anulación revierte el movimiento correspondiente.

**Resultado:** Aprobado.

### Venta con entrega de efectivo

Se verificaron la propuesta de billetes, el excedente mínimo aceptable, el rechazo cuando no hay efectivo suficiente, la confirmación y los movimientos de caja asociados. Un usuario cliente no puede realizar acciones de cajero.

**Resultado:** Aprobado.

### Terminal de autoservicio

Se verificaron el acceso exclusivo del rol `terminal`, el menú restringido, la identificación de un cliente activo, la selección de compra o venta, la simulación con tasa y comisión, la creación de la operación pendiente y la cancelación ante cambio de cotización. El comprobante solo queda disponible después de confirmar la operación y la terminal permite consultar cotizaciones.

El flujo guiado de terminal fue además recorrido manualmente durante el desarrollo: identificación, simulación, operación pendiente, atención por el cajero y comprobante.

**Resultado:** Aprobado.

### Pago, acreditación y facturación

Se verificaron pagos aprobados o rechazados, cancelación de pagos reembolsos simulados, emisión de factura para compras y ventas, reintentos y fallos de facturación sin revertir una operación confirmada. La acreditación de una venta queda registrada en la operación; no existe una integración bancaria o de
billetera externa real.

**Resultado:** Aprobado en el entorno simulado o controlado.

### Recorrido manual funcional

Los recorridos visuales disponibles se verificaron progresivamente durante el desarrollo de las historias. Se comprobó que el cajero recibe efectivo de una compra, entrega efectivo de una venta y que esas acciones se reflejan en la caja. También se comprobó la consulta de comprobantes, historial y documentos disponibles desde los roles correspondientes.

**Resultado:** Aprobado para los flujos funcionales disponibles en el entorno local.

### Límite de integraciones externas

Factura Segura y dLocal no se invocan contra sus servicios reales durante
pytest: las pruebas usan proveedores simulados o solicitudes controladas. Una emisión fiscal real o un cobro real por pasarela solo puede marcarse como aprobado con credenciales, rango de numeración y ambiente externos autorizados.

---

## Hallazgos y correcciones
- No se identificaron fallos nuevos durante la ejecución automatizada de
  GEG9-70.

## Conclusión

GEG9-70 queda aprobado para los flujos funcionales verificables localmente, con 199 pruebas automatizadas aprobadas y recorridos manuales realizados. Las integraciones reales de dLocal y Factura Segura conservan la limitación propia de sus credenciales y ambientes externos.