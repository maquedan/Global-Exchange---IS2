"""Armado del DE — Documento Electrónico (RF026 — GEG9-50).

Traduce una compra o una venta de divisas al "JSON resumido de Factura
Electrónica" que espera `calcular_de`. Los nombres de los campos son los del
SIFEN (`dRucEm`, `gCamItem`, ...), no los nuestros: se dejan tal cual para
poder comparar contra el documento de Factura Segura línea por línea.

Los códigos del SIFEN están todos en `codigos_sifen.py`, no acá.
"""
from decimal import ROUND_HALF_UP

from django.conf import settings
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.conversiones.models import CompraDivisa

from . import codigos_sifen as sifen


class DatosDeFacturacionIncompletos(Exception):
    """Faltan datos imprescindibles del cliente o del emisor para facturar."""


def monto_facturable(operacion):
    """Importe a facturar, en guaraníes, y la cifra original de la operación.

    Decisión del equipo para RF026 (documentada en el CHIA del Sprint 5): se
    factura el **monto total** de la operación, no solo la comisión.

    Factura Segura solo acepta `cMoneOpe` en PYG o USD, y nuestras
    operaciones pueden ser en EUR, BRL, ARS, GBP o JPY. En vez de dos caminos
    según la moneda, se factura **siempre en guaraníes**: así no hace falta
    mandar `dTiCam` ni lidiar con las reglas de decimales del SIFEN para
    moneda extranjera. La cifra en la moneda original se guarda igual en la
    `Factura` y se muestra en el comprobante.

    La conversión usa `tasa_aplicada`, la tasa ya congelada en la operación —
    el mismo criterio que `apps.pagos.services.monto_para_pasarela`. Todas
    las cotizaciones del sistema son contra el guaraní, así que esa tasa son
    guaraníes por unidad de la moneda de la operación.

    Devuelve ``(monto_pyg, monto_origen, moneda_origen)``.
    """
    if isinstance(operacion, CompraDivisa):
        base = operacion.total_a_pagar
        codigo = operacion.moneda_pagada.codigo
    else:
        base = operacion.monto_entregado
        codigo = operacion.moneda_entregada.codigo

    if codigo == "PYG":
        monto_pyg = base
    else:
        monto_pyg = base * operacion.tasa_aplicada

    # El guaraní no tiene decimales.
    return monto_pyg.to_integral_value(rounding=ROUND_HALF_UP), base, codigo


def _requerido(nombre, por_defecto=""):
    valor = getattr(settings, nombre, por_defecto)
    if not valor:
        raise DatosDeFacturacionIncompletos(
            f"Falta {nombre} en la configuración: no se puede emitir la factura."
        )
    return valor


def datos_emisor():
    """Datos del emisor, desde la configuración (nunca escritos en el código).

    Los valores reales dependen del emisor que la cátedra asocie al usuario
    ESI de Factura Segura; todavía no los tenemos. Los valores por defecto de
    `config/settings/base.py` son **claramente de prueba** y la factura no
    sirve ante el SIFEN hasta que se completen de verdad en el `.env`.
    """
    return {
        "dNumTim": _requerido("FACTURACION_TIMBRADO"),
        "dFeIniT": _requerido("FACTURACION_TIMBRADO_INICIO"),
        "dRucEm": _requerido("FACTURACION_EMISOR_RUC"),
        "dDVEmi": _requerido("FACTURACION_EMISOR_DV"),
        "iTipCont": _requerido("FACTURACION_EMISOR_TIPO_CONTRIBUYENTE"),
        "dNomEmi": _requerido("FACTURACION_EMISOR_NOMBRE"),
        "dDirEmi": _requerido("FACTURACION_EMISOR_DIRECCION"),
        "dNumCas": _requerido("FACTURACION_EMISOR_NUMERO_CASA"),
        "cDepEmi": _requerido("FACTURACION_EMISOR_DEPARTAMENTO"),
        "dDesDepEmi": _requerido("FACTURACION_EMISOR_DEPARTAMENTO_NOMBRE"),
        "cCiuEmi": _requerido("FACTURACION_EMISOR_CIUDAD"),
        "dDesCiuEmi": _requerido("FACTURACION_EMISOR_CIUDAD_NOMBRE"),
        "dTelEmi": _requerido("FACTURACION_EMISOR_TELEFONO"),
        "dEmailE": _requerido("FACTURACION_EMISOR_EMAIL"),
        "gActEco": _actividades_economicas(),
    }


