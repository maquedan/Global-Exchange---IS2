Scripts de apoyo
================

Herramientas de línea de comandos para preparar el entorno. No forman parte de
la aplicación web: se ejecutan a mano, desde la raíz del proyecto.

``scripts/sincronizar_secret.py``
---------------------------------

Copia el *client secret* que genera Keycloak al archivo ``.env``.

El realm versionado en ``keycloak/realm-global-exchange.json`` **no** incluye el
secret, porque los secretos no se guardan en Git. Cuando Keycloak importa el
realm por primera vez genera uno nuevo al azar; este script lo lee por la API de
administración y lo escribe en el ``.env``.

.. code-block:: bash

   python3 scripts/sincronizar_secret.py

Hay que ejecutarlo una vez después del primer ``docker compose up``, y cada vez
que se recree el realm desde cero.

``scripts/configurar_smtp.py``
------------------------------

Configura el servidor de correo de Keycloak, que es quien envía los correos de
verificación del autorregistro.

Lee los datos de correo del ``.env`` (que no se versiona) y los aplica al realm,
de modo que la contraseña queda en un solo lugar y nunca llega a Git.

.. code-block:: bash

   python3 scripts/configurar_smtp.py                    # aplica lo del .env
   python3 scripts/configurar_smtp.py --probar tu@correo.com
   python3 scripts/configurar_smtp.py --mailpit          # buzón falso de desarrollo

Si ``EMAIL_HOST`` está vacío deja configurado Mailpit, el buzón falso de
desarrollo, para que el entorno funcione sin credenciales reales.
