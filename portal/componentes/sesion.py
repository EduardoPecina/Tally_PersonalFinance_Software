"""Conexión del portal con el motor.

Una sola ``Sesion`` del motor para todo el portal (todas las pestañas). Cada
cambio se hace con :func:`aplicar`, que guarda al momento y muestra los
errores del motor como mensajes amables.
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import streamlit as st

from motor import cierre, rutas
from motor.errores import ErrorDatos, ErrorTally
from motor.libro import Libro
from motor.sesion import Sesion

T = TypeVar("T")


_PRECARGADAS: dict[str, Sesion] = {}         # abiertas antes de la primera vista (portal/servidor.py)


@st.cache_resource(show_spinner=False)
def _abrir(ruta: str) -> Sesion:
    from portal.componentes import candado              # la llave, si tus datos tienen contraseña

    precargada = _PRECARGADAS.pop(ruta, None)
    if precargada is not None and candado.llave() is None and _al_dia(precargada):
        return precargada
    return Sesion.abrir(ruta, llave=candado.llave())


def precargar() -> None:
    """Abre tus datos antes de la primera vista, mientras tu navegador abre (portal/servidor.py). Solo si ya existen
    y no tienen contraseña (con contraseña hay que esperar a que la escribas)."""
    from motor import seguridad

    ruta = ruta_datos()
    if Path(ruta).exists() and seguridad.config(ruta) is None:
        _PRECARGADAS[ruta] = Sesion.abrir(ruta)


def _al_dia(precargada: Sesion) -> bool:
    """Que nadie haya cambiado el archivo desde que se precargó."""
    try:
        return precargada.almacen.revision == precargada.almacen.revision_en_disco()
    except ErrorTally:
        return False


def ruta_datos() -> str:
    return str(rutas.archivo_datos())


def sesion() -> Sesion:
    """La sesión abierta. Lanza ``ErrorDatos`` si el archivo no se puede abrir."""
    return _abrir(ruta_datos())


def olvidar_sesion() -> None:
    """Cierra la sesión en memoria (p. ej. tras apartar un archivo dañado, o al bloquear TALLY), con lo calculado."""
    _abrir.clear()
    with _CANDADO_CALCULOS:
        _CALCULOS.clear()


def llave_actual() -> bytes | None:
    """La llave con la que está abierta la sesión (si ya se abrió); no la abre."""
    try:
        return sesion().almacen.llave
    except ErrorTally:
        return None


def libro() -> Libro:
    return sesion().libro


MAXIMO_CALCULOS = 32          # por versión de tus datos (unos MB a lo más cada uno: el Historial completo ~3 MB)
# Lo calculado, junto a la sesión de la que salió: se comparte entre pestañas y se va con ella (al bloquear TALLY o
# recargar tus datos no queda nada en memoria).
_CALCULOS: weakref.WeakKeyDictionary[Sesion, tuple[tuple, dict]] = weakref.WeakKeyDictionary()
_CANDADO_CALCULOS = threading.Lock()


def calculado(funcion: Callable[..., T], *args, **kwargs) -> T:
    """``funcion(libro(), *args, **kwargs)``, recordado mientras tus datos no cambien (y el mismo día).

    Para lo que tarda y se vuelve a pedir en cada clic de la misma página (elegir un renglón, abrir una pestaña,
    volver a la página). Cualquier cambio a tus datos lo olvida todo. Lo que regresa no se debe modificar."""
    actual = sesion()
    lib = actual.libro
    version = (id(lib), actual.almacen.revision, lib.hoy())
    llave = (funcion.__module__, funcion.__qualname__, _congelar(args), _congelar(kwargs))
    with _CANDADO_CALCULOS:
        guardados = _CALCULOS.get(actual)
        if guardados is None or guardados[0] != version:
            guardados = _CALCULOS[actual] = (version, {})
        memoria = guardados[1]
        if llave in memoria:
            return memoria[llave]
    resultado = funcion(lib, *args, **kwargs)
    with _CANDADO_CALCULOS:
        if len(memoria) >= MAXIMO_CALCULOS:
            memoria.pop(next(iter(memoria)))                # el más viejo
        memoria[llave] = resultado
    return resultado


def _congelar(valor):
    """Una versión que sirve de llave: las listas, conjuntos y diccionarios (p. ej. los filtros) no la sirven."""
    if isinstance(valor, dict):
        return tuple(sorted((k, _congelar(v)) for k, v in valor.items()))
    if isinstance(valor, (list, tuple)):
        return tuple(_congelar(v) for v in valor)
    if isinstance(valor, (set, frozenset)):
        return frozenset(_congelar(v) for v in valor)
    return valor


def _intentar(accion: Callable[[Libro], T], exito: str | None) -> tuple[bool, T | None]:
    tocados: list[str] = []
    try:
        with sesion().cambio() as lib:
            antes = cierre.huella(lib) if lib.cierres() else None
            resultado = accion(lib)
            if antes is not None:
                tocados = cierre.meses_tocados(lib, antes)
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
    for mes in tocados:
        anio, numero = (int(x) for x in mes.split("-"))
        avisar(f"Eso cambió {_mes(anio, numero)}, que ya cerraste: en su cierre aparece como cambio posterior.", "🔒")
    return True, resultado


def _mes(anio: int, numero: int) -> str:
    from portal.componentes import formato

    return f"{formato.MESES[numero - 1]} de {anio}"


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
