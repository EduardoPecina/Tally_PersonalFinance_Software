"""La pantalla para entrar cuando tus datos tienen contraseña (y para recuperarla con el Kit de emergencia)."""

from __future__ import annotations

import streamlit as st

from motor import seguridad
from motor.errores import ErrorContrasena, ErrorTally
from motor.sesion import Sesion
from portal.componentes import candado
from portal.componentes.sesion import avisar, ruta_datos


def mostrar() -> None:
    config = candado.config()
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title("🔒 Tus datos están protegidos")
        st.caption("Escribe tu contraseña de TALLY para entrar.")
        espera = candado.intentos().espera()
        with st.form("acceso", clear_on_submit=True):
            contrasena = st.text_input("Contraseña", type="password", key="acceso_contrasena",
                                       placeholder="Tu contraseña de TALLY")
            entrar = st.form_submit_button("Entrar", type="primary", icon=":material/lock_open:", width="stretch")
        if entrar:
            _entrar(contrasena)
        elif espera:
            _pedir_espera(espera)
        if config is not None and config.pista:
            with st.expander("Ver mi pista"):
                st.markdown(f"💡 {config.pista}")

        st.divider()
        with st.expander("😕 ¿Olvidaste tu contraseña? Usa tu Kit de emergencia"):
            _olvide(config)
        with st.expander("¿Perdiste también tu Kit de emergencia?"):
            _sin_kit()


def _pedir_espera(segundos: int) -> None:
    cuanto = "1 segundo" if segundos == 1 else f"{segundos} segundos"
    st.warning(f"Por seguridad, espera **{cuanto}** antes de volver a intentar.", icon="⏳")


def _entrar(contrasena: str) -> None:
    intentos = candado.intentos()
    espera = intentos.espera()
    if espera:
        _pedir_espera(espera)
        return
    if not contrasena:
        st.error("Escribe tu contraseña.")
        return
    try:
        llave = seguridad.entrar(ruta_datos(), contrasena)
    except ErrorContrasena as error:
        intentos.fallo()
        st.error(f"{error}", icon="🔑")
        if intentos.fallidos >= 3:
            st.caption(f"Llevas {intentos.fallidos} intentos. Si no la recuerdas, abre «¿Olvidaste tu contraseña?» "
                       "aquí abajo: con tu Kit de emergencia entras y pones una nueva, sin perder nada.")
        return
    except ErrorTally as error:
        st.error(str(error))
        return
    candado.entrar(llave)
    st.rerun()


def _olvide(config) -> None:
    final = f" (su llave termina en **…{config.kit_final}**)" if config else ""
    st.markdown(
        "No pasa nada: **no se pierde nada**. Busca tu **Kit de emergencia** — el archivo o la hoja que guardaste "
        f"cuando pusiste la contraseña{final}. Escribe su llave aquí y elige una contraseña nueva.")
    st.caption("Puede estar en tus Descargas («Kit de emergencia TALLY»), en tu correo, en una foto en tu celular o "
               "impreso con tus papeles importantes.")
    with st.form("olvide", clear_on_submit=False):
        kit = st.text_input("Llave de tu Kit de emergencia", placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX",
                            help="Como sea: con o sin guiones, en mayúsculas o minúsculas.")
        nueva = st.text_input("Contraseña nueva", type="password")
        otra_vez = st.text_input("Escríbela otra vez", type="password")
        if st.form_submit_button("Poner mi contraseña nueva y entrar", type="primary"):
            try:
                llave = seguridad.recuperar(ruta_datos(), kit, nueva, otra_vez)
            except ErrorTally as error:
                st.error(str(error))
                return
            candado.refrescar()
            candado.entrar(llave)
            avisar("¡Listo! Ya tienes contraseña nueva. Tu Kit de emergencia sigue siendo el mismo: no lo tires.", "🔑")
            st.rerun()


def _sin_kit() -> None:
    st.markdown(
        "Sin tu contraseña **y** sin tu Kit, **nadie puede abrir estos datos**: ni TALLY, ni un técnico. Así "
        "funciona el cifrado: si existiera otra forma de entrar, también la podría usar un ladrón.\n\n"
        "Antes de rendirte:\n"
        "1. Busca en tu correo «Kit de emergencia TALLY» y en tu carpeta de **Descargas**.\n"
        "2. Revisa las fotos y notas de tu celular.\n"
        "3. Prueba tus contraseñas de siempre (la pista te puede ayudar).\n\n"
        "Si aun así no aparece, puedes **empezar de nuevo** y, si tienes una copia **sin contraseña** (la que "
        "TALLY te ofreció guardar en una USB), restaurarla. Tus datos cifrados **no se borran**: se guardan aparte "
        "con otro nombre, por si algún día encuentras tu contraseña o tu Kit.")
    escrito = st.text_input("Para confirmar, escribe EMPEZAR", key="acceso_empezar")
    if st.button("Guardar mis datos cifrados aparte y empezar de nuevo", disabled=escrito.strip().upper() != "EMPEZAR"):
        Sesion.apartar_archivo_danado(ruta_datos())
        candado.refrescar()
        candado.bloquear()
        st.rerun()
