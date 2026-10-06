"""⚙️ Configuración: tu nombre, respaldos, cómo se ve el Resumen y datos de esta instalación."""

from __future__ import annotations

import os
import sys

import streamlit as st

from motor import perfil, reportes, rutas
from motor.config import VERSION
from motor.perfil import MAXIMO_RESPALDOS
from portal.componentes import respaldo
from portal.componentes.sesion import ejecutar, libro, sesion
from portal.navegacion import enlace


def _perfil() -> None:
    actual = libro().perfil
    st.subheader("Tu nombre")
    st.caption("Así te saluda TALLY. Puede ser tu nombre o un apodo.")
    with st.form("configuracion_perfil", border=False):
        nombre = st.text_input("Nombre", value=actual.nombre, max_chars=60)
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: perfil.ajustar(lib, nombre=nombre), exito=f"¡Listo, {nombre.strip()}!"):
                st.rerun()


def _respaldos() -> None:
    actual = libro().perfil
    st.subheader("Respaldo para llevar")
    st.caption("Tu información completa en un archivo .zip. Si cambias de PC o empiezas de cero, súbelo en la "
               "bienvenida («Ya usaba TALLY») o en Respaldos → Restaurar.")
    respaldo.boton_descargar("configuracion")

    st.subheader("Respaldo automático")
    with st.form("configuracion_respaldos", border=False):
        diario = st.toggle("Hacer un respaldo automático al abrir TALLY (uno por día)", value=actual.respaldo_diario)
        conservar = st.number_input("Cuántos respaldos automáticos conservar", min_value=1, max_value=MAXIMO_RESPALDOS,
                                    value=actual.respaldos_a_conservar, step=1,
                                    help="Los más viejos se borran solos. Los que descargas o creas tú no se tocan.")
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: perfil.ajustar(lib, respaldo_diario=diario, respaldos_a_conservar=int(conservar)),
                        exito="Respaldo automático actualizado"):
                st.rerun()
    st.caption(f"Se guardan en **{rutas.carpeta_respaldos()}** (solo en esta PC).")
    enlace("respaldos", "Restaurar un respaldo o empezar de cero", "💾")


def _resumen() -> None:
    actual = libro().perfil
    st.subheader("Resumen")
    with st.form("configuracion_resumen", border=False):
        periodos = list(reportes.PERIODOS)
        periodo = st.selectbox("Periodo que se muestra al abrir", periodos, format_func=reportes.PERIODOS.get,
                               index=periodos.index(actual.periodo_inicial) if actual.periodo_inicial in periodos else 0)
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: perfil.ajustar(lib, periodo_inicial=periodo), exito="Preferencia guardada"):
                st.session_state.pop("_mem_inicio", None)          # el Resumen toma el nuevo periodo
                st.session_state.pop("_w_inicio_periodo", None)
                st.rerun()


def _acerca() -> None:
    lib = libro()
    ruta = sesion().almacen.ruta
    st.subheader("Esta instalación")
    tamano = ruta.stat().st_size / 1024 if ruta.exists() else 0
    st.markdown(
        f"- **TALLY {VERSION}**, software libre (licencia MIT).\n"
        f"- Tus datos: `{ruta}` ({tamano:,.0f} KB) · {len(lib.cuentas())} cuenta(s), "
        f"{len(lib.operaciones())} movimiento(s).\n"
        f"- Usuario desde el {lib.perfil.creado_en:%d/%m/%Y}.\n"
        "- Nada sale de esta PC: sin nube, sin bancos conectados, sin telemetría."
    )
    if sys.platform == "win32" and st.button("Abrir la carpeta de mis datos", icon=":material/folder_open:"):
        os.startfile(rutas.carpeta_usuario())  # noqa: S606 - abre el Explorador en la carpeta local del usuario
    enlace("cargar", "Cargar datos desde Excel", "📥")
    enlace("categorias", "Categorías y subcategorías", "🏷️")


def mostrar() -> None:
    st.title("Configuración")
    tu, respaldos, resumen, acerca = st.tabs(["Tu perfil", "Respaldos", "Resumen", "Acerca de TALLY"])
    with tu:
        _perfil()
    with respaldos:
        _respaldos()
    with resumen:
        _resumen()
    with acerca:
        _acerca()
