"""Gráficas a tu gusto: eliges el tipo, qué agrupar y qué sumar, y das clic en «Visualizar gráfica»."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

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


# Al desglosar un grupo, en qué se parte: una categoría en sus subcategorías, una cuenta en categorías…
SUBDIVISION = {"rubro": ("categoria", "Subcategoría"), "grupo": ("categoria", "Subcategoría"),
               "cuenta": ("rubro", "Categoría"), "categoria": ("cuenta", "Cuenta")}
DETALLE = "grafica_detalle"


def _desglose(config: dict, totales: dict, desde, hasta, cuentas, clic: str | None) -> None:
    """Todos los importes (también lo que la gráfica junta en OTROS) y el detalle de lo que el usuario elija, con
    un clic en la gráfica o en la lista."""
    lib = libro()
    totales = {k: v for k, v in totales.items() if v}
    if not totales:
        return
    agrupar, medida = config["agrupar"], config["medida"]
    nombre = AGRUPAR[agrupar]
    orden = sorted(totales, key=lambda k: (-totales[k], k))
    plegado = graficas.plegar(totales)
    en_otros = [k for k in orden if plegado[k] == graficas.OTROS]
    total = sum(totales.values())
    with st.expander(f"Todos los importes ({len(orden)})" + (f" · OTROS junta {len(en_otros)}" if en_otros else ""),
                     expanded=bool(en_otros)):
        st.dataframe(formato.pintar(pd.DataFrame({
            nombre: orden,
            "Importe": [formato.dinero(totales[k]) for k in orden],
            "% del total": [f"{totales[k] / total:.1%}" if total else "" for k in orden],
            "En la gráfica": ["dentro de OTROS" if k in en_otros else k for k in orden],
        })), hide_index=True, width="stretch", height=min(38 + 35 * len(orden), 420))

    opciones = ([graficas.OTROS] if en_otros else []) + orden
    if clic is not None and clic != st.session_state.get("_grafica_ultimo_clic"):
        st.session_state["_grafica_ultimo_clic"] = clic            # un clic nuevo en la gráfica manda
        if clic in opciones:
            st.session_state[DETALLE] = clic
    if st.session_state.get(DETALLE) not in opciones:
        st.session_state.pop(DETALLE, None)
    elegido = st.selectbox(
        "Ver el detalle de", opciones, index=None, key=DETALLE,
        placeholder="Da clic en la gráfica o elige aquí qué quieres desglosar",
        format_func=lambda n: f"OTROS ({len(en_otros)} juntas)" if n == graficas.OTROS else n)
    if elegido is None:
        st.caption("Tip: da clic en una rebanada o barra para ver de qué se compone.")
        return

    miembros = set(en_otros) if elegido == graficas.OTROS else {elegido}
    filas = analisis.detalle(lib, agrupar, miembros, medida=medida, desde=desde, hasta=hasta, cuentas=cuentas)
    subtotal = sum((f.monto for f in filas), Decimal(0))
    st.markdown(f"#### Detalle de {elegido}")
    st.caption(f"{formato.dinero_md(subtotal)} en {len(filas)} movimiento(s) · {filtros.describir(lib, config)}")
    campo, titulo = (agrupar, nombre) if elegido == graficas.OTROS else SUBDIVISION[agrupar]
    partes: dict[str, Decimal] = defaultdict(Decimal)
    for f in filas:
        partes[getattr(f, campo) or "—"] += f.monto
    nombres = sorted(partes, key=lambda k: (-partes[k], k))
    izquierda, derecha = st.columns([2, 3])
    with izquierda:
        st.markdown(f"**Por {titulo.lower()}**")
        st.dataframe(formato.pintar(pd.DataFrame({
            titulo: nombres,
            "Importe": [formato.dinero(partes[k]) for k in nombres],
            "%": [f"{partes[k] / subtotal:.0%}" if subtotal else "" for k in nombres],
        })), hide_index=True, width="stretch")
    with derecha:
        st.markdown("**Movimientos**")
        st.dataframe(formato.pintar(pd.DataFrame({
            "Fecha": [formato.fecha(f.fecha) for f in filas],
            "Descripción": [f.descripcion for f in filas],
            "Subcategoría": [f"{f.rubro} › {f.categoria}" for f in filas],
            "Cuenta": [f.cuenta for f in filas],
            "Importe": [formato.dinero(f.monto) for f in filas],
        })), hide_index=True, width="stretch", height=min(38 + 35 * len(filas), 420))


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
            clic = graficas.dona(filas, SUMAR[medida], AGRUPAR[config["agrupar"]], clave="grafica_clic")
        else:
            clic = graficas.barras([(n, v) for n, v in filas if v > 0], SUMAR[medida], AGRUPAR[config["agrupar"]],
                                   clave="grafica_clic")
        _desglose(config, pivot.total_fila, desde, hasta, cuentas, clic)
    elif tipo in ("apiladas", "lineas"):
        pivot = analisis.pivot(lib, filas=config["agrupar"], columnas="mes", medida=medida, desde=desde,
                               hasta=hasta, cuentas=cuentas)
        if tipo == "apiladas":
            clic = graficas.barras_por_periodo(_largo(pivot), pivot.columnas, SUMAR[medida],
                                               AGRUPAR[config["agrupar"]], clave="grafica_clic")
        else:
            clic = None
            graficas.lineas_por_periodo(_largo(pivot), pivot.columnas, SUMAR[medida], AGRUPAR[config["agrupar"]])
        _desglose(config, pivot.total_fila, desde, hasta, cuentas, clic)
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
