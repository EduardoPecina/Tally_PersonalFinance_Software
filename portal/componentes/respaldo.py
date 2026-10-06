"""Descargar un respaldo y restaurar uno (los usan Respaldos, Configuración y la bienvenida)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from motor import respaldos
from motor.errores import ErrorTally
from portal.componentes.sesion import avisar, sesion

TIPOS = ["zip", "db"]


def boton_descargar(clave: str, *, principal: bool = True) -> None:
    """Un clic: crea el respaldo (también queda una copia en la carpeta Respaldos) y lo descarga."""
    actual = sesion()
    nombre = f"TALLY_respaldo_{actual.libro.ahora():%Y-%m-%d_%H%M%S}.zip"
    st.download_button(
        "Descargar respaldo", lambda: respaldos.crear(actual, prefijo="descargado").read_bytes(), file_name=nombre,
        mime="application/zip", type="primary" if principal else "secondary", icon=":material/download:",
        on_click="ignore", key=f"{clave}_descargar",
        help="Un archivo .zip con TODO: cuentas, movimientos, categorías, configuración y bitácora. Guárdalo en "
             "una memoria USB o donde quieras; con él recuperas todo en cualquier PC.",
    )


def subido(archivo) -> Path:
    """Guarda en TEMP el archivo que subió el usuario (Streamlit lo tiene en memoria)."""
    sufijo = Path(archivo.name).suffix.lower() or ".zip"
    ruta = Path(tempfile.gettempdir()) / f"tally_subido_{archivo.file_id}{sufijo}"
    ruta.write_bytes(archivo.getvalue())
    return ruta


def revisar_y_restaurar(ruta: Path, clave: str, *, pedir_confirmacion: bool = True, nombre: str | None = None) -> None:
    """Muestra qué trae el respaldo y lo restaura con un botón. Antes se respalda lo actual."""
    try:
        info = respaldos.inspeccionar(ruta)
    except ErrorTally as error:
        st.error(str(error))
        return
    with st.container(border=True):
        origen = f"TALLY {info.version_app}" if info.version_app != "(archivo de datos)" else "un archivo de datos"
        st.markdown(f"**{nombre or Path(info.ruta).name}**  \nCreado el {info.creado_en.replace('T', ' a las ')} con {origen}")
        columnas = st.columns(3)
        columnas[0].metric("Perfil", info.perfil or "—")
        columnas[1].metric("Cuentas", info.cuentas)
        columnas[2].metric("Movimientos", info.movimientos)
        if info.primera_fecha:
            st.caption(f"Movimientos del {info.primera_fecha} al {info.ultima_fecha}.")
    confirmado = True
    if pedir_confirmacion:
        confirmado = st.checkbox("Entiendo que mis datos actuales se reemplazarán por los de este respaldo",
                                 key=f"{clave}_confirmar")
    if st.button("Restaurar este respaldo", type="primary", disabled=not confirmado, key=f"{clave}_restaurar"):
        try:
            resultado = respaldos.restaurar(sesion(), ruta)
        except (ErrorTally, OSError) as error:
            st.error(f"No se restauró nada: {error}")
            return
        avisar(f"Respaldo restaurado. Lo que había antes quedó en {resultado.respaldo_de_seguridad.name}")
        st.rerun()
