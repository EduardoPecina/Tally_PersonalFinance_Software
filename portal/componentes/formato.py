"""Formato de presentación: dinero, fechas y textos."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from motor.dinero import formatear

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")
MESES_CORTOS = tuple(m[:3] for m in MESES)


def dinero(importe: Decimal | int) -> str:
    return formatear(importe)


def dinero_con_signo(importe: Decimal, sentido: str) -> str:
    """``-$300.00``, ``+$1,000.00`` o ``↔ $500.00`` según el efecto del movimiento."""
    if sentido == "↔":
        return f"↔ {formatear(importe)}"
    return f"{sentido}{formatear(abs(importe))}"


def md(texto: str) -> str:
    """Escapa ``$`` para Markdown: con dos ``$`` en un texto, Streamlit lo dibujaría como fórmula."""
    return texto.replace("$", "\\$")


def dinero_md(importe: Decimal | int) -> str:
    """Como :func:`dinero`, para usar dentro de ``st.markdown``/``st.caption``."""
    return md(dinero(importe))


def dinero_con_signo_md(importe: Decimal, sentido: str) -> str:
    return md(dinero_con_signo(importe, sentido))


def fecha(valor: date) -> str:
    return f"{valor.day:02d}/{valor.month:02d}/{valor.year}"


def fecha_larga(valor: date) -> str:
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


def rango(desde: date, hasta: date) -> str:
    if desde.year == hasta.year:
        if desde.month == hasta.month:
            return f"{desde.day} – {hasta.day} de {MESES[desde.month - 1]} de {desde.year}"
        return f"{desde.day} {MESES_CORTOS[desde.month - 1]} – {hasta.day} {MESES_CORTOS[hasta.month - 1]} {desde.year}"
    return f"{fecha(desde)} – {fecha(hasta)}"


def mes(anio: int, numero: int) -> str:
    return f"{MESES[numero - 1].capitalize()} {anio}"


def tabla_en_pesos(tabla, columnas, *, fijar: str | None = None):
    """(tabla para mostrar, column_config): esas columnas como texto en pesos, alineado a la derecha, y las
    celdas vacías en blanco (Streamlit pondría «None»). Para exportar se usa la tabla original, con números."""
    import pandas as pd
    import streamlit as st

    def pesos(valor) -> str:
        return "" if valor is None or pd.isna(valor) else formatear(Decimal(str(round(valor, 2))))

    vista = tabla.copy()
    for columna in columnas:
        vista[columna] = vista[columna].map(pesos)
    config = {c: st.column_config.TextColumn(alignment="right") for c in columnas}
    if fijar:
        config[fijar] = st.column_config.TextColumn(pinned=True)
    return vista, config
