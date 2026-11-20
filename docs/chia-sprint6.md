# CHIA — Conversaciones con Inteligencia Artificial

Registro del uso de IA como herramienta de apoyo durante el **Sprint 6** del
proyecto Global Exchange (Grupo 9, FP-UNA).

- **Modalidad de trabajo:** se utilizó como apoyo para relevar el código,
  implementar cambios puntuales y ejecutar pruebas en el entorno local del
  proyecto. Se documentan las decisiones y verificaciones de esta conversación;
  no se incluyen secretos ni credenciales.

## 1. Leyda Fleitas — RF025, Conciliación Manual (GEG9-75)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

El ticket pedía reportar el diseño y las decisiones abiertas antes de
implementar.

### 1.1. «El ticket pide pasar por `confirmar_pago_compra`, pero un administrador no puede»

**Lo que aprendimos.** `confirmar_pago_compra` filtra así:

```python
.filter(pk=pk,
        cliente__asociaciones_usuarios__usuario=usuario,
        cliente__activo=True)
```

Ese filtro es el control de dueño que agregaron RF008 y RF010. Un
administrador **no está asociado** al cliente, así que el filtro devuelve
`None` y el servicio responde "la operación no existe o no te pertenece".
Pasar por ahí tal cual era imposible.

**Decisión.** Extraer el núcleo a `_confirmar_compra_pendiente(compra, *,
usuario, motivo)` y dejar dos puertas de entrada que solo se diferencian en
el control de acceso: `confirmar_pago_compra` (dueño) y `conciliar_compra`
(rol `administrador`). Así la revalidación de tasa de RF051, la trazabilidad
de RF023 y la facturación de RF026 son idénticas por los dos caminos, que es
lo que el ticket pedía con "no dupliques lógica", y el historial registra al
administrador real y no al cliente.

Había **precedente en el repo**: `anular_venta` (RF059, de un compañero) ya
valida el grupo `administrador` dentro del servicio y busca sin filtro de
dueño. Se siguió esa misma forma.

### 1.2. «La función no serviría: la ventana es de 15 minutos»

**Lo que aprendimos**, y fue el hallazgo que cambió el alcance:
`MINUTOS_EXPIRACION_PENDIENTE = 15`, y `confirmar_pago_compra` llama a
`expirar_compra_si_corresponde` **antes** de confirmar. Verificar una
transferencia bancaria lleva horas o días: para cuando el administrador
entrara a conciliar, **toda** compra pendiente ya se habría cancelado sola.
La pantalla habría estado siempre vacía.

**Decisión de la integrante** (entre tres opciones planteadas): un campo
nuevo `espera_transferencia` en `CompraDivisa`. El cliente lo marca al elegir
cómo pagar, y esa compra deja de vencerse.

La protección de RF051 **no se pierde**: al conciliar se revalida la
cotización igual, y si cambió la operación se cancela en vez de confirmarse.
Lo que se suspende es el vencimiento por tiempo, no el control de tasa.

### 1.3. «¿Alcanza con el cambio de estado, o se registra un `Pago`?»

**Decisión de la integrante:** registrar también un `Pago` con proveedor
`"manual"` y estado `APROBADO`. `Pago.proveedor` es texto libre, así que no
hizo falta migrar nada, y el comprobante ya muestra un bloque "Pago" leyendo
`compra.pagos.first`: la conciliación aparece ahí **sin tocar esa
plantilla**. La referencia bancaria va en `id_externo` y quién concilió en
`respuesta_cruda`.

Se registra el importe **tal como lo transfirió el cliente** (el total en la
moneda de la operación), no el convertido para la pasarela: acá no hubo
pasarela que convirtiera nada.

### 1.4. «Bug propio: lanzar una excepción revertía la cancelación»

**Lo que aprendimos.** `conciliar_compra` está decorado con
`@transaction.atomic`. Cuando RF051 detectaba que la cotización había
cambiado, el servicio cancelaba la compra y después **lanzaba** una excepción
para avisarle al administrador. Resultado: la transacción revertía la
cancelación que se acababa de registrar, y la compra quedaba pendiente como
si nada hubiera pasado.

Lo destapó una prueba que esperaba `CANCELADA` y encontró `PENDIENTE`.

**Decisión.** El servicio **devuelve** la compra en vez de lanzar, y la vista
mira el estado para mostrar el mensaje. Así la cancelación persiste, igual
que en el pago normal. Queda documentado en el docstring, porque es un
contrato fácil de romper: *no alcanza con que no haya excepción, hay que
mirar el estado*.

### 1.5. «Incidente: una prueba llamó a la API real de Factura Segura»

**Lo que aprendimos.** Al correr las pruebas nuevas, una de ellas emitió
contra Factura Segura **de verdad**. La causa es la ya conocida de la sección
2.9: `config.settings.dev` lee el `.env`, que en esta máquina tiene
`FACTURACION_PROVEEDOR=facturasegura`. Las pruebas de `apps/facturacion` se
protegían con un fixture propio, pero esa protección **no alcanzaba a un
archivo de pruebas de otra app**.

No se perdió ningún número: la API rechazó el intento con `NUMDOC_APROBADO`
—el número ya estaba aprobado— y la secuencia real quedó intacta. Fue suerte,
no diseño.

**Decisión.** Mover la protección a un **`conftest.py` en la raíz** del
proyecto, con fixtures `autouse` que fuerzan el proveedor simulado de
facturación **y** de pagos en todas las pruebas. Ahora ninguna prueba del
proyecto puede salir a la red, la escriba quien la escriba y esté donde esté.
La lección de 2.9 estaba bien aprendida pero mal ubicada: una salvaguarda que
vive en el archivo que ya se acordó de ponerla no protege de los olvidos.

### 1.6. Hallazgos del ambiente (no son de esta historia, pero se verificaron)

- El certificado TLS de Factura Segura, que entre el 28/10 y mediados de
  noviembre fue emitido por una CA interna de un FortiGate y rompía toda
  llamada, **está corregido**: ahora lo emite Amazon y la conexión valida.
- Con la API otra vez disponible se consultó `get_estado_sifen` de las tres
  facturas emitidas: las **tres figuran `0260 - Aprobado`**, incluida la de
  una compra. Es decir, la emisión automática de RF026 produce documentos
  fiscalmente válidos, y los datos de prueba del emisor no impidieron la
  aprobación: Factura Segura valida la identidad contra el RUC y el timbrado
  registrados en la cuenta ESI, no contra el nombre y la dirección enviados.

## 1.7. Verificaciones realizadas

- **16 pruebas nuevas.** Suite completa: **328 aprobadas** (eran 312), sin
  regresiones en las historias de los compañeros (RF028, RF029, RF053, RF055,
  RF056, RF059) ni en las propias.
- Casos cubiertos: conciliar deja la compra confirmada y con factura
  generada; queda registrado quién concilió y con qué referencia; se crea el
  `Pago` manual con la referencia y el importe correctos; no se puede
  conciliar una cancelada; conciliar dos veces no duplica pago, factura ni
  cambio de estado; la referencia es obligatoria; si la cotización cambió se
  cancela y **no** se registra pago; la compra por transferencia no se vence
  ni a los dos días mientras que una normal sí; la lista solo trae las que
  esperan transferencia; el servicio y las vistas rechazan a quien no es
  administrador (GET y POST); y un fallo de la facturación no deshace la
  conciliación (RNF011).
- `python manage.py check` sin errores, migración `conversiones.0011`
  aplicada y Sphinx genera **sin warnings** — de paso se repuso
  `docs/sphinx/notificaciones.rst`, que el `index` referenciaba y no existía
  en el repositorio.

---

## 2. Leyda Fleitas — RF012, Recuperación de Acceso (GEG9-22)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

El ticket sospechaba que la recuperación ya funcionaba y que lo que faltaba
era comprobarlo. Era casi cierto, pero el relevamiento destapó otra cosa.

### 2.1. «No contestes de memoria: probá el flujo de verdad»

**Lo que aprendimos.** La pregunta del ticket —si Keycloak manda el enlace
cuando el correo **no** está verificado— se podía responder de memoria y
equivocarse. Se probó pidiendo la recuperación para tres usuarios distintos y
mirando qué correos llegaban realmente:

| Usuario | Mensaje en pantalla | ¿Llegó el correo? |
|---|---|---|
| `cliente.demo` (verificado) | *"En breve deberías recibir…"* | **Sí** |
| `sinverificar.demo` (sin verificar) | *"En breve deberías recibir…"* | **Sí** |
| `noexiste@ejemplo.com` | *"En breve deberías recibir…"* | No |

Dos conclusiones: **Keycloak manda el enlace aunque el correo no esté
verificado**, y el mensaje es **idéntico en los tres casos**, así que no se
puede averiguar qué correos están registrados. El punto 3 del ticket ya se
cumplía sin tocar nada.

### 2.2. «El mensaje genérico no prueba que se haya mandado el correo»

**Lo que aprendimos**, y casi lleva a una conclusión falsa: en el primer
intento los tres casos mostraron *"You should receive an email shortly"* y
**Mailpit estaba vacío**. La tentación era concluir "no manda nada".

Pero ese mensaje Keycloak lo muestra igual aunque no mande nada —es
justamente así como evita revelar si el usuario existe—, o sea que **no
prueba nada**. Tampoco los logs: los eventos exitosos no se registran por
defecto, solo los de error.

Lo que sí probó algo fue mandarle un correo a Mailpit desde Django: llegó al
instante. Mailpit funcionaba; el que no le hablaba era Keycloak.

### 2.3. «El archivo del realm y el Keycloak que corre no coincidían»

**Lo que aprendimos**, y es el hallazgo de fondo:

```
keycloak/realm-global-exchange.json  ->  smtpServer: mailpit:1025
Keycloak en ejecución                ->  smtpServer: smtp.gmail.com
```

El realm **se importa solo en el primer arranque** del contenedor. Después
alguien corrió `scripts/configurar_smtp.py`, que toma `EMAIL_HOST` del `.env`
y lo aplica al servidor. Desde ese momento el archivo versionado y el
servidor cuentan historias distintas, y nada avisa.

Consecuencia práctica: los correos de recuperación de los usuarios demo
—direcciones `@globalexchange.local`— salían hacia Gmail, que no puede
entregarlos a un dominio inexistente. Se perdían en silencio.

**Decisión.** Volver el Keycloak local a Mailpit para probar, y documentar en
`docs/keycloak.md` tanto la desincronización como el comando para comparar
archivo contra servidor. Es el mismo tipo de problema que el `.env`: estado
que vive fuera de git y que nadie recuerda.

### 2.4. «¿Qué se puede arreglar con configuración y qué no?»

**Lo que aprendimos.** El ERS pide que el enlace vaya "al correo verificado",
pero Keycloak no tiene ninguna opción para condicionar el envío a eso.
Lograrlo exigiría un autenticador propio, que es justo el tipo de código que
RNF003 evita.

**Decisión.** No escribir ese código. Lo que protege la cuenta es
`verifyEmail: true`, que ya estaba: mientras el correo no se verifique,
Keycloak exige verificarlo para poder usar la cuenta, así que restablecer la
contraseña por sí solo no alcanza para entrar.

Queda anotado como **no verificado punta a punta**: es lo que indica la
configuración, pero no se probó ese caso completo, y en la documentación está
dicho así y no como un hecho.

### 2.5. «Lo que faltaba versionar»

**Lo que aprendimos.** Tres cosas dependían de valores por defecto de
Keycloak y no estaban en el archivo:

- **El idioma.** `internationalizationEnabled: false`: pantallas y correos
  salían en inglés.
- **La vida del enlace.** `actionTokenGeneratedByUserLifespan` no estaba, así
  que valía el default de 5 minutos por casualidad, no por decisión.
- **El uso único.** Se comprobó completando el cambio de contraseña y
  reintentando el mismo enlace: *"Action expired. Please continue with login
  now."* Funciona, y es comportamiento propio de Keycloak.

**Decisión de la integrante:** dejar los **5 minutos**, pero **fijados en el
archivo**, no heredados. Más el idioma español. Siete líneas de diff.

## 2.6. Verificaciones realizadas

- **7 pruebas nuevas** que leen el realm versionado (Keycloak no se puede
  levantar dentro de pytest): recuperación habilitada, `verifyEmail`, SMTP
  definido, **sin credenciales en el archivo**, vencimiento fijado, idioma
  español y que los usuarios demo tengan correo.
- Suite completa: **343 aprobadas** (eran 336).
- Flujo recorrido a mano de punta a punta: pedido → correo en Mailpit
  (*"Reiniciar contraseña"*) → enlace → contraseña nueva → el mismo enlace ya
  no sirve.
- Tras aplicar el idioma, el mensaje pasó a *"En breve deberías recibir un
  mensaje con más instrucciones"* y el asunto a *"Reiniciar contraseña"*.
- `sphinx-build` sin warnings.

---

## 3. Leyda Fleitas — RF009, Conmutación de Cliente en Sesión (GEG9-19)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

El ticket anticipaba que la historia ya estaba casi hecha por RF008 y pedía
relevar antes de tocar nada. Era cierto en lo funcional, pero el relevamiento
destapó un agujero de seguridad.

### 3.1. «Bug propio: redirección abierta en el parámetro `siguiente`»

**Lo que aprendimos.** La vista de selección volvía a donde estabas con:

```python
siguiente = request.POST.get("siguiente") or request.GET.get("siguiente")
...
return redirect(siguiente or "usuarios:panel")
```

Ese valor **lo controla quien arma el enlace** y no se validaba. Se comprobó:

```
POST /elegir-cliente/  siguiente=https://sitio-malicioso.example.com/phishing
302 → https://sitio-malicioso.example.com/phishing
```

Es una **redirección abierta**. Sirve para engañar: alguien manda un enlace
que empieza con el dominio real de la aplicación, la víctima elige su cliente
con toda normalidad y termina en una página ajena que imita la nuestra y le
pide la contraseña. El enlace que compartió era legítimo.

Lo escribí yo en RF008 y pasó desapercibido porque **funcionaba bien**: el
caso normal —volver a `/conversiones/comprar/`— anda igual con o sin
validación. El error solo aparece si alguien busca abusarlo.

**Decisión.** Validar con `url_has_allowed_host_and_scheme` de Django, que
es la función que el propio framework usa para el `next` del login, y exigir
además que la ruta empiece con `/` para no dejar pasar algo como
`javascript:`. Ante cualquier duda, al panel.

La prueba es parametrizada con cuatro formas distintas del ataque: URL
absoluta, `//dominio` (que el navegador interpreta como externa), otro
dominio por `http` y `javascript:`.

### 3.2. «Cambiar de cliente dejaba operable lo del cliente anterior»

**Lo que aprendimos**, y no lo esperaba: estando asociada a dos clientes, se
podía elegir el cliente B y **confirmar igual una compra pendiente del
cliente A**. Lo destapó una prueba escrita justamente para descartarlo.

No es un robo de datos —el usuario está asociado a los dos clientes—, pero
contradice lo que RF008 le promete: *"todas las operaciones que hagas se van
a registrar en nombre del que elijas acá"*. Si lo que elegís en la barra no
delimita sobre qué podés actuar, el selector es decorativo.

La causa: los servicios filtran por *"alguno de los clientes del usuario"*,
que es el control de dueño correcto, pero ninguna capa miraba el cliente
**activo**.

**Decisión.** Un helper `_es_del_cliente_activo()` en las vistas, aplicado a
confirmar y cancelar compra y a cancelar venta. Va en la vista y no en el
servicio a propósito: el cliente activo es un concepto de **sesión**, y los
servicios no conocen la sesión ni deberían.

**Lo que NO se tocó:** `confirmar_venta_view`, que un compañero reescribió
para el flujo del cajero (RF058). El cajero opera sin cliente activo, así que
aplicarle el mismo filtro habría roto su historia. Queda dicho en el
docstring del helper.

### 3.3. «Una prueba que escribí mal, y lo que enseñó»

Escribí una prueba esperando que al desactivar el cliente activo el sistema
volviera a pedir elegir. Falló: el sistema había pasado solo al otro cliente.

**La prueba estaba mal, no el código.** RF008 define que con un solo cliente
disponible no se pregunta nada. Se corrigió para verificar el comportamiento
real, y se agregó una segunda que cubre el caso que yo creía estar probando:
desactivar **todos** los clientes, ahí sí se vuelve a pedir.

### 3.4. Lo que ya estaba y no se tocó

El ticket pedía no reescribir lo de RF008, y efectivamente no hizo falta:
el enlace **Cambiar** en la barra, `puede_cambiar_cliente` (que se calcula
con `cantidad_clientes > 1`, así que con uno solo no se ofrece), la vista de
selección reutilizada, y la revalidación contra la base en cada request.

Sobre el "selector" que menciona el ERS: hoy es un enlace a una pantalla.
**Decisión de la integrante:** dejarlo así. Cumple la intención —cambiar de
cliente sin cerrar sesión, en dos clics— y la pantalla muestra el documento y
la categoría de cada cliente, que un desplegable escondería.

## 3.5. Verificaciones realizadas

- **13 pruebas nuevas**, ninguna de las cuales existía: las 10 de
  `test_cliente_activo.py` cubren RF008 (la primera elección), no el cambio.
- Suite completa: **356 aprobadas** (eran 343), sin regresiones.
- Casos cubiertos: el cambio mantiene la **misma sesión**; el encabezado
  muestra el cliente nuevo y ya no el anterior; el enlace sólo aparece con más
  de un cliente; se vuelve a la pantalla de origen; **cuatro formas de
  redirección externa quedan rechazadas**, por POST y por query string; no se
  puede cambiar a un cliente ajeno; una operación pendiente del cliente
  anterior deja de ser operable; al desactivar un cliente se pasa al que
  queda, y al desactivarlos todos se vuelve a pedir.
- `manage.py check` sin errores y Sphinx genera sin warnings.

---

## 4. Leyda Fleitas — RF016, Gráficos de Evolución de Tasas (GEG9-68)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

El ticket anticipaba que la historia ya estaba hecha y pedía relevar contra
seis criterios antes de tocar nada. Lo estaba: el panel de cotizaciones ya
tenía el gráfico SVG con dos líneas, el selector de período y el tooltip.

### 4.1. «Revisar contra los criterios, uno por uno»

| Criterio | Estado |
|---|---|
| Gráfico de evolución por par | ✅ SVG propio, líneas de compra y venta |
| Selector de período | ✅ 7D / 1M / 3M / Todo, filtra sin recargar |
| Muestra compra y venta | ✅ ambas líneas y ambas filas de estadísticas |
| Historial real (`TasaCambio`) | ✅ `_historial_del_par` |
| Visible para todos los roles | ✅ solo `@login_required`, sin control de rol |
| Par sin historial / una sola tasa | ✅ estado vacío con sugerencias; con una tasa no dibuja el gráfico pero muestra las estadísticas |

El acceso del usuario **sin cliente asociado** ya estaba cubierto por dos
pruebas propias de RF008 y RF010, que verifican que `/tasas/` responde 200 sin
ningún cliente. No se duplicó.

**Decisión: no se tocó el gráfico ni se agregó ninguna librería**, que es lo
que el ticket pedía explícitamente.

### 4.2. «El selector decía "7 días" y mostraba datos de hace 74»

**Lo que aprendimos** al mirar el criterio 3 —cómo se ve con los datos de
demo— y que no se veía leyendo solo el código: **todas las tasas del fixture
tienen entre 74 y 101 días**.

| Par | Puntos | En 7D | En 1M | En 3M |
|---|---|---|---|---|
| USD/PYG | 4 | **0** | **0** | 4 |
| EUR/PYG | 4 | **0** | **0** | 3 |

Al tocar **7D** no queda ningún punto en el rango. El código tiene un guard
deliberado:

```js
if (puntosFiltrados.length < 2) puntosFiltrados = puntosCompletos.slice(-2);
```

O sea que el botón queda marcado como activo y el gráfico dibuja **los dos
registros más recientes, de hace 74 días**, sin decir nada. No se rompe:
**informa mal**, que es peor, porque no hay forma de notarlo.

Conviene separar las dos cosas: **el código está bien** —el filtro funciona y
el fallback evita un gráfico vacío— y **lo que faltaba era avisar**.

**Decisión.** Un aviso que aparece solo cuando el rango elegido se quedó sin
datos: *"No hay registros en los últimos 7 días. Se muestran los 2 más
recientes."* Ocho líneas de JavaScript, sin librerías nuevas y sin tocar el
dibujo. Se distingue además el caso de **un solo** registro en el rango, que
tampoco alcanza para trazar una línea.

### 4.3. «Bug propio en las pruebas: una sola tasa activa por par»

Las primeras pruebas nuevas fallaron con `IntegrityError`: el modelo tiene una
restricción `tasa_cambio_unica_activa_por_par`, y el helper de pruebas crea
las tasas con `activo=True` por defecto. Creé varias activas del mismo par.

**La restricción estaba bien; mis pruebas estaban mal.** Se corrigieron para
crear el historial con `activo=False` y dejar activa solo la última, que es lo
que pasa en la realidad: una tasa vigente y las anteriores como histórico.

## 4.4. Verificaciones realizadas

- **8 pruebas nuevas**, que llevan el archivo de 12 a **20**. El selector de
  período no tenía ninguna, y es la mitad del segundo criterio.
- Suite completa sin regresiones.
- Casos cubiertos: los cuatro rangos están en la página; el filtro es del lado
  del navegador (el historial completo viaja en `historial_json`, así que
  ningún botón recarga); cada punto lleva fecha, compra y venta, ordenados de
  más viejo a más nuevo; el JSON embebido es válido; el aviso de rango vacío
  está presente; las dos líneas del gráfico son compra y venta; el usuario sin
  cliente ve el panel; y el servidor no recorta el historial.
- `sphinx-build` sin warnings.

---

## 5. Leyda Fleitas — RF034, Alertas de Operación (GEG9-76)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

El ticket sospechaba que el enganche era único y pedía confirmarlo leyendo el
código antes de implementar.

### 5.1. «¿De verdad hay un solo punto donde enganchar?»

**Lo que aprendimos.** Sí: `registrar_cambio_estado` se llama en **once
lugares**, todos dentro de `apps/conversiones/services.py` — iniciar compra y
venta, vencimiento, cancelación por cambio de cotización, confirmación,
cancelación por el cliente, anulación, y los flujos de terminal y
conciliación manual, que reutilizan los mismos servicios.

Enganchando **adentro** de esa función quedan cubiertas las once sin tocar
ninguna, que es lo que RF023 había preparado sin saberlo.

**Pero dos de esas once no deben avisar:** las que llaman con
`estado_anterior=""`, que son el nacimiento de la operación. Avisarle a
alguien "tu compra pasó de nada a pendiente" justo después de que la creó él
mismo es ruido, no información.

### 5.2. «La terminal rompía el enfoque obvio»

**Lo que aprendimos**, y es el hallazgo que cambió el diseño: lo natural era
avisarle al `usuario` que recibe `registrar_cambio_estado`. En el flujo de
autoservicio (RF055) **ese usuario es la terminal**, no una persona: el
cliente se identifica por documento o RUC.

Tomando el destinatario de ahí, las notificaciones de las operaciones hechas
en la terminal le habrían llegado **a la máquina**.

**Decisión.** Los destinatarios salen del **cliente de la operación**, no de
quien la disparó: `AsociacionUsuarioCliente.objects.filter(cliente=...)`.
Y puede no haber ninguno —alguien que opera en la terminal sin cuenta—, lo
cual **no es un error**: simplemente no hay a quién avisarle, y eso no puede
romper la operación.

### 5.3. «Los destinatarios no se resuelven como en RF033»

**Lo que aprendimos.** `_destinatarios` de RF033 devuelve **todos** los
usuarios con rol cliente, porque un cambio de tasa le interesa a cualquiera.
Reutilizarlo acá habría sido un problema serio: el ticket exige que nadie
reciba avisos de operaciones ajenas.

**Decisión.** Una función aparte, `_usuarios_del_cliente`, acotada al cliente
de esa operación. Se reutiliza la app, el modelo y la pantalla de RF033, pero
no esa función: hacen cosas distintas aunque se parezcan.

### 5.4. «Los duplicados: comprobar o hacerlos imposibles»

El ticket pedía que registrar dos veces el mismo cambio no genere dos avisos.
Se podía comparar el texto del mensaje, pero eso es frágil: cambia una coma y
deja de detectarlos.

**Decisión de la integrante:** una FK de `Notificacion` a `CambioEstado`, con
una restricción de unicidad sobre (usuario, cambio de estado). El duplicado
pasa a ser **imposible por construcción**, no algo que haya que acordarse de
comprobar. De paso, el aviso queda ligado a la transición concreta, que le
sirve a RF053.

También decidió **tres tipos** (`OPERACION_CONFIRMADA`, `CANCELADA`,
`ANULADA`) en vez de uno genérico, para poder distinguirlos en la lista sin
otra migración. Esa decisión se aprovechó enseguida: ver 8.6.

### 5.5. «Que avisar no pueda romper nada»

Mismo criterio que la facturación (RF026): `transaction.on_commit` para no
avisar de algo que luego se revierta, y un `except` amplio alrededor. El
aviso es un efecto secundario; la transición es el hecho. Hay una prueba que
tumba el servicio de notificaciones a propósito y verifica que la compra
igual queda confirmada.

### 5.6. «Color por tipo sin que quede chocante»

**Lo que aprendimos** al colorear la lista: el borde izquierdo **ya estaba
usado** para indicar leída o no leída. Agregar color por tipo encima habría
dado dos significados al mismo elemento.

**Decisión.** El borde pasa a indicar el **tipo** —que es el dato que cambia
entre una fila y otra— y lo leído se sigue viendo por la opacidad y el badge
"Nueva". Se agregó además una **etiqueta de texto** con el tipo: si el color
fuera el único dato, quien no distingue verde de ámbar se quedaría sin esa
información.

Cancelada va en **ámbar y no en rojo**: merece atención, pero no es un error
—muchas veces la canceló el propio cliente— y el rojo diría "algo salió mal".
Queda anotado que la línea de tiempo del comprobante usa rojo para ese mismo
estado desde RF023: son dos criterios distintos conviviendo, y conviene
unificarlos en algún momento.

### 5.7. Un error propio en las pruebas

Una prueba fallaba con `TypeError: 'Cliente' object is not callable`: al
desempaquetar el fixture con `usuario, _cliente = duenio`, la variable
`_cliente` tapaba a la función `_cliente()` que crea clientes. Se renombró la
variable.

## 5.8. Verificaciones realizadas

- **12 pruebas nuevas**, que llevan `apps/notificaciones` de 10 a **22**.
- Suite completa: **377 aprobadas** (eran 364), sin regresiones.
- Casos cubiertos: cada transición relevante (confirmar, cancelar, vencer,
  anular) genera el aviso del tipo correcto y con el motivo; **crear la
  operación no avisa**; un usuario de otro cliente no recibe nada; todos los
  usuarios del cliente sí; un cliente **sin usuarios** no rompe; un fallo al
  avisar **no deshace** la confirmación; registrar el mismo cambio dos veces
  no duplica; el aviso aparece en la lista y en el contador del menú; se
  puede marcar como leída; y el formateo de montos tiene un único punto.
- `manage.py check` sin errores, migración `notificaciones.0002` aplicada y
  Sphinx genera sin warnings.

---

## 6. Ryuto Maehara - RF013, Control de sesiones por inactividad y cierre voluntario

### 6.1. «¿Por qué `DJANGO_SESSION_IDLE_TIMEOUT=30` no cerraba la sesión?»

**Lo que aprendimos.** El contenedor sí había cargado `SESSION_COOKIE_AGE=30`
y `SESSION_SAVE_EVERY_REQUEST=True`. La caducidad del lado servidor impedía
usar una sesión vencida en la siguiente solicitud, pero no podía actualizar
una página que seguía abierta en el navegador. Hacía falta un temporizador en
la interfaz para que el vencimiento tuviera un efecto visible.

**Decisión.** Mantener la expiración de Django como control del lado servidor
y agregar un temporizador para las páginas autenticadas. El plazo se expone
desde la sesión al template y se usa para enviar un `POST` de cierre, con
protección CSRF.

### 6.2. «¿Por qué al volver a cargar la página seguía dentro de la cuenta?»

**Lo que aprendimos.** El cierre estándar de `mozilla-django-oidc` cierra la
sesión de Keycloak solo si la solicitud todavía identifica al usuario como
autenticado en Django. Cuando el temporizador enviaba el cierre en el mismo
instante en que caducaba Django, Keycloak no recibía el `id_token_hint`; su
sesión SSO seguía activa y el siguiente login autenticaba al usuario de nuevo.
Además, sin ese token Keycloak podía pedir confirmación en una pantalla
intermedia.

**Decisión.** Agregar una ruta de cierre por inactividad que obtiene la URL de
cierre de Keycloak y cierra Django incluso si la sesión local ya venció. El
temporizador se adelanta hasta dos segundos (o el 10 % del plazo, si es menor)
para enviar el `id_token_hint` antes de que Django elimine la sesión. Si la
sesión ya venció, se usa el `client_id` como alternativa.

### 6.3. «¿Cómo se configura y se comprueba el plazo?»

- `DJANGO_SESSION_IDLE_TIMEOUT` se interpreta en segundos y tiene un valor
  predeterminado de 900 (15 minutos); se documentó en los ejemplos de entorno.
- El contenedor local se verificó con un valor efectivo de 30 segundos. Si se
  cambia `.env`, hay que reiniciar el servicio `web` para que el proceso vuelva
  a leer la configuración.
- La prueba manual en navegador confirmó que, tras la inactividad, el flujo
  termina en Keycloak y muestra la pantalla de inicio de sesión, no la cuenta
  autenticada.

### 6.4. Verificaciones realizadas

- 103 pruebas de `apps/usuarios/tests` aprobadas, incluidas las de expiración,
  renovación con actividad, cierre voluntario y cierre por inactividad con la
  sesión Django ya vencida.
- `python manage.py check` sin errores y `git diff --check` limpio.

---

## 7. Ryuto Maehara — GEG9-23, Menú — Ocultar opciones de historial y diferencias de caja

**Consulta:** quitar «Historial de caja» y «Diferencias de caja» de la barra
de navegación.

**Decisión.** Eliminar únicamente esas dos opciones del menú principal; las
rutas y funcionalidades de caja se mantienen disponibles. Se agregó una
prueba que confirma que ambas etiquetas no aparecen para el rol administrador.

**Verificación.** Las 13 pruebas de `apps/usuarios/tests/test_menu.py`
aprobaron.

---

## 8. Ryuto Maehara - RF024, Gestión de Anulaciones

### 8.1. «¿La anulación debe incluir compras y se puede reembolsar?»

**Lo que aprendimos.** La anulación de ventas ya registraba el motivo, el
administrador y la fecha, además de revertir los movimientos de efectivo
asociados. Las compras no tenían un flujo equivalente de anulación. Los pagos
electrónicos sí permiten solicitar el reembolso al proveedor original; una
transferencia conciliada requiere una devolución manual verificada por un
administrador.

**Decisión.** Incorporar la anulación de compras confirmadas, exigir un motivo y
registrar la transición a `ANULADA` con el actor y la fecha. Para pagos de
pasarela, anular solo si el proveedor confirma el reembolso. Para pagos manuales
o compras sin un pago asociado, exigir confirmación administrativa de que la
devolución ya se realizó. Si el proveedor deja el reembolso pendiente o lo
rechaza, mantener la compra pagada y dejar el pago para revisión; la anulación
se puede completar después de verificar manualmente la devolución.

### 8.2. «¿Cómo se accede y qué se muestra?»

- Se agregó «Compras y anulaciones» al menú del administrador y un listado de
  compras con acceso al comprobante y a la trazabilidad.
- El comprobante permite anular solo compras confirmadas; una compra anulada
  no se puede anular nuevamente.
- La migración agrega `anulado_en` a las compras. Las vistas de historial que
  filtran por estado confirmado dejan de incluir las compras anuladas.
- Se actualizaron las pruebas de menú y permisos para limitar las acciones al
  administrador.

### 8.3. Verificaciones y alcance

- Pasaron las pruebas focalizadas de conversiones, pagos y menú; también
  `python manage.py check`, `makemigrations --check --dry-run` y `git diff
  --check`.
- Se aplicó la migración `0012_compradivisa_anulado_en` y se verificó en el
  navegador el listado y el comprobante con compras de ejemplo. No se ejecutó
  un reembolso real de dLocal.
- Al integrarse RF057, las compras cobradas en efectivo generan un movimiento
  de ingreso vinculado. La anulación registra el retiro inverso con las mismas
  denominaciones antes de marcar la compra como anulada, manteniendo el saldo
  y el inventario del cajero consistentes.

---

## 9. Ryuto Maehara - GEG9-78, Configuración de seguridad (RF036)

### 9.1. «¿Cómo se configura el tiempo de inactividad?»

**Decisión.** Agregar la pantalla «Seguridad», visible y accesible solo para el
rol administrador. Allí se configura el tiempo máximo de inactividad entre 5
minutos y 8 horas. El valor se guarda en la base de datos y el middleware lo
aplica a las sesiones autenticadas en sus solicitudes, sin reiniciar Django.
Los cambios se registran con el usuario, la fecha y los valores anterior y
nuevo.

### 9.2. «¿Sigue siendo necesaria `DJANGO_SESSION_IDLE_TIMEOUT`?»

- La variable se expresa en segundos y sirve como valor inicial si todavía no
  existe una configuración guardada; `900` equivale a 15 minutos.
- Una vez creada la configuración en la base de datos, el valor guardado tiene
  prioridad. Cambiar `.env` no reemplaza el parámetro configurado en la
  pantalla.
- Las sesiones activas adoptan el nuevo plazo en su siguiente solicitud. Una
  pestaña abierta puede conservar su temporizador anterior hasta volver a
  cargar o hacer otra solicitud.

### 9.3. «¿Por qué aparecía `ProgrammingError` en `/panel/`?»

**Causa y resolución.** El código consultaba la tabla nueva de configuración,
pero la migración aún no se había aplicado en la base de datos del contenedor.
Se ejecutó `python manage.py migrate usuarios`; luego se verificó que el panel
y la pantalla de seguridad cargaran correctamente.

### 9.4. Verificaciones realizadas

- Las 460 pruebas del proyecto aprobaron con SQLite; `python manage.py check`
  y `makemigrations --check --dry-run` no detectaron problemas.
- Se verificó en el navegador el panel y la pantalla de seguridad después de
  aplicar la migración `0002_cambioconfiguracionseguridad_configuracionseguridad`.

## 10. Ryuto Maehara — GEG9-81, Registro de auditoría

### 10.1. «¿Cómo registrar las operaciones críticas de administración?»

**Decisión.** Agregar un registro con usuario, acción, fecha y hora, además de
detalles para identificar el objeto afectado. Se auditan altas y cambios de
tasas, comisiones y clientes, anulaciones de compras y ventas, y conciliaciones
de compras. Los registros se generan al completar las operaciones.

### 10.2. «¿Quién puede consultar los registros y qué filtros hay?»

- Se agregó la pantalla «Auditoría», accesible solo para el rol administrador,
  con filtros por usuario, acción y rango de fechas.
- La pantalla y la entrada del modelo en Django Admin son de solo lectura; no
  se ofrecen acciones de alta, edición ni borrado.

### 10.3. «¿Por qué aparecía `ProgrammingError` en `/administracion/auditoria/`?»

**Causa y resolución.** El contenedor web aún no tenía aplicada la migración que
crea `usuarios_registroauditoria`. Se ejecutó
`docker compose exec -T web python manage.py migrate usuarios` en el entorno
local y se comprobó que la migración `0003_registroauditoria` quedara aplicada.
Después de recargar, la pantalla abrió correctamente; quedó vacía porque todavía
no se habían registrado operaciones desde su activación.

### 10.4. Verificaciones realizadas

- Aprobaron las pruebas enfocadas de auditoría, clientes, comisiones, tasas,
  anulaciones y conciliaciones; `python manage.py check`,
  `makemigrations --check --dry-run` y `git diff --check` finalizaron sin
  errores.
- Se verificó la pantalla en el navegador después de aplicar la migración.

---
---

## 11. Leyda Fleitas — RF035, Configuración de Pagos (GEG9-77)

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

### 11.1. «Proveedor y método de pago no son lo mismo»

**Lo que aprendimos**, y era el malentendido que había que deshacer antes de
modelar nada. El punto de partida del ticket mencionaba `PAGO_PROVEEDOR`
como si fuera la configuración de métodos de pago. No lo es:

| | Qué decide | Quién lo cambia |
|---|---|---|
| `PAGO_PROVEEDOR` | Qué **pasarela** se usa: dLocal o el simulado | Variable de entorno |
| Método de pago | Con **qué paga** el cliente: tarjeta, transferencia | El administrador, desde la app |

`PAGO_PROVEEDOR` es un interruptor técnico —"¿llamo a la API real o al doble
de pruebas?"— y no tiene nada que hacer en una pantalla de negocio. **No se
tocó.**

Lo que el ERS llama método de pago **no existía como dato**: los dos botones
estaban escritos a mano en `templates/pagos/elegir_pago.html`. Habilitar o
deshabilitar uno exigía editar el HTML y desplegar.

### 11.2. «¿Qué métodos se modelan?»

**Decisión de la integrante:** solo los **dos que ya funcionaban**, tarjeta y
transferencia. El ERS menciona también billeteras, pero no hay código detrás:
crear esa fila habría puesto en la pantalla un botón que al tocarlo no hace
nada, o una fila permanentemente deshabilitada que nadie puede habilitar sin
programar.

Cada fila de la tabla corresponde a algo que de verdad anda. Cuando se
implemente billetera, se crea con la migración que traiga su código.

### 11.3. «El punto delicado: deshabilitar no puede trabar lo que ya está en curso»

**Lo que aprendimos**, y es el requisito del ERS que más fácil se incumple
sin darse cuenta: la comprobación obvia sería *"¿este método está
habilitado?"* en todo el flujo de pago. Eso rompería el punto 5.

Si un administrador deshabilita la transferencia mientras hay compras
esperando conciliación, esas compras quedarían **trabadas**: no se podrían
confirmar ni cancelar. Y el cliente **ya transfirió el dinero**.

**Decisión.** La comprobación va **solo al iniciar** un pago
(`exigir_metodo_habilitado`), nunca al confirmarlo, cancelarlo o conciliarlo.
Queda escrito en el docstring de esa función, porque es un invariante fácil
de romper de buena fe: alguien que agregue la validación "por completitud" en
`confirmar_pago` estaría introduciendo el problema.

Hay tres pruebas dedicadas: un pago por pasarela ya iniciado se confirma
igual, una compra que espera transferencia se cancela igual, y la
conciliación manual de RF025 sigue funcionando.

### 11.4. «¿Último cambio o historial completo?»

**Decisión de la integrante:** historial completo, con una tabla
`CambioMetodoPago`, en vez de dos campos `modificado_por` y `modificado_en`
en el propio modelo.

El motivo es concreto: con solo el último cambio, si alguien deshabilita un
método y otra persona lo vuelve a habilitar, **el primer cambio desaparece**
y no queda forma de saber quién lo apagó. Es el mismo patrón de
`CambioEstado` (RF023).

El servicio además no registra un cambio que no ocurrió: deshabilitar algo ya
deshabilitado no ensucia el historial.

### 11.5. «La plantilla deja de saber los métodos de memoria»

El campo `flujo` (PASARELA o MANUAL) existe para que la plantilla sepa a qué
vista mandar el botón **sin conocer cada método por su nombre**. Si tuviera
un `{% if metodo.codigo == "tarjeta" %}`, agregar un método nuevo volvería a
exigir editar el HTML, que es justo lo que esta historia vino a sacar.

## 11.6. Verificaciones realizadas

- **16 pruebas nuevas.** Suite completa: **400 aprobadas** (eran 384), sin
  regresiones.
- Casos cubiertos: la migración de datos crea exactamente los dos métodos
  que funcionaban; habilitar y deshabilitar; queda registro de quién y
  cuándo; el historial guarda **todos** los cambios y no inventa los que no
  ocurrieron; un método deshabilitado no aparece en la pantalla de pago y no
  se puede usar ni forzando el POST; sin ningún método habilitado avisa y no
  rompe; **un pago ya iniciado se confirma, se cancela y se concilia aunque
  se deshabilite el método**; un no administrador recibe 403 por GET y por
  POST; y cambiar el estado exige POST.
- `manage.py check` sin errores, migraciones `pagos.0002` y `0003` aplicadas
  y Sphinx genera sin warnings.

---

## 12. Leyda Fleitas — GEG9-82, Formato de Números y Montos

**Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.

Pedido transversal de la cátedra, no del ERS: separador de miles y columnas
numéricas alineadas a la derecha.

### 12.1. «La opción más obvia de Django no sirve, y se comprobó»

**Lo que aprendimos.** Lo primero que se evaluó fue activar
`USE_THOUSAND_SEPARATOR = True`, que parecía resolver todo con una línea. Se
probó antes de decidir:

```
HOY                    : 1250000,5
CON THOUSAND_SEPARATOR : 1 250 000,5      ← espacio fino, no punto
```

El locale `es` de Django es el de España y agrupa con **espacio**. La cátedra
pidió `1.250.000`. Activarlo habría cambiado el formato de **todas** las
pantallas de golpe, y al que no corresponde.

Cambiar a `es_PY` habría arrastrado también el formato de fechas en todo el
sistema.

**Decisión: filtro propio.** Formato exacto, aplicado donde se quiere, sin
efectos a distancia.

De paso se comprobó algo que tranquilizó el resto del trabajo: Django **no
localiza los `NumberInput`**, así que esa opción nunca habría roto los
formularios. Era un riesgo que valía la pena descartar con una prueba y no
con una suposición.

### 12.2. «Los formularios: donde el criterio chocaba con el HTML»

**Lo que aprendimos.** El criterio pedía que los formularios acepten el valor
escrito con separadores. Los campos de monto eran `<input type="number">`, y
ese tipo de campo **solo admite un número con punto decimal**: escribir
`10.000` hace que el navegador lo rechace o vacíe el campo antes de que llegue
al servidor.

**Decisión de la integrante:** pasar a campo de texto con un parser propio
(`MontoField`). Cumple el criterio al pie de la letra.

El contrapeso, que quedó anotado en el código: se pierde el teclado numérico
del celular y la validación del navegador. La validación de Django sigue
intacta —`MontoField` hereda de `DecimalField`, así que mínimos, máximos y
dígitos siguen valiendo— y **el valor guardado no cambia**.

**Las comisiones se dejaron como estaban**: son porcentajes de 0 a 100, nunca
llevan separador de miles, y el `max="100"` del navegador es útil. Cambiarlas
habría sido perder algo sin ganar nada.

### 12.3. «Un riesgo que apareció a mitad de camino: `7.120` como tasa»

**Lo que aprendimos**, y casi se cuela sin que nadie lo note. La regla para
desambiguar `10.000` —punto con exactamente tres dígitos detrás es separador
de miles— es correcta para importes. **Para tasas es peligrosa:** una
cotización de `7.120` significa siete coma doce, no siete mil ciento veinte,
porque las tasas llevan hasta seis decimales.

Con la regla aplicada a todo, alguien cargando una tasa de `1.234` habría
guardado mil doscientos treinta y cuatro.

**Decisión.** Un `TasaField` que desactiva esa regla: en una tasa, un punto
suelto siempre es decimal, y para los miles hay que usar la coma
(`7.120,00`). Quedó escrito en el docstring, porque es exactamente el tipo de
diferencia que alguien "unificaría" de buena fe.

### 12.4. «Dónde viven los decimales de cada moneda»

**Lo que aprendimos.** `Moneda` guardaba código, nombre, símbolo y poco más.
Que el guaraní no lleve decimales estaba **implícito y repartido**:
`to_integral_value()` en facturación, `quantize(Decimal("0.01"))` en pagos, y
`floatformat` sueltos con criterios distintos en seis plantillas.

**Decisión de la integrante:** un campo `decimales` en `Moneda`, con
migración de datos. Es una propiedad de la moneda y ahí corresponde; cuando
el administrador cargue una moneda nueva, lo define en la misma pantalla.

Se puso **JPY en 0** además del guaraní: el yen tampoco usa decimales.

### 12.5. «Las descargas no tienen ninguna librería»

**Lo que aprendimos** al llegar al criterio de alinear en Excel y PDF: no hay
`openpyxl` ni `reportlab`. El "Excel" es **SpreadsheetML escrito a mano**, con
todas las celdas como `ss:Type="String"` —Excel las mostraba pegadas a la
izquierda y no se podían sumar— y el PDF se arma **byte a byte**, uniendo los
campos con `" | "`.

