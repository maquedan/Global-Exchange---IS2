Formato de números y montos
===========================

Un solo lugar donde se decide cómo se ve un número (GEG9-82), para no
repetir criterios distintos en cada plantilla.

**Punto para los miles y coma para los decimales**: ``1.250.000`` y
``1.234,56``.

Por qué un filtro propio y no la configuración de Django
--------------------------------------------------------

Lo primero que se evaluó fue ``USE_THOUSAND_SEPARATOR = True``. No sirve: con
``LANGUAGE_CODE = "es"`` Django agrupa con **espacio fino** —``1 250 000``—,
no con punto. Se comprobó antes de descartarlo.

Cambiar el locale a ``es_PY`` habría arrastrado también el formato de fechas
en todo el sistema. Un filtro propio da el formato exacto, donde se lo quiere
y sin efectos a distancia.

Todo trabaja con ``Decimal`` y **nunca con** ``float``: un ``float`` no
representa 0,1 con exactitud y en importes de dinero eso se nota.

Cuántos decimales lleva cada moneda
-----------------------------------

Lo define cada moneda en su campo ``decimales`` (``apps.monedas``), no una
lista escrita en el código: el guaraní y el yen usan 0, el resto 2, y una
moneda nueva lo define desde la pantalla de administración.

Los formularios aceptan el formato
----------------------------------

``MontoField`` entiende ``10.000`` y ``1.234,56``. No se puede hacer con
``<input type="number">``, que solo admite un número con punto decimal, así
que usa un campo de texto y convierte en el servidor. **El valor guardado y
los cálculos no cambian**: sigue siendo el mismo ``Decimal`` de siempre.

Para desambiguar ``10.000`` —¿diez mil, o diez con tres decimales?— se usa la
regla con la que escribe la gente: si hay coma, los puntos son de miles; si
no hay coma, un punto con exactamente tres dígitos detrás también lo es.

``TasaField`` **desactiva esa última regla**, y el motivo vale la pena: una
cotización de ``7.120`` significa siete coma doce, no siete mil ciento
veinte, porque las tasas llevan hasta seis decimales. Para escribir siete mil
ciento veinte como tasa hay que usar la coma: ``7.120,00``.

Alineación a la derecha
-----------------------

La clase ``.num`` vive en ``templates/base.html``, así que vale en todas las
pantallas sin repetirla. Usa cifras tabulares (``tabular-nums``): sin eso los
dígitos tienen anchos distintos y las comas de una columna no quedan
alineadas aunque el texto sí lo esté.

En el gráfico de tasas el formateo es JavaScript, y usa
``Intl.NumberFormat("es-PY")``, que da el mismo resultado sin reimplementarlo.

En las descargas no hay ninguna librería externa: el XLSX se arma con los XML
mínimos de Office dentro de un ZIP y el PDF se arma byte a byte. Los importes
numéricos se conservan como números en el XLSX para que puedan sumarse, y en
el PDF las columnas se rellenan con espacios, que funciona porque usa una sola
tipografía.

Formato
-------

.. automodule:: apps.comun.formato
   :members:

Campos de formulario
--------------------

.. automodule:: apps.comun.campos
   :members:

Filtros de plantilla
--------------------

.. automodule:: apps.comun.templatetags.formato_extras
   :members:

Exportaciones
-------------

.. automodule:: apps.comun.exportaciones
   :members:
