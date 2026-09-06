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

## 4. [Nombre del compañero] — RF014, Administración de Monedas (GEG9-26)

*(Pendiente: completar con tus propias consultas reales a la IA, si la
usaste para esta historia.)*

---

## 5. [Nombre del compañero] — RF015, Actualización de Tasas (GEG9-27)

*(Pendiente: completar con tus propias consultas reales a la IA, si la
usaste para esta historia.)*

---

## 6. [Nombre del compañero] — RF0XX, Simulación de Conversión (GEG9-29)

*(Pendiente: completar con tus propias consultas reales a la IA, si la
usaste para esta historia.)*
