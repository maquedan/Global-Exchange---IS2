"""Pruebas de RF010 — Restricción de Operaciones (GEG9-20).

El ERS pide limitar al usuario no asociado a un cliente "únicamente a
funciones de consulta". Lo que se verifica acá es sobre todo el **bloqueo en
el servidor**: ocultar botones del menú es comodidad, no seguridad, así que
cada vista de operación se prueba con GET y con POST.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CompraDivisa, VentaDivisa
from apps.conversiones.services import (
    confirmar_pago_compra,
    iniciar_compra,
    iniciar_venta,
)
from apps.cuentas.models import CuentaPago
from apps.monedas.models import Moneda
from apps.pagos.models import Pago
from apps.pagos.services import iniciar_pago
from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.menu import construir_menu
from apps.usuarios.services import ClienteNoHabilitado, cliente_habilitado_para


# URLs que operan en nombre de un cliente. Es la lista que hace de red: si
# mañana alguien agrega una vista de operación y se olvida de protegerla,
# agregarla acá la delata. Los pk son inexistentes a propósito — el bloqueo
# tiene que pasar ANTES de buscar el objeto.
URLS_DE_OPERACION = [
    ("conversiones:comprar", [], "GET"),
    ("conversiones:comprar", [], "POST"),
    ("conversiones:vender", [], "GET"),
    ("conversiones:vender", [], "POST"),
    ("conversiones:confirmar_compra", [1], "POST"),
    ("conversiones:cancelar_compra", [1], "POST"),
    ("conversiones:confirmar_venta", [1], "POST"),
    ("conversiones:cancelar_venta", [1], "POST"),
    ("cuentas:crear", [], "GET"),
    ("cuentas:crear", [], "POST"),
    ("cuentas:editar", [1], "POST"),
    ("cuentas:eliminar", [1], "GET"),
    ("pagos:elegir_pago", [1], "GET"),
    ("pagos:elegir_pago", [1], "POST"),
    ("pagos:esperando", [1], "GET"),
    ("pagos:simulado_aprobar", [1], "POST"),
    ("pagos:simulado_rechazar", [1], "POST"),
]

URLS_DE_CONSULTA = [
    ("tasas:panel", []),
    ("tasas:datos_actuales", []),
    ("usuarios:panel", []),
    ("usuarios:sin_cliente", []),
    ("conversiones:simular", []),
    ("notificaciones:lista", []),
]


def _usuario(django_user_model, username, rol):
    usuario = django_user_model.objects.create_user(
        username=username, email=f"{username}@example.com"
    )
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    return usuario


@pytest.fixture
def sin_cliente(django_user_model):
    """Usuario recién registrado: tiene el rol, pero ningún cliente asociado."""
    return _usuario(django_user_model, "recien-registrado", "usuario_cliente")


@pytest.fixture
def monedas(db):
    return (
        Moneda.objects.create(codigo="USD", nombre="Dolar", simbolo="$"),
        Moneda.objects.create(codigo="PYG", nombre="Guarani", simbolo="Gs"),
    )


@pytest.fixture
def tasa(monedas):
    return TasaCambio.objects.create(
        moneda_origen=monedas[0],
        moneda_destino=monedas[1],
        tasa_compra=Decimal("7100.00"),
        tasa_venta=Decimal("7200.00"),
        vigente_desde=timezone.now(),
    )


@pytest.fixture
def comision(db):
    return ComisionCategoria.objects.create(
        categoria=Cliente.Categoria.MINORISTA, porcentaje=Decimal("2.50")
    )


@pytest.fixture
def con_cliente(django_user_model):
    """Usuario asociado a un cliente activo: tiene que poder operar."""
    usuario = _usuario(django_user_model, "con-cliente", "usuario_cliente")
    cliente = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Ana",
        apellidos="Gomez",
        documento="1234567",
        email="ana@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=cliente)
    return usuario, cliente


# ---------------------------------------------------------------------------
# Consulta: sigue funcionando
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("nombre,args", URLS_DE_CONSULTA)
def test_sin_cliente_puede_consultar(client, sin_cliente, nombre, args):
    client.force_login(sin_cliente)
    assert client.get(reverse(nombre, args=args)).status_code == 200


@pytest.mark.django_db
def test_simular_no_registra_nada(client, sin_cliente, monedas, tasa):
    """La simulación (RF017) es solo cálculo: es consulta, no operación."""
    client.force_login(sin_cliente)
    respuesta = client.post(
        reverse("conversiones:simular"),
        {
            "moneda_origen": monedas[0].pk,
            "moneda_destino": monedas[1].pk,
            "monto": "100.00",
            "tipo_operacion": "compra",
        },
    )
    assert respuesta.status_code == 200
    assert CompraDivisa.objects.count() == 0


# ---------------------------------------------------------------------------
# Operación: bloqueada en el servidor
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("nombre,args,metodo", URLS_DE_OPERACION)
def test_sin_cliente_no_puede_operar(client, sin_cliente, nombre, args, metodo):
    """Ni por GET ni por POST, aunque escriba la URL a mano."""
    client.force_login(sin_cliente)
    url = reverse(nombre, args=args)

    respuesta = client.post(url, {}) if metodo == "POST" else client.get(url)

    assert respuesta.status_code == 302
    assert respuesta.url == reverse("usuarios:sin_cliente")


@pytest.mark.django_db
def test_el_bloqueo_no_deja_ningun_registro(client, sin_cliente, monedas, tasa, comision):
    """Lo que importa no es solo el 302: que no se cree nada."""
    client.force_login(sin_cliente)
    ajeno = Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres="Victima",
        apellidos="Ajena",
        documento="9999999",
        email="ajeno@example.com",
        telefono="0981999999",
        direccion="Asuncion",
    )

    client.post(
        reverse("conversiones:comprar"),
        {
            "cliente": ajeno.pk,
            "moneda_pagada": monedas[0].pk,
            "moneda_adquirida": monedas[1].pk,
            "monto_pagado": "100.00",
        },
    )
    client.post(
        reverse("cuentas:crear"),
        {
            "tipo": CuentaPago.Tipo.BANCARIA,
            "entidad": "Itau",
            "numero_cuenta": "123456",
            "titular": "Victima Ajena",
        },
    )

    assert CompraDivisa.objects.count() == 0
    assert VentaDivisa.objects.count() == 0
    assert Pago.objects.count() == 0
    assert CuentaPago.objects.count() == 0


@pytest.mark.django_db
def test_con_cliente_opera_con_normalidad(client, con_cliente, monedas, tasa, comision):
    usuario, cliente = con_cliente
    client.force_login(usuario)

    respuesta = client.post(
        reverse("conversiones:comprar"),
        {
            "moneda_pagada": monedas[0].pk,
            "moneda_adquirida": monedas[1].pk,
            "monto_pagado": "100.00",
        },
    )

    assert CompraDivisa.objects.count() == 1
    compra = CompraDivisa.objects.get()
    assert compra.cliente == cliente
    assert respuesta.url == reverse("conversiones:comprobante_compra", args=[compra.pk])


@pytest.mark.django_db
def test_cliente_desactivado_no_puede_operar(client, con_cliente, monedas, tasa, comision):
    """La asociación sigue existiendo, pero el cliente fue dado de baja (RF003)."""
    usuario, cliente = con_cliente
    cliente.desactivar()
    client.force_login(usuario)

    respuesta = client.post(
        reverse("conversiones:comprar"),
        {
            "moneda_pagada": monedas[0].pk,
            "moneda_adquirida": monedas[1].pk,
            "monto_pagado": "100.00",
        },
    )

    assert respuesta.url == reverse("usuarios:sin_cliente")
    assert CompraDivisa.objects.count() == 0


@pytest.mark.django_db
def test_cliente_desactivado_no_puede_confirmar_una_operacion_pendiente(
    client, con_cliente, monedas, tasa, comision
):
    """El hueco que había antes de RF010: la operación ya estaba iniciada."""
    usuario, cliente = con_cliente
    compra = iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )
    cliente.desactivar()
    client.force_login(usuario)

    respuesta = client.post(reverse("conversiones:confirmar_compra", args=[compra.pk]))

    compra.refresh_from_db()
    assert respuesta.url == reverse("usuarios:sin_cliente")
    assert compra.estado == CompraDivisa.Estado.PENDIENTE


# ---------------------------------------------------------------------------
# Defensa en profundidad: la capa de servicios
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_iniciar_compra_rechaza_un_usuario_sin_cliente(
    sin_cliente, con_cliente, monedas, tasa, comision
):
    """Sin pasar por la vista: el servicio se niega por su cuenta."""
    _usuario_ajeno, cliente_ajeno = con_cliente

    with pytest.raises(ClienteNoHabilitado):
        iniciar_compra(
            usuario=sin_cliente,
            cliente_id=cliente_ajeno.pk,
            moneda_pagada=monedas[0],
            moneda_adquirida=monedas[1],
            monto_pagado="100.00",
        )

    assert CompraDivisa.objects.count() == 0


@pytest.mark.django_db
def test_iniciar_venta_rechaza_un_usuario_sin_cliente(
    sin_cliente, con_cliente, monedas, tasa, comision
):
    _usuario_ajeno, cliente_ajeno = con_cliente
    cuenta = CuentaPago.objects.create(
        cliente=cliente_ajeno,
        tipo=CuentaPago.Tipo.BANCARIA,
        entidad="Itau",
        numero_cuenta="123456",
        titular="Ana Gomez",
    )

    with pytest.raises(ClienteNoHabilitado):
        iniciar_venta(
            usuario=sin_cliente,
            cliente_id=cliente_ajeno.pk,
            moneda_entregada=monedas[0],
            moneda_acreditada=monedas[1],
            cuenta_destino=cuenta,
            monto_entregado="100.00",
        )

    assert VentaDivisa.objects.count() == 0


@pytest.mark.django_db
def test_iniciar_pago_rechaza_la_compra_de_otro(
    sin_cliente, con_cliente, monedas, tasa, comision
):
    """Antes de RF010 alcanzaba con pasarle el pk de la compra de cualquiera."""
    usuario, cliente = con_cliente
    compra = iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )

    with pytest.raises(ClienteNoHabilitado):
        iniciar_pago(compra.pk, usuario=sin_cliente)

    assert Pago.objects.count() == 0


@pytest.mark.django_db
def test_cliente_habilitado_para_exige_asociacion_y_cliente_activo(con_cliente):
    usuario, cliente = con_cliente

    assert cliente_habilitado_para(usuario, cliente.pk) == cliente

    cliente.desactivar()
    with pytest.raises(ClienteNoHabilitado):
        cliente_habilitado_para(usuario, cliente.pk)


@pytest.mark.django_db
def test_confirmar_pago_compra_falla_si_el_cliente_fue_dado_de_baja(
    con_cliente, monedas, tasa, comision
):
    from apps.conversiones.services import CompraNoConfirmable

    usuario, cliente = con_cliente
    compra = iniciar_compra(
        usuario=usuario,
        cliente_id=cliente.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )
    cliente.desactivar()

    with pytest.raises(CompraNoConfirmable):
        confirmar_pago_compra(pk=compra.pk, usuario=usuario)

    compra.refresh_from_db()
    assert compra.estado == CompraDivisa.Estado.PENDIENTE


# ---------------------------------------------------------------------------
# Menú y roles
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_el_menu_sin_cliente_no_ofrece_operar(sin_cliente):
    textos = {opcion["texto"] for opcion in construir_menu(sin_cliente, None)}

    assert "Comprar divisas" not in textos
    assert "Vender divisas" not in textos
    assert "Mis medios de pago" not in textos
    assert "Historial de transacciones" not in textos
    # Las de consulta siguen estando.
    assert "Cotizaciones" in textos
    assert "Simular conversion" in textos


@pytest.mark.django_db
def test_el_menu_con_cliente_si_ofrece_operar(con_cliente):
    usuario, cliente = con_cliente
    textos = {opcion["texto"] for opcion in construir_menu(usuario, cliente)}

    assert "Comprar divisas" in textos
    assert "Vender divisas" in textos
    assert "Mis medios de pago" in textos


@pytest.mark.django_db
@pytest.mark.parametrize("rol", ["administrador", "analista_cambiario"])
def test_administrador_y_analista_no_son_bloqueados(client, django_user_model, rol):
    """RF010 es sobre `usuario_cliente` sin cliente, no sobre RF011."""
    usuario = _usuario(django_user_model, f"staff-{rol}", rol)
    client.force_login(usuario)

    assert client.get(reverse("tasas:panel")).status_code == 200
    assert client.get(reverse("usuarios:panel")).status_code == 200
    # Las pantallas de administración se rigen por su propio control de rol.
    esperado = 200 if rol == "administrador" else 403
    assert client.get(reverse("clientes:lista")).status_code == esperado
