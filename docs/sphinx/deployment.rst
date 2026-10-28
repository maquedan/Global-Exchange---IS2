Despliegue
==========

Requisitos
----------

Se necesita Docker con Docker Compose v2. Para ejecutar ``scripts/deploy.sh``
también se necesitan Bash, Python 3 y ``curl``. Los comandos se ejecutan desde
la raíz del repositorio.

Desarrollo
----------

Ejecutá un solo comando:

.. code-block:: bash

   ./scripts/deploy.sh dev

La primera ejecución crea el archivo local ``.env`` a partir de
``.env.example`` y genera claves aleatorias para Django, PostgreSQL y el
administrador de Keycloak. El archivo queda excluido de Git. El script
construye Django, inicia PostgreSQL, Keycloak y Mailpit, espera que las bases
estén listas, sincroniza los secretos OIDC, ejecuta las migraciones, recoge los
archivos estáticos y arranca el servidor de desarrollo.

La aplicación queda en ``http://localhost:8000``, Keycloak en
``http://localhost:8080`` y Mailpit en ``http://localhost:8025``. La contraseña
generada para Keycloak se conserva en ``KC_ADMIN_PASSWORD`` dentro de
``.env``. Para crear un superusuario de Django:

.. code-block:: bash

   docker compose exec web python manage.py createsuperuser

Producción
----------

1. Copiá ``.env.prod.example`` a ``.env.prod``.
2. Reemplazá los valores ``REEMPLAZAR`` y completá dominios, ``DATABASE_URL``,
   ``DJANGO_ALLOWED_HOSTS`` y las credenciales requeridas. Definí y aprobá
   también la tasa USD/PYG inicial (``INITIAL_USD_PYG_BUY_RATE`` y
   ``INITIAL_USD_PYG_SELL_RATE``) y las comisiones por categoría
   (``INITIAL_COMMISSION_*``). Usá secretos aleatorios; URL-encodeá la
   contraseña PostgreSQL en ``DATABASE_URL``.
3. Ejecutá:

.. code-block:: bash

   ./scripts/deploy.sh prod

El script valida las variables necesarias, construye la imagen, espera ambas
bases de datos, inicia Keycloak e importa el realm, y luego sincroniza los
secretos OIDC. Antes de iniciar Gunicorn y Nginx, aplica las migraciones y
ejecuta ``collectstatic``. El archivo ``.env.prod`` está excluido de Git y debe
mantenerse privado.

Datos iniciales
---------------

El despliegue ejecuta ``python manage.py cargar_datos_iniciales`` después de
las migraciones. Usa ``--profile demo`` en desarrollo y ``--profile minimal``
en producción. La carga es idempotente: identifica registros por claves
naturales, completa solo los que faltan y no sobrescribe tasas ni comisiones
existentes.

El perfil demo agrega monedas, tasas y comisiones ficticias, los grupos de rol
de Django, clientes de ejemplo y una caja con saldos e inventario en cero. Los
clientes usan datos reservados para demostraciones y no se crean usuarios ni
contraseñas. El perfil minimal agrega USD/PYG, una tasa USD/PYG suministrada
por el operador, las comisiones configuradas por el operador y los grupos de
rol; no crea clientes, sucursales ni cajas demo. Las tasas de muestra no son
cotizaciones de mercado. Confirmá los valores financieros antes de habilitar
operaciones en producción.

También se puede repetir la carga manualmente:

.. code-block:: bash

   docker compose exec web python manage.py cargar_datos_iniciales --profile demo

Por defecto, Nginx publica la aplicación en el puerto 80 y Keycloak en el
8080. Configurá TLS en un proxy o balanceador antes de exponerlos a Internet.
Para aplicar cambios de configuración, actualizá ``.env.prod`` y ejecutá
nuevamente el mismo comando.

Datos y secretos
----------------

Los datos de PostgreSQL se conservan en volúmenes de Docker. ``docker compose
down`` detiene los servicios sin borrarlos. No incluyas ``.env``, ``.env.prod``
ni secretos en Git; las plantillas contienen solo valores de ejemplo y
marcadores para completar.
