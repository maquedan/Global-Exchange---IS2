# CHIA — Conversación asistida para RF011

Fecha: 28 de agosto de 2026.

## Solicitud

Implementar RF011: como administrador, definir, gestionar y asignar
dinámicamente roles y permisos para controlar el acceso a las funcionalidades.

## Decisiones técnicas acordadas durante el desarrollo

- El proyecto ya autentica con Keycloak y sincroniza sus realm roles a grupos
  de Django en cada inicio de sesión. Por ello los roles no se gestionan como
  grupos locales: se administran mediante la API administrativa de Keycloak.
- Los permisos son capacidades de la aplicación y se modelan en Django para
  que puedan vincularse dinámicamente a cualquier rol del realm.
- Se incorporó una pantalla exclusiva para administradores, pruebas unitarias,
  migración y documentación de puesta en marcha.

## Resultado

RF011 queda disponible en `/administracion/roles-permisos/`. El documento
`docs/rf011-roles-permisos.md` describe el flujo operativo y de seguridad.
