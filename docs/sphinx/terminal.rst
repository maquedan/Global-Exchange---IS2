Terminal de autoservicio
========================

La terminal permite identificar a un cliente y completar una compra o venta
sin exponer la sesión operativa del cliente (RF054/RF055 — GEG9-55). Todas sus
rutas requieren el rol ``terminal`` y el flujo conserva la operación en la
sesión de la terminal hasta mostrar el comprobante.

Las operaciones se crean mediante los mismos servicios de conversiones que el
flujo web. Por eso quedan en ``CompraDivisa`` y ``VentaDivisa``, aparecen en el
reporte administrativo y participan de las notificaciones y facturación
correspondientes.

Vistas
------

.. automodule:: apps.terminal.views
   :members:

Formularios
-----------

.. automodule:: apps.terminal.forms
   :members:
