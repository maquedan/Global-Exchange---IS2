Usuarios y autenticación
========================

Módulo responsable del inicio de sesión con Keycloak, la sincronización de
roles, el menú principal, el cliente activo de la sesión (RF008) y la
restricción de operaciones a quien no está asociado a ningún cliente
(RF010).

La restricción de RF010 vive acá y no en cada app porque se apoya en la misma
pieza que RF008: ``request.cliente_activo``. Son dos herramientas, una por
capa:

* ``requiere_cliente_para_operar``, el decorador de vistas, que corta el GET
  y el POST antes de llegar a la vista.
* ``cliente_habilitado_para`` y la excepción ``ClienteNoHabilitado``, la
  defensa en profundidad que usan los servicios para negarse por su cuenta,
  sin depender de que los llamen desde una vista bien decorada.

Autenticación con Keycloak
--------------------------

.. automodule:: apps.usuarios.auth
   :members:

Menú principal según el rol
---------------------------

.. automodule:: apps.usuarios.menu
   :members:

.. automodule:: apps.usuarios.context_processors
   :members:

Cliente activo y restricción de operaciones
-------------------------------------------

Acá están ``cliente_activo_de`` (RF008), el decorador
``requiere_cliente_para_operar``, el helper ``cliente_habilitado_para`` y la
excepción ``ClienteNoHabilitado`` (RF010).

.. automodule:: apps.usuarios.services
   :members:

.. automodule:: apps.usuarios.middleware
   :members:

Vistas
------

.. automodule:: apps.usuarios.views
   :members:

Permisos por rol
----------------

.. automodule:: apps.usuarios.models
   :members:

.. automodule:: apps.usuarios.keycloak_admin
   :members:
