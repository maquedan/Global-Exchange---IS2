"""Pruebas del formato de números y montos (GEG9-82).

El criterio de la cátedra: punto para los miles y coma para los decimales,
y las monedas sin decimales sin decimales — nunca "10.0".
"""
from decimal import Decimal

import pytest
from django.template import Context, Template

from apps.comun.campos import MontoField, interpretar_monto
from apps.comun.formato import (
    formatear_monto,
    formatear_numero,
    formatear_tasa,
)
from apps.monedas.models import Moneda


# ---------------------------------------------------------------------------
# El formato en sí
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor,decimales,esperado",
    [
        ("1250000.5", 2, "1.250.000,50"),
        ("10000", 0, "10.000"),
        ("1234.56", 2, "1.234,56"),
        ("999", 0, "999"),
        ("1000", 0, "1.000"),
        # Cero, negativos y números grandes: los tres casos que pide el ERS.
        ("0", 0, "0"),
        ("0", 2, "0,00"),
        ("-1234.5", 2, "-1.234,50"),
        ("-1000000", 0, "-1.000.000"),
        ("999999999999.99", 2, "999.999.999.999,99"),
        # Redondeo hacia arriba en el medio exacto, como el resto del sistema.
        ("0.005", 2, "0,01"),
        ("2.675", 2, "2,68"),
    ],
)
def test_formatea_con_punto_de_miles_y_coma_decimal(valor, decimales, esperado):
    assert formatear_numero(Decimal(valor), decimales) == esperado


def test_nunca_muestra_un_solo_decimal():
    """El pedido era explícito: 10.000 y no 10.0."""
    assert formatear_numero(Decimal("10000"), 0) == "10.000"
    assert formatear_numero(Decimal("10.5"), 2) == "10,50"


def test_un_valor_ilegible_no_rompe_la_pantalla():
    """Un dato faltante no debería tumbar todo lo demás."""
    assert formatear_numero(None) == ""
    assert formatear_numero("no es un numero") == ""


def test_no_usa_float_en_ningun_momento():
    """Un float no representa 0,1 con exactitud, y en dinero eso se nota."""
    # 1.005 en float es 1.00499999999999989341858963598497211933135986328125,
    # así que redondear por float daría 1,00 en vez de 1,01.
    assert formatear_numero(Decimal("1.005"), 2) == "1,01"


# ---------------------------------------------------------------------------
# Los decimales salen de cada moneda
# ---------------------------------------------------------------------------


@pytest.fixture
def monedas(db):
    return {
        m.codigo: m
        for m in [
            Moneda.objects.create(codigo="PYG", nombre="Guarani", simbolo="Gs", decimales=0),
            Moneda.objects.create(codigo="USD", nombre="Dolar", simbolo="$", decimales=2),
            Moneda.objects.create(codigo="EUR", nombre="Euro", simbolo="E", decimales=2),
        ]
    }


@pytest.mark.django_db
def test_el_guarani_no_lleva_decimales(monedas):
    assert formatear_monto(Decimal("10000"), monedas["PYG"]) == "10.000"


@pytest.mark.django_db
@pytest.mark.parametrize("codigo", ["USD", "EUR"])
def test_el_dolar_y_el_euro_llevan_dos(monedas, codigo):
    assert formatear_monto(Decimal("102.5"), monedas[codigo]) == "102,50"


@pytest.mark.django_db
def test_tambien_acepta_el_codigo_suelto(monedas):
    """Algunas plantillas tienen el código y no el objeto."""
    assert formatear_monto(Decimal("10000"), "PYG") == "10.000"


@pytest.mark.django_db
def test_con_codigo_agrega_la_moneda(monedas):
    assert formatear_monto(Decimal("10000"), monedas["PYG"], con_codigo=True) == "10.000 PYG"


def test_sin_moneda_usa_dos_decimales():
    assert formatear_monto(Decimal("1234.5")) == "1.234,50"


# ---------------------------------------------------------------------------
# Las tasas conservan su precisión
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("7120.00", "7.120,00"),
        ("7120", "7.120,00"),
        ("0.000125", "0,000125"),
        ("1.5", "1,50"),
        ("48.2", "48,20"),
    ],
)
def test_la_tasa_conserva_los_decimales_necesarios(valor, esperado):
    """Redondear una tasa a dos decimales la haría dejar de ser la aplicada."""
    assert formatear_tasa(Decimal(valor)) == esperado


