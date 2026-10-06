"""Tema oscuro (Configuración → Apariencia), al estilo de Dark Reader: se invierten los colores de toda la página
y se regresan a su color las imágenes (como las vistas previas del ícono). Funciona con todos los controles
y gráficas sin tener que redibujarlos."""

from __future__ import annotations

import streamlit as st

OSCURO = """
<style>
html { filter: invert(0.92) hue-rotate(180deg); background: #ffffff; }
[data-testid="stImage"] img, video { filter: invert(1) hue-rotate(180deg); }
</style>
"""


def aplicar(tema: str) -> None:
    if tema == "oscuro":
        st.html(OSCURO)
