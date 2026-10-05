"""Portal de TALLY. Se inicia con ``portal/iniciar.py`` (o ``streamlit run portal/app.py``)."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import streamlit as st  # noqa: E402

from motor import perfil  # noqa: E402
from motor.config import VERSION  # noqa: E402
from motor.errores import ErrorDatos  # noqa: E402
from portal import navegacion  # noqa: E402
from portal.apagado import cerrar_portal, vigilar_inactividad  # noqa: E402
from portal.componentes.cierre import pagina_cerrado  # noqa: E402
from portal.componentes.sesion import mostrar_avisos, sesion  # noqa: E402
from portal.limpieza import limpiar_copias  # noqa: E402
from portal.paginas import recuperacion  # noqa: E402

RECURSOS = RAIZ / "portal" / "recursos"
LOGO, MARCA = RECURSOS / "logo.png", RECURSOS / "marca.png"


@st.cache_resource(show_spinner=False)
def _vigilante() -> bool:
    """Una sola vez por servidor: se apaga solo si nadie lo usa (portal/apagado.py) y borra las copias que haya
    dejado una actualización (portal/limpieza.py)."""
    vigilar_inactividad()
    limpiar_copias()
    return True


def _barra_lateral() -> None:
    with st.sidebar:
        nombre = sesion().libro.perfil.nombre
        st.caption(f"Sesión de **{nombre}** · TALLY {VERSION}  \nTus datos se quedan en esta PC.")
        if st.button("Cerrar TALLY", icon=":material/power_settings_new:", width="stretch",
                     help="Cierra TALLY por completo. Todo queda guardado. Para volver a abrirlo: acceso "
                          "directo TALLY de tu Escritorio."):
            st.html(pagina_cerrado(), unsafe_allow_javascript=True)
            cerrar_portal()
            st.stop()


def main() -> None:
    st.set_page_config(page_title="TALLY", page_icon=str(MARCA) if MARCA.exists() else "💰", layout="wide")
    if LOGO.exists():
        st.logo(str(LOGO), size="large", icon_image=str(MARCA) if MARCA.exists() else None)
    _vigilante()
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
