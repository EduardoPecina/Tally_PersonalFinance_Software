"""Resumen: ¿cuánto dinero tengo, cuánto gasté y en qué?"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from motor import cuentas, reportes, tarjetas
from motor.modelo import TipoCuenta
from portal.componentes import estado, formato, graficas
from portal.componentes.sesion import libro
from portal.navegacion import enlace

PERSONALIZADO = "personalizado"
PERIODOS = {**reportes.PERIODOS, PERSONALIZADO: "Elegir fechas"}


def _periodo() -> tuple[date, date]:
    lib = libro()
    clave = estado.control("inicio", "periodo", "mes_actual", lambda k: st.segmented_control(
        "Periodo", list(PERIODOS), format_func=PERIODOS.get, key=k, required=True, label_visibility="collapsed"))
    if clave == PERSONALIZADO:
        inicial = reportes.rango_periodo(lib, "mes_actual")
        rango = estado.control("inicio", "rango", inicial, lambda k: st.date_input(
            "Fechas", key=k, format="DD/MM/YYYY"))
        if isinstance(rango, (tuple, list)) and len(rango) == 2:
            return rango[0], rango[1]
        st.caption("Elige la fecha final.")
        return inicial
    return reportes.rango_periodo(lib, clave)


def _situacion() -> None:
    ind = reportes.indicadores(libro())
    columnas = st.columns(5 if ind.te_deben else 4)
    columnas[0].metric("Dinero disponible", formato.dinero(ind.dinero_disponible),
                       help="Lo que puedes usar ya: tus cuentas marcadas como disponibles (débito, efectivo…).")
    columnas[1].metric("Total en cuentas", formato.dinero(ind.total_en_cuentas),
                       help="Débito, ahorro, efectivo, inversiones y otras cuentas.")
    columnas[2].metric("Deuda de tarjetas", formato.dinero(ind.deuda_tarjetas))
    columnas[3].metric("Patrimonio neto", formato.dinero(ind.patrimonio_neto),
                       help="Todo lo que tienes menos lo que debes (aproximado).")
    if ind.te_deben:
        columnas[4].metric("Te deben", formato.dinero(ind.te_deben))


def _delta(valor) -> str | None:
    return None if not valor else f"{'+' if valor > 0 else ''}{formato.dinero(valor)} vs. periodo anterior"


def _periodo_resumen(desde: date, hasta: date) -> None:
    comparacion = reportes.comparar(libro(), desde, hasta)
    actual, diferencia = comparacion.actual, comparacion.diferencia
    columnas = st.columns(4)
    columnas[0].metric("Ingresos", formato.dinero(actual.ingresos), delta=_delta(diferencia.ingresos))
    columnas[1].metric("Gastos", formato.dinero(actual.gastos), delta=_delta(diferencia.gastos), delta_color="inverse")
    columnas[2].metric("Ahorro real", formato.dinero(actual.ahorro_real), delta=_delta(diferencia.ahorro_real),
                       help="Ingresos menos gastos del periodo.")
    columnas[3].metric("Apartado a ahorro", formato.dinero(actual.apartado_a_ahorro),
                       help="Lo que pasaste a tus cuentas de ahorro e inversión (neto).")
    if actual.ajustes:
        st.caption(f"Ajustes de saldo en el periodo: {formato.dinero_md(actual.ajustes)} "
                   "(no cuentan como ingreso ni gasto).")


def _tarjetas() -> None:
    lib = libro()
    lista = cuentas.listar(lib, tipo=TipoCuenta.CREDITO)
    if not lista:
        return
    st.subheader("Tarjetas de crédito")
    columnas = st.columns(min(len(lista), 3))
    for i, tarjeta in enumerate(lista):
        with columnas[i % len(columnas)], st.container(border=True):
            st.markdown(f"**{tarjeta.nombre}**")
            st.metric("Debes", formato.dinero(tarjetas.deuda(lib, tarjeta.id)))
            por_pagar = tarjetas.ciclo_por_pagar(lib, tarjeta.id)
            if por_pagar is not None:
                texto = f"Por liquidar del corte {formato.fecha(por_pagar.fin)}: **{formato.dinero_md(por_pagar.por_liquidar)}**"
                if por_pagar.por_liquidar and por_pagar.fecha_limite_pago:
                    texto += f"  \nPagar antes del **{formato.fecha(por_pagar.fecha_limite_pago)}**"
                st.markdown(texto)
                actual = tarjetas.ciclo_actual(lib, tarjeta.id)
                st.caption(f"Ciclo actual ({formato.rango(actual.inicio, actual.fin)}): "
                           f"cargos {formato.dinero_md(actual.cargos)}")
            disponible = tarjetas.credito_disponible(lib, tarjeta.id)
            if disponible is not None:
                st.caption(f"Crédito disponible: {formato.dinero_md(disponible)}")


def _quincenas() -> None:
    lib = libro()
    for cuenta in cuentas.listar(lib):
        sobrantes = reportes.sobrantes_de_quincena(lib, cuenta.id)[-6:]
        if len(sobrantes) < 2:
            continue
        st.subheader(f"Lo que te sobró antes de cada nómina · {cuenta.nombre}")
        graficas.barras([(formato.fecha(s.fecha), s.sobrante) for s in reversed(sobrantes)], "Sobrante",
                       "Nómina del")


def mostrar() -> None:
    lib = libro()
    st.title(f"¡Hola, {lib.perfil.nombre}!" if lib.perfil else "Resumen")
    st.caption(f"Hoy es {formato.fecha_larga(lib.hoy())}.")
    if not cuentas.listar(lib):
        st.info("Agrega tu primera cuenta para empezar.")
        enlace("cuentas", "Ir a Cuentas", "🏦")
        return

    st.subheader("Tu situación hoy")
    _situacion()

    st.divider()
    desde, hasta = _periodo()
    st.subheader(f"Periodo: {formato.rango(desde, hasta)}")
    _periodo_resumen(desde, hasta)

    izquierda, derecha = st.columns(2)
    with izquierda:
        st.markdown("**¿En qué gasté?**")
        graficas.barras([(t.nombre, t.total) for t in reportes.gastos_por_categoria(lib, desde, hasta)
                         if t.total > 0], "Gasto")
    with derecha:
        st.markdown("**Por grupo**")
        graficas.barras([(g, v) for g, v in reportes.gastos_por_grupo(lib, desde, hasta).items() if v > 0], "Gasto",
                       "Grupo")

    # Al menos tres meses de contexto, aunque el periodo elegido sea más corto.
    hasta_grafica = max(desde, min(hasta, lib.hoy()))
    desde_grafica = min(desde, hasta_grafica - timedelta(days=90))
    st.markdown(f"**Evolución de tu patrimonio** · {formato.rango(desde_grafica, hasta_grafica)}")
    graficas.linea([(p.fecha, p.patrimonio_neto) for p in reportes.evolucion(lib, desde_grafica, hasta_grafica)])

    _tarjetas()
    _quincenas()
    st.divider()
    enlace("registrar", "Registrar un movimiento", "➕")
