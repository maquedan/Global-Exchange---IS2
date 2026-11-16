"""Asocia un usuario a los clientes de demostración (RF007).

Existe por un problema concreto de trabajo en equipo: `cargar_datos_iniciales
--profile demo` crea los clientes, pero **no** puede asociarlos a ningún
usuario. Los usuarios de Django no se crean con una migración ni con un
fixture: los crea `mozilla_django_oidc` la primera vez que la persona entra
por Keycloak, así que su id cambia en cada máquina y no se puede dejar
escrito en ningún lado.

Por eso la asociación se hace después, con este comando, buscando por nombre
de usuario y por documento en vez de por id.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db import transaction

from apps.clientes.models import AsociacionUsuarioCliente, Cliente

# Los que crea `cargar_datos_iniciales --profile demo`.
DOCUMENTOS_DEMO = ("DEMO-000001", "DEMO-000002")
RUCS_DEMO = ("DEMO-RUC-0001",)


class Command(BaseCommand):
    help = (
        "Asocia un usuario (por defecto cliente.demo) a los clientes de "
        "demostración, para poder operar sin cargar nada a mano."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--usuario",
            default="cliente.demo",
            help="Nombre de usuario a asociar (por defecto, cliente.demo).",
        )
        parser.add_argument(
            "--documento",
            action="append",
            default=None,
            help=(
                "Documento o RUC de un cliente concreto. Se puede repetir. "
                "Si no se indica ninguno, se usan los clientes demo."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        nombre_usuario = opciones["usuario"]
        usuario = get_user_model().objects.filter(username=nombre_usuario).first()

        if usuario is None:
            self.stdout.write(
                self.style.ERROR(
                    f"El usuario «{nombre_usuario}» todavía no existe en Django.\n"
                    "Se crea solo la primera vez que esa persona inicia sesión por "
                    "Keycloak: entrá una vez con ese usuario y volvé a correr esto."
                )
            )
            return

        clientes = self._clientes(opciones["documento"])
        if not clientes:
            self.stdout.write(
                self.style.ERROR(
                    "No se encontró ningún cliente para asociar. Si todavía no "
                    "cargaste los datos de demostración, corré antes:\n"
                    "  python manage.py cargar_datos_iniciales --profile demo"
                )
            )
            return

        nuevas = 0
        for cliente in clientes:
            _, creada = AsociacionUsuarioCliente.objects.get_or_create(
                usuario=usuario, cliente=cliente
            )
            estado = "asociado" if creada else "ya estaba asociado"
            nuevas += int(creada)
            self.stdout.write(f"  {cliente} — {estado}")

        self.stdout.write(
            self.style.SUCCESS(
                f"{nombre_usuario}: {nuevas} asociación(es) nueva(s), "
                f"{len(clientes)} cliente(s) en total."
            )
        )

    @staticmethod
    def _clientes(documentos):
        """Clientes activos a asociar, por documento o RUC.

        Se busca por el identificador y no por id para que el comando valga
        igual en cualquier máquina.
        """
        if documentos:
            filtro = Q(documento__in=documentos) | Q(ruc__in=documentos)
        else:
            filtro = Q(documento__in=DOCUMENTOS_DEMO) | Q(ruc__in=RUCS_DEMO)

        return list(Cliente.objects.filter(filtro, activo=True))
