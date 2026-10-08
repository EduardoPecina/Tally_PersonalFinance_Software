"""Respaldar, restaurar y consultar la bitácora de cambios."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from motor import auditoria, comprobantes, respaldos, rutas
from motor.errores import ErrorTally
from portal.componentes import respaldo
from portal.componentes.sesion import avisar, sesion


def _crear() -> None:
    st.subheader("Descargar respaldo")
    st.caption("Un clic y te llevas **todo** en un archivo .zip, a tu carpeta de Descargas. Guárdalo en una "
               "memoria USB o donde quieras: si cambias de PC, "
               "formateas o empiezas de cero, con él recuperas todo, aquí en **Restaurar** o en la bienvenida "
               "(«Ya usaba TALLY»).")
    adjuntos = comprobantes.resumen(sesion().libro)
    if adjuntos.cuantos:
        st.caption(f"📎 Incluye tus {adjuntos.cuantos} comprobante(s) ({comprobantes.tamano(adjuntos.bytes)}).")
    respaldo.boton_descargar("respaldos")
    st.caption(f"¿Solo quieres guardar una copia en la carpeta **{rutas.carpeta_respaldos()}**, sin descargarla? "
               "Ahí también están los automáticos: uno por día (los últimos que elijas en Configuración) y los "
               "de seguridad, antes de actualizar, cargar datos o restaurar (los últimos 5 de cada tipo).")
    if st.button("Guardar respaldo en la carpeta"):
        try:
            avisar(f"Respaldo guardado: {respaldos.crear(sesion()).name}")
            st.rerun()
        except (ErrorTally, OSError) as error:
            st.error(f"No se pudo crear el respaldo: {error}")


def _disponibles() -> list[Path]:
    carpeta = rutas.carpeta_respaldos()
    return sorted(carpeta.glob("TALLY_*.zip"), reverse=True) if carpeta.exists() else []


def _restaurar() -> None:
    st.subheader("Restaurar un respaldo")
    st.caption("Reemplaza **todos** tus datos actuales por los del respaldo. Antes de hacerlo, TALLY guarda "
               "automáticamente un respaldo de lo que tienes ahora, así que nada se pierde. Sirve un respaldo "
               "(.zip) o el archivo de datos de TALLY (tally.db) de otra PC.")
    origen = st.radio("¿De dónde?", ["De la carpeta Respaldos", "Subir un archivo"], horizontal=True)
    ruta: Path | None = None
    nombre = None
    if origen == "De la carpeta Respaldos":
        disponibles = _disponibles()
        if not disponibles:
            st.info("Aún no hay respaldos en la carpeta.")
            return
        ruta = st.selectbox("Respaldo", disponibles, format_func=lambda p: p.name, index=None,
                            placeholder="Elige un respaldo")
    else:
        archivo = st.file_uploader("Respaldo (.zip) o archivo de datos (.db)", type=respaldo.TIPOS)
        if archivo is not None:
            ruta, nombre = respaldo.subido(archivo), archivo.name
    if ruta is not None:
        respaldo.revisar_y_restaurar(ruta, "respaldos", nombre=nombre)


CONFIRMAR = "BORRAR"


def _empezar_de_cero() -> None:
    st.subheader("Empezar de cero")
    st.markdown("Borra **todo**: tu nombre, tus cuentas, tus movimientos, las categorías que creaste y la bitácora. "
                "TALLY queda como recién instalado y te vuelve a saludar.")
    st.info("Antes de borrar, TALLY guarda un respaldo completo en la carpeta Respaldos "
            "(«TALLY_antes_de_empezar_de_cero_…»). Si te arrepientes, restáuralo en la pestaña **Restaurar** y "
            "recuperas todo.", icon="🛟")
    confirmacion = st.text_input(f"Para confirmar, escribe {CONFIRMAR}", key="confirmar_empezar_de_cero",
                                 max_chars=20)
    if st.button("Borrar todo y empezar de cero", type="primary",
                 disabled=confirmacion.strip().upper() != CONFIRMAR):
        try:
            seguridad = respaldos.empezar_de_cero(sesion())
        except (ErrorTally, OSError) as error:
            st.error(f"No se borró nada: {error}")
            return
        for clave in [k for k in st.session_state if not k.startswith("_avisos")]:
            del st.session_state[clave]
        avisar(f"Empezaste de cero. Lo anterior quedó respaldado en {seguridad.name}")
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
    if rutas.datos_sin_mover():
        st.warning(f"Tus datos siguen en **{rutas.carpeta_usuario()}**, porque al actualizar Windows no dejó "
                   "moverlos. Para pasarlos a tu carpeta de usuario (fuera de OneDrive), cierra TALLY y vuelve a "
                   "correr INSTALAR.bat.")
    else:
        st.caption(f"Tus datos viven solo en esta PC, en **{rutas.carpeta_usuario()}** (fuera de OneDrive y de "
                   "cualquier nube).")
    crear, restaurar, bitacora, cero = st.tabs(["Descargar respaldo", "Restaurar", "Bitácora", "Empezar de cero"])
    with crear:
        _crear()
    with restaurar:
        _restaurar()
    with bitacora:
        _bitacora()
    with cero:
        _empezar_de_cero()
