"""Gráficas sencillas (Altair). Una serie por gráfica, un solo tono, con tooltip."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from portal.componentes.formato import dinero

COLOR = "#6B53F1"  # acento de la marca (.streamlit/config.toml)
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


# ------------------------------------------------------------ varias series
# Paleta categórica validada (8 tonos en orden fijo, legibles con daltonismo en pares contiguos). Más de 7
# grupos se juntan en OTROS (gris): nunca se inventan colores.
PALETA = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
OTROS = "OTROS"
GRIS = "#9b9a95"
MAXIMO_GRUPOS = 7
INGRESOS_COLOR, GASTOS_COLOR = PALETA[2], PALETA[1]


def _escala(grupos: list[str]) -> alt.Scale:
    """Cada grupo con su color, decidido por su nombre (no por su lugar): filtrar no repinta los demás."""
    propios = sorted(g for g in grupos if g != OTROS)
    dominio = propios + ([OTROS] if OTROS in grupos else [])
    colores = [PALETA[i % len(PALETA)] for i in range(len(propios))] + ([GRIS] if OTROS in grupos else [])
    return alt.Scale(domain=dominio, range=colores)


def plegar(totales: dict[str, Decimal], maximo: int = MAXIMO_GRUPOS) -> dict[str, str]:
    """Nombre → grupo que se dibuja: los ``maximo`` más grandes por su nombre y el resto como OTROS."""
    grandes = sorted(totales, key=lambda k: -abs(totales[k]))[:maximo]
    return {k: (k if k in grandes else OTROS) for k in totales}


def _leyenda() -> alt.Legend:
    return alt.Legend(orient="bottom", title=None, labelLimit=260, columns=4, symbolType="circle")


def dona(filas: list[tuple[str, Decimal]], titulo_valor: str = "Importe", titulo_nombre: str = "Grupo") -> None:
    """¿Qué parte del total es cada grupo? Dona con leyenda y porcentaje en el tooltip."""
    filas = [(n, v) for n, v in filas if v > 0]
    if not filas:
        st.caption("Sin datos en este periodo.")
        return
    grupos = plegar(dict(filas))
    datos = pd.DataFrame({"Nombre": [grupos[n] for n, _ in filas], "Valor": [float(v) for _, v in filas]})
    datos = datos.groupby("Nombre", as_index=False)["Valor"].sum()
    total = datos["Valor"].sum()
    datos["Texto"] = [dinero(Decimal(str(round(v, 2)))) for v in datos["Valor"]]
    datos["Parte"] = datos["Valor"] / total
    grafica = alt.Chart(datos).mark_arc(innerRadius=70, stroke="white", strokeWidth=2).encode(
        theta=alt.Theta("Valor:Q", stack=True),
        color=alt.Color("Nombre:N", scale=_escala(list(datos["Nombre"])), legend=_leyenda()),
        order=alt.Order("Valor:Q", sort="descending"),
        tooltip=[alt.Tooltip("Nombre:N", title=titulo_nombre), alt.Tooltip("Texto:N", title=titulo_valor),
                 alt.Tooltip("Parte:Q", title="Del total", format=".1%")],
    )
    st.altair_chart(grafica.properties(height=360), width="stretch")


def barras_por_periodo(datos: pd.DataFrame, orden: list[str], titulo_valor: str = "Importe",
                       titulo_grupo: str = "Grupo") -> None:
    """Barras apiladas por periodo (``Periodo``, ``Grupo``, ``Valor``): cuánto y en qué, mes a mes."""
    if datos.empty:
        st.caption("Sin datos en este periodo.")
        return
    datos = datos.assign(Texto=[dinero(Decimal(str(round(v, 2)))) for v in datos["Valor"]])
    grafica = alt.Chart(datos).mark_bar(stroke="white", strokeWidth=1, cornerRadiusTopLeft=2,
                                        cornerRadiusTopRight=2).encode(
        x=alt.X("Periodo:N", sort=orden, title=None, axis=alt.Axis(labelAngle=0, labelColor=TEXTO_SECUNDARIO)),
        y=alt.Y("sum(Valor):Q", title=None, axis=alt.Axis(format="$,.0f", labelColor=TEXTO_SECUNDARIO,
                                                          gridOpacity=0.4)),
        color=alt.Color("Grupo:N", scale=_escala(list(datos["Grupo"].unique())), legend=_leyenda()),
        order=alt.Order("Valor:Q", sort="descending"),
        tooltip=[alt.Tooltip("Periodo:N", title="Periodo"), alt.Tooltip("Grupo:N", title=titulo_grupo),
                 alt.Tooltip("Texto:N", title=titulo_valor)],
    )
    st.altair_chart(grafica.properties(height=380), width="stretch")


def lineas_por_periodo(datos: pd.DataFrame, orden: list[str], titulo_valor: str = "Importe",
                       titulo_grupo: str = "Grupo") -> None:
    """Una línea por grupo a lo largo de los periodos, con tooltip al pasar el cursor."""
    if datos.empty or datos["Periodo"].nunique() < 2:
        st.caption("Hacen falta al menos dos periodos con datos para ver la tendencia.")
        return
    datos = datos.assign(Texto=[dinero(Decimal(str(round(v, 2)))) for v in datos["Valor"]])
    escala = _escala(list(datos["Grupo"].unique()))
    base = alt.Chart(datos).encode(
        x=alt.X("Periodo:N", sort=orden, title=None, axis=alt.Axis(labelAngle=0, labelColor=TEXTO_SECUNDARIO)),
        y=alt.Y("Valor:Q", title=None, axis=alt.Axis(format="$,.0f", labelColor=TEXTO_SECUNDARIO, gridOpacity=0.4)),
        color=alt.Color("Grupo:N", scale=escala, legend=_leyenda()),
    )
    puntos = base.mark_point(size=70, filled=True).encode(
        tooltip=[alt.Tooltip("Periodo:N", title="Periodo"), alt.Tooltip("Grupo:N", title=titulo_grupo),
                 alt.Tooltip("Texto:N", title=titulo_valor)])
    st.altair_chart((base.mark_line(strokeWidth=2) + puntos).properties(height=360), width="stretch")


def ingresos_y_gastos(datos: pd.DataFrame, orden: list[str]) -> None:
    """Barras lado a lado de ingresos y gastos por periodo (``Periodo``, ``Grupo`` = INGRESOS/GASTOS, ``Valor``)."""
    if datos.empty:
        st.caption("Sin datos en este periodo.")
        return
    datos = datos.assign(Texto=[dinero(Decimal(str(round(v, 2)))) for v in datos["Valor"]])
    escala = alt.Scale(domain=["INGRESOS", "GASTOS"], range=[INGRESOS_COLOR, GASTOS_COLOR])
    grafica = alt.Chart(datos).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("Periodo:N", sort=orden, title=None, axis=alt.Axis(labelAngle=0, labelColor=TEXTO_SECUNDARIO)),
        xOffset=alt.XOffset("Grupo:N", sort=["INGRESOS", "GASTOS"]),
        y=alt.Y("Valor:Q", title=None, axis=alt.Axis(format="$,.0f", labelColor=TEXTO_SECUNDARIO, gridOpacity=0.4)),
        color=alt.Color("Grupo:N", scale=escala, legend=_leyenda()),
        tooltip=[alt.Tooltip("Periodo:N", title="Periodo"), alt.Tooltip("Grupo:N", title="Qué"),
                 alt.Tooltip("Texto:N", title="Importe")],
    )
    st.altair_chart(grafica.properties(height=360), width="stretch")
