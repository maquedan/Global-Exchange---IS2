"""Pruebas de RF009 — Conmutación de Cliente en Sesión (GEG9-19).

RF008 dejó hecho el mecanismo (elegir, guardar en sesión, revalidar). Lo que
se verifica acá es lo propio de RF009: **cambiar** de cliente estando ya
operando con otro, sin cerrar sesión, y que ese cambio no abra ninguna
puerta.

La prueba que más importa es `test_no_redirige_a_un_sitio_externo`: el
parámetro `siguiente` llega del navegador y, sin validar, permitía una
redirección abierta.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import AsociacionUsuarioCliente, Cliente
from apps.comisiones.models import ComisionCategoria
from apps.conversiones.models import CompraDivisa
from apps.conversiones.services import iniciar_compra
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio
from apps.usuarios.services import CLAVE_SESION


def _cliente(nombre, documento):
    return Cliente.objects.create(
        tipo=Cliente.Tipo.FISICA,
        nombres=nombre,
        apellidos="Prueba",
        documento=documento,
        email=f"{nombre.lower()}@example.com",
        telefono="0981000000",
        direccion="Asuncion",
    )


@pytest.fixture
def usuario_con_dos_clientes(db, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="cliente-rf009", email="rf009@example.com"
    )
    grupo, _ = Group.objects.get_or_create(name="usuario_cliente")
    usuario.groups.add(grupo)
    primero = _cliente("Ana", "1111111")
    segundo = _cliente("Beto", "2222222")
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=primero)
    AsociacionUsuarioCliente.objects.create(usuario=usuario, cliente=segundo)
    return usuario, primero, segundo


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


# ---------------------------------------------------------------------------
# El cambio en sí
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cambia_de_cliente_sin_cerrar_sesion(client, usuario_con_dos_clientes):
    usuario, primero, segundo = usuario_con_dos_clientes
    client.force_login(usuario)
    sesion_antes = client.session.session_key

    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": primero.pk})
    assert client.session[CLAVE_SESION] == primero.pk

    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": segundo.pk})

    assert client.session[CLAVE_SESION] == segundo.pk
    # Lo importante: es la MISMA sesión, no se deslogueó en el medio.
    assert client.session.session_key == sesion_antes


@pytest.mark.django_db
def test_el_encabezado_muestra_el_cliente_nuevo(client, usuario_con_dos_clientes):
    usuario, primero, segundo = usuario_con_dos_clientes
    client.force_login(usuario)

    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": primero.pk})
    pagina = client.get(reverse("usuarios:panel")).content.decode()
    assert "Ana Prueba" in pagina

    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": segundo.pk})
    pagina = client.get(reverse("usuarios:panel")).content.decode()

    assert "Beto Prueba" in pagina
    assert "Ana Prueba" not in pagina


@pytest.mark.django_db
def test_el_enlace_para_cambiar_solo_aparece_con_varios_clientes(
    client, usuario_con_dos_clientes
):
    usuario, primero, segundo = usuario_con_dos_clientes
    client.force_login(usuario)
    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": primero.pk})

    respuesta = client.get(reverse("usuarios:panel"))
    assert respuesta.context["puede_cambiar_cliente"] is True

    # Con un solo cliente no hay nada que elegir: el enlace no debe ofrecerse.
    AsociacionUsuarioCliente.objects.filter(cliente=segundo).delete()
    respuesta = client.get(reverse("usuarios:panel"))
    assert respuesta.context["puede_cambiar_cliente"] is False


# ---------------------------------------------------------------------------
# A dónde vuelve después de cambiar
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_vuelve_a_la_pantalla_en_la_que_estaba(client, usuario_con_dos_clientes):
    usuario, primero, _segundo = usuario_con_dos_clientes
    client.force_login(usuario)
    destino = reverse("conversiones:comprar")

    respuesta = client.post(
        reverse("usuarios:seleccionar_cliente"),
        {"cliente_id": primero.pk, "siguiente": destino},
    )

    assert respuesta.url == destino


@pytest.mark.django_db
@pytest.mark.parametrize(
    "destino_hostil",
    [
        "https://sitio-malicioso.example.com/phishing",
        "//sitio-malicioso.example.com/phishing",
        "http://otrodominio.test/",
        "javascript:alert(1)",
    ],
)
def test_no_redirige_a_un_sitio_externo(
    client, usuario_con_dos_clientes, destino_hostil
):
    """Redirección abierta: el agujero que esta historia vino a tapar.

    `siguiente` lo controla quien arma el enlace. Sin validarlo, bastaba con
    mandarle a alguien una dirección que empieza con nuestro dominio para
    terminar depositándolo en una página ajena que imita la nuestra.
    """
    usuario, primero, _segundo = usuario_con_dos_clientes
    client.force_login(usuario)

    respuesta = client.post(
        reverse("usuarios:seleccionar_cliente"),
        {"cliente_id": primero.pk, "siguiente": destino_hostil},
    )

    assert respuesta.url == reverse("usuarios:panel")
    assert "malicioso" not in respuesta.url
    assert not respuesta.url.startswith("javascript:")


@pytest.mark.django_db
def test_tampoco_por_query_string(client, usuario_con_dos_clientes):
    """El mismo parámetro viaja por GET cuando lo arma el middleware."""
    usuario, primero, _segundo = usuario_con_dos_clientes
    client.force_login(usuario)
    url = reverse("usuarios:seleccionar_cliente") + "?siguiente=https://malo.example.com"

    respuesta = client.post(url, {"cliente_id": primero.pk})

    assert respuesta.url == reverse("usuarios:panel")


# ---------------------------------------------------------------------------
# Que cambiar de cliente no abra ninguna puerta
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_se_puede_cambiar_a_un_cliente_ajeno(client, usuario_con_dos_clientes):
    usuario, primero, _segundo = usuario_con_dos_clientes
    ajeno = _cliente("Carlos", "9999999")
    client.force_login(usuario)
    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": primero.pk})

    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": ajeno.pk})

    # Sigue operando con el suyo: el id ajeno se ignora.
    assert client.session[CLAVE_SESION] == primero.pk


@pytest.mark.django_db
def test_una_operacion_pendiente_del_otro_cliente_no_queda_operable(
    client, usuario_con_dos_clientes, monedas, tasa, comision
):
    """Al cambiar de cliente, lo de antes no debe poder confirmarse.

    El servicio filtra por el cliente de la operación, no por el activo, así
    que la compra de Ana sigue siendo de Ana. Lo que se verifica es que
    cambiar el cliente de la sesión no la vuelva confirmable "por arrastre".
    """
    usuario, primero, segundo = usuario_con_dos_clientes
    compra = iniciar_compra(
        usuario=usuario,
        cliente_id=primero.pk,
        moneda_pagada=monedas[0],
        moneda_adquirida=monedas[1],
        monto_pagado="100.00",
    )
    client.force_login(usuario)
    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": segundo.pk})

    client.post(reverse("conversiones:confirmar_compra", args=[compra.pk]))

    compra.refresh_from_db()
    assert compra.estado == CompraDivisa.Estado.PENDIENTE
    assert compra.cliente == primero


@pytest.mark.django_db
def test_si_desactivan_el_cliente_elegido_pasa_al_que_queda(
    client, usuario_con_dos_clientes
):
    """Con uno solo disponible no se le pregunta nada: se elige solo (RF008)."""
    usuario, primero, segundo = usuario_con_dos_clientes
    client.force_login(usuario)
    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": primero.pk})

    primero.desactivar()

    respuesta = client.get(reverse("usuarios:panel"))
    assert respuesta.context["cliente_activo"] == segundo
    # Y ya no tiene sentido ofrecerle cambiar: le queda uno.
    assert respuesta.context["puede_cambiar_cliente"] is False


@pytest.mark.django_db
def test_si_desactivan_todos_sus_clientes_se_vuelve_a_pedir(
    client, usuario_con_dos_clientes
):
    usuario, primero, segundo = usuario_con_dos_clientes
    client.force_login(usuario)
    client.post(reverse("usuarios:seleccionar_cliente"), {"cliente_id": primero.pk})

    primero.desactivar()
    segundo.desactivar()

    respuesta = client.get(reverse("usuarios:panel"))
    assert respuesta.context["cliente_activo"] is None
