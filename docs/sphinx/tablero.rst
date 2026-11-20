Tablero de control del administrador
====================================

Pantalla exclusiva del administrador que consolida las métricas del negocio
(RF038 — GEG9-67). Vive en ``/tablero/`` y aparece en el menú solo para ese
rol; cualquier otro recibe 403 incluso escribiendo la dirección.

Es una pantalla **aparte** del panel común. ``usuarios:panel`` lo usan todos
los roles —cliente, cajero, analista, terminal— y meterle un ``if`` por rol
habría puesto en riesgo una pantalla que ya funciona para los otros cuatro.

Las ganancias no se recalculan
------------------------------

El tablero **no vuelve a calcular las ganancias**: se las pide a
:func:`apps.ganancias.services.resumen_ganancias` (RF031), con el mismo rango
de fechas que el resto de la pantalla. Hay una prueba que compara los dos
resultados, así que si alguien cambia la regla de ganancias, las dos
pantallas siguen coincidiendo o la prueba se pone roja.

La ganancia total, en guaraníes
-------------------------------

RF031 devuelve un desglose por moneda y además un total, pero ese total suma
importes de **monedas distintas**: guaraníes más dólares en un mismo número,
sin unidad. El tablero no lo usa.

En su lugar convierte cada moneda a guaraníes con la **tasa de compra
vigente**, la que la casa de cambio paga por esa moneda, y recién entonces
suma. Es una decisión y conviene saberlo:

- **Por qué la tasa de compra y no la de venta.** Es la valuación
  conservadora: nunca infla el resultado. Con la de venta el total daría más
  alto. Cambiarlo es una línea en :func:`cotizaciones_a_guaranies`.
- **Por qué la cotización de hoy y no la del día de cada operación.** RF031
  entrega las ganancias ya sumadas por moneda, no operación por operación,
  así que la cotización histórica no está disponible sin recalcular todo por
  fuera de RF031. La consecuencia, anotada acá: el total de un período pasado
  se mueve si cambian las tasas.
- **Una moneda sin tasa activa hacia el guaraní no se convierte.** No entra
  en el total y la pantalla la nombra. Inventarle una cotización daría un
  número falso; callarla daría un total que parece completo y no lo está.

El desglose por moneda se sigue mostrando entero, así que nada queda oculto
detrás de la conversión.

El gráfico de evolución
-----------------------

Barras de ganancia en guaraníes a lo largo del período, en SVG escrito a
mano: igual que el gráfico de tasas de RF016, sin agregar ninguna librería.

La geometría —posición, ancho y alto de cada barra— se calcula en Python, no
en la plantilla, para poder probarla: hay una prueba que verifica que el día
con el doble de ganancia dibuje el doble de alto y que ninguna barra se salga
del dibujo.

**El gráfico no reimplementa la regla de ganancia.** Llama a las mismas
funciones de RF031 que usa ``resumen_ganancias``, operación por operación, y
una prueba exige que **la suma de las barras sea igual** al resumen del
período completo. Esa prueba es la que evita que el gráfico empiece a contar
una ganancia distinta de la del resto de la pantalla.

Se recorren las operaciones una sola vez, en dos consultas. La alternativa
—pedirle a RF031 un resumen por cada barra— habría costado dos consultas por
barra.

Las barras nunca pasan de ``MAXIMO_BARRAS``: si el período es corto va una
por día, y si es largo cada barra junta varios días. Así el gráfico no se
vuelve ilegible ni el costo depende del largo del período.

Dos fechas, porque son dos preguntas distintas
----------------------------------------------

Los conteos por estado se filtran por ``creado_en`` —cuándo se inició la
operación— y las ganancias por ``confirmado_en``, igual que RF031.

No es un descuido. Una operación cancelada nunca tiene fecha de confirmación:
filtrar los conteos por ``confirmado_en`` haría que las canceladas no
aparecieran nunca. El efecto a tener presente: una compra iniciada ayer y
confirmada hoy cuenta como operación de ayer y como ganancia de hoy.

Lo que el modelo no permite informar
------------------------------------

Dos métricas se cambiaron por lo que los modelos sí pueden sostener:

- **Diferencias de arqueo:** dice *registradas*, no *pendientes*.
  ``DiferenciaCaja`` no tiene ningún campo de resolución, así que el sistema
  no distingue una diferencia ya resuelta de una abierta.
- **Sucursales:** no hay contador. ``Sucursal.es_unica`` es un campo único,
  o sea que el modelo impone que haya una sola; el contador diría siempre
  «1». Se informa el nombre de la caja y si está activa.

Rendimiento
-----------

Todo se agrega en la base de datos (``Count``, ``Sum``, ``filter=Q(...)``).
El costo en consultas es fijo y no crece con la cantidad de operaciones, que
es lo que pide RNF001.

La prueba que lo cuida no verifica un número escrito a mano: corre el
servicio con pocas operaciones, crea veinte más y exige que la cantidad de
consultas sea **la misma**. Un número fijo se rompería con cualquier cambio
inocente; así solo se rompe cuando el costo empieza a depender de los datos.

Por eso el servicio devuelve los decimales de cada moneda junto con su saldo:
el filtro de formato puede averiguarlos solo, pero lo hace con una consulta
por moneda.

Servicio
--------

.. automodule:: apps.tablero.services
   :members:

Vista
-----

.. automodule:: apps.tablero.views
   :members:

Lo que la pantalla no explica
-----------------------------

El tablero muestra datos y nada más: la integrante pidió sacarle los textos
que justificaban las decisiones, y tenía razón —un tablero se mira de un
vistazo, no se lee—. Esas explicaciones viven acá y en el CHIA.

La única advertencia que quedó en pantalla es la de las **monedas sin
cotización vigente**, y queda por un motivo distinto: no explica una
decisión, avisa que el total está incompleto. Solo aparece cuando eso pasa
de verdad.