def _actividades_economicas():
    """Las actividades económicas del emisor, en el formato que pide `gActEco`.

    En la configuración vienen como ``codigo:descripcion`` separadas por
    ``|``, porque son varias y cada código tiene que conservar su propia
    descripción (el emisor que nos habilitaron tiene dos).
    """
    actividades = []
    for parte in _requerido("FACTURACION_EMISOR_ACTIVIDADES").split("|"):
        if not parte.strip():
            continue
        codigo, _, descripcion = parte.partition(":")
        if not codigo.strip() or not descripcion.strip():
            raise DatosDeFacturacionIncompletos(
                f"La actividad económica «{parte.strip()}» no tiene el formato "
                "codigo:descripcion (por ejemplo 62010:Actividades de "
                "programación informática)."
            )
        actividades.append(
            {"cActEco": codigo.strip(), "dDesActEco": descripcion.strip()}
        )

    if not actividades:
        raise DatosDeFacturacionIncompletos(
            "Falta FACTURACION_EMISOR_ACTIVIDADES en la configuración: el SIFEN "
            "exige al menos una actividad económica del emisor."
        )
    return actividades


def _ruc_y_dv(cliente):
    """Separa el RUC del cliente jurídico en número y dígito verificador.

    El SIFEN pide `dRucRec` y `dDVRec` por separado, pero el modelo `Cliente`
    (RF001) guarda un solo campo `ruc` de texto libre. Si no viene con el
    formato ``80002247-5`` no se puede partir: antes que mandar un DV
    inventado, la factura queda en error con un mensaje claro.
    """
    partes = (cliente.ruc or "").strip().split("-")
    if len(partes) != 2 or not partes[0].strip() or not partes[1].strip():
        raise DatosDeFacturacionIncompletos(
            f"El RUC de «{cliente}» ({cliente.ruc or 'vacío'}) no tiene el formato "
            "RUC-DV (por ejemplo 80002247-5), que es como el SIFEN lo necesita."
        )
    return partes[0].strip(), partes[1].strip()


def datos_receptor(cliente):
    """Datos del receptor según sea persona física o jurídica."""
    if not cliente.email:
        raise DatosDeFacturacionIncompletos(
            f"El cliente «{cliente}» no tiene correo electrónico, y Factura "
            "Segura lo exige para emitir la factura."
        )

    comunes = {
        "cPaisRec": sifen.PAIS_PARAGUAY,
        "dNomRec": str(cliente),
        "dEmailRec": cliente.email,
    }

    if cliente.tipo == Cliente.Tipo.JURIDICA:
        ruc, dv = _ruc_y_dv(cliente)
        return {
            **comunes,
            "iNatRec": sifen.RECEPTOR_CONTRIBUYENTE,
            "iTiOpe": sifen.TIPO_OPERACION_B2B,
            "iTiContRec": sifen.TIPO_CONTRIBUYENTE_PERSONA_JURIDICA,
            "dRucRec": ruc,
            "dDVRec": dv,
        }

    if not cliente.documento:
        raise DatosDeFacturacionIncompletos(
            f"El cliente «{cliente}» no tiene número de documento, que es como "
            "se identifica al receptor no contribuyente."
        )

    # Persona física: consumidor final, identificado con la cédula. No se usan
    # `dRucRec` ni `dDVRec` — la cédula no lleva dígito verificador.
    return {
        **comunes,
        "iNatRec": sifen.RECEPTOR_NO_CONTRIBUYENTE,
        "iTiOpe": sifen.TIPO_OPERACION_B2C,
        "iTipIDRec": sifen.TIPO_IDENTIFICACION_CEDULA,
        "dNumIDRec": cliente.documento,
    }


