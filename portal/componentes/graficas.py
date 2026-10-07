"""Gráficas sencillas (Altair). Una serie por gráfica, un solo tono, con tooltip."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from motor import monedas
from portal.componentes.formato import dinero

COLOR = "#6B53F1"  # acento de la marca (.streamlit/config.toml)
TEXTO_SECUNDARIO = "#52514e"
SELECCION = "eleccion"


FECHAS = alt.TimeLocale(           # los ejes de fechas en español: «12 jul», no «12 Jul»
    dateTime="%A, %e de %B de %Y, %X", date="%d/%m/%Y", time="%H:%M:%S", periods=["a. m.", "p. m."],
    days=["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"],
    shortDays=["dom", "lun", "mar", "mié", "jue", "vie", "sáb"],
    months=["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
            "noviembre", "diciembre"],
    shortMonths=["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"])


def _altair(grafica, **opciones):
    """``st.altair_chart`` con los números de tu moneda: el eje ``$,.0f`` sale como $1,000, 1.000 €, S/ 1,000…"""
    m = monedas.activa()
    espacio = " " if m.espacio else ""
    moneda = ["", f"{espacio}{m.simbolo}"] if m.despues else [f"{m.simbolo}{espacio}", ""]
    local = alt.Locale(number=alt.NumberLocale(decimal=m.decimal, thousands=m.miles, grouping=[3], currency=moneda),
                       time=FECHAS)
    return st.altair_chart(grafica.configure(locale=local), **opciones)


def _clic(campo: str) -> alt.Parameter:
    """Selección por clic en una barra o rebanada (para el desglose); un clic en el vacío la quita."""
    return alt.selection_point(name=SELECCION, fields=[campo], on="click", clear="dblclick")


def _mostrar(grafica, clave: str | None, campo: str) -> str | None:
    """Dibuja la gráfica. Con ``clave``, se le puede dar clic y devuelve el nombre elegido (o ``None``)."""
    if clave is None:
        _altair(grafica, width="stretch")
        return None
    evento = _altair(grafica, width="stretch", key=clave, on_select="rerun", selection_mode=SELECCION)
    try:
        puntos = evento["selection"][SELECCION]
    except (KeyError, TypeError):
        return None
    return puntos[0].get(campo) if puntos else None


def barras(filas: list[tuple[str, Decimal]], titulo_valor: str = "Importe", titulo_nombre: str = "Categoría",
           clave: str | None = None) -> str | None:
    """Barras horizontales de magnitud, de mayor a menor (p. ej. gasto por categoría). Con ``clave`` se les puede
    dar clic: devuelve la barra elegida."""
    if not filas:
        st.caption("Sin datos en este periodo.")
        return None
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
    barra = base.mark_bar(color=COLOR, cornerRadiusEnd=4, height={"band": 0.7})
    if clave is not None:
        clic = _clic("Nombre")
        barra = barra.add_params(clic).encode(opacity=alt.condition(clic, alt.value(1.0), alt.value(0.45)))
    grafica = barra + base.mark_text(align="left", dx=4, color=TEXTO_SECUNDARIO, fontSize=11).encode(text="Texto:N")
    return _mostrar(grafica.properties(height=max(120, 28 * len(filas))), clave, "Nombre")


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
    _altair((trazo + puntos_ocultos).properties(height=260), width="stretch")


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


def dona(filas: list[tuple[str, Decimal]], titulo_valor: str = "Importe", titulo_nombre: str = "Grupo",
         clave: str | None = None) -> str | None:
    """¿Qué parte del total es cada grupo? Dona con leyenda y porcentaje en el tooltip. Con ``clave`` se le puede
    dar clic a una rebanada: devuelve el grupo elegido (puede ser OTROS)."""
    filas = [(n, v) for n, v in filas if v > 0]
    if not filas:
        st.caption("Sin datos en este periodo.")
        return None
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
    if clave is not None:
        clic = _clic("Nombre")
        grafica = grafica.add_params(clic).encode(opacity=alt.condition(clic, alt.value(1.0), alt.value(0.45)))
    return _mostrar(grafica.properties(height=360), clave, "Nombre")


def barras_por_periodo(datos: pd.DataFrame, orden: list[str], titulo_valor: str = "Importe",
                       titulo_grupo: str = "Grupo", clave: str | None = None) -> str | None:
    """Barras apiladas por periodo (``Periodo``, ``Grupo``, ``Valor``): cuánto y en qué, mes a mes. Con ``clave``
    se le puede dar clic a un pedazo: devuelve su grupo."""
    if datos.empty:
        st.caption("Sin datos en este periodo.")
        return None
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
    if clave is not None:
        clic = _clic("Grupo")
        grafica = grafica.add_params(clic).encode(opacity=alt.condition(clic, alt.value(1.0), alt.value(0.45)))
    return _mostrar(grafica.properties(height=380), clave, "Grupo")


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
    _altair((base.mark_line(strokeWidth=2) + puntos).properties(height=360), width="stretch")


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
    _altair(grafica.properties(height=360), width="stretch")


# ------------------------------------------------------------- inversiones
GANANCIA_COLOR, PERDIDA_COLOR = PALETA[0], PALETA[1]   # azul / naranja: se distinguen también con daltonismo
MAXIMO_PUNTOS = 400


def _reducir(filas: list, maximo: int = MAXIMO_PUNTOS) -> list:
    """Uno de cada tantos días para que la gráfica no pese; siempre conserva el primero y el último."""
    paso = -(-len(filas) // maximo)
    return [f for i, f in enumerate(filas) if i % paso == 0 or i == len(filas) - 1]


def _eje_fecha(dias: int) -> alt.Axis:
    return alt.Axis(format="%d/%m/%y" if dias <= 400 else "%m/%Y", labelColor=TEXTO_SECUNDARIO, grid=False,
                    labelAngle=0)


def valor_y_lo_invertido(puntos: list[tuple[date, Decimal, Decimal]]) -> None:
    """El valor (línea de color) y lo que metiste (gris punteada). La distancia entre ambas es la ganancia."""
    if len(puntos) < 2:
        st.caption("Aún no hay suficiente historia para la gráfica.")
        return
    puntos = _reducir(puntos)
    nombres = ["Valor", "Lo que metiste"]
    largo = pd.DataFrame(
        [{"Fecha": pd.Timestamp(f), "Serie": nombres[0], "Valor": float(v)} for f, v, _ in puntos]
        + [{"Fecha": pd.Timestamp(f), "Serie": nombres[1], "Valor": float(m)} for f, _, m in puntos])
    ancho = pd.DataFrame({"Fecha": [pd.Timestamp(f) for f, _, _ in puntos],
                          "Valor": [float(v) for _, v, _ in puntos],
                          "Texto": [dinero(v) for _, v, _ in puntos],
                          "Metiste": [dinero(m) for _, _, m in puntos],
                          "Ganancia": [dinero(v - m) for _, v, m in puntos]})
    x = alt.X("Fecha:T", title=None, axis=_eje_fecha((puntos[-1][0] - puntos[0][0]).days))
    y = alt.Y("Valor:Q", title=None, scale=alt.Scale(zero=False),
              axis=alt.Axis(format="$,.0f", labelColor=TEXTO_SECUNDARIO, gridOpacity=0.4))
    lineas = alt.Chart(largo).mark_line(strokeWidth=2).encode(
        x=x, y=y,
        color=alt.Color("Serie:N", scale=alt.Scale(domain=nombres, range=[COLOR, GRIS]), legend=_leyenda()),
        strokeDash=alt.StrokeDash("Serie:N", scale=alt.Scale(domain=nombres, range=[[1, 0], [5, 4]]), legend=None))
    cercano = alt.selection_point(nearest=True, on="pointerover", fields=["Fecha"], empty=False)
    regla = alt.Chart(ancho).mark_rule(color=GRIS).encode(x=x).transform_filter(cercano)
    marcas = alt.Chart(ancho).mark_point(color=COLOR, size=70, filled=True).encode(
        x=x, y=y, opacity=alt.condition(cercano, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Fecha:T", title="Fecha", format="%d/%m/%Y"), alt.Tooltip("Texto:N", title="Valor"),
                 alt.Tooltip("Metiste:N", title="Lo que metiste"), alt.Tooltip("Ganancia:N", title="Ganancia")],
    ).add_params(cercano)
    _altair((lineas + regla + marcas).properties(height=320), width="stretch")


def valor_por_serie(series: dict[str, list[tuple[date, Decimal]]]) -> None:
    """Una línea por título (o cuenta), con su valor en el tiempo; color fijo por nombre."""
    series = {n: _reducir(p) for n, p in series.items() if len(p) >= 2}
    if not series:
        st.caption("Aún no hay suficiente historia para la gráfica.")
        return
    totales = {n: abs(p[-1][1]) + abs(max((v for _, v in p), default=0)) for n, p in series.items()}
    grupo = plegar(totales)
    filas: dict[tuple, float] = defaultdict(float)
    for nombre, puntos in series.items():
        for fecha_, valor in puntos:
            filas[(pd.Timestamp(fecha_), grupo[nombre])] += float(valor)
    datos = pd.DataFrame([{"Fecha": f, "Grupo": g, "Valor": v} for (f, g), v in filas.items()])
    datos["Texto"] = [dinero(Decimal(str(round(v, 2)))) for v in datos["Valor"]]
    dias = (datos["Fecha"].max() - datos["Fecha"].min()).days
    base = alt.Chart(datos).encode(
        x=alt.X("Fecha:T", title=None, axis=_eje_fecha(dias)),
        y=alt.Y("Valor:Q", title=None, axis=alt.Axis(format="$,.0f", labelColor=TEXTO_SECUNDARIO, gridOpacity=0.4)),
        color=alt.Color("Grupo:N", scale=_escala(list(datos["Grupo"].unique())), legend=_leyenda()),
    )
    cercano = alt.selection_point(nearest=True, on="pointerover", fields=["Fecha", "Grupo"], empty=False)
    marcas = base.mark_point(size=70, filled=True).encode(
        opacity=alt.condition(cercano, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Fecha:T", title="Fecha", format="%d/%m/%Y"), alt.Tooltip("Grupo:N", title="Qué"),
                 alt.Tooltip("Texto:N", title="Valor")],
    ).add_params(cercano)
    _altair((base.mark_line(strokeWidth=2) + marcas).properties(height=320), width="stretch")


def ganancias(filas: list[tuple[str, Decimal]]) -> None:
    """Ganancia (azul) o pérdida (naranja) de cada mes o año, con su importe al pasar el cursor."""
    if not filas:
        st.caption("Sin datos en este periodo.")
        return
    nombres = ["Ganancia", "Pérdida"]
    datos = pd.DataFrame({"Periodo": [p for p, _ in filas], "Valor": [float(v) for _, v in filas],
                          "Texto": [("+" if v > 0 else "") + dinero(v) for _, v in filas],
                          "Signo": [nombres[0] if v >= 0 else nombres[1] for _, v in filas]})
    orden = [p for p, _ in filas]
    barras_ = alt.Chart(datos).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X("Periodo:N", sort=orden, title=None, axis=alt.Axis(labelAngle=0, labelColor=TEXTO_SECUNDARIO)),
        y=alt.Y("Valor:Q", title=None, axis=alt.Axis(format="$,.0f", labelColor=TEXTO_SECUNDARIO, gridOpacity=0.4)),
        color=alt.Color("Signo:N", scale=alt.Scale(domain=nombres, range=[GANANCIA_COLOR, PERDIDA_COLOR]),
                        legend=_leyenda()),
        tooltip=[alt.Tooltip("Periodo:N", title="Periodo"), alt.Tooltip("Texto:N", title="Ganancia")],
    )
    cero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=GRIS).encode(y="y:Q")
    _altair((barras_ + cero).properties(height=300), width="stretch")
