Documentación de Global Exchange
================================

Plataforma web de cambio de divisas. Esta documentación se genera
**automáticamente** a partir de los docstrings del código fuente: al documentar
una función en el código, aparece acá sin trabajo extra.

Para regenerarla después de cambiar el código:

.. code-block:: bash

   docker compose exec web sphinx-build -b html docs/sphinx docs/sphinx/_build

El sitio queda en ``docs/sphinx/_build/index.html``.

.. toctree::
   :maxdepth: 2
   :caption: Módulos del proyecto

   usuarios
   clientes

.. toctree::
   :maxdepth: 1
   :caption: Guías

   scripts

Índices
-------

* :ref:`genindex`
* :ref:`modindex`