**Decisión.** No agregar librerías a esta altura de la entrega:

- **Excel:** los importes pasan a `ss:Type="Number"` con un estilo
  `ss:Horizontal="Right"` y formato `#.##0,00`. Ahora además **se pueden
  sumar**, que era un problema que nadie había notado.
- **PDF:** las columnas se rellenan con espacios hasta el ancho máximo, y las
  numéricas se alinean a la derecha. Funciona porque el PDF usa una sola
  tipografía; con una proporcional los espacios no alcanzarían.

### 12.6. «Cifras tabulares, no solo `text-align: right`»

Alinear a la derecha no alcanza: en la mayoría de las tipografías los dígitos
tienen anchos distintos, así que las comas de una columna quedan desparejas
aunque el borde derecho esté alineado. La clase `.num` agrega
`font-variant-numeric: tabular-nums`, que hace que todos los dígitos ocupen
lo mismo.

Vive en `templates/base.html` y no en cada pantalla, porque Tailwind no se
puede recompilar en este entorno (Node 18 contra el 20 que pide).

## 12.7. Verificaciones realizadas

- **42 pruebas nuevas.** Suite completa: **442 aprobadas** (eran 400), sin
  regresiones.
- Casos cubiertos: enteros, decimales, **cero, negativos y números grandes**;
  cada moneda con sus decimales (PYG y JPY sin, USD y EUR con dos); que la
  tasa conserve la precisión; que **no se use float** —`Decimal("1.005")`
  redondea a `1,01`, que en float daría `1,00`—; que el formulario acepte las
  dos formas de escribir y que **el valor guardado no cambie**; que siga
  validando el mínimo; que las columnas numéricas lleven la clase de
  alineación; que el Excel lleve los importes como número alineados a la
  derecha; que el PDF los alinee rellenando con espacios; y que el gráfico
  use el mismo formato.
- Dos pruebas existentes de tasas se adaptaron: verificaban el atributo
  `step` del `NumberInput`, que ya no existe. Ahora verifican lo que importa,
  que es que siga aceptando seis decimales.
- `manage.py check` sin errores, migraciones `monedas.0002` y `0003`
  aplicadas y Sphinx genera sin warnings.

<<<<<<< HEAD
---
=======
---

## 13. Fabrizio Cardozo — RF031, Monitoreo de Ganancias en Tiempo Real (GEG9-64)

### 13.1. «¿Cómo calcular la ganancia de las operaciones?»

**Lo que aprendimos.** Las compras y ventas ya conservan la comisión, la tasa
aplicada, la tasa de compra y la tasa de venta utilizadas en la operación. No
hace falta persistir un nuevo valor de ganancia ni crear una migración; el
resumen puede calcularse con los datos históricos de cada operación.

**Decisión.** Calcular la ganancia como la suma de la comisión cobrada y la
diferencia entre la tasa de venta y la tasa de compra, aplicada al monto base.
La comisión de una compra se convierte a la moneda recibida para que el
desglose sea consistente. El resultado se agrupa por moneda y también se
muestra como total global.

### 13.2. «¿Qué operaciones deben incluirse?»

**Decisión.** Consultar exclusivamente operaciones con estado `CONFIRMADA` y
con `confirmado_en` registrado. Las operaciones `PENDIENTE`, `CANCELADA` y
`ANULADA` quedan fuera del cálculo. El rango de fechas se aplica sobre la fecha
de confirmación, porque es el momento en que la operación genera rendimiento.

### 13.3. «¿Cómo se actualiza el dashboard?»

- Se agregó la pantalla `/ganancias/` y el endpoint `/ganancias/datos/`.
- El dashboard permite filtrar por fecha desde/hasta y muestra totales,
  comisiones, diferencia de tasa, cantidad de operaciones y desglose por
  moneda.
- La pantalla consulta nuevamente el endpoint cada 15 segundos, por lo que
  refleja nuevas operaciones confirmadas sin almacenar un resumen obsoleto.
- El acceso está restringido a los roles `administrador` y
  `analista_cambiario`; ambos roles ven la opción «Ganancias» en el menú.

### 13.4. Verificaciones y alcance

- Se agregaron pruebas para la suma de comisión y diferencia de tasa, exclusión
  de operaciones canceladas, filtro por fecha y permisos de acceso.
- RF031 no agrega modelos ni migraciones.
- La ejecución de las pruebas queda pendiente de validación en el contenedor
  Docker del proyecto.
>>>>>>> 228221b (feature/GEG9-64: Monitoreo de Ganancias en Tiempo Real (RF031))

## Daniela González — RF030, Reporte de Transacciones para la Administración (GEG9-66)

### 14.1. «¿Cómo complementar el historial por cliente?»

**Lo que aprendimos.** El historial existente está deliberadamente limitado al
cliente activo y a operaciones confirmadas. Cambiarlo para que un administrador
vea todos los clientes rompería ese límite de privacidad y el propósito de RF030
original.

**Decisión.** Crear una pantalla independiente de reporte global. El historial
por cliente se conserva sin cambios; el nuevo reporte consulta compras y ventas
por separado, las transforma a una estructura común y las ordena por fecha de
creación.

### 14.2. «¿Las operaciones de la terminal necesitan otro registro?»

**Lo que aprendimos.** La terminal inicia operaciones mediante los mismos
servicios `iniciar_compra` e `iniciar_venta`, con `desde_terminal=True`, y las
guarda en `CompraDivisa` y `VentaDivisa`. No existe un modelo separado de
transacciones de terminal.

**Decisión.** Reutilizar esas fuentes históricas. De esta forma el reporte
incluye también operaciones iniciadas desde autoservicio sin duplicar datos ni
agregar una migración.

### 14.3. «¿Qué filtros necesita la auditoría?»

**Decisión.** Agregar filtros combinables por cliente, moneda —en cualquiera
de los extremos de la conversión—, tipo de operación, estado y rango inclusivo
de fechas. La fecha mostrada y filtrada es `creado_en`, para que también puedan
auditarse operaciones pendientes, canceladas y anuladas.

### 14.4. Verificaciones realizadas

- Se agregó `/conversiones/reporte-transacciones/` como pantalla de consulta
  independiente.
- El acceso está restringido a `administrador` y `analista_cambiario`.
- Se agregaron 6 pruebas unitarias para listado, estados, filtros, monedas,
  permisos y coexistencia con el historial por cliente.
- No se agregó migración: el reporte utiliza `CompraDivisa` y `VentaDivisa`.
- `manage.py check` no reporta errores y las pruebas de `apps/conversiones/`
  pasan.
