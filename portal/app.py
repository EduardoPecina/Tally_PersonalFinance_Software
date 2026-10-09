"""Portal de TALLY. Se inicia con ``portal/iniciar.py`` (o ``streamlit run portal/app.py``)."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import streamlit as st  # noqa: E402

from motor import monedas, perfil, respaldos  # noqa: E402
from motor.config import LEMA, VERSION  # noqa: E402
from motor.errores import ErrorBloqueado, ErrorDatos, ErrorTally  # noqa: E402
from portal import accesos, navegacion  # noqa: E402
from portal.componentes import candado, formato, por_recuperar, tema  # noqa: E402
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


def _respaldo_del_dia(actual) -> None:
    """Una vez por sesión del navegador: el respaldo automático del día (Configuración → Respaldos)."""
    if st.session_state.get("_respaldo_del_dia"):
        return
    st.session_state["_respaldo_del_dia"] = True
    try:
        respaldos.respaldo_del_dia(actual)
    except Exception as error:  # noqa: BLE001 - un respaldo fallido nunca impide usar TALLY
        st.toast(f"No se pudo hacer el respaldo automático de hoy: {error}", icon="⚠️")


def _recordar_kit() -> None:
    """Cada 90 días, una vez por visita: «¿Todavía tienes tu Kit de emergencia?»."""
    config = candado.config()
    if config is None or st.session_state.get("_recordar_kit"):
        return
    st.session_state["_recordar_kit"] = True
    from datetime import date

    if config.recordatorio_kit(date.today()):
        st.toast("¿Todavía tienes tu Kit de emergencia? Compruébalo en Configuración → Seguridad.", icon="🔑")


def _barra_lateral() -> None:
    with st.sidebar:
        nombre = sesion().libro.perfil.nombre
        st.caption(f"Sesión de **{nombre}** · TALLY {VERSION}  \n*{LEMA}*")
        ultimo = sesion().almacen.ultimo_cambio()
        st.caption((":green[✓ Todo guardado] · último cambio " + formato.cuando(ultimo, sesion().libro.hoy()))
                   if ultimo else ":green[✓] Todo se guarda solo, al momento",
                   help="TALLY guarda cada cambio en tu computadora en cuanto lo haces: no hay que darle «Guardar» "
                        "a nada más. Si se va la luz o cierras la ventana, no se pierde nada. Además hace un "
                        "respaldo automático cada día.")
        if candado.config() is not None and st.button(
                "Bloquear ahora", icon=":material/lock:", width="stretch", key="bloquear_ahora",
                help="Cierra tus datos: para volver a verlos hay que escribir tu contraseña."):
            candado.bloquear()
            st.rerun()
        if st.button("Cerrar TALLY", icon=":material/power_settings_new:", width="stretch",
                     help="Cierra TALLY por completo. Todo queda guardado. Para volver a abrirlo: acceso "
                          "directo TALLY de tu Escritorio."):
            st.html(pagina_cerrado(), unsafe_allow_javascript=True)
            cerrar_portal()
            st.stop()
        candado.vigilar()                                   # el bloqueo automático, aunque no toques nada


def _preferencias():
    """El perfil (tema e ícono), o None si aún no hay, los datos no abren o están con contraseña."""
    try:
        if not candado.abierto():
            return None
        return sesion().libro.perfil
    except ErrorTally:
        return None


def main() -> None:
    preferencias = _preferencias()
    icono = accesos.imagen_pestana(preferencias.icono if preferencias else "claro")
    st.set_page_config(page_title="TALLY", page_icon=str(icono) if icono.exists() else "💰", layout="wide")
    tema.aplicar(preferencias.tema if preferencias else "claro")
    monedas.usar(preferencias.moneda if preferencias else None)
    if LOGO.exists():
        st.logo(str(LOGO), size="large", icon_image=str(MARCA) if MARCA.exists() else None)
    _vigilante()
    try:
        abierto = candado.abierto()
    except ErrorDatos as error:
        recuperacion.mostrar(error)
        return
    if not abierto:                                         # con contraseña: primero hay que escribirla
        st.navigation([st.Page("vistas/acceso.py", title="Entrar", icon="🔒", url_path="acceso")],
                      position="hidden").run()
        return
    candado.tocar()
    try:
        actual = sesion()
    except ErrorBloqueado:
        candado.bloquear()
        st.rerun()
    except ErrorDatos as error:
        recuperacion.mostrar(error)
        return
    _recordar_kit()
    mostrar_avisos()

    if perfil.necesita_bienvenida(actual.libro):
        st.navigation([st.Page("vistas/bienvenida.py", title="Bienvenida", icon="👋", url_path="bienvenida")],
                      position="hidden").run()
        return

    _respaldo_del_dia(actual)
    pagina = st.navigation(navegacion.por_seccion(), expanded=True)   # todas las páginas a la vista
    if pagina.url_path != "cuentas":
        st.session_state.pop("cuenta_abierta", None)       # al volver a Cuentas se ve la lista
    if pagina.url_path not in ("", "inicio"):
        por_recuperar.cerrar()                              # la ventana de un cargo temporal no te sigue
    _barra_lateral()
    pagina.run()


main()
