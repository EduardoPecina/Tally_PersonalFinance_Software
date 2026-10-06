"""Días hábiles bancarios en México.

Sirve para calcular fechas límite de pago de tarjetas: muchos contratos dicen
«N días hábiles después del corte» o «si el vencimiento cae en día inhábil, se
recorre al día hábil siguiente».

Días inhábiles para los bancos (calendario que publica cada año la CNBV):

- sábados y domingos;
- 1 de enero, 1 de mayo, 16 de septiembre, 2 de noviembre, 12 y 25 de diciembre;
- primer lunes de febrero (Constitución), tercer lunes de marzo (Benito Juárez)
  y tercer lunes de noviembre (Revolución);
- jueves y viernes santos (cambian cada año con la Pascua);
- 1 de octubre cada seis años, cuando hay cambio de Poder Ejecutivo (2024, 2030…).

Es una referencia: si la CNBV agrega un día extraordinario, TALLY no lo sabrá.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo anónimo gregoriano, de Meeus/Jones/Butcher)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 - nombre del algoritmo original
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def _lunes_numero(anio: int, mes: int, numero: int) -> date:
    """El n-ésimo lunes del mes (``numero`` = 1 para el primero)."""
    primero = date(anio, mes, 1)
    return primero + timedelta(days=(7 - primero.weekday()) % 7 + 7 * (numero - 1))


@lru_cache(maxsize=64)
def dias_inhabiles(anio: int) -> frozenset[date]:
    """Días festivos bancarios del año (sin contar sábados ni domingos)."""
    domingo_pascua = pascua(anio)
    dias = {
        date(anio, 1, 1),
        _lunes_numero(anio, 2, 1),
        _lunes_numero(anio, 3, 3),
        domingo_pascua - timedelta(days=3),  # jueves santo
        domingo_pascua - timedelta(days=2),  # viernes santo
        date(anio, 5, 1),
        date(anio, 9, 16),
        date(anio, 11, 2),
        _lunes_numero(anio, 11, 3),
        date(anio, 12, 12),
        date(anio, 12, 25),
    }
    if anio >= 2024 and (anio - 2024) % 6 == 0:
        dias.add(date(anio, 10, 1))
    return frozenset(dias)


def es_habil(fecha: date) -> bool:
    return fecha.weekday() < 5 and fecha not in dias_inhabiles(fecha.year)


def siguiente_habil(fecha: date) -> date:
    """La misma fecha si es hábil; si no, el siguiente día hábil."""
    while not es_habil(fecha):
        fecha += timedelta(days=1)
    return fecha


def sumar_dias_habiles(fecha: date, dias: int) -> date:
    """La fecha que resulta de contar ``dias`` días hábiles después de ``fecha`` (sin contarla)."""
    while dias > 0:
        fecha += timedelta(days=1)
        if es_habil(fecha):
            dias -= 1
    return fecha
