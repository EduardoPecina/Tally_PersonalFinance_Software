"""Cuando el archivo de datos no se puede abrir: restaurar un respaldo o empezar de cero.

En ningún caso se borra el archivo dañado: se aparta con otro nombre.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from motor import respaldos, rutas
from motor.errores import ErrorTally
from motor.sesion import Sesion
from portal.componentes.sesion import avisar, olvidar_sesion, ruta_datos, sesion


def mostrar(error: Exception) -> None:
    st.title("No se pudieron abrir tus datos")
    st.error(str(error))
    st.markdown(
        "Tus datos **no se han borrado**. Puedes restaurar un respaldo o empezar de cero; en ambos casos el "
        f"archivo actual se conserva aparte en **{rutas.carpeta_datos()}** con la palabra «danado» en el nombre."
    )

    st.subheader("Restaurar un respaldo")
    carpeta = rutas.carpeta_respaldos()
    disponibles = sorted(carpeta.glob("TALLY_*.zip"), reverse=True) if carpeta.exists() else []
    ruta: Path | None = None
    if disponibles:
        ruta = st.selectbox("Respaldo", disponibles, format_func=lambda p: p.name, index=0)
    subido = st.file_uploader("…o sube un archivo de respaldo (.zip)", type=["zip"])
    if subido is not None:
        ruta = Path(tempfile.gettempdir()) / f"tally_subido_{subido.file_id}.zip"
        ruta.write_bytes(subido.getvalue())
    secreto = None
    if ruta is not None:
        from portal.componentes import respaldo

        secreto = respaldo.pedir_contrasena_de(ruta, "recuperacion")
        if secreto is False:
            ruta = None
    if ruta is not None:
        try:
            info = respaldos.inspeccionar(ruta, secreto=secreto or None)
            st.caption(f"{ruta.name}: {info.cuentas} cuenta(s), {info.movimientos} movimiento(s), "
                       f"creado el {info.creado_en.replace('T', ' ')}.")
        except ErrorTally as error_respaldo:
            st.error(str(error_respaldo))
            ruta = None
    if st.button("Restaurar este respaldo", type="primary", disabled=ruta is None):
        Sesion.apartar_archivo_danado(ruta_datos())
        olvidar_sesion()
        try:
            resultado = respaldos.restaurar(sesion(), ruta, secreto=secreto or None)
        except (ErrorTally, OSError) as error_restaurar:
            st.error(f"No se pudo restaurar: {error_restaurar}")
            return
        from portal.componentes import respaldo

        respaldo.despues_de_restaurar(resultado)
        avisar("Respaldo restaurado")
        st.rerun()

    st.subheader("Empezar de cero")
    confirmar = st.checkbox("Entiendo que empezaré con TALLY vacío (el archivo actual se conserva aparte)")
    if st.button("Empezar de cero", disabled=not confirmar):
        Sesion.apartar_archivo_danado(ruta_datos())
        olvidar_sesion()
        st.rerun()
