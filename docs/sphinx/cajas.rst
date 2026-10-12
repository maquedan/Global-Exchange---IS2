Cajas
=====

Administración de sucursales, saldos de caja y fondos en efectivo asignados a
cajeros (RF041 y RF043), con control del inventario de billetes por denominación
(RF042), arqueos de caja (RF046) y registro de diferencias (RF047). Las
asignaciones a cajeros se registran como movimientos de caja con
cantidades por denominación, importe total, sucursal, cajero, divisa y fecha y
hora; los conteos reconciliados quedan auditados con su detalle.

La pantalla de detalle de una sucursal se dedica a consultar saldos, existencias
e historiales. Registrar movimientos, agregar denominaciones y reconciliar el
inventario son operaciones disponibles en páginas independientes.
Desde la página de denominaciones se pueden modificar o eliminar las que aún no
se hayan usado. Las denominaciones referenciadas por inventarios, movimientos o
conteos quedan protegidas para conservar la interpretación del historial.

RF046 — Arqueo de Caja
----------------------

El cajero registra el efectivo contado por denominación desde
``/cajas/arqueo/``. El sistema compara el total contado con el saldo de su
fondo en la caja y guarda un ``ArqueoCaja`` con el saldo esperado, total
contado, diferencia, observaciones y estado: ``CUADRADO``, ``FALTANTE`` o
``SOBRANTE``. Cada arqueo conserva además el detalle inmutable de billetes
mediante ``DetalleArqueoBillete``.

La operación está restringida al rol ``cajero`` y solo permite seleccionar
cajas y monedas en las que el usuario tenga fondos asignados.

RF047 — Registro de Diferencias de Caja
---------------------------------------

El administrador registra desde ``/cajas/diferencias/`` las discrepancias
detectadas en un arqueo. Cada ``DiferenciaCaja`` conserva el arqueo asociado,
monto positivo, divisa, motivo, responsable, usuario que realizó el registro
y fecha de creación.

La divisa de la diferencia debe coincidir con la del arqueo, y el formulario
solo ofrece monedas y responsables activos. La pantalla también muestra el
historial de las últimas diferencias registradas. El acceso está restringido
al rol ``administrador``.

Modelos
-------

.. automodule:: apps.cajas.models
   :members:

Servicios
---------

.. automodule:: apps.cajas.services
   :members:

Formularios
-----------

.. automodule:: apps.cajas.forms
   :members:

Vistas
------

.. automodule:: apps.cajas.views
   :members:
