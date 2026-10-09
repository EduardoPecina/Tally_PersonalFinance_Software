"""Lo negativo en rojo: textos, métricas y tablas. Solo datos ficticios."""

from datetime import date, datetime
from decimal import Decimal

import pytest

pytest.importorskip("streamlit")
import pandas as pd  # noqa: E402

from motor import monedas  # noqa: E402
from portal.componentes import formato  # noqa: E402


@pytest.fixture(autouse=True)
def volver_a_la_de_siempre():
    yield
    monedas.usar(None)


def test_textos_y_metricas():
    assert formato.dinero_md(Decimal("-300")) == ":red[-\\$300.00]"
    assert formato.dinero_md(Decimal("300")) == "\\$300.00"
    assert formato.dinero_md(Decimal("-0.001")) == "\\$0.00"                 # sin un «-0» rojo
    assert formato.dinero_con_signo_md(Decimal(80), "-") == ":red[-\\$80.00]"
    assert formato.dinero_con_signo_md(Decimal(80), "+") == "+\\$80.00"
    assert formato.dinero_con_signo_md(Decimal(80), "↔") == "↔ \\$80.00"
    assert formato.dinero_metrica(Decimal(-5)) == ":red[-\\$5.00]"
    assert formato.dinero_metrica(Decimal(5)) == "$5.00"                      # igual que antes
    monedas.usar("EUR")
    assert formato.dinero_metrica(Decimal("-1234.5")) == ":red[-1.234,50 €]"


def _rojas(estilo) -> set[tuple[int, int]]:
    estilo._compute()
    return {celda for celda, css in estilo.ctx.items() if ("color", formato.ROJO) in css}


def test_tablas_con_lo_negativo_en_rojo():
    monedas.usar("EUR")
    tabla = pd.DataFrame({
        "Texto": ["-$300.00", "+$1,000.00", "—", "-5.2 %", "-1.234,56 €", "- nota", "↔ $50.00"],
        "Número": [-1.5, 2.0, None, float("nan"), 0.0, 3.0, -0.01],
    })
    assert _rojas(formato.pintar(tabla)) == {(0, 0), (3, 0), (4, 0), (0, 1), (6, 1)}
    assert _rojas(formato.pintar(tabla, rojas=("Número",))) >= {(1, 1), (5, 1)}   # columna de salidas: completa
    con_estilo = tabla.style.map(lambda v: "font-weight: bold", subset=["Texto"])
    assert (0, 0) in _rojas(formato.pintar(con_estilo))                       # respeta el estilo que ya tenía


def test_tablas_enormes_y_vacias_van_tal_cual():
    grande = pd.DataFrame({"Importe": ["-$1.00"] * (formato.LIMITE_COLOR + 1)})
    assert formato.pintar(grande) is grande
    vacia = pd.DataFrame({"Importe": []})
    assert formato.pintar(vacia) is vacia


def test_cuando_se_guardo():
    hoy = date(2026, 10, 9)
    assert formato.cuando(datetime(2026, 10, 9, 18, 42), hoy) == "hoy 6:42 p. m."
    assert formato.cuando(datetime(2026, 10, 8, 9, 5), hoy) == "ayer 9:05 a. m."
    assert formato.cuando(datetime(2026, 10, 7, 0, 30), hoy) == "el 07/10/2026 12:30 a. m."
    assert formato.hora(datetime(2026, 10, 9, 12, 0)) == "12:00 p. m."
