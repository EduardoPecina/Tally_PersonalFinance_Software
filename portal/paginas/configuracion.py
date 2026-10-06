"""⚙️ Configuración: tu nombre, respaldos, cómo se ve el Resumen y datos de esta instalación."""

from __future__ import annotations

import os
import sys

import streamlit as st

from motor import perfil, reportes, rutas
from motor.config import LEMA, VERSION
from motor.perfil import MAXIMO_RESPALDOS
from portal import accesos
from portal.componentes import respaldo
from portal.componentes.sesion import avisar, ejecutar, libro, sesion
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


def _apariencia() -> None:
    actual = libro().perfil
    st.subheader("Tema")
    st.caption("El tema oscuro descansa la vista de noche o si te cansa el blanco (como Dark Reader).")
    temas = list(perfil.TEMAS)
    elegido = st.radio("Tema", temas, format_func=perfil.TEMAS.get, index=temas.index(actual.tema), horizontal=True,
                       key="configuracion_tema", label_visibility="collapsed")
    if elegido != actual.tema and ejecutar(lambda lib: perfil.ajustar(lib, tema=elegido), exito="Tema cambiado"):
        st.rerun()

    st.subheader("Ícono de TALLY")
    st.caption("El color del ícono del acceso directo del Escritorio y de la pestaña del navegador.")
    columnas = st.columns(len(perfil.ICONOS))
    for columna, (variante, nombre) in zip(columnas, perfil.ICONOS.items()):
        with columna, st.container(border=True):
            st.image(str(accesos.imagen_pestana(variante)), width=56)
            en_uso = variante == actual.icono
            if st.button("En uso ✓" if en_uso else f"Usar {nombre.lower()}", disabled=en_uso,
                         key=f"configuracion_icono_{variante}", width="stretch"):
                if ejecutar(lambda lib: perfil.ajustar(lib, icono=variante)):
                    cambiados, mensaje = accesos.cambiar_icono(variante)
                    avisar(mensaje, "✅" if cambiados else "ℹ️")
                    st.rerun()


def _resumen() -> None:
    actual = libro().perfil
    st.subheader("Resumen")
    with st.form("configuracion_resumen", border=False):
        periodos = list(reportes.PERIODOS)
        periodo = st.selectbox("Periodo que se muestra al abrir", periodos, format_func=reportes.PERIODOS.get,
                               index=periodos.index(actual.periodo_inicial) if actual.periodo_inicial in periodos else 0)
        dias = st.number_input("Avisarme de un cargo temporal sin devolver después de (días)", min_value=1,
                               max_value=perfil.MAXIMO_DIAS_PARA_RECLAMAR, value=actual.dias_para_reclamar, step=1,
                               help="Cargos temporales: lo que te cobran para verificar tu tarjeta y te devuelven "
                                    "después. Pasado este plazo, el Resumen te avisa para que lo reclames.")
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: perfil.ajustar(lib, periodo_inicial=periodo, dias_para_reclamar=int(dias)),
                        exito="Preferencia guardada"):
                st.session_state.pop("_mem_inicio", None)          # el Resumen toma el nuevo periodo
                st.session_state.pop("_w_inicio_periodo", None)
                st.rerun()


def _acerca() -> None:
    lib = libro()
    ruta = sesion().almacen.ruta
    st.subheader("Esta instalación")
    tamano = ruta.stat().st_size / 1024 if ruta.exists() else 0
    st.markdown(
        f"- **TALLY {VERSION}** · *{LEMA}* · software libre (licencia MIT).\n"
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
    tu, apariencia, respaldos, resumen, acerca = st.tabs(
        ["Tu perfil", "Apariencia", "Respaldos", "Resumen", "Acerca de TALLY"])
    with tu:
        _perfil()
    with apariencia:
        _apariencia()
    with respaldos:
        _respaldos()
    with resumen:
        _resumen()
    with acerca:
        _acerca()
