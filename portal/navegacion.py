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
            presupuestos=st.Page("vistas/presupuestos.py", title="Presupuestos", icon="🎯", url_path="presupuestos"),
            pivots=st.Page("vistas/pivots.py", title="Tablas dinámicas", icon="🧮", url_path="pivots"),
            graficas=st.Page("vistas/graficas.py", title="Gráficas", icon="📊", url_path="graficas"),
            inversiones=st.Page("vistas/inversiones.py", title="Inversiones", icon="📈", url_path="inversiones"),
            contabilidad=st.Page("vistas/contabilidad.py", title="Contabilidad Técnica", icon="📒",
                                 url_path="contabilidad"),
            categorias=st.Page("vistas/categorias.py", title="Categorías", icon="🏷️", url_path="categorias"),
            cargar=st.Page("vistas/cargar.py", title="Cargar datos", icon="📥", url_path="cargar"),
            respaldos=st.Page("vistas/respaldos.py", title="Respaldos y bitácora", icon="💾", url_path="respaldos"),
            configuracion=st.Page("vistas/configuracion.py", title="Configuración", icon="⚙️",
                                  url_path="configuracion"),
        )
    return _PAGINAS


SECCIONES = {
    "Tu dinero": ("inicio", "registrar", "historial", "cuentas", "presupuestos"),
    "Análisis": ("pivots", "graficas", "inversiones", "contabilidad"),
    "Ajustes": ("categorias", "cargar", "respaldos", "configuracion"),
}


def por_seccion() -> dict[str, list[st.Page]]:
    """Las páginas agrupadas para el menú de la izquierda."""
    todas = paginas()
    return {seccion: [todas[n] for n in nombres] for seccion, nombres in SECCIONES.items()}


def enlace(pagina: str, texto: str, icono: str | None = None) -> None:
    st.page_link(paginas()[pagina], label=texto, icon=icono)
