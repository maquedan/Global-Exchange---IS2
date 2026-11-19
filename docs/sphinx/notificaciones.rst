Notificaciones
==============

Avisos a los clientes por dos motivos: cuando cambia una tasa de cambio
(RF033 — GEG9-38) y cuando cambia el estado de una de sus operaciones
(RF034 — GEG9-76).

Los dos avisos se registran con ``transaction.on_commit`` y ninguno puede
tumbar lo que los disparó.

Alertas de cambio de estado (RF034 — GEG9-76)
---------------------------------------------

El aviso se engancha dentro de ``registrar_cambio_estado``
(:doc:`conversiones`), que es el **único** punto por donde pasan los once
cambios de estado del proyecto: confirmar, cancelar, vencer, anular, la
terminal de autoservicio y la conciliación manual. Así ninguna transición
puede quedar sin avisar por olvido.

Dos detalles que no son evidentes:

* **Los destinatarios salen del cliente de la operación, no de quien la
  disparó.** En la terminal de autoservicio el usuario que provoca el cambio
  es la propia terminal: tomar de ahí el destinatario le mandaría los avisos
  a la máquina. Un cliente puede además no tener ningún usuario con cuenta,
  y eso no es un error, simplemente no hay a quién avisarle.
* **La creación de la operación no avisa.** ``estado_anterior`` vacío
  significa que recién se creó, y contarle a alguien lo que acaba de hacer
  es ruido.

Los duplicados no se evitan comprobando: son imposibles por construcción,
gracias a la unicidad de ``Notificacion`` sobre (usuario, cambio de estado).

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
