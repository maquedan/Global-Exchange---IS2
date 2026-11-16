Conversiones y compras de divisas
=================================

Simulación de conversiones (RF017), compra y venta de divisas con tasa y
comisión vigentes (RF018, RF019), cancelación de la operación por cambio de
cotización antes de confirmar el pago (RF051), consulta de historial de
transacciones en modo solo lectura (RF030), trazabilidad de cada cambio de
estado por el que pasa una operación (RF023) y conciliación manual de
transferencias bancarias por parte del administrador (RF025).

Modelos
-------

.. automodule:: apps.conversiones.models
   :members:

Conciliación manual (RF025 — GEG9-75)
-------------------------------------

Una compra se puede pagar por la pasarela o por **transferencia bancaria**.
En el segundo caso el cliente la marca al elegir cómo pagar y la operación
queda con ``espera_transferencia = True``: **no se vence a los 15 minutos**,
porque verificar una transferencia lleva horas o días y si no se cancelaría
antes de que el administrador llegara a conciliarla.

La confirmación tiene dos puertas de entrada que se diferencian **solo en el
control de acceso**, y comparten el mismo núcleo
(``_confirmar_compra_pendiente``):

* ``confirmar_pago_compra`` — exige ser el dueño de la operación. La usan el
  cliente y la pasarela.
* ``conciliar_compra`` — exige el rol ``administrador``. Es RF025.

Gracias a eso, por los dos caminos se revalida la cotización (RF051), se
registra el cambio de estado con su autor (RF023) y se emite la factura
electrónica (RF026), sin duplicar nada.

``conciliar_compra`` **devuelve** la compra en lugar de lanzar cuando la
cotización cambió: todo corre dentro de una transacción, y lanzar revertiría
la cancelación que RF051 acaba de registrar. Quien la llama tiene que mirar
el estado; no alcanza con que no haya excepción.

Servicios
---------

.. automodule:: apps.conversiones.services
   :members:

Formularios
-----------

.. automodule:: apps.conversiones.forms
   :members:

Vistas
------

.. automodule:: apps.conversiones.views
   :members:
