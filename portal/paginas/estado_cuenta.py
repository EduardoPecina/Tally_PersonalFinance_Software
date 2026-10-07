"""Estado de cuenta: los movimientos de UNA cuenta con su saldo después de cada uno (como el Excel)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from motor import consultas, cuentas, tarjetas
from motor.consultas import ETIQUETA_TIPO_CUENTA
from motor.modelo import TipoCuenta
from portal.componentes import exportar, formato, portafolio
from portal.componentes import tarjeta as estado_tarjeta
from portal.componentes.sesion import libro
from portal.paginas import historial, registrar

ABIERTA = "cuenta_abierta"
RANGOS = {"todo": "Todo", "mes": "Este mes", "3m": "Últimos 3 meses", "anio": "Este año"}
ORDENES = {"recientes": "Más recientes primero", "antiguos": "Más antiguos primero"}


def abrir(cuenta_id: str | None) -> None:
    st.session_state[ABIERTA] = cuenta_id


def abierta() -> str | None:
    cuenta_id = st.session_state.get(ABIERTA)
    try:
        return libro().cuenta(cuenta_id).id if cuenta_id else None
    except LookupError:
        return None


@st.dialog("Agregar movimiento", width="large")
def _agregar(cuenta_id: str) -> None:
    st.caption(f"En **{formato.md(libro().cuenta(cuenta_id).nombre)}**")
    if registrar.formulario(f"dialogo_{cuenta_id}", cuenta_fija=cuenta_id):
        st.rerun()


def _desde(clave: str, hoy: date) -> date | None:
    return {"mes": hoy.replace(day=1), "3m": hoy - timedelta(days=90), "anio": hoy.replace(month=1, day=1)}.get(clave)


def _msi(cuenta_id: str) -> None:
    compras = tarjetas.compras_a_msi(libro(), cuenta_id)
    if not compras:
        return
    st.markdown("**Compras a meses sin intereses**")
    st.dataframe(pd.DataFrame({
        "Compra": [formato.fecha(c.fecha) for c in compras],
        "Descripción": [c.descripcion for c in compras],
        "Total": [float(c.total) for c in compras],
        "Mensualidad": [float(c.mensualidad) for c in compras],
        "Pagadas": [f"{c.cobradas} de {c.meses}" for c in compras],
        "Falta": [float(c.restante) for c in compras],
        "Última mensualidad": [formato.fecha(c.ultima) for c in compras],
    }), hide_index=True, width="stretch", column_config={
        k: st.column_config.NumberColumn(format=formato.columna_dinero()) for k in ("Total", "Mensualidad", "Falta")})


def mostrar(cuenta_id: str) -> None:
    lib = libro()
    cuenta = lib.cuenta(cuenta_id)
    es_credito = cuenta.tipo is TipoCuenta.CREDITO
    if st.button("← Todas mis cuentas", key="cuenta_volver"):
        abrir(None)
        st.rerun()
    st.title(cuenta.nombre)
    st.caption(ETIQUETA_TIPO_CUENTA[cuenta.tipo] + (f" · {cuenta.institucion}" if cuenta.institucion else ""))
    if es_credito:
        with st.container(border=True):
            estado_tarjeta.mostrar(cuenta)
        _msi(cuenta.id)
    else:
        st.metric("Saldo", formato.dinero(cuentas.saldo(lib, cuenta.id)))
    if cuenta.tipo is TipoCuenta.INVERSION:
        with st.container(border=True):
            portafolio.mostrar(cuenta)

    izquierda, derecha, orden_col = st.columns([1, 2, 1.2], vertical_alignment="bottom")
    if not cuenta.activa:
        st.info("Esta cuenta está eliminada: aquí ves su historial guardado. Para volver a usarla, restáurala en "
                "Cuentas → «Mostrar eliminadas».", icon="🗄️")
    elif izquierda.button("Agregar movimiento", type="primary", icon=":material/add:", key="cuenta_agregar"):
        _agregar(cuenta.id)
    rango = derecha.segmented_control("Periodo", list(RANGOS), format_func=RANGOS.get, default="todo",
                                      required=True, key="cuenta_rango", label_visibility="collapsed")
    orden = orden_col.selectbox("Orden", list(ORDENES), format_func=ORDENES.get, key="cuenta_orden",
                                label_visibility="collapsed")
    filas = consultas.movimientos_de_cuenta(lib, cuenta.id, desde=_desde(rango, lib.hoy()))
    if orden == "antiguos":
        filas = filas[::-1]           # en el orden real: los del mismo día también quedan en su lugar
    if not filas:
        st.info("Sin movimientos en este periodo.")
        return

    columna_saldo = "Debes" if es_credito else "Saldo"
    tabla = pd.DataFrame({
        "Fecha": [f.fecha for f in filas],
        "Descripción": [f.descripcion + (f" ({f.msi} MSI)" if f.msi else "") for f in filas],
        "Subcategoría o cuenta": [f.detalle for f in filas],
        "Entrada": [float(f.abono) or None for f in filas],
        "Salida": [float(f.cargo) or None for f in filas],
        columna_saldo: [float(-f.saldo if es_credito else f.saldo) for f in filas],
    })
    entradas, salidas = sum(f.abono for f in filas), sum(f.cargo for f in filas)
    st.caption(f"{len(filas)} movimiento(s) · Entradas {formato.dinero_md(entradas)} · "
               f"Salidas {formato.dinero_md(salidas)}. El saldo es el que quedó después de cada movimiento; para "
               "verlo de arriba abajo usa «Orden» (al ordenar con clic en una columna, el saldo no se recalcula).")
    vista, config = formato.tabla_en_pesos(tabla, ("Entrada", "Salida", columna_saldo))
    evento = st.dataframe(
        vista, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="cuenta_tabla",
        height=min(38 + 35 * len(filas), 560),
        column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"), **config},
    )
    st.download_button(
        "Exportar a Excel", exportar.excel({cuenta.nombre: tabla}), icon=":material/table_view:",
        file_name=f"TALLY_{cuenta.nombre}_{lib.hoy():%Y-%m-%d}.xlsx", on_click="ignore", key="cuenta_excel",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    seleccion = evento.selection.rows if evento else []
    if seleccion:
        historial.detalle_movimiento(filas[seleccion[0]].id, tabla="cuenta_tabla")
    else:
        st.caption("Selecciona un movimiento (casilla a la izquierda) para editarlo, repetirlo o eliminarlo.")
