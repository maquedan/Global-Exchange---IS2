Facturación electrónica
=======================

Emisión automática de la factura electrónica al confirmarse una operación
(RF026 — GEG9-50), contra la API de Factura Segura en su ambiente de pruebas.

El cliente de la API es intercambiable (patrón adaptador, el mismo que en
:doc:`pagos`): hay uno real y uno simulado, sin red, para desarrollo, demos y
pruebas automáticas. Se elige con la variable de entorno
``FACTURACION_PROVEEDOR``.

Esta historia es la base de la facturación: RF027 (envío por correo), RF028
(estado en el SIFEN), RF029 (descarga de KuDE y XML) y RF053 (visualización)
se construyen sobre el modelo ``Factura``, que guarda el CDC y deja
``estado_fiscal`` vacío para que RF028 lo complete.

Modelos
-------

.. automodule:: apps.facturacion.models
   :members:

Códigos del SIFEN
-----------------

.. automodule:: apps.facturacion.codigos_sifen
   :members:

Armado del documento electrónico
--------------------------------

.. automodule:: apps.facturacion.de
   :members:

Clientes de la API
------------------

.. automodule:: apps.facturacion.clientes.base
   :members:

.. automodule:: apps.facturacion.clientes.facturasegura
   :members:

.. automodule:: apps.facturacion.clientes.simulado
   :members:

Servicios
---------

.. automodule:: apps.facturacion.services
   :members:

Comando de reintento
--------------------

.. automodule:: apps.facturacion.management.commands.emitir_facturas_pendientes
   :members:
