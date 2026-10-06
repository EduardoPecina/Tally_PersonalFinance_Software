"""Presupuestos: cuánto te propones gastar al mes en cada categoría y cómo vas."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import categorias, reportes
from motor.modelo import ClaseCategoria
from portal.componentes import formato
from portal.componentes.sesion import ejecutar, libro


def avance(desde, hasta, *, titulo: bool = True) -> None:
    """Barras de avance de cada presupuesto (también se usa en el Resumen)."""
    lista = reportes.presupuestos(libro(), desde, hasta)
    if not lista:
        return
    if titulo:
        st.subheader("Presupuestos del mes")
    columnas = st.columns(2)
    for i, a in enumerate(sorted(lista, key=lambda a: -a.avance)):
        with columnas[i % 2]:
            porcentaje = float(a.avance)
            if a.restante >= 0:
                texto = f"**{a.nombre}** · {formato.dinero_md(a.gastado)} de {formato.dinero_md(a.presupuesto)} · " \
                        f"te quedan {formato.dinero_md(a.restante)}"
            else:
                texto = f"**{a.nombre}** · :red[te pasaste por {formato.dinero_md(-a.restante)}] " \
                        f"({formato.dinero_md(a.gastado)} de {formato.dinero_md(a.presupuesto)})"
            st.markdown(texto)
            st.progress(min(porcentaje, 1.0), text=f"{porcentaje:.0%}")


def mostrar() -> None:
    lib = libro()
    st.title("Presupuestos")
    st.caption("Ponle un tope mensual a las categorías que quieras cuidar (por ejemplo, ALIMENTACION o "
               "ENTRETENIMIENTO). TALLY te muestra cuánto llevas este mes, aquí y en el Resumen.")
    desde, hasta = reportes.rango_periodo(lib, "mes_actual")
    if reportes.presupuestos(lib, desde, hasta):
        st.subheader(f"Cómo vas · {formato.mes(desde.year, desde.month)}")
        avance(desde, hasta, titulo=False)
        st.divider()

    st.subheader("Tus presupuestos")
    rubros = [r for r in lib.rubros() if r.clase is ClaseCategoria.GASTO]
    gastado = reportes.gastos_por_rubro(lib, desde, hasta)
    tabla = pd.DataFrame({
        "Categoría": [r.nombre for r in rubros],
        "Presupuesto mensual": [r.presupuesto / 100 if r.presupuesto else None for r in rubros],
        "Gastado este mes": [float(gastado.get(r.nombre, 0)) for r in rubros],
    })
    editada = st.data_editor(
        tabla, hide_index=True, width="stretch", key="presupuestos_tabla", disabled=["Categoría", "Gastado este mes"],
        column_config={"Presupuesto mensual": st.column_config.NumberColumn(min_value=0, step=100, format="dollar",
                                                                           help="Vacío = sin presupuesto"),
                       "Gastado este mes": st.column_config.NumberColumn(format="dollar")},
        height=min(38 + 35 * len(tabla), 560),
    )
    if st.button("Guardar presupuestos", type="primary"):
        cambios = {r.id: editada.loc[i, "Presupuesto mensual"] for i, r in enumerate(rubros)
                   if (editada.loc[i, "Presupuesto mensual"] or 0) * 100 != (r.presupuesto or 0)}

        def accion(lib):
            for rubro_id, monto in cambios.items():
                categorias.fijar_presupuesto(lib, rubro_id, None if pd.isna(monto) else round(float(monto), 2))
        if not cambios:
            st.info("No cambiaste nada.")
        elif ejecutar(accion, exito=f"{len(cambios)} presupuesto(s) guardado(s)"):
            st.rerun()
