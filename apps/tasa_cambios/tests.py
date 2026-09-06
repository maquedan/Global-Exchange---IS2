from datetime import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.monedas.models import Moneda

from .forms import TasaCambioForm
from .models import TasaCambio


Usuario = get_user_model()


def usuario_con_rol(rol):
	usuario = Usuario.objects.create_user(username=f"tasa-{rol}")
	usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
	return usuario


@pytest.fixture
def monedas():
	return (
		Moneda.objects.create(codigo="USD", nombre="Dolar", simbolo="$"),
		Moneda.objects.create(codigo="EUR", nombre="Euro", simbolo="E"),
	)


def datos_tasa(moneda_origen, moneda_destino, **cambios):
	datos = {
		"moneda_origen": moneda_origen.pk,
		"moneda_destino": moneda_destino.pk,
		"tasa_compra": "7.100000",
		"tasa_venta": "7.200000",
		"vigente_desde": datetime(2026, 9, 6, 10, 0).strftime("%Y-%m-%dT%H:%M"),
		"activo": "on",
	}
	datos.update(cambios)
	return datos


@pytest.mark.django_db
def test_analista_puede_crear_tasa(client, monedas):
	usuario = usuario_con_rol("analista_cambiario")
	client.force_login(usuario)

	respuesta = client.post(
		reverse("tasa_cambios:crear"),
		datos_tasa(*monedas),
	)

	assert respuesta.status_code == 302
	assert TasaCambio.objects.filter(moneda_origen=monedas[0], moneda_destino=monedas[1]).exists()


@pytest.mark.django_db
def test_usuario_cliente_no_puede_gestionar_tasas(client):
	client.force_login(usuario_con_rol("usuario_cliente"))

	assert client.get(reverse("tasa_cambios:lista")).status_code == 403


@pytest.mark.django_db
def test_formulario_rechaza_misma_moneda(monedas):
	formulario = TasaCambioForm(datos_tasa(monedas[0], monedas[0]))

	assert not formulario.is_valid()
	assert "moneda_destino" in formulario.errors


@pytest.mark.django_db
def test_formulario_rechaza_dos_tasas_activas_para_el_mismo_par(monedas):
	TasaCambio.objects.create(
		moneda_origen=monedas[0],
		moneda_destino=monedas[1],
		tasa_compra=Decimal("7.100000"),
		tasa_venta=Decimal("7.200000"),
		vigente_desde=timezone.now(),
	)

	formulario = TasaCambioForm(datos_tasa(monedas[0], monedas[1]))

	assert not formulario.is_valid()
	assert "moneda_origen" in formulario.errors or "__all__" in formulario.errors

# Create your tests here.
