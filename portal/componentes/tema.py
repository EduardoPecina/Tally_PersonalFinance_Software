"""Estilos del portal. El tema oscuro (Configuración → Apariencia) es al estilo de Dark Reader: se invierten los
colores de toda la página y se regresan a su color las imágenes (como las vistas previas del ícono). Funciona con
todos los controles y gráficas sin tener que redibujarlos."""

from __future__ import annotations

import streamlit as st

# Los enlaces a otras páginas (fuera del menú) con su cajita, como los botones.
BASE = """
<style>
[data-testid="stMain"] [data-testid="stPageLink-NavLink"] {
    border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 0.5rem; padding: 0.375rem 0.75rem;
    width: fit-content; background: #ffffff;
}
[data-testid="stMain"] [data-testid="stPageLink-NavLink"]:hover { border-color: #6B53F1; }
</style>
"""

OSCURO = """
<style>
html { filter: invert(0.92) hue-rotate(180deg); background: #ffffff; }
[data-testid="stImage"] img, video { filter: invert(1) hue-rotate(180deg); }
</style>
"""


def aplicar(tema: str) -> None:
    st.html(BASE)
    if tema == "oscuro":
        st.html(OSCURO)
