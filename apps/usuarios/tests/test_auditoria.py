from datetime import timedelta

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.admin import RegistroAuditoriaAdmin
from apps.usuarios.models import RegistroAuditoria


def usuario_con_rol(username, rol):
    usuario = get_user_model().objects.create_user(username=username)
    grupo, _ = Group.objects.get_or_create(name=rol)
    usuario.groups.add(grupo)
    return usuario


@pytest.mark.django_db
def test_solo_administrador_puede_consultar_auditoria(client):
    analista = usuario_con_rol("analista-auditoria", "analista_cambiario")
    client.force_login(analista)

    assert client.get(reverse("usuarios:auditoria")).status_code == 302


@pytest.mark.django_db
def test_administrador_filtra_registros_por_usuario_accion_y_fecha(client):
    administrador = usuario_con_rol("admin-auditoria", "administrador")
    otro_usuario = usuario_con_rol("otro-auditoria", "administrador")
    registro = RegistroAuditoria.objects.create(
        usuario=administrador,
        usuario_nombre=administrador.username,
        accion=RegistroAuditoria.Accion.COMISION_CREADA,
        detalles="Categoría Minorista.",
    )
    RegistroAuditoria.objects.create(
        usuario=administrador,
        usuario_nombre=administrador.username,
        accion=RegistroAuditoria.Accion.TASA_CREADA,
    )
    RegistroAuditoria.objects.create(
        usuario=otro_usuario,
        usuario_nombre=otro_usuario.username,
        accion=RegistroAuditoria.Accion.COMISION_CREADA,
    )
    RegistroAuditoria.objects.filter(pk=registro.pk).update(
        creado_en=timezone.now() - timedelta(days=1)
    )
    client.force_login(administrador)

    respuesta = client.get(
        reverse("usuarios:auditoria"),
        {
            "usuario": administrador.username,
            "accion": RegistroAuditoria.Accion.COMISION_CREADA,
            "fecha_desde": timezone.localdate().isoformat(),
            "fecha_hasta": timezone.localdate().isoformat(),
        },
    )

    assert respuesta.status_code == 200
    assert list(respuesta.context["registros"]) == []
    respuesta = client.get(
        reverse("usuarios:auditoria"),
        {
            "usuario": administrador.username,
            "accion": RegistroAuditoria.Accion.COMISION_CREADA,
        },
    )
    assert list(respuesta.context["registros"]) == [registro]


@pytest.mark.django_db
def test_pantalla_de_auditoria_no_permite_editar_ni_borrar(client):
    administrador = usuario_con_rol("admin-auditoria-post", "administrador")
    client.force_login(administrador)

    respuesta = client.post(reverse("usuarios:auditoria"), {"accion": "borrar"})

    assert respuesta.status_code == 405
    assert RegistroAuditoria.objects.count() == 0


@pytest.mark.django_db
def test_admin_de_django_solo_expone_auditoria_en_modo_lectura():
    administrador = usuario_con_rol("admin-auditoria-modelo", "administrador")
    operador = usuario_con_rol("staff-auditoria-modelo", "analista_cambiario")
    operador.is_staff = True
    operador.save(update_fields=["is_staff"])
    modelo_admin = RegistroAuditoriaAdmin(RegistroAuditoria, admin.site)
    fabrica = RequestFactory()

    solicitud_admin = fabrica.get("/admin/")
    solicitud_admin.user = administrador
    solicitud_operador = fabrica.get("/admin/")
    solicitud_operador.user = operador

    assert modelo_admin.has_view_permission(solicitud_admin)
    assert not modelo_admin.has_add_permission(solicitud_admin)
    assert not modelo_admin.has_change_permission(solicitud_admin)
    assert not modelo_admin.has_delete_permission(solicitud_admin)
    assert not modelo_admin.has_view_permission(solicitud_operador)


@pytest.mark.django_db
def test_registra_operaciones_de_alta_de_cliente_y_comision(client):
    administrador = usuario_con_rol("admin-auditoria-alta", "administrador")
    client.force_login(administrador)

    respuesta_cliente = client.post(
        reverse("clientes:crear"),
        {
            "tipo": "FISICA",
            "categoria": "MINORISTA",
            "nombres": "Ana",
            "apellidos": "Gómez",
            "documento": "AUD-12345",
            "email": "ana-auditoria@example.com",
            "telefono": "0981000000",
            "direccion": "Asunción",
        },
    )
    respuesta_comision = client.post(
        reverse("comisiones:crear"),
        {"categoria": "MINORISTA", "porcentaje": "2.50"},
    )

    assert respuesta_cliente.status_code == 302
    assert respuesta_comision.status_code == 302
    assert list(
        RegistroAuditoria.objects.order_by("accion").values_list("accion", flat=True)
    ) == [
        RegistroAuditoria.Accion.CLIENTE_CREADO,
        RegistroAuditoria.Accion.COMISION_CREADA,
    ]
