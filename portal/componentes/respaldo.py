"""Descargar un respaldo y restaurar uno (los usan Respaldos, Configuración y la bienvenida)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from motor import cifrado, respaldos
from motor.errores import ErrorTally
from portal.componentes.sesion import avisar, llave_actual, sesion

TIPOS = ["zip", "db"]


def boton_descargar(clave: str, *, principal: bool = True) -> None:
    """Un clic: crea el respaldo y lo descarga. No deja copia en la carpeta Respaldos: el archivo va a donde el
    navegador guarda las descargas."""
    actual = sesion()
    nombre = f"TALLY_respaldo_{actual.libro.ahora():%Y-%m-%d_%H%M%S}.zip"

    def contenido() -> bytes:
        with tempfile.TemporaryDirectory() as temporal:
            return respaldos.crear(actual, Path(temporal), prefijo="descargado").read_bytes()

    st.download_button(
        "Descargar respaldo", contenido, file_name=nombre,
        mime="application/zip", type="primary" if principal else "secondary", icon=":material/download:",
        on_click="ignore", key=f"{clave}_descargar",
        help="Un archivo .zip con TODO: cuentas, movimientos, categorías, configuración y bitácora. Guárdalo en "
             "una memoria USB o donde quieras; con él recuperas todo en cualquier PC. Si TALLY tiene contraseña, "
             "sale cifrado: se abre con tu contraseña o con tu Kit de emergencia.",
    )


def subido(archivo) -> Path:
    """Guarda en TEMP el archivo que subió el usuario (Streamlit lo tiene en memoria)."""
    sufijo = Path(archivo.name).suffix.lower() or ".zip"
    ruta = Path(tempfile.gettempdir()) / f"tally_subido_{archivo.file_id}{sufijo}"
    ruta.write_bytes(archivo.getvalue())
    return ruta


def revisar_y_restaurar(ruta: Path, clave: str, *, pedir_confirmacion: bool = True, nombre: str | None = None) -> None:
    """Muestra qué trae el respaldo y lo restaura con un botón. Antes se respalda lo actual.

    Si el respaldo tiene contraseña (y no es la de tus datos), la pide: la de ese día o la llave del Kit."""
    secreto = pedir_contrasena_de(ruta, clave)
    if secreto is False:
        return
    try:
        info = respaldos.inspeccionar(ruta, llave=llave_actual(), secreto=secreto or None)
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
            resultado = respaldos.restaurar(sesion(), ruta, secreto=secreto or None)
        except (ErrorTally, OSError) as error:
            st.error(f"No se restauró nada: {error}")
            return
        despues_de_restaurar(resultado)
        avisar(f"Respaldo restaurado. Lo que había antes quedó en {resultado.respaldo_de_seguridad.name}")
        st.rerun()


def pedir_contrasena_de(ruta: Path, clave: str) -> str | None | bool:
    """``None`` si no hace falta contraseña; el texto escrito; o ``False`` si falta escribirla."""
    try:
        config = respaldos.contrasena_de(ruta)
    except ErrorTally as error:
        st.error(str(error))
        return False
    llave = llave_actual()
    if config is None or (llave is not None and cifrado.huella(llave) == config.llave_id):
        return None
    st.info(f"🔒 Este respaldo tiene contraseña. Escribe la **contraseña que tenías ese día** o la **llave de tu Kit "
            f"de emergencia** del {cifrado._fecha(config.kit_creado)} (termina en …{config.kit_final}).")
    if config.pista:
        st.caption(f"Pista de ese día: {config.pista}")
    secreto = st.text_input("Contraseña o llave del Kit", type="password", key=f"{clave}_secreto_respaldo")
    return secreto if secreto else False


def despues_de_restaurar(resultado) -> None:
    """Si tus datos quedaron con la contraseña del respaldo, TALLY entra con ella de una vez."""
    from portal.componentes import candado

    if resultado.adopto_contrasena:
        llave = sesion().almacen.llave
        candado.refrescar()
        candado.entrar(llave)
        avisar("Tus datos quedaron con la contraseña de ese respaldo (y el mismo Kit de emergencia).", "🔒")
        if resultado.con_kit:
            avisar("Entraste con tu Kit: pon una contraseña nueva en Configuración → Seguridad → Cambiar "
                   "contraseña (como «actual» usa la llave de tu Kit).", "🔑")
    else:
        candado.refrescar()
