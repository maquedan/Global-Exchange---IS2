"""Visualización de tasas de cambio en tiempo real (RF016 — GEG9-28).

Esta app no tiene modelos propios: solo LEE los datos que administran
apps.monedas (catálogo de divisas) y apps.tasa_cambios (tasas vigentes e
históricas), para mostrarlos al usuario final. Inspirado en el selector de
monedas de xe.com/es/currencycharts: se elige un par con dos desplegables
y se ve el gráfico de ese par, con estadísticas del período.
"""
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


def _formatear_tasa(valor):
    """Muestra al menos dos decimales y conserva hasta seis si son significativos."""
    entero, decimales = f"{Decimal(valor):.6f}".split(".")
    return f"{entero}.{decimales.rstrip('0').ljust(2, '0')}"


def _pares_disponibles():
    """Los pares (origen, destino) que tienen al menos una tasa cargada."""
    return list(
        TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
        .order_by("moneda_origen__codigo", "moneda_destino__codigo")
        .values_list("moneda_origen__codigo", "moneda_destino__codigo")
        .distinct()
    )


def _historial_del_par(codigo_origen, codigo_destino):
    """Todas las tasas (vigentes e históricas) de ESE par, de más vieja a más nueva."""
    return list(
        TasaCambio.objects.filter(
            moneda_origen__codigo=codigo_origen,
            moneda_destino__codigo=codigo_destino,
        )
        .select_related("moneda_origen", "moneda_destino")
        .order_by("vigente_desde")
    )


def _estadisticas(historial, campo):
    """Variación, máximo, mínimo y promedio de un campo ('tasa_compra' o
    'tasa_venta') a lo largo del historial mostrado.

    Los valores ya salen formateados como texto (".2f", punto decimal fijo)
    en vez de dejar que la plantilla los formatee: los filtros de Django
    (floatformat, stringformat) respetan el idioma del sitio y muestran los
    decimales con COMA en español, lo que rompería la comparación que hace
    el JavaScript del auto-refresco (que siempre usa punto).
    """
    valores = [getattr(tasa, campo) for tasa in historial]
    primero, ultimo = valores[0], valores[-1]
    variacion = (
        ((float(ultimo) - float(primero)) / float(primero)) * 100
        if primero
        else 0
    )

    return {
        "variacion": f"{variacion:+.2f}",
        "subio": variacion > 0,
        "bajo": variacion < 0,
        "maximo": _formatear_tasa(max(valores)),
        "minimo": _formatear_tasa(min(valores)),
        "promedio": _formatear_tasa(sum(valores) / len(valores)),
    }


def _resumen_de_pares(pares_disponibles):
    """Para la grilla de 'pares populares': la tasa vigente de cada par y
    cómo cambió respecto a la entrada anterior (si hay al menos dos)."""
    resumen = []
    for codigo_origen, codigo_destino in pares_disponibles:
        historial = _historial_del_par(codigo_origen, codigo_destino)
        if not historial:
            continue

        ultima = historial[-1]
        cambio = None
        if len(historial) > 1:
            anterior = float(historial[-2].tasa_venta)
            actual = float(ultima.tasa_venta)
            if anterior:
                cambio = round(((actual - anterior) / anterior) * 100, 2)

        resumen.append(
            {
                "origen": ultima.moneda_origen,
                "destino": ultima.moneda_destino,
                "compra": _formatear_tasa(ultima.tasa_compra),
                "venta": _formatear_tasa(ultima.tasa_venta),
                "cambio": cambio,
            }
        )
    return resumen


@login_required
def panel(request):
    """Panel de cotizaciones: elegís un par con los desplegables y ves su
    gráfico de evolución, con estadísticas del período mostrado."""
    monedas = Moneda.objects.filter(activo=True).order_by("codigo")
    pares_disponibles = _pares_disponibles()

    codigo_origen = request.GET.get("origen", "")
    codigo_destino = request.GET.get("destino", "")

    # Solo elegimos un par por defecto si la URL no pedía ninguno en
    # particular (primera visita). Si el usuario SÍ eligió un par (aunque no
    # tenga datos todavía), respetamos su elección y mostramos el estado
    # vacío con sugerencias, en vez de reemplazarlo en silencio por otro.
    if not codigo_origen and not codigo_destino and pares_disponibles:
        codigo_origen, codigo_destino = pares_disponibles[0]

    historial = _historial_del_par(codigo_origen, codigo_destino) if codigo_origen else []

    contexto = {
        "monedas": monedas,
        "pares_disponibles": pares_disponibles,
        "codigo_origen": codigo_origen,
        "codigo_destino": codigo_destino,
        "historial": historial,
        "activa": next((t for t in reversed(historial) if t.activo), None),
        "resumen_pares": _resumen_de_pares(pares_disponibles),
    }

    if contexto["activa"]:
        contexto["tasa_venta_actual"] = _formatear_tasa(
            contexto["activa"].tasa_venta
        )

    if historial:
        contexto["estadisticas_compra"] = _estadisticas(historial, "tasa_compra")
        contexto["estadisticas_venta"] = _estadisticas(historial, "tasa_venta")
        contexto["historial_json"] = [
            {
                "fecha": tasa.vigente_desde.isoformat(),
                "compra": float(tasa.tasa_compra),
                "venta": float(tasa.tasa_venta),
            }
            for tasa in historial
        ]

    return render(request, "tasas/panel.html", contexto)


@login_required
def datos_actuales(request):
    """Endpoint JSON con SOLO las tasas vigentes ahora, para el auto-refresco.

    El panel lo consulta cada 20 segundos por JavaScript, sin recargar la
    página, para sentirse "en tiempo real".
    """
    activas = TasaCambio.objects.filter(activo=True).select_related(
        "moneda_origen",
        "moneda_destino",
    )
    datos = [
        {
            "par": f"{tasa.moneda_origen.codigo}/{tasa.moneda_destino.codigo}",
            "compra": float(tasa.tasa_compra),
            "venta": float(tasa.tasa_venta),
            "actualizado_en": tasa.actualizado_en.isoformat(),
        }
        for tasa in activas
    ]
    return JsonResponse({"tasas": datos})
