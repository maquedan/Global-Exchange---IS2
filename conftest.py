"""Configuración común a TODAS las pruebas del proyecto.

Existe por un incidente real: una prueba de RF025 terminó llamando a la API
de Factura Segura de verdad, porque el `.env` de la máquina tenía
`FACTURACION_PROVEEDOR=facturasegura` y `config.settings.dev` lee ese
archivo. Las pruebas de `apps/facturacion` ya se protegían con un fixture
propio, pero esa protección no alcanzaba a los demás archivos de prueba.

Acá el fixture es `autouse` y está en la raíz, así que vale para todo el
proyecto: ninguna prueba puede salir a la red ni gastar un número del rango
de facturación autorizado, corra en la máquina que corra.
"""
import pytest


@pytest.fixture(autouse=True)
def _facturacion_siempre_simulada(settings):
    """Fuerza el proveedor simulado de facturación en todas las pruebas.

    Una prueba que necesite otro valor lo sobrescribe: su propia asignación
    corre después de este fixture.
    """
    settings.FACTURACION_PROVEEDOR = "simulado"
    settings.FACTURASEGURA_TOKEN = ""


@pytest.fixture(autouse=True)
def _pagos_siempre_simulados(settings):
    """Mismo motivo, para la pasarela de pago (RF022).

    Hoy las pruebas de pagos reemplazan el proveedor con un doble, así que
    no dependen de esto; el fixture está para que una prueba nueva que se
    olvide de hacerlo tampoco llame a dLocal.
    """
    settings.PAGO_PROVEEDOR = "simulado"
    settings.DLOCAL_X_LOGIN = ""
    settings.DLOCAL_X_TRANS_KEY = ""
    settings.DLOCAL_SECRET_KEY = ""
