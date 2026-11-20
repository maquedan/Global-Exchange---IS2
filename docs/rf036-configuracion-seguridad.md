# RF036: configuración de seguridad

El rol `administrador` puede configurar el tiempo máximo de inactividad en
**Administración → Seguridad** (`/administracion/seguridad/`). El valor se
expresa en minutos y se limita a un rango de 5 minutos a 8 horas.

La configuración se guarda en la base de datos. El middleware consulta el
valor vigente en cada solicitud autenticada y renueva la expiración de esa
sesión, por lo que no hace falta reiniciar Django. Las sesiones activas adoptan
el nuevo tiempo al realizar su siguiente solicitud. Los cambios efectivos
quedan registrados con el usuario, la fecha y los valores anterior y nuevo.
