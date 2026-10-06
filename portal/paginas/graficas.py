"""Gráficas a tu gusto: eliges el tipo, qué agrupar y qué sumar, y das clic en «Visualizar gráfica»."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from motor import analisis, reportes
from portal.componentes import filtros, formato, graficas
from portal.componentes.sesion import libro

GUARDADO = "_grafica"
TIPOS = {
    "dona": "Dona: ¿qué parte se lleva cada uno?",
    "barras": "Barras: de mayor a menor",
    "apiladas": "Barras por mes: cuánto y en qué",
    "lineas": "Líneas: tendencia mes a mes",
    "ingresos_gastos": "Ingresos vs. gastos por mes",
    "patrimonio": "Evolución de mi patrimonio",
}
CON_GRUPOS = ("dona", "barras", "apiladas", "lineas")
AGRUPAR = {k: v for k, v in analisis.FILAS.items() if k != "clase"}
SUMAR = {"gastos": "Gastos", "ingresos": "Ingresos"}


def _config() -> dict:
    return st.session_state.setdefault(GUARDADO, {"tipo": "dona", "agrupar": "rubro", "medida": "gastos",
                                                  "periodo": "todo", "cuentas": []})


def _formulario(config: dict) -> None:
    lib = libro()
    with st.form("grafica_formulario"):
        a, b, c = st.columns(3)
        tipo = a.selectbox("Tipo de gráfica", list(TIPOS), format_func=TIPOS.get, index=list(TIPOS).index(config["tipo"]))
        agrupar = b.selectbox("Agrupar por", list(AGRUPAR), format_func=AGRUPAR.get,
                              index=list(AGRUPAR).index(config["agrupar"]),
                              help="Para dona, barras y por mes. Los más grandes se muestran; el resto, en OTROS.")
        medida = c.selectbox("Qué sumar", list(SUMAR), format_func=SUMAR.get, index=list(SUMAR).index(config["medida"]))
        elegido = filtros.periodo_y_cuentas(lib, config, "grafica")
        if st.form_submit_button("Visualizar gráfica", type="primary", icon=":material/insert_chart:"):
            config.update(tipo=tipo, agrupar=agrupar, medida=medida, **elegido)
            st.rerun()


def _largo(pivot: analisis.Pivot) -> pd.DataFrame:
    grupos = graficas.plegar(pivot.total_fila)
    filas = [{"Periodo": c, "Grupo": grupos[f], "Valor": float(v)}
             for (f, c), v in pivot.valores.items()]
    datos = pd.DataFrame(filas, columns=["Periodo", "Grupo", "Valor"])
    return datos.groupby(["Periodo", "Grupo"], as_index=False)["Valor"].sum() if not datos.empty else datos


def mostrar() -> None:
    st.title("Gráficas")
    st.caption("Elige el tipo de gráfica y qué quieres ver; se arma con tus datos más recientes. Pasa el cursor "
               "sobre la gráfica para ver los importes, y con el menú «⋯» la guardas como imagen.")
    config = _config()
    _formulario(config)

    lib = libro()
    desde, hasta = filtros.fechas(lib, config)
    cuentas = set(config["cuentas"]) or None
    tipo, medida = config["tipo"], config["medida"]
    titulo = TIPOS[tipo].split(":")[0]
    if tipo in CON_GRUPOS:
        titulo = f"{SUMAR[medida]} por {AGRUPAR[config['agrupar']].lower()}"
    st.subheader(titulo)
    st.caption(filtros.describir(lib, config))

    if tipo in ("dona", "barras"):
        pivot = analisis.pivot(lib, filas=config["agrupar"], columnas="ninguna", medida=medida, desde=desde,
                               hasta=hasta, cuentas=cuentas)
        filas = [(f, pivot.total_fila[f]) for f in pivot.filas]
        if tipo == "dona":
            graficas.dona(filas, SUMAR[medida], AGRUPAR[config["agrupar"]])
        else:
            graficas.barras([(n, v) for n, v in filas if v > 0], SUMAR[medida], AGRUPAR[config["agrupar"]])
    elif tipo in ("apiladas", "lineas"):
        pivot = analisis.pivot(lib, filas=config["agrupar"], columnas="mes", medida=medida, desde=desde,
                               hasta=hasta, cuentas=cuentas)
        dibujar = graficas.barras_por_periodo if tipo == "apiladas" else graficas.lineas_por_periodo
        dibujar(_largo(pivot), pivot.columnas, SUMAR[medida], AGRUPAR[config["agrupar"]])
    elif tipo == "ingresos_gastos":
        pivot = analisis.pivot(lib, filas="clase", columnas="mes", medida="todo", desde=desde, hasta=hasta,
                               cuentas=cuentas)
        datos = pd.DataFrame([{"Periodo": c, "Grupo": f, "Valor": float(v)} for (f, c), v in pivot.valores.items()],
                             columns=["Periodo", "Grupo", "Valor"])
        graficas.ingresos_y_gastos(datos, pivot.columnas)
        if not pivot.vacia:
            ingresos, gastos = pivot.total_fila.get("INGRESOS", 0), pivot.total_fila.get("GASTOS", 0)
            st.caption(f"En el periodo: ingresos {formato.dinero_md(ingresos)} · gastos {formato.dinero_md(gastos)} · "
                       f"te quedaron {formato.dinero_md(ingresos - gastos)}.")
    else:
        primera = analisis.meses_con_datos(lib)
        inicio = desde or (primera[0] if primera else lib.hoy() - timedelta(days=90))
        fin = min(hasta or lib.hoy(), lib.hoy())
        graficas.linea([(p.fecha, p.patrimonio_neto) for p in reportes.evolucion(lib, inicio, fin)])
        if cuentas:
            st.caption("El patrimonio siempre incluye todas tus cuentas.")
