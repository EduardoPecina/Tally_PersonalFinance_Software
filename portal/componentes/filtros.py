"""Filtros compartidos por Tablas dinámicas y Gráficas: periodo y cuentas."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from motor import analisis
from motor.libro import Libro
from portal.componentes import formato

PERIODOS = {"todo": "Todo el historial", "anio": "Este año", "12m": "Últimos 12 meses", "rango": "Elegir meses"}


def _meses(desde: date, hasta: date) -> list[date]:
    meses, actual = [], desde.replace(day=1)
    while actual <= hasta:
        meses.append(actual)
        actual = (actual + timedelta(days=32)).replace(day=1)
    return meses


def _fin_de_mes(mes: date) -> date:
    return (mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def periodo_y_cuentas(lib: Libro, guardado: dict, clave: str) -> dict:
    """Dibuja los filtros (dentro de un formulario) y devuelve lo elegido."""
    izquierda, derecha = st.columns(2)
    claves = list(PERIODOS)
    periodo = izquierda.selectbox("Periodo", claves, format_func=PERIODOS.get, key=f"{clave}_periodo",
                                  index=claves.index(guardado.get("periodo", "todo")))
    hoy = lib.hoy()
    datos = analisis.meses_con_datos(lib)
    meses = _meses(min(datos[0], hoy) if datos else hoy, max(datos[1], hoy) if datos else hoy)
    rango = guardado.get("rango") or (meses[0], meses[-1])
    rango = (rango[0] if rango[0] in meses else meses[0], rango[1] if rango[1] in meses else meses[-1])
    meses_elegidos = izquierda.select_slider(
        "Meses (si eliges «Elegir meses»)", options=meses, value=rango, key=f"{clave}_rango",
        format_func=lambda m: formato.mes(m.year, m.month)) if len(meses) > 1 else (meses[0], meses[0])
    todas = {c.id: c.nombre for c in lib.cuentas()}
    cuentas = derecha.multiselect("Cuentas", list(todas), format_func=todas.get, placeholder="Todas",
                                  default=[c for c in guardado.get("cuentas", []) if c in todas], key=f"{clave}_cuentas")
    return {"periodo": periodo, "rango": tuple(meses_elegidos), "cuentas": cuentas}


def fechas(lib: Libro, elegido: dict) -> tuple[date | None, date | None]:
    hoy = lib.hoy()
    periodo = elegido.get("periodo", "todo")
    if periodo == "anio":
        return hoy.replace(month=1, day=1), hoy
    if periodo == "12m":
        return (hoy.replace(day=1) - timedelta(days=330)).replace(day=1), hoy
    if periodo == "rango":
        inicio, fin = elegido["rango"]
        return inicio, _fin_de_mes(fin)
    return None, None


def describir(lib: Libro, elegido: dict) -> str:
    desde, hasta = fechas(lib, elegido)
    texto = "Todo el historial" if desde is None else formato.rango(desde, hasta)
    if elegido.get("cuentas"):
        texto += " · " + ", ".join(lib.cuenta(c).nombre for c in elegido["cuentas"])
    return texto
