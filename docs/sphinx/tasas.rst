Visualización de tasas en tiempo real
======================================

Panel de cotizaciones para el usuario final: selector de monedas, gráfico
histórico, estadísticas y auto-refresco cada 20 segundos. Esta app no tiene
modelos propios: solo lee los de ``apps.monedas`` y ``apps.tasa_cambios``
(RF016 — GEG9-28).

Vistas
------

.. automodule:: apps.tasas.views
   :members:

Filtro de plantilla: banderas
------------------------------

.. automodule:: apps.tasas.templatetags.tasas_extras
   :members:
