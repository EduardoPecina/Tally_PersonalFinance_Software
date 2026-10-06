"""Cargos temporales que aún no te devuelven (motor/temporales.py): lista, avisos y botones para cerrarlos."""

from __future__ import annotations

import streamlit as st

from motor import categorias, cuentas, temporales
from motor.modelo import TipoOperacion
from portal.componentes import formato
from portal.componentes.sesion import ejecutar, libro

ABIERTA = "_por_recuperar_ventana"
DEVOLVER, GASTO = "devolver", "gasto"


def avisos() -> None:
    """Los que ya pasaron del plazo para reclamar, hasta arriba del Resumen."""
    for cargo in temporales.vencidos(libro()):
        st.warning(f"**{formato.md(cargo.descripcion)}**: el cargo temporal de {formato.dinero_md(cargo.monto)} "
                   f"({formato.md(cargo.cuenta)}) lleva {cargo.dias} días sin devolverse. Conviene reclamarlo.",
                   icon="↩️")


def mostrar() -> None:
    pendientes = temporales.pendientes(libro())
    if not pendientes:
        cerrar()
        return
    total = sum(c.monto for c in pendientes)
    st.subheader("Por recuperar")
    st.caption(f"Cargos temporales que te van a devolver: {formato.dinero_md(total)}. No cuentan como gasto.")
    for cargo in pendientes:
        with st.container(border=True):
            texto, devolvieron, no = st.columns([3, 1.3, 1.3], vertical_alignment="center")
            plazo = " · :red[vencido, reclámalo]" if cargo.vencido else ""
            texto.markdown(f"**{formato.md(cargo.descripcion)}** · {formato.dinero_md(cargo.monto)}  \n"
                           f":gray[{formato.md(cargo.cuenta)} · {formato.fecha(cargo.fecha)} · "
                           f"hace {cargo.dias} día(s)]{plazo}")
            devolvieron.button("Ya me lo devolvieron", key=f"devuelto_{cargo.operacion_id}", width="stretch",
                               icon=":material/check:", on_click=_abrir, args=(DEVOLVER, cargo.operacion_id))
            no.button("No me lo devolvieron", key=f"no_devuelto_{cargo.operacion_id}", width="stretch",
                      on_click=_abrir, args=(GASTO, cargo.operacion_id))
    # La ventana sigue abierta mientras esté anotada (se cierra al guardar o con la X).
    abierta = st.session_state.get(ABIERTA)
    if abierta:
        (_dialogo_devolver if abierta[0] == DEVOLVER else _dialogo_gasto)(abierta[1])


def _abrir(accion: str, cargo_id: str) -> None:
    st.session_state[ABIERTA] = (accion, cargo_id)


def cerrar() -> None:
    st.session_state.pop(ABIERTA, None)


def _guardado() -> None:
    cerrar()
    st.rerun()


def _cargo(cargo_id: str) -> temporales.CargoTemporal | None:
    return next((c for c in temporales.pendientes(libro()) if c.operacion_id == cargo_id), None)


@st.dialog("Ya me lo devolvieron", on_dismiss=cerrar)
def _dialogo_devolver(cargo_id: str) -> None:
    lib, cargo = libro(), _cargo(cargo_id)
    if cargo is None:
        cerrar()
        st.info("Este cargo ya no está pendiente.")
        return
    st.markdown(f"**{formato.md(cargo.descripcion)}** · {formato.dinero_md(cargo.monto)}")
    activas = [c.id for c in cuentas.listar(lib) if c.id != temporales.cuenta(lib).id]
    destino = st.selectbox("¿A qué cuenta volvió?", activas, format_func=lambda i: lib.cuenta(i).nombre,
                           index=activas.index(cargo.cuenta_id) if cargo.cuenta_id in activas else 0)
    fecha = st.date_input("Fecha de la devolución", value=max(lib.hoy(), cargo.fecha), min_value=cargo.fecha,
                          format="DD/MM/YYYY")
    if st.button("Guardar", type="primary") and ejecutar(
            lambda lib: temporales.devolver(lib, cargo_id, fecha, cuenta_id=destino),
            exito=f"Devolución de {formato.dinero(cargo.monto)} guardada"):
        _guardado()


@st.dialog("No me lo devolvieron", on_dismiss=cerrar)
def _dialogo_gasto(cargo_id: str) -> None:
    lib, cargo = libro(), _cargo(cargo_id)
    if cargo is None:
        cerrar()
        st.info("Este cargo ya no está pendiente.")
        return
    st.markdown(f"**{formato.md(cargo.descripcion)}** · {formato.dinero_md(cargo.monto)}")
    st.caption("Se vuelve un gasto en la fecha que elijas. Antes, si puedes, reclámalo con el comercio o tu banco.")
    etiquetas = {c.id: categorias.etiqueta(lib, c.id) for c in categorias.para_tipo(lib, TipoOperacion.GASTO)}
    otros = categorias.buscar(lib, "OTROS GASTOS")
    ids = list(etiquetas)
    categoria = st.selectbox("Subcategoría", ids, format_func=etiquetas.get,
                             index=ids.index(otros.id) if otros and otros.id in ids else None,
                             placeholder="Escribe para buscar")
    fecha = st.date_input("Fecha del gasto", value=max(lib.hoy(), cargo.fecha), min_value=cargo.fecha,
                          format="DD/MM/YYYY")
    if st.button("Pasar a gasto", type="primary", disabled=categoria is None) and ejecutar(
            lambda lib: temporales.pasar_a_gasto(lib, cargo_id, fecha, categoria),
            exito=f"Gasto de {formato.dinero(cargo.monto)} guardado"):
        _guardado()
