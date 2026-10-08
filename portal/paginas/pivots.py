"""Tablas dinámicas (pivots): como las de Excel, pero ya armadas con tus movimientos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import analisis, reportes
from portal.componentes import exportar, filtros, formato
from portal.componentes.sesion import libro

GUARDADO = "_pivot"
RAPIDAS = {
    "Gasto por categoría y mes": dict(filas="rubro", columnas="mes", medida="gastos"),
    "Total por categoría": dict(filas="rubro", columnas="ninguna", medida="gastos"),
    "Subcategorías por mes": dict(filas="categoria", columnas="mes", medida="gastos"),
    "Por clasificación": dict(filas="grupo", columnas="mes", medida="gastos"),
    "Ingresos y gastos por mes": dict(filas="clase", columnas="mes", medida="todo"),
    "Gasto por cuenta": dict(filas="cuenta", columnas="mes", medida="gastos"),
}
SUMA_TOTAL = "Suma total"


def _config() -> dict:
    return st.session_state.setdefault(GUARDADO, dict(RAPIDAS["Gasto por categoría y mes"], periodo="todo",
                                                      cuentas=[], apartado=False))


def tabla(pivot: analisis.Pivot, titulo_filas: str) -> pd.DataFrame:
    """La tabla dinámica como DataFrame: una columna por periodo, la columna Total y la fila «Suma total»."""
    datos = {titulo_filas: pivot.filas + [SUMA_TOTAL]}
    for columna in pivot.columnas:
        valores = [pivot.valor(f, columna) for f in pivot.filas] + [pivot.total_columna.get(columna)]
        datos[columna] = [float(v) if v is not None else None for v in valores]
    if len(pivot.columnas) > 1 or pivot.columnas != [analisis.TOTAL]:
        datos[analisis.TOTAL] = [float(pivot.total_fila[f]) for f in pivot.filas] + [float(pivot.total)]
    return pd.DataFrame(datos)


def _formulario(config: dict) -> None:
    lib = libro()
    with st.form("pivot_formulario"):
        a, b, c = st.columns(3)
        filas = a.selectbox("Filas", list(analisis.FILAS), format_func=analisis.FILAS.get,
                            index=list(analisis.FILAS).index(config["filas"]))
        columnas = b.selectbox("Columnas", list(analisis.COLUMNAS), format_func=analisis.COLUMNAS.get,
                               index=list(analisis.COLUMNAS).index(config["columnas"]))
        medida = c.selectbox("Qué sumar", list(analisis.MEDIDAS), format_func=analisis.MEDIDAS.get,
                             index=list(analisis.MEDIDAS).index(config["medida"]))
        elegido = filtros.periodo_y_cuentas(lib, config, "pivot")
        apartado = st.checkbox("Agregar lo que apartaste a ahorro e inversión como una fila", value=config["apartado"],
                               help="Como la fila AHORRO de tu Excel. Va aparte: no es un gasto.")
        if st.form_submit_button("Generar pivot", type="primary", icon=":material/table_chart:"):
            config.update(filas=filas, columnas=columnas, medida=medida, apartado=apartado, **elegido)
            st.rerun()


def mostrar() -> None:
    st.title("Tablas dinámicas")
    st.caption("Elige qué ver en filas y columnas, qué sumar, de qué meses y de qué cuentas. Siempre con tus datos "
               "más recientes. Las transferencias y los pagos de tarjeta nunca cuentan como gasto.")
    config = _config()
    st.markdown("**Rápidas**")
    columnas = st.columns(3)
    for i, (nombre, opciones) in enumerate(RAPIDAS.items()):
        if columnas[i % 3].button(nombre, key=f"rapida_{i}", width="stretch"):
            config.update(opciones)
            st.rerun()
    with st.expander("Personalizar", expanded=False):
        _formulario(config)

    lib = libro()
    desde, hasta = filtros.fechas(lib, config)
    pivot = analisis.pivot(lib, filas=config["filas"], columnas=config["columnas"], medida=config["medida"],
                           desde=desde, hasta=hasta, cuentas=set(config["cuentas"]) or None,
                           incluir_apartado=config["apartado"])
    titulo = f"{analisis.MEDIDAS[config['medida']]} por {analisis.FILAS[config['filas']].lower()}"
    if config["columnas"] != "ninguna":
        titulo += f" y {analisis.COLUMNAS[config['columnas']].lower()}"
    st.subheader(titulo)
    st.caption(filtros.describir(lib, config))
    if pivot.vacia:
        st.info("No hay movimientos con estas opciones.")
        return
    datos = tabla(pivot, analisis.FILAS[config["filas"]])
    dinero = [c for c in datos.columns if c != analisis.FILAS[config["filas"]]]
    vista, columnas_vista = formato.tabla_en_pesos(datos, dinero, fijar=analisis.FILAS[config["filas"]])
    st.dataframe(formato.pintar(vista), hide_index=True, width="stretch", height=min(38 + 35 * len(datos), 640),
                 column_config=columnas_vista)

    elegidas = {lib.cuenta(c).nombre for c in config["cuentas"]}

    def _movimientos() -> pd.DataFrame:                  # solo al descargar (con años de datos tarda)
        return pd.DataFrame([
            {"Fecha": f["fecha"], "Cuenta": f["cuenta"], "Categoría": f["rubro"], "Subcategoría": f["categoria"],
             "Clasificación": f["grupo"], "Tipo": f["clase"], "Monto": float(f["monto"]),
             "Descripción": f["descripcion"]}
            for f in reportes.hechos(lib, desde, hasta) if not elegidas or f["cuenta"] in elegidas
        ])
    izquierda, derecha = st.columns(2)
    izquierda.download_button(
        "Exportar a Excel", lambda: exportar.excel({"Pivot": datos, "Movimientos": _movimientos()}), on_click="ignore",
        file_name=f"TALLY_pivot_{lib.hoy():%Y-%m-%d}.xlsx", icon=":material/table_view:", width="stretch",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Dos hojas: la tabla dinámica y los movimientos que la forman (para que armes tus propios pivots).")
    derecha.download_button("Exportar a CSV", lambda: exportar.csv(datos), file_name=f"TALLY_pivot_{lib.hoy():%Y-%m-%d}.csv",
                            mime="text/csv", on_click="ignore", icon=":material/download:", width="stretch")
