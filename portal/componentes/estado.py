"""Valores de pantalla que deben sobrevivir al cambiar de página (p. ej. filtros).

Streamlit borra el estado de un control cuando su página deja de mostrarse.
Aquí se guarda una copia aparte y se le devuelve al control al regresar.
"""

from __future__ import annotations

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
