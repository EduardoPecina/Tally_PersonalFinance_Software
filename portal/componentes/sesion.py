"""Conexión del portal con el motor.

Una sola ``Sesion`` del motor para todo el portal (todas las pestañas). Cada
cambio se hace con :func:`aplicar`, que guarda al momento y muestra los
errores del motor como mensajes amables.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import streamlit as st

from motor import rutas
from motor.errores import ErrorDatos, ErrorTally
from motor.libro import Libro
from motor.sesion import Sesion

T = TypeVar("T")


@st.cache_resource(show_spinner=False)
def _abrir(ruta: str) -> Sesion:
    return Sesion.abrir(ruta)


def ruta_datos() -> str:
    return str(rutas.archivo_datos())


def sesion() -> Sesion:
    """La sesión abierta. Lanza ``ErrorDatos`` si el archivo no se puede abrir."""
    return _abrir(ruta_datos())


def olvidar_sesion() -> None:
    """Cierra la sesión en memoria (p. ej. tras apartar un archivo dañado)."""
    _abrir.clear()


def libro() -> Libro:
    return sesion().libro


def _intentar(accion: Callable[[Libro], T], exito: str | None) -> tuple[bool, T | None]:
    try:
        with sesion().cambio() as lib:
            resultado = accion(lib)
    except ErrorDatos as error:
        try:
            sesion().recargar()
            st.error(f"{error} Ya se recargaron los datos más recientes: revisa y vuelve a intentarlo.")
        except ErrorDatos:
            st.error(str(error))
        return False, None
    except ErrorTally as error:
        st.error(str(error))
        return False, None
    if exito:
        avisar(exito)
    return True, resultado


def ejecutar(accion: Callable[[Libro], object], exito: str | None = None) -> bool:
    """Ejecuta un cambio del motor y lo guarda. Si falla, muestra el motivo, no cambia nada y devuelve False."""
    return _intentar(accion, exito)[0]


def aplicar(accion: Callable[[Libro], T], exito: str | None = None) -> T | None:
    """Como :func:`ejecutar`, pero devuelve lo que regresó el motor (``None`` si falló)."""
    return _intentar(accion, exito)[1]


def avisar(mensaje: str, icono: str = "✅") -> None:
    """Aviso breve que se muestra en la siguiente ejecución (sobrevive a ``st.rerun``)."""
    st.session_state.setdefault("_avisos", []).append((mensaje, icono))


def mostrar_avisos() -> None:
    for mensaje, icono in st.session_state.pop("_avisos", []):
        st.toast(mensaje, icon=icono)
