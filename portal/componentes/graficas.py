"""Gráficas sencillas (Altair). Una serie por gráfica, un solo tono, con tooltip."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from portal.componentes.formato import dinero

COLOR = "#2E7D5B"  # el color principal del portal (.streamlit/config.toml)
TEXTO_SECUNDARIO = "#52514e"


def barras(filas: list[tuple[str, Decimal]], titulo_valor: str = "Importe", titulo_nombre: str = "Categoría") -> None:
    """Barras horizontales de magnitud, de mayor a menor (p. ej. gasto por categoría)."""
    if not filas:
        st.caption("Sin datos en este periodo.")
        return
    datos = pd.DataFrame(
        {"Nombre": [n for n, _ in filas], "Valor": [float(v) for _, v in filas],
         "Texto": [dinero(v) for _, v in filas]}
    )
    base = alt.Chart(datos).encode(
        y=alt.Y("Nombre:N", sort=None, title=None, axis=alt.Axis(labelLimit=220, labelColor=TEXTO_SECUNDARIO)),
        x=alt.X("Valor:Q", title=None, axis=alt.Axis(format="$,.0f", grid=True, gridOpacity=0.4,
                                                    labelColor=TEXTO_SECUNDARIO)),
        tooltip=[alt.Tooltip("Nombre:N", title=titulo_nombre), alt.Tooltip("Texto:N", title=titulo_valor)],
    )
    grafica = base.mark_bar(color=COLOR, cornerRadiusEnd=4, height={"band": 0.7}) + base.mark_text(
        align="left", dx=4, color=TEXTO_SECUNDARIO, fontSize=11
    ).encode(text="Texto:N")
    st.altair_chart(grafica.properties(height=max(120, 28 * len(filas))), width="stretch")


def linea(puntos: list[tuple[date, Decimal]], titulo_valor: str = "Patrimonio") -> None:
    """Una línea en el tiempo (p. ej. evolución del patrimonio), con tooltip por punto."""
    if len(puntos) < 2:
        st.caption("Aún no hay suficiente historia para la gráfica.")
        return
    datos = pd.DataFrame(
        {"Fecha": [pd.Timestamp(f) for f, _ in puntos], "Valor": [float(v) for _, v in puntos],
         "Texto": [dinero(v) for _, v in puntos]}
    )
    base = alt.Chart(datos).encode(
        x=alt.X("Fecha:T", title=None, axis=alt.Axis(format="%d %b", labelColor=TEXTO_SECUNDARIO, grid=False)),
        y=alt.Y("Valor:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(format="$,.0f", labelColor=TEXTO_SECUNDARIO, gridOpacity=0.4)),
    )
    cercano = alt.selection_point(nearest=True, on="pointerover", fields=["Fecha"], empty=False)
    trazo = base.mark_line(color=COLOR, strokeWidth=2)
    puntos_ocultos = base.mark_point(color=COLOR, size=60, filled=True).encode(
        opacity=alt.condition(cercano, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Fecha:T", title="Fecha", format="%d/%m/%Y"),
                 alt.Tooltip("Texto:N", title=titulo_valor)],
    ).add_params(cercano)
    st.altair_chart((trazo + puntos_ocultos).properties(height=260), width="stretch")
