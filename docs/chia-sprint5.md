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

## 2. Leyda Fleitas — RF026, Generación Automática de Facturas (GEG9-50)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

El ticket pedía explícitamente **relevar antes de programar**: leer el
documento completo de Factura Segura y los módulos del repo con los que la
historia se engancha. Estas son las consultas que salieron de ahí.

### 2.1. «¿El brief de la historia coincide con el documento de la API?»

**Lo que aprendimos.** No del todo. Cuatro diferencias, todas verificadas
contra el documento (que es la fuente de verdad):

1. **El login no está bajo `/misife00/v1/esi`.** Es
   `POST https://apitest.facturasegura.com.py/login?include_auth_token`, en
   el dominio raíz, y el token viene anidado en
   `user.authentication_token`.
2. **Las respuestas vienen anidadas dentro de `results`:** `calcular_de`
   devuelve `results[0]["DE"]` y `generar_de` devuelve `results[0]["CDC"]`,
   no el valor directo.
3. **Falta `gPaConEIni` en el brief.** El documento lo marca
   **obligatorio cuando la factura es CONTADO** (`iCondOpe=1`), que es
   nuestro caso: cobramos antes de confirmar (RF022).
4. **Al final del documento hay un hilo de soporte con bugs conocidos** de
   `dRucEm` (string de 8 caracteres, con o sin ceros a la izquierda según la
   operación) y `dNumTim` (string, no entero). No nos pega en RF026, pero sí
   le va a pegar a Fabri en RF028.

Además: `cUniMed` solo acepta `77` (UNIDAD), y Factura Segura no soporta
descuento global, anticipos, comisiones ni redondeo SEDECO: van en 0.

### 2.2. «¿Qué se factura, y por qué monto?»

**El ticket pedía proponer, no asumir** — es una decisión fiscal y no está
en el documento. Las dos opciones razonables eran facturar **solo la
comisión** (lo que Global Exchange cobra como servicio) o **el monto total
de la operación**.

**Decisión de la integrante:** el **monto total** de la operación
(`total_a_pagar` en una compra, `monto_entregado` en una venta), **gravado
al IVA 10%** (`iAfecIVA=1`, `dTasaIVA=10`, `dPropIVA=100`).

Los tres códigos quedaron como constantes en `apps/facturacion/codigos_sifen.py`
y están marcados **«a confirmar con la cátedra»**: el tratamiento fiscal real
de una casa de cambio puede ser otro, y no corresponde inventarlo.

### 2.3. «La API solo acepta PYG o USD, y nosotras operamos en seis monedas»

**Lo que aprendimos.** `cMoneOpe` solo admite `PYG` o `USD`, pero el sistema
opera también en EUR, BRL, ARS, GBP y JPY. Facturar en USD habría obligado a
mandar además `dTiCam` y a cumplir las reglas de decimales del SIFEN para
moneda extranjera.

Verificamos en el código que la conversión ya estaba resuelta: todas las
cotizaciones del sistema son **contra el guaraní** (se revisó
`apps/tasa_cambios/fixtures/tasas_demo.json`: los seis pares tienen
`moneda_destino = PYG`), así que `tasa_aplicada` —la tasa **ya congelada en
la operación**— son guaraníes por unidad. Es el mismo criterio que
`monto_para_pasarela()` en RF022.

**Decisión.** Facturar **siempre en guaraníes**, un solo camino. La cifra en
la moneda original se guarda igual en la `Factura` (`monto_origen`,
`moneda_origen`) y se muestra en el comprobante y en `dInfAdic`, el texto que
se imprime en el KuDE.

### 2.4. «El modelo `Cliente` no tiene campo para el DV del RUC»

**Lo que aprendimos.** El SIFEN pide `dRucRec` y `dDVRec` **por separado**,
pero `Cliente` (RF001) guarda un único campo `ruc` de texto libre, y
`documento` es la cédula sin dígito verificador.

**Decisión**, sin tocar el modelo de otra historia: para persona **física**
se usa la cédula (`iTipIDRec`), que no lleva DV; para **jurídica** se parte
el `ruc` por el guion (`80002247-5`). Si no tiene ese formato, la factura
queda en `ERROR` con un mensaje claro, **antes** de llamar a la API: mejor
eso que mandar un DV inventado.

### 2.5. «Si se corta la conexión, ¿se reintenta?»

**Lo que aprendimos.** La petición es **síncrona**: ante un timeout o un
corte, el servidor **pudo haber procesado el documento igual**, y sin el CDC
no hay forma de consultar qué pasó. Reenviar a ciegas duplicaría la factura.

**Decisión.** Un estado propio, `A_VERIFICAR`, que **nunca** se reintenta
solo —ni automáticamente ni con el comando `emitir_facturas_pendientes`—.
Los otros fallos (`ERROR`, `PENDIENTE`) sí son reintentables, porque ahí
sabemos que el documento no se generó.

Detalle fino que apareció programando: en la librería `requests`, el error de
JSON **hereda** de `RequestException`. Si se capturaban juntos, una respuesta
ilegible (que sí llegó y sí fue respondida) se habría tomado como corte de
comunicación y habría mandado la factura a `A_VERIFICAR` sin motivo. Se
separó el `POST` del parseo del cuerpo.

