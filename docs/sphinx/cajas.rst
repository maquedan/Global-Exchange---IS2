Cajas
=====

Administración de sucursales, saldos de caja y fondos en efectivo asignados a
cajeros (RF041 y RF043), con control del inventario de billetes por denominación
(RF042). Las asignaciones a cajeros se registran como movimientos de caja con
cantidades por denominación, importe total, sucursal, cajero, divisa y fecha y
hora; los conteos reconciliados quedan auditados con su detalle.

La pantalla de detalle de una sucursal se dedica a consultar saldos, existencias
e historiales. Registrar movimientos, agregar denominaciones y reconciliar el
inventario son operaciones disponibles en páginas independientes.
Desde la página de denominaciones se pueden modificar o eliminar las que aún no
se hayan usado. Las denominaciones referenciadas por inventarios, movimientos o
conteos quedan protegidas para conservar la interpretación del historial.

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
