"""Códigos del SIFEN usados al armar la factura electrónica (RF026 — GEG9-50).

Están todos acá, en un solo lugar, para no tenerlos desparramados por el
código y para que se vea de un vistazo cuáles hacen falta revisar.

El documento de Factura Segura **no lista los valores posibles** de la
mayoría: en cada campo remite al "Manual Técnico de SIFEN 150". Por eso están
separados en dos grupos: los que el documento sí fija explícitamente, y los
que elegimos por interpretación y hay que confirmar contra ese manual antes
de usar esto fuera del ambiente de pruebas. Estos últimos están marcados con
VERIFICAR.
"""

# ---------------------------------------------------------------------------
# Fijados por el documento de Factura Segura (no hay nada que confirmar)
# ---------------------------------------------------------------------------

# iTiDE: "hardcoded Factura electrónica".
TIPO_DOCUMENTO_FACTURA = "1"

# cUniMed: "Factura segura solo soporta 77 UNIDAD".
UNIDAD_MEDIDA = "77"

# dCondTiCam: "hardcoded. Tipo de Cambio Global. Factura Segura no soporta
# tipo de cambio por ítem".
TIPO_CAMBIO_GLOBAL = "1"

# dSisFact: "hardcoded".
SISTEMA_FACTURACION = "1"

# cMoneOpe: "PYG o USD. Factura Segura no soporta otras monedas".
MONEDAS_SOPORTADAS = ("PYG", "USD")

# CDC, dCodSeg y dDVId: "hardcoded. Será generado por Factura Segura" — se
# mandan en cero y los completa el servicio.
LO_GENERA_FACTURA_SEGURA = "0"

# El documento marca estos campos del ítem como hardcoded en 0: Factura Segura
# no soporta descuento global ni anticipos.
SIN_DESCUENTO_ITEM = "0"
SIN_DESCUENTO_GLOBAL = "0"
SIN_ANTICIPO = "0"

# ---------------------------------------------------------------------------
# VERIFICAR contra el Manual Técnico de SIFEN 150
# ---------------------------------------------------------------------------

# iTipEmi — emisión normal (vs. contingencia).
TIPO_EMISION_NORMAL = "1"

# iTImp — operación afectada al IVA.
TIPO_IMPUESTO_IVA = "1"

# iTipTra — tipo de transacción.
TIPO_TRANSACCION = "1"

# iIndPres — indicador de presencia. La operación es por la web, no presencial.
INDICADOR_PRESENCIA = "1"

# iCondOpe — 1 = contado, 2 = crédito (estos dos sí los dice el documento).
# Nuestras operaciones se cobran antes de confirmarse (RF022), así que siempre
# son contado. Eso es lo que obliga a mandar `gPaConEIni` (ver abajo).
CONDICION_OPERACION_CONTADO = "1"

# iNatRec — naturaleza del receptor: contribuyente o no.
RECEPTOR_CONTRIBUYENTE = "1"
RECEPTOR_NO_CONTRIBUYENTE = "2"

# iTiContRec — tipo de contribuyente del receptor (solo si es contribuyente).
TIPO_CONTRIBUYENTE_PERSONA_JURIDICA = "2"

# iTiOpe — tipo de operación.
TIPO_OPERACION_B2B = "1"   # cliente contribuyente (persona jurídica)
TIPO_OPERACION_B2C = "2"   # consumidor final (persona física)

# iTipIDRec / dNumIDRec — documento de identidad del receptor no
# contribuyente. Nuestros clientes FISICA se identifican con cédula.
TIPO_IDENTIFICACION_CEDULA = "1"

# cPaisRec — país del receptor.
PAIS_PARAGUAY = "PRY"

# iTiPago — forma de pago declarada en `gPaConEIni`.
#
# Nuestros cobros son con tarjeta vía dLocal (RF022), que sería iTiPago = 3.
# Pero el ejemplo del documento muestra que con tarjeta hay que mandar además
# `iDenTarj` (denominación de la tarjeta) e `iForProPa` (forma de
# procesamiento), dos códigos más del Manual SIFEN que no pudimos verificar y
# que dLocal tampoco nos devuelve. Se declara transferencia (5), que en el
# ejemplo no pide campos extra. Pendiente: con el manual a mano, pasarlo a 3 y
# completar esos dos códigos.
FORMA_PAGO_TRANSFERENCIA = "5"

# iAfecIVA / dTasaIVA / dPropIVA — afectación al IVA del ítem.
# Decisión del equipo para RF026 (ver el CHIA del Sprint 5): se factura el
# monto total de la operación, gravado al 10%. A confirmar con la cátedra.
AFECTACION_IVA_GRAVADO = "1"
TASA_IVA = "10"
PROPORCION_IVA_GRAVADA = "100"
