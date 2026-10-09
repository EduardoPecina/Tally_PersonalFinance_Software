"""Datos ficticios compartidos por las pruebas. Nunca usar datos reales."""

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor import categorias, cuentas  # noqa: E402
from motor.libro import Libro  # noqa: E402
from motor.modelo import TipoCuenta  # noqa: E402

AHORA = datetime(2026, 7, 20, 12, 0, 0)
JULIO = (date(2026, 7, 1), date(2026, 7, 31))


def D(valor) -> Decimal:
    return Decimal(str(valor))


@pytest.fixture(autouse=True)
def _sin_respaldos_pendientes():
    """El portal hace el respaldo del día en segundo plano: ninguna prueba termina con uno a medias."""
    yield
    from motor import respaldos

    respaldos.esperar_en_curso()


@pytest.fixture
def libro() -> Libro:
    """Libro vacío con el catálogo inicial y reloj fijo."""
    lib = Libro(reloj=lambda: AHORA)
    categorias.cargar_catalogo_inicial(lib)
    return lib


@pytest.fixture
def cat(libro):
    """Atajo: ``cat("Alimentos")`` → id de la categoría."""

    def buscar(nombre: str) -> str:
        encontrada = categorias.buscar(libro, nombre)
        assert encontrada is not None, nombre
        return encontrada.id

    return buscar


@pytest.fixture
def ctas(libro):
    """Cuentas ficticias típicas: débito, crédito, ahorro e inversión."""

    class Cuentas:
        debito = cuentas.crear(libro, "Banco Ficticio Débito", TipoCuenta.DEBITO, fecha_creacion=date(2026, 1, 1)).id
        credito = cuentas.crear(
            libro, "Tarjeta Ficticia", TipoCuenta.CREDITO, limite_credito=1000, dia_corte=3, dia_pago=23,
            fecha_creacion=date(2026, 1, 1),
        ).id
        ahorro = cuentas.crear(libro, "Ahorro Ficticio", TipoCuenta.AHORRO, fecha_creacion=date(2026, 1, 1)).id
        inversion = cuentas.crear(libro, "Inversión Ficticia", TipoCuenta.INVERSION, fecha_creacion=date(2026, 1, 1)).id

    return Cuentas
