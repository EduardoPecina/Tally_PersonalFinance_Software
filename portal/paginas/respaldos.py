"""Respaldar, restaurar y consultar la bitácora de cambios."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from motor import auditoria, respaldos, rutas
from motor.errores import ErrorTally
from portal.componentes.sesion import avisar, sesion


def _crear() -> None:
    st.subheader("Crear respaldo")
    st.caption(
        f"Se guarda en la carpeta **{rutas.carpeta_respaldos()}** y además puedes descargarlo para guardarlo "
        "donde quieras (una memoria USB, tu nube…). Con él recuperas todo tu historial en cualquier PC."
    )
    if st.button("Crear respaldo ahora", type="primary"):
        try:
            st.session_state["_ultimo_respaldo"] = str(respaldos.crear(sesion()))
            avisar("Respaldo creado")
        except (ErrorTally, OSError) as error:
            st.error(f"No se pudo crear el respaldo: {error}")
    ultimo = st.session_state.get("_ultimo_respaldo")
    if ultimo and Path(ultimo).exists():
        st.success(f"Respaldo creado: {Path(ultimo).name}")
        st.download_button("Descargar este respaldo", Path(ultimo).read_bytes(), file_name=Path(ultimo).name,
                           mime="application/zip", on_click="ignore")


def _disponibles() -> list[Path]:
    carpeta = rutas.carpeta_respaldos()
    return sorted(carpeta.glob("TALLY_*.zip"), reverse=True) if carpeta.exists() else []


def _restaurar() -> None:
    st.subheader("Restaurar un respaldo")
    st.caption("Reemplaza **todos** tus datos actuales por los del respaldo. Antes de hacerlo, TALLY guarda "
               "automáticamente un respaldo de lo que tienes ahora, así que nada se pierde.")
    origen = st.radio("¿De dónde?", ["De la carpeta Respaldos", "Subir un archivo"], horizontal=True)
    ruta: Path | None = None
    if origen == "De la carpeta Respaldos":
        disponibles = _disponibles()
        if not disponibles:
            st.info("Aún no hay respaldos en la carpeta.")
            return
        ruta = st.selectbox("Respaldo", disponibles, format_func=lambda p: p.name, index=None,
                            placeholder="Elige un respaldo")
    else:
        subido = st.file_uploader("Archivo de respaldo (.zip)", type=["zip"])
        if subido is not None:
            temporal = Path(tempfile.gettempdir()) / f"tally_subido_{subido.file_id}.zip"
            temporal.write_bytes(subido.getvalue())
            ruta = temporal
    if ruta is None:
        return

    try:
        info = respaldos.inspeccionar(ruta)
    except ErrorTally as error:
        st.error(str(error))
        return
    with st.container(border=True):
        st.markdown(f"**{ruta.name}**  \nCreado el {info.creado_en.replace('T', ' a las ')} con TALLY {info.version_app}")
        columnas = st.columns(3)
        columnas[0].metric("Perfil", info.perfil or "—")
        columnas[1].metric("Cuentas", info.cuentas)
        columnas[2].metric("Movimientos", info.movimientos)
        if info.primera_fecha:
            st.caption(f"Movimientos del {info.primera_fecha} al {info.ultima_fecha}.")
    confirmar = st.checkbox("Entiendo que mis datos actuales se reemplazarán por los de este respaldo")
    if st.button("Restaurar este respaldo", type="primary", disabled=not confirmar):
        try:
            resultado = respaldos.restaurar(sesion(), ruta)
        except (ErrorTally, OSError) as error:
            st.error(f"No se restauró nada: {error}")
            return
        avisar(f"Respaldo restaurado. Lo anterior quedó en {resultado.respaldo_de_seguridad.name}")
        st.rerun()


def _bitacora() -> None:
    st.subheader("Bitácora de cambios")
    st.caption("Qué cambió y cuándo. Se guarda solo en esta PC.")
    registros = sesion().almacen.bitacora(limite=200)
    if not registros:
        st.info("Aún no hay cambios registrados.")
        return
    st.dataframe(
        pd.DataFrame({
            "Fecha y hora": [r.fecha_hora.replace("T", " ") for r in registros],
            "Cambio": [auditoria.resumen(r) for r in registros],
        }),
        hide_index=True, width="stretch", height=400,
    )


def mostrar() -> None:
    st.title("Respaldos y bitácora")
    crear, restaurar, bitacora = st.tabs(["Crear respaldo", "Restaurar", "Bitácora"])
    with crear:
        _crear()
    with restaurar:
        _restaurar()
    with bitacora:
        _bitacora()
