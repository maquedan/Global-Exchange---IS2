Notificaciones
==============

Alertas a los clientes cuando cambia una tasa de cambio (RF033 — GEG9-38).

Se avisa por dos vías a la vez: una notificación interna, que se ve con un
contador en el menú, y un correo electrónico. El envío se registra con
``transaction.on_commit`` para no avisar de un cambio que termine
revirtiéndose, y un fallo al mandar el correo no impide que la tasa quede
guardada ni que la notificación interna exista.

Modelos
-------

.. automodule:: apps.notificaciones.models
   :members:

Servicios
---------

.. automodule:: apps.notificaciones.services
   :members:

Vistas
------

.. automodule:: apps.notificaciones.views
   :members:
