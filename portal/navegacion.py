"""Páginas del portal y enlaces entre ellas."""

from __future__ import annotations

import streamlit as st

_PAGINAS: dict[str, st.Page] = {}


def paginas() -> dict[str, st.Page]:
    """Las páginas, creadas una sola vez. Cada una es un archivo en ``portal/vistas``."""
    if not _PAGINAS:
        _PAGINAS.update(
            inicio=st.Page("vistas/inicio.py", title="Resumen", icon="🏠", default=True),
            registrar=st.Page("vistas/registrar.py", title="Registrar", icon="➕", url_path="registrar"),
            historial=st.Page("vistas/historial.py", title="Historial", icon="📋", url_path="historial"),
            cuentas=st.Page("vistas/cuentas.py", title="Cuentas", icon="🏦", url_path="cuentas"),
            categorias=st.Page("vistas/categorias.py", title="Categorías", icon="🏷️", url_path="categorias"),
            respaldos=st.Page("vistas/respaldos.py", title="Respaldos y bitácora", icon="💾", url_path="respaldos"),
        )
    return _PAGINAS


def enlace(pagina: str, texto: str, icono: str | None = None) -> None:
    st.page_link(paginas()[pagina], label=texto, icon=icono)
