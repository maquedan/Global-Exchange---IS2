import os
from decimal import Decimal, InvalidOperation

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.cajas.models import (
    Caja,
    DenominacionBillete,
    InventarioBilleteCaja,
    SaldoCaja,
    Sucursal,
)
from apps.clientes.models import Cliente
from apps.comisiones.models import ComisionCategoria
from apps.monedas.models import Moneda
from apps.tasa_cambios.models import TasaCambio


MONEDAS = {
    "USD": ("Dólar estadounidense", "$"),
    "PYG": ("Guaraní", "₲"),
    "EUR": ("Euro", "€"),
    "BRL": ("Real brasileño", "R$"),
    "ARS": ("Peso argentino", "$"),
    "GBP": ("Libra esterlina", "£"),
    "JPY": ("Yen japonés", "¥"),
}
ROLES = ("administrador", "analista_cambiario", "usuario_cliente", "cajero")
CATEGORIAS = tuple(valor for valor, _ in Cliente.Categoria.choices)
COMISIONES_DEMO = {
    "MINORISTA": Decimal("2.50"),
    "CORPORATIVO": Decimal("2.00"),
    "VIP": Decimal("1.50"),
}
TASAS_DEMO = {
    "USD": (Decimal("7120.00"), Decimal("7220.00")),
    "EUR": (Decimal("7690.00"), Decimal("7820.00")),
    "BRL": (Decimal("1300.00"), Decimal("1350.00")),
    "ARS": (Decimal("7.00"), Decimal("7.35")),
    "GBP": (Decimal("9100.00"), Decimal("9250.00")),
    "JPY": (Decimal("48.20"), Decimal("50.40")),
}
DENOMINACIONES_DEMO = {
    "USD": (Decimal("100.00"), Decimal("50.00"), Decimal("20.00"), Decimal("10.00"), Decimal("5.00"), Decimal("1.00")),
    "PYG": (Decimal("100000.00"), Decimal("50000.00"), Decimal("20000.00"), Decimal("10000.00"), Decimal("5000.00")),
}


class Command(BaseCommand):
    help = "Carga datos iniciales mínimos de producción o datos demo de desarrollo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            choices=("demo", "minimal"),
            required=True,
            help="demo incluye datos ficticios; minimal solo catálogos y configuración de producción.",
        )

    def handle(self, *args, **options):
        perfil = options["profile"]
        codigos_monedas = tuple(MONEDAS) if perfil == "demo" else ("USD", "PYG")
        comisiones = COMISIONES_DEMO if perfil == "demo" else self._comisiones_produccion()
        tasas = TASAS_DEMO if perfil == "demo" else self._tasas_produccion()

        with transaction.atomic():
            monedas_creadas = {
                codigo: Moneda.objects.get_or_create(
                    codigo=codigo,
                    defaults={
                        "nombre": MONEDAS[codigo][0],
                        "simbolo": MONEDAS[codigo][1],
                        "activo": True,
                    },
                )[0]
                for codigo in codigos_monedas
            }

            for codigo, porcentaje in comisiones.items():
                ComisionCategoria.objects.get_or_create(
                    categoria=codigo,
                    defaults={"porcentaje": porcentaje},
                )

            for rol in ROLES:
                Group.objects.get_or_create(name=rol)

            moneda_pyg = monedas_creadas["PYG"]
            for codigo, (compra, venta) in tasas.items():
                moneda_origen = monedas_creadas[codigo]
                if not moneda_origen.activo or not moneda_pyg.activo:
                    continue
                if TasaCambio.objects.filter(
                    moneda_origen=moneda_origen,
                    moneda_destino=moneda_pyg,
                ).exists():
                    continue
                TasaCambio.objects.create(
                    moneda_origen=moneda_origen,
                    moneda_destino=moneda_pyg,
                    tasa_compra=compra,
                    tasa_venta=venta,
                    vigente_desde=timezone.now(),
                    activo=True,
                )

            if perfil == "demo":
                self._crear_clientes_demo()
                self._crear_caja_demo(monedas_creadas)

        self.stdout.write(self.style.SUCCESS(f"Datos iniciales ({perfil}) cargados correctamente."))

    def _comisiones_produccion(self):
        return {
            categoria: self._decimal_requerido(
                f"INITIAL_COMMISSION_{categoria}",
                minimo=Decimal("0"),
                maximo=Decimal("100"),
            )
            for categoria in CATEGORIAS
        }

    def _tasas_produccion(self):
        maximo = Decimal("9999999999.99")
        compra = self._decimal_requerido(
            "INITIAL_USD_PYG_BUY_RATE",
            minimo=Decimal("0.01"),
            maximo=maximo,
        )
        venta = self._decimal_requerido(
            "INITIAL_USD_PYG_SELL_RATE",
            minimo=Decimal("0.01"),
            maximo=maximo,
        )
        if compra > venta:
            raise CommandError("INITIAL_USD_PYG_BUY_RATE no puede superar INITIAL_USD_PYG_SELL_RATE.")
        return {"USD": (compra, venta)}

    @staticmethod
    def _decimal_requerido(nombre, *, minimo, maximo=None):
        valor = os.environ.get(nombre, "").strip()
        try:
            numero = Decimal(valor)
        except (InvalidOperation, ValueError):
            raise CommandError(f"Definí {nombre} con un valor decimal válido.") from None
        try:
            normalizado = numero.quantize(Decimal("0.01"))
        except InvalidOperation:
            raise CommandError(f"{nombre} debe tener como máximo dos decimales.") from None
        if normalizado != numero:
            raise CommandError(f"{nombre} debe tener como máximo dos decimales.")
        numero = normalizado
        if not numero.is_finite() or numero < minimo or (maximo is not None and numero > maximo):
            limite = f" entre {minimo} y {maximo}" if maximo is not None else f" mayor o igual que {minimo}"
            raise CommandError(f"{nombre} debe ser{limite}.")
        return numero

    @staticmethod
    def _crear_clientes_demo():
        clientes = (
            {
                "documento": "DEMO-000001",
                "tipo": Cliente.Tipo.FISICA,
                "categoria": Cliente.Categoria.MINORISTA,
                "nombres": "Ana",
                "apellidos": "Ejemplo",
                "email": "ana.ejemplo@example.org",
                "telefono": "+595 21 000 000",
                "direccion": "Dirección de prueba 100",
            },
            {
                "documento": "DEMO-000002",
                "tipo": Cliente.Tipo.FISICA,
                "categoria": Cliente.Categoria.VIP,
                "nombres": "Luis",
                "apellidos": "Demostración",
                "email": "luis.demo@example.org",
                "telefono": "+595 21 000 001",
                "direccion": "Dirección de prueba 200",
            },
            {
                "ruc": "DEMO-RUC-0001",
                "tipo": Cliente.Tipo.JURIDICA,
                "categoria": Cliente.Categoria.CORPORATIVO,
                "razon_social": "Comercial de Ejemplo S.A.",
                "email": "contacto@example.org",
                "telefono": "+595 21 000 002",
                "direccion": "Dirección de prueba 300",
            },
        )
        for datos in clientes:
            identificador = (
                {"documento": datos["documento"]}
                if "documento" in datos
                else {"ruc": datos["ruc"]}
            )
            Cliente.objects.get_or_create(**identificador, defaults=datos)

    @staticmethod
    def _crear_caja_demo(monedas):
        sucursal, _ = Sucursal.objects.get_or_create(
            nombre="Casa Central Demo",
            defaults={"direccion": "Dirección de demostración"},
        )
        caja, _ = Caja.objects.get_or_create(sucursal=sucursal)
        for codigo in ("USD", "PYG"):
            moneda = monedas[codigo]
            SaldoCaja.objects.get_or_create(
                caja=caja,
                moneda=moneda,
                defaults={"saldo": Decimal("0.00")},
            )
            for valor in DENOMINACIONES_DEMO[codigo]:
                denominacion, _ = DenominacionBillete.objects.get_or_create(
                    moneda=moneda,
                    valor=valor,
                )
                InventarioBilleteCaja.objects.get_or_create(
                    caja=caja,
                    denominacion=denominacion,
                    defaults={"cantidad": 0},
                )
