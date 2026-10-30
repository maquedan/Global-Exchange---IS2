from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone

from apps.comisiones.models import ComisionCategoria
from apps.conversiones.services import calcular_comision, calcular_conversion, iniciar_compra, iniciar_venta, CompraNoDisponible, VentaNoDisponible
from apps.conversiones.models import CompraDivisa, VentaDivisa
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.menu import tiene_rol
from apps.clientes.models import Cliente

from decimal import Decimal, InvalidOperation

from .forms import DatosOperacionTerminalForm, IdentificarClienteTerminalForm


def requiere_terminal(vista):
    """Restringe las pantallas de autoservicio al perfil terminal."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not tiene_rol(request.user, "terminal"):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura

def cliente_terminal_activo(request):
    """Obtiene el cliente activo identificado para la operación de Terminal."""
    cliente_id = request.session.get("terminal_cliente_id")

    cliente = Cliente.objects.filter(
        pk=cliente_id,
        activo=True,
    ).first()

    if cliente is None:
        request.session.pop("terminal_cliente_id", None)

    return cliente


@login_required
@requiere_terminal
def inicio_terminal(request):
    """Pantalla inicial del modo terminal de autoservicio (GEG9-55 - RF054)."""
    return render(request, "terminal/inicio.html")


@login_required
@requiere_terminal
def identificar_cliente_terminal(request):
    """Identifica un cliente activo por documento o RUC para GEG9-56 - RF055."""
    formulario = IdentificarClienteTerminalForm(request.POST or None)

    if request.method == "POST" and formulario.is_valid():
        identificador = formulario.cleaned_data["identificador"]

        coincidencias = list(
            Cliente.objects.filter(activo=True)
            .filter(
                Q(documento__iexact=identificador)
                | Q(ruc__iexact=identificador)
            )[:2]
        )

        if not coincidencias:
            formulario.add_error(
                "identificador",
                "No encontramos un cliente activo con ese documento o RUC.",
            )
        elif len(coincidencias) > 1:
            formulario.add_error(
                "identificador",
                "El identificador es ambiguo. Solicitá asistencia al personal.",
            )
        else:
            cliente = coincidencias[0]
            request.session["terminal_cliente_id"] = cliente.pk

            for clave in (
                "terminal_tipo_operacion",
                "terminal_compra_id",
                "terminal_venta_id",
                "terminal_moneda_origen_id",
                "terminal_moneda_destino_id",
                "terminal_monto",
                "terminal_tasa_cambio_id",
            ):
                request.session.pop(clave, None)

            return redirect("terminal:seleccionar_operacion")

    return render(
        request,
        "terminal/identificar_cliente.html",
        {"formulario": formulario},
    )


@login_required
@requiere_terminal
def seleccionar_operacion_terminal(request):
    """Permite elegir compra o venta para continuar el flujo guiado."""
    cliente = cliente_terminal_activo(request)

    if cliente is None:
        return redirect("terminal:identificar")

    error = None

    if request.method == "POST":
        tipo_operacion = request.POST.get("tipo_operacion")

        if tipo_operacion not in ("compra", "venta"):
            error = "Seleccioná una operación para continuar."
        else:
            request.session["terminal_tipo_operacion"] = tipo_operacion

            for clave in (
                "terminal_compra_id",
                "terminal_venta_id",
                "terminal_moneda_origen_id",
                "terminal_moneda_destino_id",
                "terminal_monto",
                "terminal_tasa_cambio_id",
            ):
                request.session.pop(clave, None)

            return redirect("terminal:datos_operacion")

    return render(
        request,
        "terminal/seleccionar_operacion.html",
        {
            "cliente": cliente,
            "error": error,
        },
    )


@login_required
@requiere_terminal
def datos_operacion_terminal(request):
    """Solicita monedas y monto antes de simular la operación (RF055)."""
    cliente = cliente_terminal_activo(request)
    tipo_operacion = request.session.get("terminal_tipo_operacion")

    if cliente is None:
        return redirect("terminal:identificar")

    if tipo_operacion not in ("compra", "venta"):
        return redirect("terminal:seleccionar_operacion")

    formulario = DatosOperacionTerminalForm(
        request.POST or None,
        tipo_operacion=tipo_operacion,
    )

    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data

        request.session["terminal_moneda_origen_id"] = datos["moneda_origen"].pk
        request.session["terminal_moneda_destino_id"] = datos["moneda_destino"].pk
        request.session["terminal_monto"] = str(datos["monto"])

        return redirect("terminal:simulacion")

    return render(
        request,
        "terminal/datos_operacion.html",
        {
            "cliente": cliente,
            "tipo_operacion": tipo_operacion,
            "formulario": formulario,
        },
    )

@login_required
@requiere_terminal
def simulacion_terminal(request):
    """Muestra tasa, comisión y resultado antes de confirmar la operación."""
    cliente = cliente_terminal_activo(request)
    tipo_operacion = request.session.get("terminal_tipo_operacion")
    moneda_origen_id = request.session.get("terminal_moneda_origen_id")
    moneda_destino_id = request.session.get("terminal_moneda_destino_id")
    monto = request.session.get("terminal_monto")

    if cliente is None:
        return redirect("terminal:identificar")

    if tipo_operacion not in ("compra", "venta"):
        return redirect("terminal:seleccionar_operacion")

    if not all((moneda_origen_id, moneda_destino_id, monto)):
        return redirect("terminal:datos_operacion")

    try:
        monto = Decimal(monto)
    except (InvalidOperation, TypeError):
        request.session.pop("terminal_monto", None)
        return redirect("terminal:datos_operacion")

    moneda_origen = Moneda.objects.filter(
        pk=moneda_origen_id,
        activo=True,
    ).first()
    moneda_destino = Moneda.objects.filter(
        pk=moneda_destino_id,
        activo=True,
    ).first()

    if moneda_origen is None or moneda_destino is None:
        return redirect("terminal:datos_operacion")

    tasa_cambio = (
        TasaCambio.objects.filter(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )

    comision = ComisionCategoria.objects.filter(
        categoria=cliente.categoria,
    ).first()

    if tasa_cambio is None or comision is None:
        return render(
            request,
            "terminal/simulacion.html",
            {
                "cliente": cliente,
                "tipo_operacion": tipo_operacion,
                "error": (
                    "No existe una tasa o comisión vigente para "
                    "esta operación."
                ),
            },
        )

    tasa_aplicada = tasa_cambio.tasa_compra
    request.session["terminal_tasa_cambio_id"] = tasa_cambio.pk

    if tipo_operacion == "compra":
        monto_comision = calcular_comision(monto, comision.porcentaje)
        monto_resultado = calcular_conversion(monto, tasa_aplicada, "compra")
        total = monto + monto_comision

        moneda_comision = moneda_origen
        moneda_total = moneda_origen
        etiqueta_resultado = "Vas a recibir"
        etiqueta_total = "Total a pagar"
    else:
        monto_convertido = calcular_conversion(monto, tasa_aplicada, "compra")
        monto_comision = calcular_comision(
            monto_convertido,
            comision.porcentaje,
        )
        monto_resultado = monto_convertido - monto_comision
        total = monto

        moneda_comision = moneda_destino
        moneda_total = moneda_origen
        etiqueta_resultado = "Vas a recibir"
        etiqueta_total = "Monto que entregarás"

    return render(
        request,
        "terminal/simulacion.html",
        {
            "cliente": cliente,
            "tipo_operacion": tipo_operacion,
            "moneda_origen": moneda_origen,
            "moneda_destino": moneda_destino,
            "monto": monto,
            "tasa_aplicada": tasa_aplicada,
            "porcentaje_comision": comision.porcentaje,
            "monto_comision": monto_comision,
            "monto_resultado": monto_resultado,
            "total": total,
            "moneda_comision": moneda_comision,
            "moneda_total": moneda_total,
            "etiqueta_resultado": etiqueta_resultado,
            "etiqueta_total": etiqueta_total,
        },
    )

@login_required
@requiere_terminal
@require_POST
def confirmar_operacion_terminal(request):
    """Crea una operación pendiente desde el flujo guiado de la terminal."""
    cliente = cliente_terminal_activo(request)
    tipo_operacion = request.session.get("terminal_tipo_operacion")
    moneda_origen_id = request.session.get("terminal_moneda_origen_id")
    moneda_destino_id = request.session.get("terminal_moneda_destino_id")
    monto = request.session.get("terminal_monto")
    tasa_cambio_id = request.session.get("terminal_tasa_cambio_id")

    if cliente is None:
        return redirect("terminal:identificar")

    if tipo_operacion not in ("compra", "venta"):
        return redirect("terminal:seleccionar_operacion")

    if not all((moneda_origen_id, moneda_destino_id, monto, tasa_cambio_id)):
        return redirect("terminal:datos_operacion")

    moneda_origen = Moneda.objects.filter(
        pk=moneda_origen_id,
        activo=True,
    ).first()
    moneda_destino = Moneda.objects.filter(
        pk=moneda_destino_id,
        activo=True,
    ).first()

    if moneda_origen is None or moneda_destino is None:
        return redirect("terminal:datos_operacion")

    tasa_vigente = (
        TasaCambio.objects.filter(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
            activo=True,
            vigente_desde__lte=timezone.now(),
        )
        .order_by("-vigente_desde")
        .first()
    )

    if tasa_vigente is None or tasa_vigente.pk != tasa_cambio_id:
        return render(
            request,
            "terminal/simulacion.html",
            {
                "cliente": cliente,
                "tipo_operacion": tipo_operacion,
                "error": (
                    "La cotización cambió o ya no está vigente. "
                    "Revisá nuevamente la simulación antes de confirmar."
                ),
            },
        )

    try:
        if tipo_operacion == "compra":
            operacion = iniciar_compra(
                usuario=request.user,
                cliente_id=cliente.pk,
                moneda_pagada=moneda_origen,
                moneda_adquirida=moneda_destino,
                monto_pagado=monto,
                desde_terminal=True,
            )
            request.session["terminal_compra_id"] = operacion.pk
            request.session.pop("terminal_venta_id", None)
        else:
            operacion = iniciar_venta(
                usuario=request.user,
                cliente_id=cliente.pk,
                moneda_entregada=moneda_origen,
                moneda_acreditada=moneda_destino,
                monto_entregado=monto,
                desde_terminal=True,
            )
            request.session["terminal_venta_id"] = operacion.pk
            request.session.pop("terminal_compra_id", None)

    except (CompraNoDisponible, VentaNoDisponible) as error:
        return render(
            request,
            "terminal/simulacion.html",
            {
                "cliente": cliente,
                "tipo_operacion": tipo_operacion,
                "error": str(error),
            },
        )

    return redirect("terminal:operacion_pendiente")

@login_required
@requiere_terminal
def operacion_pendiente_terminal(request):
    """Muestra el cierre del flujo tras registrar una operación pendiente."""
    cliente = cliente_terminal_activo(request)
    compra_id = request.session.get("terminal_compra_id")
    venta_id = request.session.get("terminal_venta_id")

    if cliente is None:
        return redirect("terminal:identificar")

    operacion = None
    tipo_operacion = None

    if compra_id:
        operacion = CompraDivisa.objects.filter(
            pk=compra_id,
            cliente=cliente,
        ).first()
        tipo_operacion = "compra"
    elif venta_id:
        operacion = VentaDivisa.objects.filter(
            pk=venta_id,
            cliente=cliente,
        ).first()
        tipo_operacion = "venta"

    if operacion is None:
        return redirect("terminal:inicio")

    return render(
        request,
        "terminal/operacion_pendiente.html",
        {
            "cliente": cliente,
            "operacion": operacion,
            "tipo_operacion": tipo_operacion,
        },
    )


@login_required
@requiere_terminal
@require_POST
def reiniciar_terminal(request):
    """Limpia los datos temporales y vuelve al inicio de la terminal."""
    for clave in (
        "terminal_cliente_id",
        "terminal_tipo_operacion",
        "terminal_compra_id",
        "terminal_venta_id",
        "terminal_moneda_origen_id",
        "terminal_moneda_destino_id",
        "terminal_monto",
        "terminal_tasa_cambio_id",
    ):
        request.session.pop(clave, None)

    return redirect("terminal:inicio")