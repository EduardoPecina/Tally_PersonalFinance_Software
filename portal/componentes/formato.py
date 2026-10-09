"""Formato de presentación: dinero, fechas y textos."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from motor import monedas
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


# Lo negativo (lo que sale) va en rojo; lo positivo, en el color normal del texto.
ROJO = "#c62828"
LIMITE_COLOR = 2_000            # renglones: pintar una tabla más grande tarda segundos (ver pintar)
_NEGATIVO = re.compile(r"^-\D{0,4}\d")      # «-$300.00», «-1.234,56 €», «-S/ 99.90», «-5.2 %»


def rojo_md(texto: str) -> str:
    """Texto en rojo para Markdown (``st.markdown``, ``st.caption``, avisos, métricas…)."""
    return f":red[{texto}]"


def dinero_md(importe: Decimal | int) -> str:
    """Como :func:`dinero`, para usar dentro de ``st.markdown``/``st.caption``. Negativo, en rojo."""
    texto = md(dinero(importe))
    return rojo_md(texto) if Decimal(importe) < 0 and texto.strip("\\$0.,- ") else texto


def dinero_con_signo_md(importe: Decimal, sentido: str) -> str:
    texto = md(dinero_con_signo(importe, sentido))
    return rojo_md(texto) if sentido == "-" else texto


def dinero_metrica(importe: Decimal | int) -> str:
    """El valor de un ``st.metric``: igual que :func:`dinero`, y en rojo si es negativo."""
    return dinero_md(importe) if Decimal(importe) < 0 else dinero(importe)


def _rojo_si_negativo(valor) -> str:
    if isinstance(valor, str):
        return f"color: {ROJO}" if _NEGATIVO.match(valor) else ""
    try:
        return f"color: {ROJO}" if valor is not None and valor == valor and valor < 0 else ""
    except TypeError:
        return ""


def pintar(tabla, columnas=None, *, rojas=()):
    """La tabla para ``st.dataframe`` con lo negativo en rojo («-$300.00», saldos de tarjeta, pérdidas…).

    Acepta un ``DataFrame`` o una tabla que ya tiene estilo (``Styler``): le suma el rojo. Con más de
    ``LIMITE_COLOR`` renglones se regresa tal cual: pintar decenas de miles de celdas tarda segundos.
    ``rojas``: columnas que son todo salidas (la «Salida» de un estado de cuenta): van en rojo completas.
    """
    datos = getattr(tabla, "data", tabla)                # el DataFrame de un Styler
    if len(datos) == 0 or len(datos) > LIMITE_COLOR:
        return tabla
    estilo = tabla if hasattr(tabla, "data") and hasattr(tabla, "map") and tabla is not datos else datos.style
    estilo = estilo.map(_rojo_si_negativo, subset=columnas)
    rojas = [c for c in rojas if c in datos.columns]
    if rojas:
        estilo = estilo.map(lambda v: f"color: {ROJO}" if v not in (None, "") and v == v else "", subset=rojas)
    return estilo


def cuantos_mostrar(total: int, clave: str) -> int:
    """Cuántos renglones mostrar en una tabla larga: hasta ``LIMITE_COLOR`` (con colores), o todos si lo pides."""
    import streamlit as st

    if total <= LIMITE_COLOR:
        return total
    if st.toggle(f"Ver los {total:,} (tarda más y van sin colores)", key=clave):
        return total
    st.caption(f"Se muestran los primeros {LIMITE_COLOR:,} en el orden elegido. Usa los filtros para encontrar "
               "otros, o activa «Ver los …».")
    return LIMITE_COLOR


def fecha(valor: date) -> str:
    return f"{valor.day:02d}/{valor.month:02d}/{valor.year}"


PRIMERA_FECHA = date(1900, 1, 1)


def limites_de_fecha(lib) -> dict:
    """``min_value`` y ``max_value`` para los filtros de fechas. Si no se le dicen, el calendario solo deja ir 10 años
    atrás o adelante de la fecha elegida: con más años de datos no podrías ver tu historia completa. Son fijos (no
    dependen de tus movimientos) para que una fecha que ya elegiste nunca quede fuera."""
    return {"min_value": PRIMERA_FECHA, "max_value": date(lib.hoy().year + 10, 12, 31)}


DIAS_SEMANA = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def fecha_con_dia(valor: date) -> str:
    """``vie 13/03/2026``."""
    return f"{DIAS_SEMANA[valor.weekday()]} {fecha(valor)}"


def hora(valor: datetime) -> str:
    """``6:42 p. m.``"""
    return f"{valor.hour % 12 or 12}:{valor.minute:02d} {'a. m.' if valor.hour < 12 else 'p. m.'}"


def cuando(valor: datetime, hoy: date) -> str:
    """``hoy 6:42 p. m.``, ``ayer 9:05 a. m.`` o ``el 07/10/2026 6:42 p. m.``"""
    dia = valor.date()
    if dia == hoy:
        return f"hoy {hora(valor)}"
    if (hoy - dia).days == 1:
        return f"ayer {hora(valor)}"
    return f"el {fecha(dia)} {hora(valor)}"


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


def columna_dinero() -> str:
    """El ``format`` de una columna de dinero editable (``st.column_config.NumberColumn``) en tu moneda."""
    m = monedas.activa()
    if m.simbolo == "$" and m.decimal == "." and not m.despues:
        return "dollar"                                   # $1,234.56
    return f"%.{m.decimales}f {m.simbolo}" if m.despues else f"{m.simbolo} %.{m.decimales}f"


def tabla_en_pesos(tabla, columnas, *, fijar: str | None = None):
    """(tabla para mostrar, column_config): esas columnas como texto en tu moneda, alineado a la derecha, y las
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
