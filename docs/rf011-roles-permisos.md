# RF011 — Asignación de Roles y Permisos

## Objetivo

Permitir que el rol **administrador** defina roles, gestione permisos de las
funcionalidades y asigne roles a usuarios sin modificar el código fuente.

## Diseño

| Elemento | Fuente de verdad | Motivo |
|---|---|---|
| Rol y asignación usuario-rol | Keycloak (realm roles) | Se propagan al token OIDC y sobreviven al inicio de sesión. |
| Permiso funcional | Django (`PermisoSistema`) | Representa una capacidad propia de Global Exchange. |
| Vínculo rol-permiso | Django (`PermisoRol`) | Permite cambiar la autorización funcional en tiempo de ejecución. |

El adaptador `apps/usuarios/keycloak_admin.py` usa un cliente de servicio con
permisos mínimos de administración del realm. El secreto se guarda solo en
`.env`; `scripts/sincronizar_secret.py` lo obtiene al preparar el ambiente. Si
el realm ya existía antes de RF011, ese script crea el cliente técnico y le
asigna esos permisos automáticamente.

## Uso

1. Ejecutar `python3 scripts/sincronizar_secret.py` y reiniciar el contenedor
   `web` si el realm se importó por primera vez.
2. Iniciar sesión como `admin.demo` y abrir **Roles y permisos** en el menú.
3. Crear un rol o permiso, marcar los permisos que corresponden a cada rol y
   guardar.
4. Elegir un usuario, marcar sus roles y guardar la asignación.
5. El usuario debe cerrar e iniciar sesión para que Django sincronice sus
   grupos desde el nuevo token de Keycloak.

Para proteger una funcionalidad futura por permiso, usar
`tiene_permiso(usuario, "codigo_del_permiso")` desde
`apps.usuarios.menu`. Así la decisión responde a la configuración de RF011 y
no queda fijada a un nombre de rol.

## Seguridad

- El endpoint `/administracion/roles-permisos/` exige sesión y rol
  `administrador`.
- El cliente técnico de Keycloak no se usa para autenticar personas; solo para
  operaciones administrativas desde el servidor Django.
- Nunca incluir `KEYCLOAK_ADMIN_CLIENT_SECRET` en Git.

## Pruebas

`apps/usuarios/tests/test_roles_permisos.py` cubre la restricción de acceso,
la creación de roles, la asignación a usuarios y la resolución de permisos.
