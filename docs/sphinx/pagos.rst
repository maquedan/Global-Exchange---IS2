Pagos
=====

Pago de una compra de divisas a través de una pasarela real en modo prueba
(RF022 — GEG9-36) y configuración de qué formas de pago se le ofrecen al
cliente (RF035 — GEG9-77).

Métodos de pago y proveedores no son lo mismo
---------------------------------------------

Conviene no confundirlos, porque el nombre se parece:

* **Proveedor** (``PAGO_PROVEEDOR``, variable de entorno): qué **pasarela**
  se usa, dLocal o el simulado sin red. Es una decisión técnica —"¿llamo a la
  API real o al doble de pruebas?"— y no se configura desde ninguna pantalla.
* **Método de pago** (modelo ``MetodoPago``): con **qué paga** el cliente,
  tarjeta o transferencia. Es una decisión de negocio y la administra el
  administrador desde la aplicación.

Antes de RF035 los métodos estaban escritos a mano en la plantilla de pago:
habilitar o deshabilitar uno exigía editar el HTML y desplegar.

Deshabilitar no traba lo que ya estaba en curso
-----------------------------------------------

La comprobación de que un método esté habilitado se hace **solo al iniciar**
un pago (``exigir_metodo_habilitado``), nunca al confirmarlo o cancelarlo.

Es deliberado: si se deshabilitara un método mientras hay operaciones
esperando, esas operaciones quedarían trabadas sin forma de resolverse —y el
cliente ya transfirió el dinero. Por eso una compra que espera conciliación
se puede confirmar, cancelar y conciliar aunque la transferencia esté
deshabilitada.

Modelos
-------

.. automodule:: apps.pagos.models
   :members:

Proveedores
-----------

.. automodule:: apps.pagos.proveedores.base
   :members:

.. automodule:: apps.pagos.proveedores.dlocal
   :members:

.. automodule:: apps.pagos.proveedores.simulado
   :members:

Servicios
---------

.. automodule:: apps.pagos.services
   :members:

Vistas
------

.. automodule:: apps.pagos.views
   :members:
