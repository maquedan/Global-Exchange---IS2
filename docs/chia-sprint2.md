# CHIA — Conversaciones con Inteligencia Artificial

Registro del uso de IA como herramienta de apoyo durante el **Sprint 2** del
proyecto Global Exchange (Grupo 9, FP-UNA).

- **Herramienta:** Claude (Anthropic), integrado en VS Code sobre WSL2.
- **Modalidad de trabajo:** se usó como asistente de consulta y de programación.
  Cada integrante definió qué construir para su propia historia, tomó las
  decisiones de diseño, ejecutó los comandos y verificó cada resultado contra
  el entorno real antes de darlo por bueno. El código propuesto por la IA se
  revisó y se ajustó antes de integrarlo.

Este documento está organizado **por integrante**, y dentro de cada sección,
**por consulta realizada**, indicando qué se preguntó, qué se aprendió y qué
se decidió a partir de eso — igual que el CHIA del Sprint 1.

**Cómo sumar tu parte:** copiá el formato de una sección de abajo y completala
con tus propias consultas reales a la IA (si la usaste). Si no usaste IA para
tu historia, dejalo dicho así, sin inventar contenido.

---

## 1. Leyda Fleitas — RF020, Cuentas y Billeteras de clientes (GEG9-30)

### 1.1 «el import `from .models import CuentaPago` no encuentra la clase»

**Lo que aprendimos.** El import relativo `from .models import ...` dentro del
paquete `tests/` busca un módulo `models.py` **dentro del propio paquete
`tests/`**, no en `apps/cuentas/`. Como ahí no existe, la prueba fallaba al
cargarse.

**Decisión.** Usar la ruta absoluta `from apps.cuentas.models import
CuentaPago`, igual que ya lo hacía el resto de las apps del proyecto.

### 1.2 «el campo Alias queda pegado a los botones Guardar/Cancelar»

**Lo que aprendimos.** Era falta de espaciado en el formulario: el campo
opcional no tenía separación con la fila de acciones que viene justo debajo.

**Decisión.** Agregar margen entre el último campo del formulario y los
botones, para que no se vean encimados.

### 1.3 «el gris del botón Eliminar no se distingue bien»

**Lo que aprendimos.** Un gris de bajo contraste sobre el fondo de la tabla es
difícil de leer, y es justo la acción destructiva la que más conviene que
resalte, no la que menos se note.

**Decisión.** Reforzar el contraste del botón Eliminar para diferenciarlo
claramente de Modificar.

### 1.4 «los botones Modificar/Eliminar se superponen en la columna Acciones»

**Lo que aprendimos.** Dos botones apilados en una columna angosta, sin
suficiente separación, se pisan visualmente y quedan poco prolijos.

**Decisión.** Simplificar la presentación de esa columna para que quede
minimalista y fácil de entender de un vistazo.

---

## 2. Leyda Fleitas — RF016, Visualización de Tasas en Tiempo Real (GEG9-28)

### 2.1 «los números que muestra la plantilla no coinciden con los que compara el JavaScript»

**Lo que aprendimos.** Django formatea los decimales según el idioma activo;
en español, `floatformat` y `{{ decimal }}` escriben la coma como separador
(`7,20`). El JavaScript, en cambio, compara con `.toFixed(2)`, que siempre usa
punto. La comparación fallaba en silencio.

**Decisión.** Usar `stringformat:".2f"` en las plantillas (no depende del
idioma) y pre-formatear los números como texto ya en la vista, para que
ambos lados hablen el mismo formato.

### 2.2 «elijo un par sin datos y me muestra otro distinto, sin avisar»

**Lo que aprendimos.** La vista sustituía silenciosamente cualquier par
inválido o sin datos por un par por defecto, sin decir por qué había cambiado
la selección — confundía al usuario, que creía estar viendo el par que eligió.