# ---------------------------------------------------------------------------
# Los filtros de plantilla
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_los_filtros_se_usan_desde_una_plantilla(monedas):
    plantilla = Template(
        "{% load formato_extras %}"
        "{{ a|monto:pyg }}|{{ b|monto_con_codigo:usd }}|{{ c|tasa }}|{{ d|numero:0 }}"
    )
    salida = plantilla.render(
        Context({
            "a": Decimal("71200"), "b": Decimal("102.5"),
            "c": Decimal("7120.00"), "d": Decimal("1500"),
            "pyg": monedas["PYG"], "usd": monedas["USD"],
        })
    )

    assert salida == "71.200|102,50 USD|7.120,00|1.500"


# ---------------------------------------------------------------------------
# Los formularios aceptan el formato
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "escrito,esperado",
    [
        ("1.250.000,50", "1250000.50"),
        ("1250000.50", "1250000.50"),
        ("10.000", "10000"),
        ("10000", "10000"),
        ("1.234,56", "1234.56"),
        # Un punto con menos de tres dígitos detrás es decimal, no de miles.
        ("10.5", "10.5"),
        ("  500  ", "500"),
    ],
)
def test_el_formulario_entiende_las_dos_formas_de_escribir(escrito, esperado):
    assert interpretar_monto(escrito) == Decimal(esperado)


def test_el_campo_de_monto_devuelve_el_mismo_decimal_de_siempre():
    """Solo cambia cómo se escribe: el valor guardado no cambia."""
    campo = MontoField(max_digits=16, decimal_places=2)

    assert campo.clean("10.000") == Decimal("10000")
    assert campo.clean("10000") == Decimal("10000")


def test_el_campo_rechaza_lo_que_no_es_un_numero():
    from django.core.exceptions import ValidationError

    campo = MontoField(max_digits=16, decimal_places=2)
    with pytest.raises(ValidationError):
        campo.clean("diez mil")


def test_el_campo_sigue_validando_el_minimo():
    """Heredar de DecimalField tiene que conservar todo lo demás."""
    from django.core.exceptions import ValidationError
    from django.core.validators import MinValueValidator

    campo = MontoField(
        max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    with pytest.raises(ValidationError):
        campo.clean("0")


# ---------------------------------------------------------------------------
# Que el formato llegue a las pantallas y a los documentos
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_logueado(client, django_user_model):
    from django.contrib.auth.models import Group

    usuario = django_user_model.objects.create_user(
        username="admin-formato", email="admin-formato@example.com"
    )
    grupo, _ = Group.objects.get_or_create(name="administrador")
    usuario.groups.add(grupo)
    client.force_login(usuario)
    return usuario


@pytest.mark.django_db
def test_la_clase_de_alineacion_esta_definida_una_sola_vez(client, admin_logueado):
    """El estilo vive en base.html: vale en todas las pantallas sin repetirlo."""
    from django.urls import reverse

    html = client.get(reverse("usuarios:panel")).content.decode()

    assert ".num {" in html
    assert "text-align: right" in html
    # Cifras tabulares: sin esto las comas de una columna no se alinean.
    assert "tabular-nums" in html


@pytest.mark.django_db
def test_las_columnas_de_montos_llevan_la_clase(client, django_user_model, monedas):
    """Historial de transacciones: tasa, comisión e importe final.

    Hace falta un cliente asociado: sin eso RF010 manda a `/sin-cliente/` y
    la pantalla ni se dibuja.
    """
    from django.contrib.auth.models import Group
    from django.urls import reverse

    from apps.clientes.models import AsociacionUsuarioCliente, Cliente

    usuario = django_user_model.objects.create_user(
        username="cliente-formato", email="cf@example.com"
    )
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    usuario.groups.add(grupo)
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Ana",
        apellidos="Formato",
        documento="1234567",
        email="ana@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)

    # La tabla solo se dibuja si hay alguna transacción confirmada. Se crea
    # directo y no por los servicios para no arrastrar facturación ni avisos:
    # acá lo que se prueba es el formato de la pantalla.
    from django.utils import timezone

    from apps.conversiones.models import CompraDivisa
    from apps.tasa_cambios.models import TasaCambio

    tasa_cambio = TasaCambio.objects.create(
        moneda_origen=monedas["USD"],
        moneda_destino=monedas["PYG"],
        tasa_compra=Decimal("7120.00"),
        tasa_venta=Decimal("7200.00"),
        vigente_desde=timezone.now(),
    )
    CompraDivisa.objects.create(
        cliente=cliente,
        moneda_pagada=monedas["USD"],
        moneda_adquirida=monedas["PYG"],
        tasa_cambio=tasa_cambio,
        monto_pagado=Decimal("100.00"),
        porcentaje_comision=Decimal("2.50"),
        monto_comision=Decimal("2.50"),
        total_a_pagar=Decimal("102.50"),
        tasa_aplicada=Decimal("7120.00"),
        monto_recibido=Decimal("712000.00"),
        estado=CompraDivisa.Estado.CONFIRMADA,
        confirmado_en=timezone.now(),
    )
    client.force_login(usuario)

    html = client.get(reverse("conversiones:historial")).content.decode()

    # Los encabezados numéricos están marcados para alinearse a la derecha.
    assert '<th class="num">Tasa aplicada</th>' in html
    assert '<th class="num">Importe final</th>' in html
    # Y el importe sale con el formato pedido, no como 712000.0
    assert "712.000" in html
    assert "7.120,00" in html


@pytest.mark.django_db
def test_el_excel_lleva_los_montos_como_numero_y_alineados():
    """Antes todas las celdas iban como texto: ni se sumaban ni se alineaban."""
    from apps.facturacion.views import _planilla_excel

    planilla = _planilla_excel(
        ["Factura", "Fecha", "Cliente", "Monto", "Moneda", "Estado"],
        [["001-001-0000001", "hoy", "Ana", Decimal("71200"), "PYG", "Aprobada"]],
    )

    assert 'ss:Type="Number"' in planilla
    assert 'ss:Horizontal="Right"' in planilla
    assert 'ss:Format="#.##0,00"' in planilla
    # El importe va crudo para que Excel pueda sumarlo.
    assert ">71200<" in planilla


@pytest.mark.django_db
def test_el_pdf_alinea_las_columnas_de_montos(monedas):
    """Sin librería de tablas, alinear es rellenar con espacios."""
    from apps.facturacion.views import _texto_pdf

    texto = _texto_pdf(
        ["Factura", "Cliente", "x", "Monto", "Moneda", "Estado"],
        [
            ["001-001-0000001", "Ana", "", Decimal("71200"), "PYG", "Aprobada"],
            ["001-001-0000002", "Beto", "", Decimal("500"), "PYG", "Aprobada"],
        ],
    )

    lineas = [l for l in texto.splitlines() if "|" in l and "-|-" not in l]
    montos = [l.split("|")[3] for l in lineas[1:]]

    # Las dos celdas de monto ocupan lo mismo y terminan en la misma columna.
    assert len(set(len(m) for m in montos)) == 1
    assert montos[0].strip() == "71.200"
    assert montos[1].strip() == "500"
    # El más corto queda rellenado por la izquierda: eso es alinear a la derecha.
    assert montos[1].startswith(" ")


@pytest.mark.django_db
def test_el_grafico_de_tasas_usa_el_mismo_formato(client, admin_logueado):
    """El JavaScript del panel formatea con Intl y el locale de Paraguay."""
    from django.urls import reverse

    html = client.get(reverse("tasas:panel")).content.decode()

    assert 'Intl.NumberFormat("es-PY"' in html


# ---------------------------------------------------------------------------
# El formateo automático mientras se escribe
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_los_campos_de_monto_se_formatean_solos(client, admin_logueado):
    """El JavaScript pone los puntos mientras la persona escribe."""
    from django.urls import reverse

    html = client.get(reverse("usuarios:panel")).content.decode()

    assert "input.monto-entrada" in html
    assert "agruparMiles" in html


def test_el_campo_de_monto_lleva_la_clase_que_dispara_el_formateo():
    campo = MontoField(max_digits=16, decimal_places=2)

    assert "monto-entrada" in campo.widget.attrs["class"]


def test_el_campo_de_tasa_NO_lleva_esa_clase():
    """Si una tasa se formateara sola, escribir 7120 daría 7,12.

    El formateo automático convertiría "7120" en "7.120", y `TasaField` lee
    un punto suelto como decimal: quedaría mil veces menos. Por eso las tasas
    se escriben tal cual.
    """
    from apps.comun.campos import TasaField

    campo = TasaField(max_digits=12, decimal_places=6)

    assert "monto-entrada" not in campo.widget.attrs["class"]
    assert "tasa-entrada" in campo.widget.attrs["class"]


def test_la_tasa_escrita_sin_puntos_se_guarda_entera():
    """El caso que el formateo automático arruinaría."""
    from apps.comun.campos import TasaField

    campo = TasaField(max_digits=12, decimal_places=6)

    assert campo.clean("7120") == Decimal("7120")
    assert campo.clean("7.120") == Decimal("7.120")
