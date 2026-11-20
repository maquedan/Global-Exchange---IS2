# QA – Sprint 6

**Historias QA incluidas:** GEG9-70 y GEG9-71

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

## GEG9-71 – Verificación del manejo de roles

### Ejecución automatizada

Fecha y hora: viernes 20 de noviembre de 2026, 05:22:58 (-03, hora de
Paraguay).

Se ejecutó:

```bash
docker compose exec web pytest \
  apps/usuarios/tests/test_menu.py \
  apps/usuarios/tests/test_roles_permisos.py \
  apps/usuarios/tests/test_restriccion_operaciones.py \
  apps/terminal/tests/test_terminal.py \
  -v
```

**Resultado:** `70 passed, 1 warning in 32.95s`.

La batería verifica el armado del menú, la procedencia de los roles desde
Keycloak, la administración de roles y permisos, la restricción de operaciones para usuarios sin cliente, y el acceso exclusivo a la terminal. En particular, un usuario sin cliente asociado puede consultar las pantallas permitidas, pero se bloquea en 17 rutas operativas por GET y POST sin crear operaciones, pagos ni cuentas.

### Administración de roles y permisos

La pantalla `/administracion/roles-permisos/` permite al administrador crear roles en Keycloak, asignarlos a usuarios y vincular permisos funcionales. Las pruebas verifican que un usuario cliente no acceda al panel y que las acciones de creación y asignación se deleguen a Keycloak.

Esto demuestra la configuración de roles, pero no reemplaza la comprobación de menús y URLs de cada perfil.

### Administrador

El administrador debe acceder a gestión de clientes, monedas, caja principal, configuración, roles y permisos, auditoría, operaciones administrativas, facturas y tablero. La ruta `/administracion/roles-permisos/` queda reservada a este perfil.

**Resultado:** Protegido y cubierto por pruebas automatizadas.

### Analista cambiario

El analista puede consultar cotizaciones, tasas de cambio, ganancias y reporte de transacciones. No debe acceder a administración de roles, caja ni atención de efectivo.

Durante la revisión manual se encontró la inconsistencia QA-ROL-01 descrita más abajo.

**Resultado:** Aprobado. No ve **Clientes** en el menú y la URL `/clientes/` continúa restringida al administrador.

### Usuario cliente

El usuario cliente puede consultar y operar únicamente en nombre de un cliente activo asociado. Sin asociación, conserva las pantallas de consulta y no puede crear, confirmar ni cancelar operaciones; el menú no ofrece acciones que requieran cliente activo.

**Resultado:** Aprobado por pruebas automatizadas.

### Cajero

El cajero puede atender compras y ventas pendientes, consultar sus existencias y realizar arqueos. No puede abrir las pantallas administrativas ni anular operaciones.

**Resultado:** Cubierto por las pruebas de conversiones, caja y el menú. Debe mantenerse la comprobación visual al cerrar la matriz de roles.

### Terminal

El perfil `terminal` muestra únicamente **Panel** y **Terminal**. Puede abrir `/terminal/`, pero no las pantallas de caja ni las administrativas.

**Resultado:** Aprobado por pruebas automatizadas.

### Hallazgo QA-ROL-01

**Error Jira:** GEG9-83, QA-ROL-01 – El analista cambiario ve Clientes en el menú, pero recibe 403

Se comprobó manualmente que un usuario con rol `analista_cambiario` ve la
opción **Clientes** en el menú, pero al abrirla recibe `403 Forbidden` porque `/clientes/` está protegida exclusivamente para el rol `administrador`.

RF039 define el centro de gestión de clientes como una función administrativa.
Por lo tanto, el menú y la autorización son inconsistentes: el analista no debería ver una opción que no puede usar.

**Corrección propuesta:** Quitar `analista_cambiario` de la opción **Clientes** en `apps/usuarios/menu.py`.

**Verificación posterior requerida:** El analista ya no debe ver **Clientes**; si intenta abrir `/clientes/` directamente debe seguir recibiendo acceso denegado. El administrador debe conservar tanto la opción como el acceso.

### Hallazgo QA-ROL-02

**Error Jira:** GEG9-84, QA-ROL-02 – La ruta elegir-cliente es accesible sin autenticación

La ruta interna `/elegir-cliente/` responde `200 OK` para un visitante sin iniciar sesión. No expone clientes porque la consulta queda vacía para un usuario anónimo, pero la pantalla de selección de cliente forma parte del flujo autenticado y no debería ser pública.

**Corrección propuesta:** agregar `@login_required` a `seleccionar_cliente` en `apps/usuarios/views.py` y añadir una prueba que compruebe la redirección al inicio de sesión para una solicitud anónima.

**Verificación posterior requerida:** Una persona no autenticada debe ser redirigida al inicio de sesión; un usuario autenticado debe conservar el flujo actual de selección de cliente.

---

## Hallazgos y correcciones

- **QA-ROL-01 (GEG9-83): corregido.** La opción **Clientes** se restringió al menú del administrador. El analista ya no la visualiza y conserva el `403` si intenta abrir `/clientes/` directamente.

- **QA-ROL-02 (GEG9-84): corregido.** La vista `/elegir-cliente/` exige autenticación; una persona anónima es redirigida al inicio de sesión y el flujo de selección autenticado se mantiene.

- **Tablero administrativo (GEG9-67): verificado.** El administrador puede acceder; analista, usuario cliente, cajero y terminal reciben `403` por URL directa y no deben disponer de esa opción en el menú.

- No se identificaron fallos nuevos durante la ejecución automatizada de GEG9-70.


### Verificación final posterior a las correcciones

Se ejecutó la batería consolidada de roles, menú, restricciones operativas, selección de cliente, clientes, terminal y tablero administrativo.

**Resultado:** `150 passed, 1 warning in 25.59s`.


## Conclusión

GEG9-70 queda aprobado para los flujos funcionales verificables localmente, con 199 pruebas automatizadas aprobadas y recorridos manuales realizados. Las integraciones reales de dLocal y Factura Segura conservan la limitación propia de sus credenciales y ambientes externos.

GEG9-71 queda aprobado: la matriz de roles, los menús y el acceso por URL
directa fueron verificados para administrador, analista cambiario, usuario
cliente, cajero y terminal. Los hallazgos QA-ROL-01 y QA-ROL-02 fueron
corregidos y reverificados.
