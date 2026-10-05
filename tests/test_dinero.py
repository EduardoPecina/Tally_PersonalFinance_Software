from decimal import Decimal

import pytest

from motor.dinero import a_centavos, a_pesos, formatear
from motor.errores import ErrorValidacion


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (500, 50000),
        ("1,234.56", 123456),
        ("$ 4,210.10", 421010),
        (Decimal("0.01"), 1),
        (0.1, 10),
        (59.94, 5994),
        ("-200", -20000),
        ("12.5", 1250),
    ],
)
def test_a_centavos(valor, esperado):
    assert a_centavos(valor) == esperado


@pytest.mark.parametrize("valor", ["abc", "", "1.234", 1.005, True, None, Decimal("NaN"), "inf"])
def test_a_centavos_rechaza_valores_invalidos(valor):
    with pytest.raises(ErrorValidacion):
        a_centavos(valor)


def test_a_pesos_y_formato():
    assert a_pesos(421010) == Decimal("4210.10")
    assert formatear(Decimal("1234.5")) == "$1,234.50"
    assert formatear(Decimal("-800")) == "-$800.00"
    assert formatear(0) == "$0.00"


def test_suma_sin_errores_de_punto_flotante():
    total = sum(a_centavos(0.1) for _ in range(10))
    assert a_pesos(total) == Decimal("1.00")
