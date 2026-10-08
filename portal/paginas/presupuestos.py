"""Presupuestos: cuánto te propones gastar al mes en cada categoría y cómo vas."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import categorias, planeacion, reportes
from motor.modelo import ClaseCategoria
from portal.componentes import formato
from portal.componentes.sesion import ejecutar, libro
from portal.navegacion import enlace


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
    plan, proyeccion = st.tabs(["¿Cuánto puedes gastar?", "Proyección del mes"])
    with plan:
        _plan()
    with proyeccion:
        _proyeccion()
    st.divider()
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
        "Gastado este mes": [formato.dinero(gastado.get(r.nombre, 0)) for r in rubros],
    })
    editada = st.data_editor(
        tabla, hide_index=True, width="stretch", key="presupuestos_tabla", disabled=["Categoría", "Gastado este mes"],
        column_config={"Presupuesto mensual": st.column_config.NumberColumn(
                           min_value=0, step=100, format=formato.columna_dinero(), help="Vacío = sin presupuesto"),
                       "Gastado este mes": st.column_config.TextColumn(alignment="right")},
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
    con_presupuesto = [r for r in rubros if r.presupuesto]
    if con_presupuesto:
        st.caption("Para quitar uno, borra su importe en la tabla y guarda.")
        with st.popover("Quitar todos mis presupuestos", icon=":material/delete_sweep:"):
            st.markdown(f"Se quitan tus **{len(con_presupuesto)} presupuesto(s)**. Tus gastos no se tocan.")
            if st.button("Sí, quitarlos", type="primary", key="presupuestos_quitar_todos"):
                def quitar(lib):
                    for r in con_presupuesto:
                        categorias.fijar_presupuesto(lib, r.id, None)
                if ejecutar(quitar, exito="Presupuestos quitados"):
                    st.rerun()


# -------------------------------------------------------------- sugeridos


def _plan() -> None:
    lib = libro()
    plan = planeacion.sugerir(lib)
    if not plan.ingreso:
        st.info("Primero configura tu ingreso principal en **Ingresos** (o escribe ahí cuánto ganas al mes).")
        enlace("ingresos", "Ir a Ingresos", "💰")
        return
    a, b, c, d = st.columns(4)
    a.metric("Ingreso esperado", formato.dinero_metrica(plan.ingreso))
    b.metric("Pagos de préstamos", formato.dinero_metrica(plan.deudas))
    c.metric(f"Ahorro ({lib.perfil.meta_ahorro} %)", formato.dinero_metrica(plan.ahorro))
    d.metric("Para gastar al mes", formato.dinero_metrica(plan.para_gastar))
    if not plan.sugerencias:
        st.caption("Aún no hay meses completos con gastos para sugerir presupuestos.")
        return
    if plan.factor < 1:
        st.warning(f"Lo que sueles gastar ({formato.dinero_md(plan.total_promedio)}) no cabe en lo que tienes para "
                   f"gastar: los sugeridos se ajustaron al {plan.factor * 100:.0f} % para que te alcance para tus "
                   "deudas y tu ahorro.", icon="⚠️")
    else:
        st.success(f"Lo que sueles gastar ({formato.dinero_md(plan.total_promedio)}) cabe en tu presupuesto: te "
                   f"sobran {formato.dinero_md(plan.para_gastar - plan.total_sugerido)} al mes además de tu ahorro.",
                   icon="✅")
    st.dataframe(formato.pintar(pd.DataFrame({
        "Categoría": [s.nombre for s in plan.sugerencias],
        "Sueles gastar": [formato.dinero(s.promedio) for s in plan.sugerencias],
        "Sugerido": [formato.dinero(s.sugerido) for s in plan.sugerencias],
        "Tu presupuesto": [formato.dinero(s.actual) if s.actual is not None else "—" for s in plan.sugerencias],
    })), hide_index=True, width="stretch")
    st.caption(f"Sugerido: tu promedio de los últimos 3 meses completos, redondeado a "
               f"{formato.dinero_md(plan.redondeo)} (los intereses de préstamos ya van en sus pagos).")
    if st.button("Usar los sugeridos como mis presupuestos", key="usar_sugeridos"):
        def aplicar(lib):
            for s in plan.sugerencias:
                categorias.fijar_presupuesto(lib, s.rubro_id, float(s.sugerido) if s.sugerido else None)
        if ejecutar(aplicar, exito="Presupuestos actualizados"):
            st.rerun()


# ----------------------------------------------------------- proyección


def _proyeccion() -> None:
    lib = libro()
    p = planeacion.proyeccion_mes(lib)
    st.caption(f"Día {p.dias_transcurridos} de {p.dias_del_mes}. Cada categoría: al menos lo que sueles gastar (si ya "
               "te pasaste, lo que llevas); las que no tienen historial, a este ritmo.")
    a, b, c = st.columns(3)
    a.metric("Llevas gastado", formato.dinero_metrica(p.gastado))
    b.metric("Gasto proyectado al cierre", formato.dinero_metrica(p.gasto_proyectado))
    c.metric("Te quedaría", formato.dinero_metrica(p.ahorro_proyectado),
             help="Tu ingreso del mes (el esperado, o lo recibido si fue más) menos el gasto proyectado.")
    if p.ahorro_proyectado < 0:
        st.error("A este ritmo vas a gastar más de lo que ganas este mes.", icon="🔴")
    pasados = [r for r in p.rubros if r.se_pasa]
    if pasados:
        st.warning("Te vas a pasar en: " + ", ".join(f"**{r.nombre}** ({formato.dinero_md(r.proyectado)} de "
                                                      f"{formato.dinero_md(r.presupuesto)})" for r in pasados),
                   icon="⚠️")
    if p.rubros:
        st.dataframe(formato.pintar(pd.DataFrame({
            "Categoría": [r.nombre for r in p.rubros], "Llevas": [formato.dinero(r.gastado) for r in p.rubros],
            "Proyectado al cierre": [formato.dinero(r.proyectado) for r in p.rubros],
            "Presupuesto": [formato.dinero(r.presupuesto) if r.presupuesto is not None else "—" for r in p.rubros],
        })), hide_index=True, width="stretch")