def _descripcion_item(operacion):
    if isinstance(operacion, CompraDivisa):
        return (
            f"Compra de divisas #{operacion.pk}: "
            f"{operacion.moneda_pagada.codigo} a {operacion.moneda_adquirida.codigo}"
        )
    return (
        f"Venta de divisas #{operacion.pk}: "
        f"{operacion.moneda_entregada.codigo} a {operacion.moneda_acreditada.codigo}"
    )


def _codigo_item(operacion):
    tipo = "COM" if isinstance(operacion, CompraDivisa) else "VEN"
    return f"{tipo}-{operacion.pk}"


def _informacion_adicional(monto_pyg, monto_origen, moneda_origen, operacion):
    """Texto que se imprime en el KuDE (no forma parte del XML firmado).

    Acá van las dos cifras: lo facturado en guaraníes y el importe en la
    moneda real de la operación, con la tasa usada para convertirlo.
    """
    if moneda_origen == "PYG":
        return f"Operación en guaraníes. Total: {monto_pyg:.0f} PYG."
    return (
        f"Importe de la operación: {monto_origen:.2f} {moneda_origen}. "
        f"Tasa aplicada: {operacion.tasa_aplicada:.2f} PYG por {moneda_origen}. "
        f"Total facturado: {monto_pyg:.0f} PYG."
    )


def armar_de(operacion, *, factura):
    """Devuelve el JSON resumido del DE para esta operación.

    Un solo ítem, cantidad 1, por el monto total de la operación en
    guaraníes. La factura es al contado (la operación se cobra antes de
    confirmarse, RF022), y por eso incluye `gPaConEIni`, que el documento
    marca obligatorio en ese caso.
    """
    monto_pyg, monto_origen, moneda_origen = monto_facturable(operacion)
    monto_texto = f"{monto_pyg:.0f}"

    de = {
        "iTipEmi": sifen.TIPO_EMISION_NORMAL,
        "iTiDE": sifen.TIPO_DOCUMENTO_FACTURA,
        "dEst": factura.establecimiento,
        "dPunExp": factura.punto_expedicion,
        "dNumDoc": factura.numero,
        "dFeEmiDE": timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S"),
        "iTipTra": sifen.TIPO_TRANSACCION,
        "iTImp": sifen.TIPO_IMPUESTO_IVA,
        "cMoneOpe": "PYG",
        "dCondTiCam": sifen.TIPO_CAMBIO_GLOBAL,
        **datos_emisor(),
        **datos_receptor(operacion.cliente),
        "iIndPres": sifen.INDICADOR_PRESENCIA,
        "iCondOpe": sifen.CONDICION_OPERACION_CONTADO,
        "gPaConEIni": [
            {
                "iTiPago": sifen.FORMA_PAGO_TRANSFERENCIA,
                "dMonTiPag": monto_texto,
                "cMoneTiPag": "PYG",
                "dTiCamTiPag": "1",
            }
        ],
        "gCamItem": [
            {
                "dCodInt": _codigo_item(operacion),
                "dDesProSer": _descripcion_item(operacion),
                "cUniMed": sifen.UNIDAD_MEDIDA,
                "dCantProSer": "1",
                "dPUniProSer": monto_texto,
                "dDescItem": sifen.SIN_DESCUENTO_ITEM,
                "dDescGloItem": sifen.SIN_DESCUENTO_GLOBAL,
                "dAntPreUniIt": sifen.SIN_ANTICIPO,
                "dAntGloPreUniIt": sifen.SIN_ANTICIPO,
                "iAfecIVA": sifen.AFECTACION_IVA_GRAVADO,
                "dPropIVA": sifen.PROPORCION_IVA_GRAVADA,
                "dTasaIVA": sifen.TASA_IVA,
            }
        ],
        "CDC": sifen.LO_GENERA_FACTURA_SEGURA,
        "dCodSeg": sifen.LO_GENERA_FACTURA_SEGURA,
        "dDVId": sifen.LO_GENERA_FACTURA_SEGURA,
        "dSisFact": sifen.SISTEMA_FACTURACION,
        "dInfAdic": _informacion_adicional(
            monto_pyg, monto_origen, moneda_origen, operacion
        ),
    }

    # `iCondCred` y `dPlazoCre` son del crédito: en una factura al contado no
    # corresponden, así que no se mandan.
    return de
