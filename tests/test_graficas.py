"""Las gráficas (portal/componentes/graficas.py) están bien escritas para Vega-Lite.

Al usar TALLY, Altair no las revisa contra el esquema (por rapidez): esta prueba sí revisa cada una, con datos
ficticios, para que un error no llegue al navegador.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest
from streamlit.elements import vega_charts

from portal.componentes import graficas

FILAS = [(f"Categoría ficticia {i}", Decimal(1000 + 37 * i)) for i in range(12)]
PUNTOS = [(date(2025, 1, 1) + timedelta(days=i), Decimal(10_000 + 3 * i)) for i in range(120)]
MESES = [f"2025-{m:02d}" for m in range(1, 7)]
POR_PERIODO = pd.DataFrame([{"Periodo": p, "Grupo": g, "Valor": float(100 * m + i)}
                            for m, p in enumerate(MESES, 1) for i, g in enumerate(("A", "B", "C"))])
INGRESOS_GASTOS = pd.DataFrame([{"Periodo": p, "Grupo": g, "Valor": float(100 * m)}
                                for m, p in enumerate(MESES, 1) for g in ("INGRESOS", "GASTOS")])

CASOS = {
    "barras": lambda: graficas.barras(FILAS),
    "barras con clic": lambda: graficas.barras(FILAS, clave="x"),
    "línea": lambda: graficas.linea(PUNTOS),
    "dona con clic": lambda: graficas.dona(FILAS, clave="d"),
    "barras por periodo": lambda: graficas.barras_por_periodo(POR_PERIODO, MESES, clave="b"),
    "líneas por periodo": lambda: graficas.lineas_por_periodo(POR_PERIODO, MESES),
    "ingresos y gastos": lambda: graficas.ingresos_y_gastos(INGRESOS_GASTOS, MESES),
    "valor y lo invertido": lambda: graficas.valor_y_lo_invertido([(f, v, v - 500) for f, v in PUNTOS]),
    "valor por serie": lambda: graficas.valor_por_serie({"A": PUNTOS, "B": [(f, v * 2) for f, v in PUNTOS]}),
    "ganancias": lambda: graficas.ganancias([(p, Decimal(10 * m - 30)) for m, p in enumerate(MESES, 1)]),
}
CON_CLIC = {"barras con clic", "dona con clic", "barras por periodo"}


@pytest.fixture
def dibujadas(monkeypatch):
    lista = []
    monkeypatch.setattr(graficas.st, "altair_chart", lambda grafica, **opciones: lista.append(grafica))
    return lista


@pytest.mark.parametrize("nombre", list(CASOS))
def test_cada_grafica_cumple_el_esquema_de_vega_lite(dibujadas, nombre):
    CASOS[nombre]()
    (grafica,) = dibujadas
    type(grafica).to_dict(grafica, validate=True)               # revisada, aunque al usar TALLY no se revise
    spec = vega_charts._convert_altair_to_vega_lite_spec(grafica)   # como la convierte Streamlit
    assert spec["datasets"] and "locale" in spec["config"]
    nombres = [p["name"] for p in spec.get("params", [])]
    assert (graficas.SELECCION in nombres) == (nombre in CON_CLIC)


def test_sin_revisar_da_lo_mismo_que_revisando(dibujadas):
    graficas.barras(FILAS, clave="x")
    (grafica,) = dibujadas
    assert grafica.to_dict() == type(grafica).to_dict(grafica, validate=True)


@pytest.mark.parametrize("vacia", [
    lambda: graficas.barras([]), lambda: graficas.linea(PUNTOS[:1]), lambda: graficas.dona([]),
    lambda: graficas.barras_por_periodo(POR_PERIODO.iloc[0:0], MESES),
    lambda: graficas.lineas_por_periodo(POR_PERIODO.iloc[0:0], MESES), lambda: graficas.ganancias([]),
    lambda: graficas.valor_y_lo_invertido([]), lambda: graficas.valor_por_serie({}),
])
def test_sin_datos_no_dibuja_nada(dibujadas, vacia):
    vacia()
    assert dibujadas == []
