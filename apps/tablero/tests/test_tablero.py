"""Pruebas del tablero de control del administrador (RF038 — GEG9-67)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.cajas.models import ArqueoCaja, DiferenciaCaja, SaldoCaja, Sucursal
from apps.clientes.models import Cliente
from apps.conversiones.models import CompraDivisa, VentaDivisa
from apps.facturacion.models import Factura
from apps.ganancias.services import resumen_ganancias
from apps.monedas.models import Moneda
from apps.tablero.services import (
    MAXIMO_BARRAS,
    _ganancias_en_guaranies,
    cotizaciones_a_guaranies,
    metricas,
    rango_de,
    serie_de_ganancias,
)
from apps.tasa_cambios.models import TasaCambio


@pytest.fixture
def datos(db):
    usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$", decimales=2)
    pyg = Moneda.objects.create(codigo="PYG", nombre="Guaraní", simbolo="Gs", decimales=0)
    tasa = TasaCambio.objects.create(
        moneda_origen=usd,
        moneda_destino=pyg,
        tasa_compra=Decimal("7100.00"),
        tasa_venta=Decimal("7200.00"),
        vigente_desde=timezone.now(),
    )
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Ana",
        apellidos="Gómez",
        documento="1000001",
        email="ana@example.com",
        telefono="0981000001",
        direccion="Asunción",
    )
    return {"usd": usd, "pyg": pyg, "tasa": tasa, "cliente": cliente}


def usuario_con_rol(django_user_model, rol, nombre=None):
    usuario = django_user_model.objects.create_user(username=nombre or f"usuario-{rol}")
    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
    return usuario


def _fechar(modelo, pk, dias_atras, confirmada):
    """Mueve las fechas de una operación al pasado.

    `creado_en` es `auto_now_add`, así que no se puede fijar al crear la
    fila: hay que actualizarla después, y `update()` no vuelve a pisarla.
    """
    momento = timezone.now() - timedelta(days=dias_atras)
    modelo.objects.filter(pk=pk).update(
        creado_en=momento, confirmado_en=momento if confirmada else None
    )


def crear_compra(datos, estado=CompraDivisa.Estado.CONFIRMADA, dias_atras=0):
    """Compra de 100 USD a 7.100, con 2,50 USD de comisión.

    Ganancia esperada en PYG: 2,50 × 7.100 = 17.750 de comisión y
    100 × (7.200 − 7.100) = 10.000 de diferencia de tasa.
    """
    confirmada = estado == CompraDivisa.Estado.CONFIRMADA
    compra = CompraDivisa.objects.create(
        cliente=datos["cliente"],
        moneda_pagada=datos["usd"],
        moneda_adquirida=datos["pyg"],
        tasa_cambio=datos["tasa"],
        monto_pagado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("2.50"),
        total_a_pagar=Decimal("102.50"),
        tasa_aplicada=Decimal("7100.00"),
        monto_recibido=Decimal("710000.00"),
        estado=estado,
    )
    # La anulada SÍ lleva fecha de confirmación: se confirmó y después se
    # anuló. Así la prueba demuestra que el filtro mira el estado y no la
    # simple presencia de `confirmado_en`.
    tuvo_confirmacion = confirmada or estado == CompraDivisa.Estado.ANULADA
    _fechar(CompraDivisa, compra.pk, dias_atras, tuvo_confirmacion)
    compra.refresh_from_db()
    return compra


def crear_venta(datos, estado=VentaDivisa.Estado.CONFIRMADA, dias_atras=0):
    confirmada = estado == VentaDivisa.Estado.CONFIRMADA
    venta = VentaDivisa.objects.create(
        cliente=datos["cliente"],
        moneda_entregada=datos["usd"],
        moneda_acreditada=datos["pyg"],
        tasa_cambio=datos["tasa"],
        monto_entregado=Decimal("50.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("8875.00"),
        monto_convertido=Decimal("355000.00"),
        monto_acreditado=Decimal("346125.00"),
        tasa_aplicada=Decimal("7100.00"),
        estado=estado,
    )
    _fechar(VentaDivisa, venta.pk, dias_atras, confirmada)
    venta.refresh_from_db()
    return venta


# --------------------------------------------------------------------------
# Permisos
# --------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "rol", ["analista_cambiario", "usuario_cliente", "cajero", "terminal"]
)
def test_los_demas_roles_reciben_403_incluso_escribiendo_la_direccion(
    client, django_user_model, rol
):
    client.force_login(usuario_con_rol(django_user_model, rol))
    assert client.get(reverse("tablero:panel")).status_code == 403


@pytest.mark.django_db
def test_el_administrador_entra(client, django_user_model):
    client.force_login(usuario_con_rol(django_user_model, "administrador"))
    assert client.get(reverse("tablero:panel")).status_code == 200


@pytest.mark.django_db
def test_un_usuario_sin_ningun_rol_tambien_recibe_403(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="pelado"))
    assert client.get(reverse("tablero:panel")).status_code == 403


@pytest.mark.django_db
def test_sin_sesion_manda_a_iniciar_sesion(client):
    respuesta = client.get(reverse("tablero:panel"))
    assert respuesta.status_code == 302
    assert reverse("tablero:panel") not in respuesta["Location"].split("?")[0]


@pytest.mark.django_db
def test_el_menu_muestra_el_tablero_solo_al_administrador(client, django_user_model):
    from apps.usuarios.menu import construir_menu

    admin = usuario_con_rol(django_user_model, "administrador", "admin-menu")
    cajero = usuario_con_rol(django_user_model, "cajero", "cajero-menu")

    textos_admin = [opcion["texto"] for opcion in construir_menu(admin)]
    textos_cajero = [opcion["texto"] for opcion in construir_menu(cajero)]

    assert "Tablero" in textos_admin
    assert "Tablero" not in textos_cajero


# --------------------------------------------------------------------------
# Conteos por estado
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_conteos_por_estado_separan_compras_de_ventas_y_dan_el_total(datos):
    crear_compra(datos, CompraDivisa.Estado.PENDIENTE)
    crear_compra(datos, CompraDivisa.Estado.CONFIRMADA)
    crear_compra(datos, CompraDivisa.Estado.CONFIRMADA)
    crear_compra(datos, CompraDivisa.Estado.CANCELADA)
    crear_venta(datos, VentaDivisa.Estado.CONFIRMADA)
    crear_venta(datos, VentaDivisa.Estado.ANULADA)

    operaciones = metricas("todo")["operaciones"]

    assert operaciones["compras"] == {
        "pendientes": 1,
        "pagadas": 2,
        "canceladas": 1,
        "anuladas": 0,
        "total": 4,
    }
    assert operaciones["ventas"] == {
        "pendientes": 0,
        "pagadas": 1,
        "canceladas": 0,
        "anuladas": 1,
        "total": 2,
    }
    assert operaciones["total"] == {
        "pendientes": 1,
        "pagadas": 3,
        "canceladas": 1,
        "anuladas": 1,
        "total": 6,
    }


# --------------------------------------------------------------------------
# Dinero
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_canceladas_y_anuladas_no_suman_dinero(datos):
    crear_compra(datos, CompraDivisa.Estado.CONFIRMADA)
    crear_compra(datos, CompraDivisa.Estado.CANCELADA)
    crear_compra(datos, CompraDivisa.Estado.ANULADA)

    ganancias = metricas("todo")["ganancias"]

    assert ganancias["operaciones"] == 1
    assert ganancias["desglose"] == [
        {
            "moneda": "PYG",
            "comision": Decimal("17750.00"),
            "diferencia_tasa": Decimal("10000.00"),
            "total": Decimal("27750.00"),
        }
    ]


@pytest.mark.django_db
def test_las_ganancias_son_las_que_calcula_el_servicio_de_rf031(datos):
    crear_compra(datos)
    crear_venta(datos)

    del_tablero = metricas("todo")["ganancias"]
    del_servicio = resumen_ganancias(None, None)

    assert del_tablero == del_servicio


@pytest.mark.django_db
def test_las_ganancias_usan_el_mismo_periodo_que_el_resto_de_la_pantalla(datos):
    crear_compra(datos, dias_atras=0)
    crear_compra(datos, dias_atras=40)

    _, desde, hasta = rango_de("30")

    assert metricas("30")["ganancias"] == resumen_ganancias(desde, hasta)
    assert metricas("30")["ganancias"]["operaciones"] == 1
    assert metricas("todo")["ganancias"]["operaciones"] == 2


# --------------------------------------------------------------------------
# Período
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_el_periodo_cambia_los_numeros(datos):
    crear_compra(datos, dias_atras=0)
    crear_compra(datos, dias_atras=3)
    crear_compra(datos, dias_atras=40)

    assert metricas("hoy")["operaciones"]["total"]["total"] == 1
    assert metricas("7")["operaciones"]["total"]["total"] == 2
    assert metricas("30")["operaciones"]["total"]["total"] == 2
    assert metricas("todo")["operaciones"]["total"]["total"] == 3


@pytest.mark.django_db
def test_siete_dias_incluye_hoy_y_los_seis_anteriores(datos):
    crear_compra(datos, dias_atras=6)
    crear_compra(datos, dias_atras=7)

    assert metricas("7")["operaciones"]["total"]["total"] == 1


@pytest.mark.django_db
def test_un_periodo_desconocido_cae_en_el_valor_por_omision(datos):
    crear_compra(datos, dias_atras=40)

    # Llega de la dirección del navegador: no puede tumbar la pantalla.
    assert rango_de("'; drop table --")[0] == "30"
    assert metricas("cualquier-cosa")["periodo"] == "30"
    assert metricas("cualquier-cosa")["operaciones"]["total"]["total"] == 0


@pytest.mark.django_db
def test_el_periodo_vacio_cae_en_el_valor_por_omision(datos):
    # `?periodo=` da cadena vacia, que no es lo mismo que no mandar el
    # parametro: `GET.get` no usa el valor por omision si la clave existe.
    assert rango_de("")[0] == "30"
    assert metricas("")["periodo"] == "30"


@pytest.mark.django_db
def test_el_periodo_invalido_en_la_direccion_devuelve_200(client, django_user_model):
    client.force_login(usuario_con_rol(django_user_model, "administrador"))
    respuesta = client.get(reverse("tablero:panel"), {"periodo": "../../etc/passwd"})
    assert respuesta.status_code == 200
    assert respuesta.context["tablero"]["periodo"] == "30"


# --------------------------------------------------------------------------
# Clientes, caja y facturas
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_clientes_activos_e_inactivos(datos):
    Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Luis",
        apellidos="Pérez",
        documento="1000002",
        email="luis@example.com",
        telefono="0981000002",
        direccion="Luque",
        activo=False,
    )

    assert metricas("todo")["clientes"] == {"activos": 1, "inactivos": 1}


@pytest.mark.django_db
def test_los_clientes_no_dependen_del_periodo(datos):
    # El cliente de la fixture se creó hoy; con "hoy" o con "todo" tiene que
    # contarse igual, porque `activo` es un estado actual y no un hecho con
    # fecha.
    assert metricas("hoy")["clientes"] == metricas("todo")["clientes"]


@pytest.mark.django_db
def test_saldos_de_caja_agrupados_por_moneda(datos):
    caja = Sucursal.objects.get(es_unica=True).caja
    SaldoCaja.objects.create(caja=caja, moneda=datos["pyg"], saldo=Decimal("5000000"))
    SaldoCaja.objects.create(caja=caja, moneda=datos["usd"], saldo=Decimal("1500.50"))

    saldos = metricas("todo")["caja"]["saldos"]

    assert saldos == [
        {"moneda": "PYG", "decimales": 0, "total": Decimal("5000000.00")},
        {"moneda": "USD", "decimales": 2, "total": Decimal("1500.50")},
    ]


@pytest.mark.django_db
def test_diferencias_de_arqueo_registradas(datos, django_user_model):
    caja = Sucursal.objects.get(es_unica=True).caja
    cajero = usuario_con_rol(django_user_model, "cajero", "cajero-arqueo")
    arqueo = ArqueoCaja.objects.create(
        caja=caja,
        cajero=cajero,
        moneda=datos["pyg"],
        saldo_esperado=Decimal("100000"),
        total_contado=Decimal("90000"),
        diferencia=Decimal("-10000"),
        estado=ArqueoCaja.Estado.FALTANTE,
    )
    DiferenciaCaja.objects.create(
        arqueo=arqueo,
        monto=Decimal("10000"),
        moneda=datos["pyg"],
        motivo="Faltante de caja",
        responsable=cajero,
        registrado_por=cajero,
    )

    caja_metricas = metricas("todo")["caja"]

    assert caja_metricas["diferencias_registradas"] == 1
    assert caja_metricas["diferencias"] == [
        {
            "moneda": "PYG",
            "decimales": 0,
            "cantidad": 1,
            "total": Decimal("10000.00"),
        }
    ]


@pytest.mark.django_db
def test_la_sucursal_se_informa_sin_contador(datos):
    sucursal = metricas("todo")["caja"]["sucursal"]

    # El modelo impone una sola sucursal (`es_unica` es único), así que la
    # pantalla informa cuál es y si está activa, no cuántas hay.
    assert sucursal == Sucursal.objects.get(es_unica=True)
    assert Sucursal.objects.count() == 1


@pytest.mark.django_db
def test_las_facturas_separan_el_error_de_emision_del_rechazo_de_sifen(datos):
    compras = [crear_compra(datos) for _ in range(4)]
    comun = {
        "timbrado": "12345678",
        "establecimiento": "001",
        "punto_expedicion": "001",
        "monto": Decimal("710000"),
        "monto_origen": Decimal("100"),
        "moneda_origen": "USD",
    }
    Factura.objects.create(
        compra=compras[0],
        numero="0000001",
        cdc="1" * 44,
        estado=Factura.Estado.GENERADA,
        estado_fiscal=Factura.EstadoFiscal.APROBADA,
        **comun,
    )
    Factura.objects.create(
        compra=compras[1],
        numero="0000002",
        cdc="2" * 44,
        estado=Factura.Estado.GENERADA,
        estado_fiscal=Factura.EstadoFiscal.RECHAZADA,
        **comun,
    )
    Factura.objects.create(
        compra=compras[2], numero="0000003", estado=Factura.Estado.ERROR, **comun
    )
    Factura.objects.create(
        compra=compras[3], numero="0000004", estado=Factura.Estado.A_VERIFICAR, **comun
    )

    facturas = metricas("todo")["facturas"]

    assert facturas == {
        "emitidas": 2,
        "aprobadas": 1,
        "rechazadas": 1,
        "con_error": 1,
        "a_verificar": 1,
    }


@pytest.mark.django_db
def test_ventas_pendientes_de_entrega_no_se_filtran_por_periodo(datos):
    crear_venta(datos, VentaDivisa.Estado.PENDIENTE, dias_atras=90)

    # Es una lista de trabajo, no una estadística: la venta vieja que nadie
    # entregó es justamente la que hay que ver.
    assert metricas("hoy")["ventas_pendientes_de_entrega"] == 1
    assert metricas("todo")["ventas_pendientes_de_entrega"] == 1
    assert metricas("hoy")["operaciones"]["ventas"]["pendientes"] == 0


# --------------------------------------------------------------------------
# Estado vacío
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_sin_datos_todo_en_cero_y_sin_error(client, django_user_model):
    client.force_login(usuario_con_rol(django_user_model, "administrador"))
    respuesta = client.get(reverse("tablero:panel"))
    tablero = respuesta.context["tablero"]

    assert respuesta.status_code == 200
    assert tablero["operaciones"]["total"]["total"] == 0
    assert tablero["clientes"] == {"activos": 0, "inactivos": 0}
    assert tablero["caja"]["saldos"] == []
    assert tablero["caja"]["diferencias"] == []
    assert tablero["caja"]["diferencias_registradas"] == 0
    assert tablero["ventas_pendientes_de_entrega"] == 0
    assert tablero["ganancias"]["desglose"] == []
    assert tablero["ganancias"]["operaciones"] == 0


# --------------------------------------------------------------------------
# Presentación y rendimiento
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_las_cifras_salen_con_separador_de_miles(client, django_user_model, datos):
    crear_compra(datos)
    client.force_login(usuario_con_rol(django_user_model, "administrador"))

    html = client.get(reverse("tablero:panel")).content.decode()

    # Comisión 2,50 × 7.100 y diferencia 100 × (7.200 − 7.100).
    assert "17.750,00" in html
    assert "10.000,00" in html
    assert "27.750,00" in html
    # Y no el formato de Django, que no agrupa los miles.
    assert "17750.00" not in html
    assert "17750,00" not in html


@pytest.mark.django_db
def test_la_cantidad_de_consultas_no_crece_con_los_datos(datos):
    crear_compra(datos)
    crear_venta(datos)

    with CaptureQueriesContext(connection) as pocos:
        metricas("todo")

    for _ in range(20):
        crear_compra(datos)
        crear_venta(datos)

    with CaptureQueriesContext(connection) as muchos:
        metricas("todo")

    # Lo que importa no es el número exacto sino que sea el MISMO: si
    # alguien agrega una métrica que consulta dentro de un bucle, acá se
    # nota. Es lo que exige RNF001 (menos de 3 segundos).
    assert len(muchos) == len(pocos)
    # 13 hoy: las métricas, una para las cotizaciones vigentes y dos para
    # recorrer las operaciones del gráfico. La cota existe para que agregar
    # algo caro se note; si sube, hay que entender por qué antes de subirla.
    assert len(pocos) <= 15, [consulta["sql"] for consulta in pocos.captured_queries]


@pytest.mark.django_db
def test_la_pantalla_completa_tampoco_consulta_de_mas(
    client, django_user_model, datos, django_assert_max_num_queries
):
    for _ in range(10):
        crear_compra(datos)
    client.force_login(usuario_con_rol(django_user_model, "administrador"))

    # Las consultas de más son de la sesión, los roles y el menú, que son
    # de todas las pantallas.
    with django_assert_max_num_queries(25):
        assert client.get(reverse("tablero:panel")).status_code == 200


# --------------------------------------------------------------------------
# Ganancias en guaraníes
# --------------------------------------------------------------------------


def _resumen(*filas):
    """Arma un resumen con la forma que devuelve RF031."""
    return {"operaciones": len(filas), "total": {}, "desglose": list(filas)}


def test_convierte_cada_moneda_y_suma_un_total_con_unidad():
    resumen = _resumen(
        {
            "moneda": "USD",
            "comision": Decimal("10.00"),
            "diferencia_tasa": Decimal("5.00"),
            "total": Decimal("15.00"),
        },
        {
            "moneda": "PYG",
            "comision": Decimal("1000.00"),
            "diferencia_tasa": Decimal("500.00"),
            "total": Decimal("1500.00"),
        },
    )
    cotizaciones = {"PYG": Decimal(1), "USD": Decimal("7100")}

    en_guaranies = _ganancias_en_guaranies(resumen, cotizaciones)

    # 15 USD × 7.100 = 106.500, más los 1.500 que ya estaban en guaraníes.
    assert en_guaranies["total_pyg"] == Decimal("108000.00")
    assert en_guaranies["comision_pyg"] == Decimal("72000.00")
    assert en_guaranies["diferencia_tasa_pyg"] == Decimal("36000.00")
    assert en_guaranies["desglose"][0]["equivalente_pyg"] == Decimal("106500.00")
    assert en_guaranies["sin_cotizacion"] == []
    assert en_guaranies["hay_conversion"] is True


def test_una_moneda_sin_cotizacion_queda_fuera_del_total_y_se_avisa():
    resumen = _resumen(
        {
            "moneda": "JPY",
            "comision": Decimal("800.00"),
            "diferencia_tasa": Decimal("200.00"),
            "total": Decimal("1000.00"),
        },
        {
            "moneda": "PYG",
            "comision": Decimal("300.00"),
            "diferencia_tasa": Decimal("0.00"),
            "total": Decimal("300.00"),
        },
    )

    en_guaranies = _ganancias_en_guaranies(resumen, {"PYG": Decimal(1)})

    # El total NO inventa una cotización: cuenta solo lo convertible…
    assert en_guaranies["total_pyg"] == Decimal("300.00")
    # …pero la moneda que quedó afuera se nombra, para que no parezca
    # que el total está completo.
    assert en_guaranies["sin_cotizacion"] == ["JPY"]
    assert en_guaranies["desglose"][0]["equivalente_pyg"] is None


def test_si_todo_ya_esta_en_guaranies_no_hay_nada_que_convertir():
    resumen = _resumen(
        {
            "moneda": "PYG",
            "comision": Decimal("100.00"),
            "diferencia_tasa": Decimal("0.00"),
            "total": Decimal("100.00"),
        }
    )

    en_guaranies = _ganancias_en_guaranies(resumen, {"PYG": Decimal(1)})

    assert en_guaranies["hay_conversion"] is False
    assert en_guaranies["total_pyg"] == Decimal("100.00")


@pytest.mark.django_db
def test_las_cotizaciones_usan_la_tasa_de_compra_vigente(datos):
    cotizaciones = cotizaciones_a_guaranies()

    # El guaraní vale 1 por definición, sin consultar nada.
    assert cotizaciones["PYG"] == Decimal(1)
    # Y el dólar, la tasa de COMPRA (7.100), no la de venta (7.200): es la
    # valuación conservadora, nunca infla la ganancia.
    assert cotizaciones["USD"] == Decimal("7100.000000")


@pytest.mark.django_db
def test_una_moneda_sin_tasa_activa_no_entra_en_las_cotizaciones(datos):
    datos["tasa"].activo = False
    datos["tasa"].save(update_fields=["activo"])

    assert "USD" not in cotizaciones_a_guaranies()


# --------------------------------------------------------------------------
# Gráfico de evolución
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_las_barras_suman_exactamente_lo_mismo_que_el_resumen_de_rf031(datos):
    """La prueba que evita que el gráfico invente su propia ganancia."""
    crear_compra(datos, dias_atras=0)
    crear_compra(datos, dias_atras=3)
    crear_venta(datos, dias_atras=5)

    cotizaciones = cotizaciones_a_guaranies()
    serie = serie_de_ganancias(None, None, cotizaciones)
    resumen = _ganancias_en_guaranies(resumen_ganancias(None, None), cotizaciones)

    assert sum(barra["total"] for barra in serie["barras"]) == resumen["total_pyg"]


@pytest.mark.django_db
def test_una_barra_por_dia_cuando_el_periodo_es_corto(datos):
    crear_compra(datos, dias_atras=0)
    crear_compra(datos, dias_atras=6)

    _, desde, hasta = rango_de("7")
    serie = serie_de_ganancias(desde, hasta, cotizaciones_a_guaranies())

    assert len(serie["barras"]) == 7
    assert serie["dias_por_barra"] == 1
    # La primera y la última tienen ganancia; las del medio no.
    assert serie["barras"][0]["total"] > 0
    assert serie["barras"][-1]["total"] > 0
    assert serie["barras"][3]["total"] == Decimal("0.00")


@pytest.mark.django_db
def test_un_periodo_largo_junta_dias_para_no_pasar_del_maximo(datos):
    crear_compra(datos, dias_atras=0)

    _, desde, hasta = rango_de("30")
    serie = serie_de_ganancias(desde, hasta, cotizaciones_a_guaranies())

    assert len(serie["barras"]) <= MAXIMO_BARRAS
    assert serie["dias_por_barra"] > 1


@pytest.mark.django_db
def test_sin_operaciones_el_grafico_queda_vacio_sin_romper(db):
    serie = serie_de_ganancias(None, None, {"PYG": Decimal(1)})

    assert serie["barras"] == []
    assert serie["maximo"] == Decimal("0.00")


@pytest.mark.django_db
def test_la_barra_mas_alta_llega_al_tope_y_las_demas_quedan_en_proporcion(datos):
    crear_compra(datos, dias_atras=0)
    crear_compra(datos, dias_atras=1)
    crear_compra(datos, dias_atras=1)

    _, desde, hasta = rango_de("7")
    barras = serie_de_ganancias(desde, hasta, cotizaciones_a_guaranies())["barras"]

    con_ganancia = [b for b in barras if b["total"] > 0]
    mas_alta = max(con_ganancia, key=lambda b: b["alto"])
    mas_baja = min(con_ganancia, key=lambda b: b["alto"])

    # El día con el doble de ganancia dibuja el doble de alto.
    assert mas_baja["total"] * 2 == mas_alta["total"]
    assert round(mas_baja["alto"] * 2) == round(mas_alta["alto"])
    # Y ninguna barra se sale del dibujo.
    for barra in barras:
        assert barra["y"] >= 0
        assert barra["alto"] >= 0


@pytest.mark.django_db
def test_la_pantalla_muestra_el_total_en_guaranies_y_el_grafico(
    client, django_user_model, datos
):
    crear_compra(datos)
    client.force_login(usuario_con_rol(django_user_model, "administrador"))

    html = client.get(reverse("tablero:panel")).content.decode()

    assert "Ganancia total" in html
    assert "27.750" in html          # la ganancia, ya en guaraníes
    assert "<svg" in html            # el gráfico se dibujó
    assert "grafico-barra" in html


@pytest.mark.django_db
def test_las_coordenadas_del_grafico_no_salen_con_coma_decimal(
    client, django_user_model, datos
):
    """El sitio está en español y Django localiza los números al renderizar.

    Escribía `width="44,64"` en vez de `44.64`, y SVG no entiende la coma
    como separador decimal: descartaba el atributo y no dibujaba ninguna
    barra. En `<text x>` era peor, porque ahí la coma SÍ es válida y
    significa "una posición por letra", así que desarmaba las fechas.

    Por eso el gráfico va dentro de `{% localize off %}`.
    """
    import re

    crear_compra(datos)
    client.force_login(usuario_con_rol(django_user_model, "administrador"))

    html = client.get(reverse("tablero:panel")).content.decode()
    svg = html[html.index("<svg") : html.index("</svg>")]

    coordenadas = re.findall(r'(?:x|y|width|height)="([^"]+)"', svg)
    assert coordenadas, "el gráfico no dibujó nada"
    for valor in coordenadas:
        assert "," not in valor, f"coordenada localizada: {valor}"

    # Y que de verdad haya barras con alto, no solo rectángulos vacíos.
    altos = [float(a) for a in re.findall(r'height="([\d.]+)"', svg)]
    assert any(alto > 0 for alto in altos)
