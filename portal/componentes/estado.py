"""Valores de pantalla que deben sobrevivir al cambiar de página (p. ej. filtros, la pestaña abierta).

Streamlit borra el estado de un control cuando su página deja de mostrarse.
Aquí se guarda una copia aparte y se le devuelve al control al regresar.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st


def recordado(grupo: str, campo: str, inicial: Any) -> Any:
    """Último valor guardado de ``grupo.campo`` (o ``inicial``)."""
    return st.session_state.setdefault(f"_mem_{grupo}", {}).get(campo, inicial)


def recordar(grupo: str, campo: str, valor: Any) -> Any:
    st.session_state.setdefault(f"_mem_{grupo}", {})[campo] = valor
    return valor


def control(grupo: str, campo: str, inicial: Any, crear) -> Any:
    """Dibuja un control que conserva su valor entre páginas.

    ``crear(valor, clave)`` debe dibujar el control usando ``valor`` como valor
    inicial y ``clave`` como ``key``; su resultado se recuerda.
    """
    clave = f"_w_{grupo}_{campo}"
    valor = recordado(grupo, campo, inicial)
    if clave not in st.session_state:
        st.session_state[clave] = valor
    return recordar(grupo, campo, crear(clave))


def olvidar(grupo: str) -> None:
    """Quita todos los valores recordados del grupo y de sus controles."""
    st.session_state.pop(f"_mem_{grupo}", None)
    for clave in [c for c in st.session_state if str(c).startswith(f"_w_{grupo}_")]:
        del st.session_state[clave]


def pestanas(grupo: str, nombres: list[str]) -> tuple[int, Any]:
    """Como ``st.tabs``, pero solo se arma la pestaña que está a la vista: las demás no se calculan ni se dibujan
    hasta que las abres (con años de datos, armarlas todas hacía lentas las páginas). Recuerda en cuál estabas
    aunque cambies de página. Devuelve el número de la pestaña abierta y su contenedor.

    Se recuerda el número, no el nombre: así sirve aunque el nombre cambie (p. ej. «Sugerencias (2)»)."""
    clave = f"_w_{grupo}_pestana"
    numero = min(recordado(grupo, "pestana", 0), len(nombres) - 1)
    contenedores = st.tabs(nombres, key=clave, default=nombres[numero], on_change=_al_cambiar_de_pestana,
                           args=(grupo, clave, tuple(nombres)))
    for i, contenedor in enumerate(contenedores):
        if contenedor.open:
            return i, contenedor
    return numero, contenedores[numero]


def _al_cambiar_de_pestana(grupo: str, clave: str, nombres: tuple[str, ...]) -> None:
    elegida = st.session_state.get(clave)
    if elegida in nombres:
        recordar(grupo, "pestana", nombres.index(elegida))


DESPLEGABLES = "desplegables"


def desplegable(etiqueta: str, clave: str, contenido: Callable[[], None], *, abierto: bool = False) -> None:
    """Como ``st.expander``, pero lo de adentro (un formulario, una tabla, una gráfica) solo se arma y se manda al
    navegador cuando lo abres, y abrirlo o cerrarlo solo rehace este desplegable, no toda la página. Recuerda si lo
    dejaste abierto, aunque cambies de página. ``clave`` debe ser única; ``abierto``: si empieza abierto."""
    _desplegable(etiqueta, clave, contenido, abierto)


@st.fragment
def _desplegable(etiqueta: str, clave: str, contenido: Callable[[], None], abierto: bool) -> None:
    caja = st.expander(etiqueta, key=clave, expanded=recordado(DESPLEGABLES, clave, abierto),
                       on_change=_al_abrir_o_cerrar, args=(clave,))
    if caja.open:
        with caja:
            contenido()


def _al_abrir_o_cerrar(clave: str) -> None:
    recordar(DESPLEGABLES, clave, bool(st.session_state.get(clave)))
