"""Reintenta las facturas que no llegaron a generarse (RF026 — GEG9-50).

Se corre a mano (o desde una tarea programada) cuando la emisión automática
falló: por ejemplo porque faltaba una credencial, porque Factura Segura
rechazó el DE o porque la API estaba caída.

Las facturas `A_VERIFICAR` quedan afuera: ahí la comunicación se cortó y el
documento pudo haberse generado igual. Reenviarlas a ciegas duplicaría la
factura, así que necesitan que alguien confirme primero en Factura Segura.
"""
from django.core.management.base import BaseCommand

from apps.facturacion.models import Factura
from apps.facturacion.services import ESTADOS_REINTENTABLES, emitir_factura


class Command(BaseCommand):
    help = "Reintenta la emisión de las facturas en estado PENDIENTE o ERROR."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite",
            type=int,
            default=50,
            help="Cuántas facturas reintentar como máximo (por defecto, 50).",
        )

    def handle(self, *args, **opciones):
        pendientes = (
            Factura.objects.filter(estado__in=ESTADOS_REINTENTABLES)
            .select_related("compra__cliente", "venta__cliente")
            .order_by("creada_en")[: opciones["limite"]]
        )

        if not pendientes:
            self.stdout.write("No hay facturas para reintentar.")
            return

        generadas = 0
        for factura in pendientes:
            resultado = emitir_factura(factura.operacion)
            if resultado.estado == Factura.Estado.GENERADA:
                generadas += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{resultado.numero_completo}: generada (CDC {resultado.cdc})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"{resultado.numero_completo}: {resultado.estado} — "
                        f"{resultado.mensaje_error}"
                    )
                )

        self.stdout.write(
            f"Reintentadas {len(pendientes)}; generadas {generadas}."
        )
