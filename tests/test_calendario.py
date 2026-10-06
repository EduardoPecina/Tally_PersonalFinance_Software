"""Calendario bancario de México: Pascua, festivos y días hábiles."""

from datetime import date

import pytest

from motor import calendario


@pytest.mark.parametrize(
    ("anio", "pascua"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)),
     (2027, date(2027, 3, 28)), (2030, date(2030, 4, 21)), (2038, date(2038, 4, 25))],
)
def test_pascua(anio, pascua):
    assert calendario.pascua(anio) == pascua


def test_dias_inhabiles_2026():
    assert sorted(calendario.dias_inhabiles(2026)) == [
        date(2026, 1, 1), date(2026, 2, 2), date(2026, 3, 16), date(2026, 4, 2), date(2026, 4, 3),
        date(2026, 5, 1), date(2026, 9, 16), date(2026, 11, 2), date(2026, 11, 16), date(2026, 12, 12),
        date(2026, 12, 25),
    ]


def test_cambio_de_poder_ejecutivo_cada_seis_anios():
    assert date(2024, 10, 1) in calendario.dias_inhabiles(2024)
    assert date(2030, 10, 1) in calendario.dias_inhabiles(2030)
    assert date(2026, 10, 1) not in calendario.dias_inhabiles(2026)


def test_habiles():
    assert calendario.es_habil(date(2026, 10, 6))          # martes
    assert not calendario.es_habil(date(2026, 10, 3))      # sábado
    assert not calendario.es_habil(date(2026, 9, 16))      # Independencia
    assert calendario.siguiente_habil(date(2026, 10, 6)) == date(2026, 10, 6)
    assert calendario.siguiente_habil(date(2026, 12, 25)) == date(2026, 12, 28)   # viernes festivo → lunes
    assert calendario.sumar_dias_habiles(date(2026, 12, 23), 2) == date(2026, 12, 28)
    assert calendario.sumar_dias_habiles(date(2026, 4, 1), 1) == date(2026, 4, 6)  # salta jueves y viernes santos
    assert calendario.sumar_dias_habiles(date(2026, 4, 1), 0) == date(2026, 4, 1)
