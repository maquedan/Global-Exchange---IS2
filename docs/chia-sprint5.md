# CHIA — Conversaciones con Inteligencia Artificial

Registro del uso de IA como herramienta de apoyo durante el **Sprint 5** del
proyecto Global Exchange (Grupo 9, FP-UNA).

- **Modalidad de trabajo:** se utilizó como asistente de consulta y de
  programación. Las decisiones de diseño, cambios de código, comandos y
  verificaciones fueron realizados y validados por la integrante en el
  entorno real del proyecto.

**Cómo sumar tu parte:** copiá el formato de la sección de abajo y
completala con tus propias consultas reales a la IA (si la usaste). Si no
usaste IA para tu historia, dejalo dicho así, sin inventar contenido.

---

## 1. Leyda Fleitas — RF008, Selección de Cliente Activo (GEG9-18)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

### 1.1. «¿Dónde se decide hoy sobre qué cliente se opera?»

**Lo que aprendimos**, antes de escribir una línea (el ticket pedía
relevar primero): había **dos mecanismos distintos** y ninguno era un
"cliente activo".

1. El usuario lo elegía a mano, en un desplegable, en **cada** operación:
   `CompraDivisaForm`, `VentaDivisaForm` y `CuentaPagoForm`.
2. Diez lugares más con `cliente__asociaciones_usuarios__usuario=request.user`,
   que no eligen cliente: solo verifican que la operación sea del usuario.

Y el historial (RF030) no filtraba por ningún cliente: mezclaba las
operaciones de **todos** los clientes asociados.

**Decisión.** Reemplazar el mecanismo 1 por el cliente activo (el
desplegable desaparece) y dejar el 2 como está: son chequeos de seguridad
que siguen siendo correctos y tocarlos era arriesgar RF051 sin ganar nada.

### 1.2. «¿Middleware para toda la app, o solo donde se opera?»

**Lo que aprendimos.** El ERS dice "antes de realizar acciones", y la
tentación era redirigir en **toda** la aplicación salvo unas pocas
excepciones. Pero un administrador o analista también puede estar asociado
a clientes: con esa regla, al entrar a administrar monedas o tasas se le
pediría elegir un cliente, que no tiene nada que ver con lo que está
haciendo.

**Decisión.** Redirigir solo en las rutas que **operan en nombre de un
cliente** (`/conversiones/`, `/cuentas/`, `/pagos/`). El resto —consultas,
administración, login— funciona igual sin elegir. Sigue cumpliendo "antes
de realizar acciones" sin molestar a quien no está operando.

### 1.3. «¿Y el usuario que no tiene ningún cliente asociado?»

**Lo que aprendimos.** Mandarlo a la pantalla de selección sería dejarlo en
un callejón sin salida: no hay nada que elegir, y la pantalla lo
redirigiría otra vez, en loop.

**Decisión.** El middleware no lo manda a elegir, y un decorador chico
(`requiere_cliente_activo`) corta la operación con un mensaje claro. El
ticket aclara que limitar a estos usuarios es RF010 (GEG9-20), así que
queda el punto de extensión listo: `request.cliente_activo is None`.

### 1.4. «¿Cómo valido que el cliente activo siga siendo válido?»

**Lo que aprendimos.** Guardar el id en la sesión no alcanza: entre un
request y otro pueden dar de baja al cliente (RF003) o desvincularlo del
usuario, y la sesión seguiría apuntando a algo que ya no corresponde.

**Decisión.** Revalidar en **cada** request contra la base, filtrando
siempre por "asociado a este usuario y activo". Si el guardado ya no pasa
ese filtro, se limpia la elección y se vuelve a pedir. El id del formulario
tampoco se cree nunca: se busca entre los clientes del propio usuario antes
de guardarlo.

### 1.5. «Bug propio: al sacar `cliente` del formulario, dejó de detectarse la cuenta duplicada»

**Lo que aprendimos.** `CuentaPago` tiene una restricción
`cuenta_pago_unica_por_cliente` sobre (cliente, entidad, numero_cuenta).
Django **excluye de la validación los campos que no están en el
formulario**, así que al sacar `cliente` de `fields` la duplicada dejó de
detectarse a nivel formulario y explotaba recién contra la base, con un
`IntegrityError` crudo en pantalla. Lo detectó una prueba ya existente de
RF020 — buen argumento para no borrar pruebas viejas cuando "molestan".

**Decisión.** Sobrescribir `_get_validation_exclusions()` en el formulario
para que `cliente` **no** quede excluido, y asignar `self.instance.cliente`
en el `__init__`. Así la validación vuelve a correr completa y el usuario
ve el mensaje de siempre en vez de un error 500.

## 1.6. Verificaciones realizadas

- Suite completa del proyecto ejecutada tras el cambio: **199 pruebas
  aprobadas** (eran 189 antes de esta historia), sin romper RF018, RF019,
  RF020, RF030 ni RF051.
- Tres pruebas existentes se adaptaron al comportamiento nuevo (ya no hay
  desplegable de cliente que pueda dar error): las dos de "cliente ajeno"
  ahora verifican algo **más fuerte** —que el id ajeno mandado en el POST
  simplemente se ignora y la operación queda a nombre del cliente activo—,
  y la de cuenta duplicada destapó el bug de 1.5.
- Casos nuevos cubiertos: selección automática con un solo cliente;
  redirección a elegir con dos o más; rechazo de un cliente ajeno; cliente
  activo dado de baja (pasa al que queda) y desvinculado (se limpia y se
  vuelve a pedir); usuario sin clientes (no rompe, `cliente_activo` es
  `None`, no puede operar); la compra se registra a nombre del cliente
  activo; y las pantallas de consulta no piden elegir.
- `python manage.py check` sin errores y Sphinx genera sin warnings.

---
