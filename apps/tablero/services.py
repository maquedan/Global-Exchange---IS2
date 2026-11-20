"""Métricas consolidadas del tablero del administrador (RF038 — GEG9-67).

Una sola función, :func:`metricas`, junta todo lo que muestra la pantalla.
La vista no consulta la base: así el mismo resumen se puede probar sin
pasar por HTTP, y todas las consultas quedan contadas en un solo lugar.

**Todo se agrega en la base de datos** (``Count``, ``Sum``, ``filter=Q(...)``).
No se recorre fila por fila en Python: con el volumen de un año de
operaciones eso sería lo único capaz de pasarse de los 3 segundos que pide
RNF001. El costo en consultas es fijo, no crece con la cantidad de datos, y
hay una prueba que lo verifica.

Las ganancias **no se recalculan acá**: se piden a
:func:`apps.ganancias.services.resumen_ganancias` (RF031). Repetir esa
cuenta daría dos números distintos en dos pantallas la primera vez que
alguien cambie la regla en un solo lado.
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.cajas.models import DiferenciaCaja, SaldoCaja, Sucursal
from apps.clientes.models import Cliente
from apps.comun.formato import formatear_numero
from apps.conversiones.models import CompraDivisa, VentaDivisa
from apps.facturacion.models import Factura
from apps.ganancias.services import (
    _ganancia_compra,
    _ganancia_venta,
    operaciones_confirmadas,
    resumen_ganancias,
)
from apps.tasa_cambios.models import TasaCambio

#: Períodos que ofrece la pantalla, en orden.
PERIODOS = [
    ("hoy", "Hoy"),
    ("7", "Últimos 7 días"),
    ("30", "Últimos 30 días"),
    ("todo", "Todo"),
]

PERIODO_POR_DEFECTO = "30"

# Días hacia atrás, contando el de hoy: "7 días" son hoy y los 6 anteriores.
DIAS_HACIA_ATRAS = {"hoy": 0, "7": 6, "30": 29}

#: Moneda en la que se expresa la ganancia total.
MONEDA_GLOBAL = "PYG"

#: Cuántas barras como máximo dibuja el gráfico de evolución.
MAXIMO_BARRAS = 12

# Medidas del `viewBox` del gráfico. Se calculan en Python y no en la
# plantilla: así la geometría se puede probar con pytest.
GRAFICO_ANCHO = 720
GRAFICO_ALTO = 240
GRAFICO_MARGEN_INFERIOR = 28


def rango_de(periodo):
    """Traduce el período elegido a ``(periodo, desde, hasta)``.

    Devuelve también el período ya normalizado, porque el valor llega de la
    dirección del navegador y puede ser cualquier cosa: lo que no reconoce
    se reemplaza por el valor por omisión en vez de romper la pantalla.

    ``"todo"`` devuelve ``(…, None, None)``, que es lo que entienden todos
    los filtros de abajo como "sin límite de fechas".

    >>> rango_de("cualquiera")[0]
    '30'
    >>> rango_de("todo")[1] is None
    True
    """
    if periodo not in dict(PERIODOS):
        periodo = PERIODO_POR_DEFECTO

    if periodo == "todo":
        return periodo, None, None

    hoy = timezone.localdate()
    return periodo, hoy - timedelta(days=DIAS_HACIA_ATRAS[periodo]), hoy


def _entre(consulta, campo, desde, hasta):
    """Acota la consulta por fecha, salteando los extremos sin definir."""
    if desde:
        consulta = consulta.filter(**{f"{campo}__date__gte": desde})
    if hasta:
        consulta = consulta.filter(**{f"{campo}__date__lte": hasta})
    return consulta


def _conteos_por_estado(modelo, desde, hasta):
    """Cuenta las operaciones de un modelo en cada estado, en UNA consulta.

    Se filtra por ``creado_en``, o sea **cuándo se inició** la operación. No
    por ``confirmado_en``, que es lo que usa RF031 para las ganancias: una
    cancelada no tiene fecha de confirmación y nunca aparecería. Son dos
    preguntas distintas y cada una necesita su propia fecha; la pantalla lo
    aclara al lado de cada número.
    """
    estados = modelo.Estado
    consulta = _entre(modelo.objects.all(), "creado_en", desde, hasta)

    return consulta.aggregate(
        pendientes=Count("pk", filter=Q(estado=estados.PENDIENTE)),
        pagadas=Count("pk", filter=Q(estado=estados.CONFIRMADA)),
        canceladas=Count("pk", filter=Q(estado=estados.CANCELADA)),
        anuladas=Count("pk", filter=Q(estado=estados.ANULADA)),
        total=Count("pk"),
    )


def _sumar(*conteos):
    """Suma clave por clave los diccionarios de conteos."""
    claves = conteos[0].keys()
    return {clave: sum(conteo[clave] for conteo in conteos) for clave in claves}


def _clientes():
    """Clientes activos e inactivos. Es una foto de HOY, no del período.

    Un cliente no se "da de baja en marzo": tiene o no tiene la marca
    ``activo`` ahora mismo. Filtrar esto por fechas daría un número que no
    significa nada.
    """
    return Cliente.objects.aggregate(
        activos=Count("pk", filter=Q(activo=True)),
        inactivos=Count("pk", filter=Q(activo=False)),
    )


def _caja(desde, hasta):
    """Estado de la caja: sucursal, saldos por moneda y diferencias.

    Los saldos son el valor actual, no del período, por el mismo motivo que
    los clientes.

    Se devuelven los decimales de cada moneda junto con su saldo. Es a
    propósito: el filtro de plantilla puede averiguarlos solo, pero lo hace
    con una consulta por moneda, y acá se trata justamente de tener el costo
    en consultas acotado.
    """
    sucursal = Sucursal.objects.first()

    saldos = [
        {
            "moneda": fila["moneda__codigo"],
            "decimales": fila["moneda__decimales"],
            "total": fila["total"],
        }
        for fila in SaldoCaja.objects.values("moneda__codigo", "moneda__decimales")
        .annotate(total=Sum("saldo"))
        .order_by("moneda__codigo")
    ]

    diferencias = _entre(DiferenciaCaja.objects.all(), "creado_en", desde, hasta)
    diferencias_por_moneda = [
        {
            "moneda": fila["moneda__codigo"],
            "decimales": fila["moneda__decimales"],
            "cantidad": fila["cantidad"],
            "total": fila["total"],
        }
        for fila in diferencias.values("moneda__codigo", "moneda__decimales")
        .annotate(cantidad=Count("pk"), total=Sum("monto"))
        .order_by("moneda__codigo")
    ]

    return {
        "sucursal": sucursal,
        "saldos": saldos,
        "diferencias": diferencias_por_moneda,
        "diferencias_registradas": sum(
            fila["cantidad"] for fila in diferencias_por_moneda
        ),
    }


def _facturas(desde, hasta):
    """Facturas del período, en una consulta.

    Hay **dos** formas distintas de que una factura salga mal y se cuentan
    separadas, porque se arreglan en lugares diferentes:

    - ``estado=ERROR``: Factura Segura rechazó la petición. El problema es
      nuestro, en los datos que mandamos.
    - ``estado_fiscal=RECHAZADA``: se emitió bien, pero SIFEN la rechazó
      después. El problema está del lado del fisco.

    Juntarlas en un solo número escondería dónde hay que mirar.
    """
    consulta = _entre(Factura.objects.all(), "creada_en", desde, hasta)

    return consulta.aggregate(
        emitidas=Count("pk", filter=Q(estado=Factura.Estado.GENERADA)),
        aprobadas=Count("pk", filter=Q(estado_fiscal=Factura.EstadoFiscal.APROBADA)),
        rechazadas=Count("pk", filter=Q(estado_fiscal=Factura.EstadoFiscal.RECHAZADA)),
        con_error=Count("pk", filter=Q(estado=Factura.Estado.ERROR)),
        a_verificar=Count("pk", filter=Q(estado=Factura.Estado.A_VERIFICAR)),
    )


def _ventas_pendientes_de_entrega():
    """Ventas esperando que el cajero entregue el efectivo.

    **Sin filtro de período**, y la diferencia importa: es una lista de
    trabajo, no una estadística. Una venta de hace dos meses que todavía
    nadie entregó es justamente la que hay que ver, y con el filtro de
    "últimos 7 días" desaparecería de la pantalla.
    """
    return VentaDivisa.objects.filter(estado=VentaDivisa.Estado.PENDIENTE).count()


def cotizaciones_a_guaranies():
    """Cuántos guaraníes vale una unidad de cada moneda, en UNA consulta.

    Usa la **tasa de compra vigente**: la que la casa de cambio paga por esa
    moneda. Es la valuación conservadora —nunca infla la ganancia— y es una
    decisión, no un hecho: con la tasa de venta el total daría más alto.

    El guaraní vale 1 por definición y no necesita cotización.

    Una moneda sin tasa activa hacia el guaraní **no aparece** en el
    diccionario. Quien lo use tiene que notar la ausencia y avisar, no
    inventar un valor: una ganancia convertida con una cotización que no
    existe es un número falso.
    """
    cotizaciones = {MONEDA_GLOBAL: Decimal(1)}
    vigentes = TasaCambio.objects.filter(
        activo=True, moneda_destino__codigo=MONEDA_GLOBAL
    ).values_list("moneda_origen__codigo", "tasa_compra")

    for codigo, tasa_compra in vigentes:
        cotizaciones[codigo] = tasa_compra

    return cotizaciones


def _a_guaranies(monto, codigo, cotizaciones):
    """Convierte un importe a guaraníes, o `None` si no hay cotización."""
    cotizacion = cotizaciones.get(codigo)
    if cotizacion is None:
        return None
    return (monto * cotizacion).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ganancias_en_guaranies(resumen, cotizaciones):
    """Agrega a cada fila del desglose su equivalente en guaraníes.

    Devuelve además el total global —ahora sí con unidad— y la lista de
    monedas que quedaron fuera por no tener cotización vigente. Esa lista se
    muestra en la pantalla: callarla daría un total que parece completo y no
    lo está.
    """
    filas = []
    total = Decimal("0.00")
    sin_cotizacion = []

    for fila in resumen["desglose"]:
        equivalente = _a_guaranies(fila["total"], fila["moneda"], cotizaciones)
        if equivalente is None:
            sin_cotizacion.append(fila["moneda"])
        else:
            total += equivalente
        filas.append({**fila, "equivalente_pyg": equivalente})

    return {
        "desglose": filas,
        "total_pyg": total,
        "sin_cotizacion": sin_cotizacion,
        # Si todo ya está en guaraníes no hubo nada que convertir, y la
        # columna de equivalencias sería la misma cifra repetida.
        "hay_conversion": any(
            fila["moneda"] != MONEDA_GLOBAL for fila in resumen["desglose"]
        ),
        "operaciones": resumen["operaciones"],
        "comision_pyg": _sumar_convertido(resumen, cotizaciones, "comision"),
        "diferencia_tasa_pyg": _sumar_convertido(resumen, cotizaciones, "diferencia_tasa"),
    }


def _sumar_convertido(resumen, cotizaciones, clave):
    """Suma en guaraníes una de las dos partes de la ganancia."""
    total = Decimal("0.00")
    for fila in resumen["desglose"]:
        equivalente = _a_guaranies(fila[clave], fila["moneda"], cotizaciones)
        if equivalente is not None:
            total += equivalente
    return total


def _tramos(desde, hasta, maximo=MAXIMO_BARRAS):
    """Parte el período en tramos contiguos de días, como mucho `maximo`.

    Un día por barra mientras entren; si el período es más largo, cada barra
    junta varios días. Nunca pasa de `maximo` barras, así que el gráfico no
    se vuelve ilegible ni el costo depende del largo del período.
    """
    dias = (hasta - desde).days + 1
    cantidad = min(maximo, dias)
    tamano = ceil(dias / cantidad)

    tramos = []
    inicio = desde
    while inicio <= hasta:
        fin = min(inicio + timedelta(days=tamano - 1), hasta)
        tramos.append({"desde": inicio, "hasta": fin, "total": Decimal("0.00")})
        inicio = fin + timedelta(days=1)
    return tramos, tamano


def serie_de_ganancias(desde, hasta, cotizaciones):
    """Ganancia en guaraníes a lo largo del período, lista para dibujar.

    **No reimplementa la regla de ganancia.** Usa las mismas funciones de
    RF031 que usa `resumen_ganancias`, operación por operación, así que si
    allá se cambia la fórmula acá cambia sola. Hay una prueba que compara la
    suma de las barras contra `resumen_ganancias` del período completo.

    Se recorren las operaciones una sola vez —**dos consultas en total**— en
    vez de pedirle a RF031 un resumen por cada barra, que habría costado dos
    consultas por barra.

    Con "Todo" no hay fechas de corte: el rango sale de la primera y la
    última operación confirmada, que ya se están recorriendo igual.

    La geometría del SVG se calcula acá y no en la plantilla para poder
    probarla.
    """
    compras, ventas = operaciones_confirmadas(desde, hasta)

    puntos = []
    for compra in compras:
        moneda, comision, diferencia = _ganancia_compra(compra)
        puntos.append((timezone.localtime(compra.confirmado_en).date(), moneda.codigo, comision + diferencia))
    for venta in ventas:
        moneda, comision, diferencia = _ganancia_venta(venta)
        puntos.append((timezone.localtime(venta.confirmado_en).date(), moneda.codigo, comision + diferencia))

    if not puntos:
        return {"barras": [], "maximo": Decimal("0.00"), "dias_por_barra": 0}

    primera = desde or min(fecha for fecha, _, _ in puntos)
    ultima = hasta or max(fecha for fecha, _, _ in puntos)
    tramos, dias_por_barra = _tramos(primera, ultima)

    for fecha, codigo, ganancia in puntos:
        if fecha < primera or fecha > ultima:
            continue
        en_guaranies = _a_guaranies(ganancia, codigo, cotizaciones)
        if en_guaranies is None:
            continue
        indice = min((fecha - primera).days // dias_por_barra, len(tramos) - 1)
        tramos[indice]["total"] += en_guaranies

    return _dibujar(tramos, dias_por_barra)


def _dibujar(tramos, dias_por_barra):
    """Convierte los tramos en rectángulos con sus coordenadas."""
    maximo = max((tramo["total"] for tramo in tramos), default=Decimal("0.00"))
    alto_util = GRAFICO_ALTO - GRAFICO_MARGEN_INFERIOR
    ancho_tramo = GRAFICO_ANCHO / len(tramos)
    # Una franja de aire entre barras, proporcional, para que no se peguen.
    ancho_barra = ancho_tramo * 0.62

    barras = []
    for indice, tramo in enumerate(tramos):
        if maximo > 0:
            alto = float(tramo["total"] / maximo) * alto_util
        else:
            alto = 0.0
        # Una barra de 0 no se ve; se le deja un hilo para que el día exista
        # visualmente en vez de parecer un hueco en el gráfico.
        alto = max(alto, 1.5) if tramo["total"] > 0 else 0.0
        barras.append(
            {
                "x": round(indice * ancho_tramo + (ancho_tramo - ancho_barra) / 2, 2),
                "y": round(alto_util - alto, 2),
                "ancho": round(ancho_barra, 2),
                "alto": round(alto, 2),
                "centro_x": round(indice * ancho_tramo + ancho_tramo / 2, 2),
                "etiqueta": tramo["desde"].strftime("%d/%m"),
                "total": tramo["total"],
                "titulo": _titulo_de_barra(tramo, dias_por_barra),
            }
        )

    return {"barras": barras, "maximo": maximo, "dias_por_barra": dias_por_barra}


def _titulo_de_barra(tramo, dias_por_barra):
    """Texto que aparece al pasar el mouse por una barra."""
    importe = formatear_numero(tramo["total"], 0)
    if dias_por_barra == 1:
        return f"{tramo['desde']:%d/%m/%Y}: {importe} PYG"
    return (
        f"{tramo['desde']:%d/%m/%Y} al {tramo['hasta']:%d/%m/%Y}: {importe} PYG"
    )


def metricas(periodo=PERIODO_POR_DEFECTO):
    """Todas las métricas del tablero para el período pedido.

    Las ganancias vienen de RF031 con el mismo rango de fechas que el resto
    de la pantalla, y se devuelven dos veces: `ganancias` tal como las da
    RF031, por moneda, y `ganancias_pyg` con todo valuado en guaraníes para
    poder dar un total con unidad.

    Sin datos no falla: devuelve todo en cero y las listas vacías.
    """
    periodo, desde, hasta = rango_de(periodo)

    compras = _conteos_por_estado(CompraDivisa, desde, hasta)
    ventas = _conteos_por_estado(VentaDivisa, desde, hasta)

    cotizaciones = cotizaciones_a_guaranies()
    ganancias = resumen_ganancias(desde, hasta)

    return {
        "periodo": periodo,
        "periodos": PERIODOS,
        "desde": desde,
        "hasta": hasta,
        "operaciones": {
            "compras": compras,
            "ventas": ventas,
            "total": _sumar(compras, ventas),
        },
        "clientes": _clientes(),
        "caja": _caja(desde, hasta),
        "facturas": _facturas(desde, hasta),
        "ventas_pendientes_de_entrega": _ventas_pendientes_de_entrega(),
        "ganancias": ganancias,
        "ganancias_pyg": _ganancias_en_guaranies(ganancias, cotizaciones),
        "serie": serie_de_ganancias(desde, hasta, cotizaciones),
    }
