# Flujo de trabajo Git — Global Exchange (Git Flow)

Este proyecto usa la metodología **Git Flow** para la gestión de versiones y ramas.
Referencia: https://www.atlassian.com/es/git/tutorials/comparing-workflows/gitflow-workflow

## Ramas

| Rama | Rol |
|------|-----|
| `main` | Código estable y entregado. De aquí se generan los **tags de release**. No se trabaja directamente sobre ella. |
| `develop` | Rama de integración. Aquí se unen las funcionalidades terminadas. |
| `feature/IS2-<id>` | Una rama por historia de usuario. Nace de `develop` y se integra de vuelta a `develop`. |

> **Nomenclatura de las ramas de funcionalidad:** `feature/IS2-<id_historia>`
> - `IS2`: acrónimo del proyecto en Jira.
> - `<id_historia>`: ID de la historia de usuario (ej. `IS2-11` = Registro de Clientes).
>
> Ejemplo: `feature/IS2-11`

## Convención de mensajes de commit

Formato: `<tipo>(IS2-<id>): descripción breve`

- `feat`: nueva funcionalidad
- `fix`: corrección de error
- `docs`: documentación
- `test`: pruebas
- `refactor`: refactorización
- `chore`: tareas de mantenimiento

Ejemplo: `feat(IS2-11): registro de clientes con segmentación`

## Flujo de una historia de usuario

```bash
# 1. Partir de develop actualizado
git checkout develop
git pull origin develop

# 2. Crear la rama de la historia
git checkout -b feature/IS2-11

# 3. Trabajar y commitear
git add .
git commit -m "feat(IS2-11): registro de clientes"
git push -u origin feature/IS2-11

# 4. Integrar a develop y cerrar la rama
git checkout develop
git merge --no-ff feature/IS2-11
git push origin develop
git branch -d feature/IS2-11
git push origin --delete feature/IS2-11
```

El `--no-ff` (no fast-forward) conserva el registro del merge de la feature en el historial.

## Cierre de Sprint — Tag de Release

Al finalizar cada Sprint se genera un **Tag de Release sobre `main`**, marcando el estado del código entregado.

```bash
git checkout main
git merge --no-ff develop
git push origin main

git tag -a v1.0.0 -m "Release Sprint 1 - Usuarios y Clientes"
git push origin v1.0.0
```

Convención de versiones (SemVer): `vMAYOR.MENOR.PARCHE` (ej. `v1.0.0` para el cierre del Sprint 1).

## Resumen del ciclo

1. Cada historia → rama `feature/IS2-<id>` creada desde `develop`.
2. Historia terminada → merge a `develop` + cierre de la rama.
3. Fin del Sprint → `develop` a `main` + **tag de release**.
