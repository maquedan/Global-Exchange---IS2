Monitoreo y exportación de ganancias
====================================

El módulo expone el monitoreo de ganancias confirmadas (RF031 — GEG9-64) y
la exportación del reporte consolidado (RF032 — GEG9-65). Ambas funciones están
disponibles solamente para los roles ``administrador`` y
``analista_cambiario``.

El cálculo suma, por moneda, la comisión y la diferencia entre la tasa de
venta y la tasa de compra. El período se filtra por ``confirmado_en``. La
pantalla se actualiza consultando ``/ganancias/datos/`` y permite descargar el
desglose en PDF o Excel ``.xlsx`` desde ``/ganancias/exportar/<formato>/``.

Los archivos respetan las fechas, moneda y estado seleccionados, e incluyen
totales y fecha de generación. Los estados distintos de confirmado no aportan
ganancias.

Servicio
--------

.. automodule:: apps.ganancias.services
   :members:

Formularios
-----------

.. automodule:: apps.ganancias.forms
   :members:

Vistas
------

.. automodule:: apps.ganancias.views
   :members:
