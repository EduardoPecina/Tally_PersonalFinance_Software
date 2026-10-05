"""Portal de TALLY. Se inicia con ``portal/iniciar.py`` (o ``streamlit run portal/app.py``)."""

from __future__ import annotations

import os
import signal
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import streamlit as st  # noqa: E402

from motor import perfil  # noqa: E402
from motor.config import VERSION  # noqa: E402
from motor.errores import ErrorDatos  # noqa: E402
from portal import navegacion  # noqa: E402
from portal.componentes.sesion import mostrar_avisos, sesion  # noqa: E402
from portal.paginas import recuperacion  # noqa: E402

LOGO = RAIZ / "portal" / "recursos" / "logo.png"


def _cerrar_tally() -> None:
    st.success("TALLY se cerró. Ya puedes cerrar esta pestaña del navegador.")
    st.caption("Para volver a abrirlo, usa el acceso directo «TALLY» de tu Escritorio.")
    # Se da un momento para que el mensaje llegue al navegador antes de apagar el servidor local.
    threading.Timer(1.5, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
    st.stop()


def _barra_lateral() -> None:
    with st.sidebar:
        if st.session_state.get("_cerrando"):
            _cerrar_tally()
        nombre = sesion().libro.perfil.nombre
        st.caption(f"Sesión de **{nombre}** · TALLY {VERSION}  \nTus datos se quedan en esta PC.")
        if st.button("Cerrar TALLY", icon=":material/power_settings_new:", width="stretch"):
            st.session_state["_cerrando"] = True
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="TALLY", page_icon=str(LOGO) if LOGO.exists() else "💰", layout="wide")
    if LOGO.exists():
        st.logo(str(LOGO), size="large")
    try:
        actual = sesion()
    except ErrorDatos as error:
        recuperacion.mostrar(error)
        return
    mostrar_avisos()

    if perfil.necesita_bienvenida(actual.libro):
        st.navigation([st.Page("vistas/bienvenida.py", title="Bienvenida", icon="👋", url_path="bienvenida")],
                      position="hidden").run()
        return

    pagina = st.navigation(list(navegacion.paginas().values()))
    _barra_lateral()
    pagina.run()


main()