**Decisión.** Sustituir por un par por defecto **solo** cuando no viene
ningún parámetro en la URL (primera visita); si el usuario eligió un par
puntual sin datos, mostrar un aviso honesto con los pares que sí tienen
información.

### 2.3 ``{{ par.historial|json_script:"datos-"|add:par.id }}`` tira error en la plantilla»

**Lo que aprendimos.** El filtro `json_script` de Django acepta un solo
argumento (el id del script); no se pueden encadenar más filtros como
`|add:` sobre él dentro de la misma expresión.

**Decisión.** Precalcular el id completo (`par.id_datos`) en la vista, en
Python, y pasarlo ya armado a la plantilla.

### 2.4 «creé la carpeta `templatetags` pero Django no encuentra el filtro nuevo»

**Lo que aprendimos.** El autoreload del servidor de desarrollo no siempre
detecta una carpeta nueva creada mientras el servidor ya está corriendo,
aunque sí detecta cambios en archivos existentes.

**Decisión.** Reiniciar el contenedor (`docker compose restart web`) después
de crear un paquete nuevo, y verificar el registro del filtro con
`get_installed_libraries()`.

### 2.5 «las banderas se ven como cuadraditos en Windows»

**Lo que aprendimos.** Los emojis de bandera no son un solo carácter: son dos
letras combinadas por una fuente que sepa hacerlo. Windows no siempre tiene
esa fuente instalada, y muestra las dos letras sueltas en vez de la bandera.

**Decisión.** Reemplazar los emojis por banderas dibujadas a mano en SVG
propio, que se ven igual en cualquier sistema operativo.

### 2.6 «¿por qué no puedo poner una bandera SVG dentro de un `<option>`?»

**Lo que aprendimos.** El elemento `<option>` del HTML solo puede mostrar
texto: es una limitación del propio estándar, no un error del código. No
acepta ningún elemento hijo, ni siquiera un `<span>` o un SVG.

**Decisión.** Mover la vista previa de la bandera a un elemento hermano del
`<select>`, en vez de intentar meterla adentro de cada `<option>`.

### 2.7 «el botón para invertir De↔A funciona una vez y después ya no hace nada»

**Lo que aprendimos.** El script empezaba con un `return` temprano
(`if (!svg) return;`) pensado solo para saltear el dibujo del gráfico cuando
no había datos. Pero ese mismo `return` también cortaba la ejecución de todo
lo que venía después en la función, incluida la definición del botón de
intercambio y el `setInterval` del auto-refresco — por eso, apenas se
recargaba una página sin gráfico, esas dos funciones dejaban de existir.

**Decisión.** Encerrar solo el código que dibuja el gráfico dentro de
`if (svg) { ... }`, dejando el botón y el auto-refresco fuera de esa
condición. Se verificó ejecutando el script real en Node.js, con
`document`/`window`/`fetch` simulados, confirmando que
`window.intercambiarMonedas` queda definida incluso cuando no hay gráfico.

---

## 3. Verificaciones realizadas

- **Suite completa de pruebas:** 73 passed.
- **Simulación de sesión real de navegador** con `django.test.Client` +
  `force_login()` + `setup_test_environment()`.
- **Verificación del bug del botón de intercambio** ejecutando el JavaScript
  real fuera del navegador (Node.js), con un DOM simulado, confirmando el
  comportamiento antes y después del arreglo.
- **Fixtures** (`monedas_demo.json`, `tasas_demo.json`) verificadas como
  idempotentes: se corrió `loaddata` más de una vez y no se duplicaron datos.

---

## 4. Daniela González — RF014, Administración de Monedas (GEG9-26)

### 4.1 «¿Qué datos debe tener una moneda para poder reutilizarse en otros módulos?»

**Lo que aprendimos.** El identificador de una divisa debe ser estable y único.
Para representar correctamente una moneda admitida se necesitan su código ISO,
nombre, símbolo y estado de disponibilidad.

**Decisión.** Definir el modelo `Moneda` con los campos `codigo`, `nombre`,
`simbolo`, `activo`, `creado_en` y `actualizado_en`. El código ISO se valida
con exactamente tres letras mayúsculas y es único; por ejemplo: `USD`, `EUR`,
`PYG` y `BRL`.

### 4.2 «¿Debo eliminar una moneda cuando deja de poder operar?»

**Lo que aprendimos.** Eliminar físicamente una moneda puede afectar tasas,
simulaciones u operaciones históricas que la referencien en el futuro. Que una
moneda ya no esté admitida no significa que deba desaparecer del historial.

**Decisión.** Implementar baja lógica mediante el campo `activo`. La interfaz
permite desactivar monedas para excluirlas de operaciones futuras y
reactivarlas cuando vuelvan a estar admitidas.

## 4.3 «¿Cómo proteger la gestión de monedas para que nadie más la use?»
**Lo que aprendimos.** Ocultar un enlace del menú no protege una funcionalidad:
un usuario podría escribir la URL directamente. La autorización debe aplicarse
también en las vistas.

**Decisión.** Reutilizar el patrón del proyecto con `login_required` y
`requiere_administrador` en las vistas de listado, alta, edición, desactivación
y reactivación. El menú muestra la opción Monedas únicamente al rol
`administrador`.

## 4.4 Verificaciones realizadas
- Migración inicial de `apps.monedas` creada y aplicada en PostgreSQL mediante Docker Compose.
- `python manage.py check` ejecutado sin errores.
- Gestión manual comprobada desde `/monedas/`: alta, modificación, desactivación y reactivación.
- Pruebas unitarias de Monedas ejecutadas con 6 pruebas aprobadas.

---

## 5. Ryuto Maehara — RF015, Actualización de Tasas (GEG9-27)

### 5.1 «Necesito implementar el modelo `TasaCambio` respetando la estructura actual del proyecto»

**Lo que se consultó.** Se pidió analizar primero las apps, modelos,
relaciones, configuración de base de datos, migraciones y autenticación antes
de escribir código.

**Lo que aprendimos.** El proyecto ya tenía el modelo `Moneda` en
`apps.monedas`, con los campos `activo`, `creado_en` y `actualizado_en`. La app
`apps.tasa_cambios` existía, pero solo contenía la estructura inicial generada
por Django.

**Decisión.** Crear `TasaCambio` en `apps.tasa_cambios`, relacionándolo dos
veces con `Moneda` mediante `moneda_origen` y `moneda_destino`. Se reutilizaron
las convenciones existentes para estado y fechas, sin modificar `Moneda`.

### 5.2 «La tasa debe conservar históricos y no permitir dos tasas activas para el mismo par»

**Lo que aprendimos.** Las tasas anteriores deben conservarse como registros
inactivos. La unicidad debía aplicarse solamente a los registros activos.

**Decisión.** Usar una `UniqueConstraint` condicional para
`moneda_origen`, `moneda_destino` y `activo=True`. También se agregaron
restricciones para impedir que las monedas sean iguales y para exigir valores
positivos en compra y venta.

### 5.3 «Quiero una lógica y una interfaz para crear y modificar tasas de cambio»

**Lo que se consultó.** Se pidió continuar con la app y agregar el flujo de
alta y modificación siguiendo la interfaz existente.

**Decisión.** Crear un `ModelForm`, vistas protegidas por roles, rutas,
plantilla de listado y plantilla de formulario. El acceso se habilitó para los
roles `administrador` y `analista_cambiario`, siguiendo el patrón de las otras
apps.

### 5.4 «No quiero trabajar con SQLite; ya estoy usando PostgreSQL en Docker»

**Decisión.** Se dejó de usar la base temporal SQLite y se continuó la
validación exclusivamente con PostgreSQL mediante Docker Compose. La
migración de `TasaCambio` se aplicó en el contenedor `web`.

### 5.5 «La parte de precio no quiero que tenga muchos decimales, sino solo dos»

**Lo que aprendimos.** El modelo y el formulario inicialmente permitían seis
decimales.

**Decisión.** Cambiar `tasa_compra` y `tasa_venta` a `DecimalField` con
`decimal_places=2`, valor mínimo `0.01` y controles HTML con `step="0.01"`.
Se generó y aplicó la migración correspondiente en PostgreSQL.

### 5.6 Verificaciones realizadas

- `manage.py check` sin errores.
- Migraciones de `tasa_cambios` aplicadas en PostgreSQL Docker.
- Pruebas focalizadas de la app `tasa_cambios`: 4 pasaron.
- Suite completa del proyecto después de implementar el CRUD: 62 pruebas
  pasaron.

---

## 6. Fabrizio Cardozo — RF017, Simulación de Conversión (GEG9-29)

### 6.1 «¿Cómo organizar la simulación de conversión sin registrar todavía una operación?»

**Lo que aprendimos.** Una simulación es una consulta temporal: debe recibir
los datos del formulario, buscar una tasa activa y mostrar un resultado, pero
no crear una cuenta, movimiento ni operación confirmada. La lógica de cálculo
conviene separarla de la vista para poder probarla de forma independiente.

**Decisión.** Crear la función `calcular_conversion` en `services.py`, usar la
vista únicamente para coordinar el formulario y la búsqueda de la tasa, y
mostrar el resultado en la misma pantalla de simulación.

### 6.2 «¿Cómo calcular correctamente una conversión de compra y una de venta?»

**Lo que aprendimos.** En una compra se multiplica el monto por
`tasa_compra`; en una venta se divide por `tasa_venta`. Para importes
monetarios no conviene usar `float`, porque puede introducir errores de
precisión. `Decimal` permite conservar el valor exacto y redondear de forma
explícita.

**Decisión.** Convertir monto y tasa a `Decimal`, seleccionar la operación
según el tipo elegido y redondear el resultado a dos decimales con
`ROUND_HALF_UP`.

### 6.3 «¿Cómo debe elegir la aplicación la tasa para el par de monedas?»

**Lo que aprendimos.** La simulación no debe usar una tasa histórica o
inactiva. La consulta tiene que filtrar por moneda de origen, moneda de
destino y `activo=True`; si existe más de una, debe preferir la más reciente
según `vigente_desde`.

**Decisión.** Buscar la tasa activa más reciente y mostrar un error en el
formulario cuando no exista una tasa para el par seleccionado, en vez de
inventar un valor o usar una tasa por defecto.

### 6.4 «¿Qué validaciones necesita el formulario de simulación?»

**Lo que aprendimos.** El monto debe ser positivo y limitarse a dos decimales.
Además, no tiene sentido convertir una moneda hacia sí misma, por lo que esa
regla debe validarse en el formulario antes de consultar la base de datos.

**Decisión.** Usar un `DecimalField` con mínimo `0.01`, dos decimales y
`step="0.01"`, y agregar un error sobre la moneda de destino cuando origen y
destino sean iguales.

### 6.5 «¿Cómo restringir la simulación a los clientes?»

**Lo que aprendimos.** `login_required` solo comprueba que exista una sesión;
no comprueba que el usuario tenga el rol funcional correcto. También es
necesario validar el rol en la vista, porque ocultar el enlace del menú no
impide que alguien acceda directamente a la URL.

**Decisión.** Proteger la vista con `login_required` y un decorador
`requiere_cliente`, que exige el grupo `usuario_cliente` y responde con `403`
para usuarios sin ese rol.

### 6.6 Verificaciones realizadas

- Pruebas focalizadas de `apps/conversiones/`: **5 pasaron**.
- Se verificó el cálculo de compra con redondeo a dos decimales.
- Se verificó el cálculo de venta mediante división por la tasa.
- Se comprobó la simulación exitosa con una tasa activa y que no se cree una
  operación persistente.
- Se comprobó el rechazo de monedas iguales y el bloqueo de usuarios sin rol
  `usuario_cliente`.
