"""🩺 Salud de tus datos: posibles duplicados, cuentas en negativo, fechas raras, datos que faltan… (motor/salud.py)."""

from __future__ import annotations

from itertools import groupby

import pandas as pd
import streamlit as st

from motor import consultas, efectivo, movimientos, salud
from portal.componentes import formato
from portal.componentes.sesion import aplicar, avisar, ejecutar, libro, sesion
from portal.navegacion import enlace

DESTINOS = {"historial": ("Ir al Historial", "📋"), "cuentas": ("Ir a Cuentas", "🏦"),
            "categorias": ("Ir a Categorías", "🏷️"), "impuestos": ("Ir a Impuestos", "🧾"),
            "deudas": ("Ir a Deudas", "💳"), "inicio": ("Ir al Resumen", "🏠"),
            "respaldos": ("Ir a Respaldos", "💾")}
MAXIMO_POR_GRUPO = 15


def revision_actual() -> salud.Revision:
    """La revisión de hoy, calculada una vez por cada versión de tus datos (el Resumen la consulta seguido)."""
    lib = libro()
    llave = (id(sesion()), sesion().almacen.revision, lib.hoy())
    guardada = st.session_state.get("_salud")
    if guardada is None or guardada[0] != llave:
        guardada = (llave, salud.revisar(lib))
        st.session_state["_salud"] = guardada
    return guardada[1]


def aviso_en_el_resumen() -> None:
    """En el Resumen, solo si hay algo 🔴 o 🟠."""
    revision = revision_actual()
    if not revision.importantes:
        return
    titulos = sorted({h.titulo.lower() for h in revision.hallazgos if h.nivel != salud.MEJORAR})
    st.warning(f"**Revisa tus datos:** encontré {revision.importantes} cosa(s) que quizá no están bien "
               f"({', '.join(titulos[:3])}).", icon="🩺")
    enlace("salud", "Revisar mis datos", "🩺")


def mostrar() -> None:
    st.title("Salud de tus datos")
    st.caption("Reviso tus datos en busca de lo que suele ser un error o algo incompleto, para que tus reportes digan "
               "la verdad. Nada cambia solo: tú decides. Si algo está bien así, márcalo y no vuelve a salir.")
    revision = revision_actual()
    a, b, c = st.columns(3)
    for columna, nivel in zip((a, b, c), (salud.ERROR, salud.REVISAR, salud.MEJORAR), strict=True):
        icono, nombre = salud.NIVELES[nivel]
        columna.metric(f"{icono} {nombre}", len(revision.por_nivel(nivel)))
    if not revision.hallazgos:
        st.success(f"Todo se ve bien. ✨ Revisé {revision.revisados['movimientos']:,} movimientos y "
                   f"{revision.revisados['cuentas']} cuentas.", icon="✅")
    for nivel in (salud.ERROR, salud.REVISAR, salud.MEJORAR):
        lista = revision.por_nivel(nivel)
        if not lista:
            continue
        icono, nombre = salud.NIVELES[nivel]
        st.subheader(f"{icono} {nombre}")
        for titulo, grupo in groupby(lista, key=lambda h: h.titulo):
            grupo = list(grupo)
            with st.expander(f"**{titulo}** · {len(grupo)}", expanded=nivel != salud.MEJORAR):
                for h in grupo[:MAXIMO_POR_GRUPO]:
                    _hallazgo(h)
                if len(grupo) > MAXIMO_POR_GRUPO:
                    st.caption(f"…y {len(grupo) - MAXIMO_POR_GRUPO} más. Resuelve estos y aparecerán los demás.")
    if revision.ignorados:
        st.divider()
        izquierda, derecha = st.columns([3, 1], vertical_alignment="center")
        izquierda.caption(f"{revision.ignorados} cosa(s) marcadas como «Está bien así» no se muestran.")
        if derecha.button("Volver a mostrarlas", key="salud_mostrar_todo"):
            if ejecutar(salud.mostrar_todo, exito="Se vuelven a mostrar"):
                st.rerun()


def _hallazgo(h: salud.Hallazgo) -> None:
    with st.container(border=True):
        st.markdown(formato.md(h.detalle))
        if h.operaciones and len(h.operaciones) <= 3:
            _movimientos(h.operaciones)
        columnas = st.columns([2, 2, 3], vertical_alignment="center")
        if h.pagina in DESTINOS:
            with columnas[0]:
                enlace(h.pagina, *DESTINOS[h.pagina])
        if h.clave.startswith("duplicado:"):
            with columnas[1].popover("Borrar uno", icon=":material/delete:"):
                _borrar_duplicado(h)
        if h.clave.startswith("efectivo:") and columnas[1].button(
                "Pasarlos a mi efectivo", key=f"salud_efectivo_{h.clave}", type="primary", icon=":material/payments:"):
            hechos = aplicar(efectivo.convertir_todos)
            if hechos is not None:
                avisar(f"{hechos} retiro(s) pasaron a tu cuenta de efectivo y ya no cuentan como gasto.", "💵")
                st.rerun()
        if h.se_puede_ignorar and columnas[2].button("Está bien así", key=f"salud_ignorar_{h.clave}",
                                                     icon=":material/check:"):
            if ejecutar(lambda lib: salud.ignorar(lib, h.clave), exito="Listo: ya no se muestra"):
                st.rerun()


def _movimientos(ids: tuple[str, ...]) -> None:
    lib = libro()
    filas = [consultas.fila(lib, lib.operacion(i)) for i in ids if _existe(i)]
    if not filas:
        return
    st.dataframe(formato.pintar(pd.DataFrame({
        "Fecha": [formato.fecha(f.fecha) for f in filas],
        "Descripción": [f.descripcion for f in filas],
        "Cuenta": [f.cuenta + (f" → {f.cuenta_destino}" if f.cuenta_destino else "") for f in filas],
        "Subcategoría": [f.categoria for f in filas],
        "Importe": [formato.dinero_con_signo(f.monto, f.sentido) for f in filas],
        "Registrado": [f"{lib.operacion(f.id).creado_en:%d/%m/%Y %H:%M}" for f in filas],
    })), hide_index=True, width="stretch")


def _existe(operacion_id: str) -> bool:
    try:
        libro().operacion(operacion_id)
        return True
    except LookupError:
        return False


def _borrar_duplicado(h: salud.Hallazgo) -> None:
    st.caption("Borra el que sobra. La bitácora conserva una copia.")
    lib = libro()
    for n, operacion_id in enumerate(h.operaciones, start=1):
        if not _existe(operacion_id):
            continue
        op = lib.operacion(operacion_id)
        if st.button(f"Borrar el del {formato.fecha(op.fecha)} (registrado {op.creado_en:%d/%m %H:%M})",
                     key=f"salud_borrar_{h.clave}_{n}"):
            if ejecutar(lambda lib_, i=operacion_id: movimientos.eliminar(lib_, i), exito="Movimiento borrado"):
                st.rerun()