### 2.6. «¿Transacción única o dos, para no dejar huecos en la numeración?»

**Lo que aprendimos.** El SIFEN exige que `dNumDoc` sea una secuencia **sin
saltos ni repeticiones** por establecimiento y punto de expedición. La
tentación era meter todo en un `@transaction.atomic`, pero eso dejaría el
candado de la secuencia tomado durante toda la llamada HTTP: ninguna otra
operación podría facturar mientras tanto.

**Decisión.** Dos transacciones: una corta que reserva el número con
`select_for_update`, y la llamada a la API afuera. Para que no queden
huecos, el reintento **reutiliza la misma `Factura` y el mismo número** en
vez de pedir uno nuevo. Hay una prueba específica para eso
(`test_reintentar_reusa_el_mismo_numero`).

### 2.7. «Llegó la habilitación de la cátedra: ¿qué cambia?»

**Lo que aprendimos**, al recibir el correo con la cuenta ESI habilitada
(emisor 2595733 en TEST): el rango autorizado es acotado —establecimiento
`001`, punto de expedición **`003`**, facturas de **`0000489` a `0000500`**,
doce números— y el emisor tiene **dos** actividades económicas, no una.

La numeración arrancaba en `0000001` y `gActEco` aceptaba una sola
actividad: las facturas habrían sido rechazadas por el SIFEN.

**Decisión.** Dos variables nuevas, `FACTURACION_NUMERO_DESDE` y
`FACTURACION_NUMERO_HASTA`: la secuencia arranca en el primer número
autorizado, y si el rango se agota la factura queda en `ERROR` con el
mensaje «hay que pedir un rango nuevo a la cátedra», **sin llamar a la API**.
Las actividades se configuran como `codigo:descripcion` separadas por `|`,
para que cada código conserve su propia descripción.

### 2.8. «Los datos del emisor, ¿hardcodeados?»

**Decisión.** Ninguno en el código: todos salen de variables de entorno. Los
valores por defecto de `config/settings/base.py` son **claramente de
prueba** (RUC `00000000`, nombre «GLOBAL EXCHANGE (DATOS DE PRUEBA)») y el
cliente real **se niega a emitir** mientras sigan así, con un mensaje que
explica qué completar. El token va únicamente en el `.env`, nunca en el
repositorio ni en los logs: hay una prueba que verifica las dos cosas.

### 2.9. «Bug propio: al cargar los datos reales en el `.env`, se rompió una prueba»

**Lo que aprendimos.** Apenas se cargaron en el `.env` los datos que mandó la
cátedra (punto de expedición `003`, rango desde `489`, proveedor
`facturasegura`), una prueba que venía pasando empezó a fallar: esperaba la
secuencia en `001-001` y encontraba `001-003`.

La causa no era el cambio: era que **las pruebas leían el `.env`**.
`config.settings.dev` lo carga, así que la configuración de cada máquina se
filtraba a la corrida. Dos consecuencias, una molesta y una grave:

1. Cualquier compañero con otros valores en su `.env` vería fallar pruebas
   que no tienen nada que ver con lo que tocó.
2. **Con `FACTURACION_PROVEEDOR=facturasegura` en el `.env`, una prueba podía
   terminar llamando a la API de verdad** y gastando uno de los doce números
   del rango autorizado.

**Decisión.** Un fixture `autouse` que fija toda la configuración de
facturación en valores conocidos antes de cada prueba, con el proveedor
simulado y el token vacío. Las pruebas que necesitan otro valor lo
sobrescriben, porque su asignación corre después del fixture. Es la misma
idea que "una prueba no debe depender del ambiente donde corre", y acá el
costo de no cumplirla no era una prueba inestable sino una llamada real a
Hacienda.

## 2.10. Verificaciones realizadas

- **29 pruebas nuevas** para esta historia, todas sin red: el cliente de la
  API se reemplaza por dobles que cumplen la misma interfaz.
- Suite completa del proyecto: **228 pruebas aprobadas** (eran 199 antes de
  esta historia), sin regresiones en RF018, RF019, RF022, RF023 ni RF051.
- Casos cubiertos: la factura se genera al confirmar una compra y una venta;
  si la facturación falla la operación **sigue confirmada** (RNF011), tanto
  con un rechazo de la API como con una excepción inesperada; el timeout deja
  `A_VERIFICAR` y no se reenvía sola; el comando reintenta los `ERROR` pero
  no los `A_VERIFICAR`; una operación no puede tener dos facturas (ni por
  servicio ni por base); la numeración no se repite, arranca en el rango
  autorizado, se detiene al agotarlo y el reintento reusa el número; la
  conversión a guaraníes; el armado del DE (receptor físico y jurídico, ítem,
  IVA, forma de pago al contado, las dos actividades económicas, las dos
  cifras en `dInfAdic`); RUC sin DV y cliente sin correo dan error claro sin
  llamar a la API; y el token no aparece ni en los logs ni en lo que se
  guarda en la base.
- `python manage.py check` sin errores, migración `0001_initial` aplicada y
  Sphinx genera sin warnings (nueva página `facturacion`).

---
