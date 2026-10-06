"""Historial: buscar, filtrar, ordenar, ver, editar y eliminar movimientos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import categorias, consultas, cuentas, movimientos
from motor.consultas import ETIQUETA_TIPO_OPERACION, ORDENES
from motor.modelo import TipoCuenta, TipoOperacion
from portal.componentes import estado, formato
from portal.componentes.sesion import ejecutar, libro

FILTROS = "historial"
TABLA = "historial_tabla"
CON_DESTINO = (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA)
CON_SIGNO = (TipoOperacion.AJUSTE, TipoOperacion.RENDIMIENTO, TipoOperacion.SALDO_INICIAL)


def _filtros() -> dict:
    lib = libro()
    todas_cuentas = {c.id: c.nombre for c in cuentas.listar(lib, incluir_archivadas=True)}
    todas_categorias = {c.id: categorias.etiqueta(lib, c.id) for c in categorias.ordenadas(lib, lib.categorias())}

    texto = estado.control(FILTROS, "texto", "", lambda k: st.text_input(
        "Buscar", key=k, placeholder="Descripción, notas, cuenta, categoría o subcategoría…"))
    col1, col2, col3 = st.columns(3)
    with col1:
        sel_cuentas = estado.control(FILTROS, "cuentas", [], lambda k: st.multiselect(
            "Cuentas", list(todas_cuentas), format_func=todas_cuentas.get, key=k, placeholder="Todas"))
    with col2:
        sel_categorias = estado.control(FILTROS, "categorias", [], lambda k: st.multiselect(
            "Subcategorías", list(todas_categorias), format_func=todas_categorias.get, key=k, placeholder="Todas"))
    with col3:
        sel_tipos = estado.control(FILTROS, "tipos", [], lambda k: st.multiselect(
            "Tipos", list(TipoOperacion), format_func=ETIQUETA_TIPO_OPERACION.get, key=k, placeholder="Todos"))
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2], vertical_alignment="bottom")
    with col1:
        desde = estado.control(FILTROS, "desde", None, lambda k: st.date_input(
            "Desde", key=k, format="DD/MM/YYYY"))
    with col2:
        hasta = estado.control(FILTROS, "hasta", None, lambda k: st.date_input(
            "Hasta", key=k, format="DD/MM/YYYY"))
    with col3:
        orden = estado.control(FILTROS, "orden", "fecha_desc", lambda k: st.selectbox(
            "Ordenar", list(ORDENES), format_func=ORDENES.get, key=k))
    with col4:
        activos = sum(bool(v) for v in (texto, sel_cuentas, sel_categorias, sel_tipos, desde, hasta))
        if st.button(f"Quitar todos los filtros ({activos})" if activos else "Quitar todos los filtros",
                     disabled=not activos, width="stretch"):
            estado.olvidar(FILTROS)
            st.session_state.pop(TABLA, None)
            st.rerun()
    # Quitar de los filtros lo que ya no existe (p. ej. una categoría borrada).
    sel_cuentas = [c for c in sel_cuentas if c in todas_cuentas]
    sel_categorias = [c for c in sel_categorias if c in todas_categorias]
    return {"texto": texto, "cuentas": sel_cuentas, "categorias": sel_categorias, "tipos": sel_tipos,
            "desde": desde, "hasta": hasta, "orden": orden}


def mostrar() -> None:
    st.title("Historial")
    st.caption("Todos tus movimientos. Los filtros se conservan aunque cambies de página.")
    filtros = _filtros()
    filas = consultas.buscar(libro(), **filtros)

    totales = consultas.total(filas)
    st.markdown(
        f"**{len(filas)}** movimiento(s) · Entradas **{formato.dinero_md(totales['+'])}** · "
        f"Salidas **{formato.dinero_md(totales['-'])}** · Entre tus cuentas {formato.dinero_md(totales['↔'])}"
    )
    if not filas:
        st.info("No hay movimientos con estos filtros.")
        return

    tabla = pd.DataFrame(
        {
            "Fecha": [f.fecha for f in filas],
            "Tipo": [f.tipo_etiqueta for f in filas],
            "Descripción": [f.descripcion for f in filas],
            "Cuenta": [f.cuenta + (f" → {f.cuenta_destino}" if f.cuenta_destino else "") for f in filas],
            "Categoría": [f.rubro for f in filas],
            "Subcategoría": [f.categoria for f in filas],
            "Importe": [formato.dinero_con_signo(f.monto, f.sentido) for f in filas],
        }
    )
    evento = st.dataframe(
        tabla, hide_index=True, on_select="rerun", selection_mode="single-row", key=TABLA,
        column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")},
        height=min(38 + 35 * len(filas), 520),
    )
    seleccion = evento.selection.rows if evento else []
    if not seleccion:
        st.caption("Selecciona un movimiento (casilla a la izquierda) para ver el detalle, editarlo o eliminarlo.")
        return
    detalle_movimiento(filas[seleccion[0]].id)


def detalle_movimiento(operacion_id: str, tabla: str = TABLA) -> None:
    """Detalle de un movimiento para verlo, editarlo, repetirlo o eliminarlo (Historial y estado de cuenta)."""
    lib = libro()
    try:
        detalle = movimientos.detalle(lib, operacion_id)
    except LookupError:
        return
    fila = consultas.fila(lib, lib.operacion(operacion_id))
    st.divider()
    st.subheader(formato.md(fila.descripcion or fila.tipo_etiqueta))
    st.markdown(
        f"{fila.tipo_etiqueta} · {formato.fecha_larga(fila.fecha)} · "
        f"**{formato.dinero_con_signo_md(fila.monto, fila.sentido)}**  \n"
        f":gray[{fila.cuenta}{' → ' + fila.cuenta_destino if fila.cuenta_destino else ''}"
        f"{' · ' + (fila.rubro + ' › ' if fila.rubro else '') + fila.categoria if fila.categoria else ''}]"
    )
    if fila.notas:
        st.caption(f"Notas: {formato.md(fila.notas)}")
    op = lib.operacion(operacion_id)
    st.caption(f"Registrado el {op.creado_en:%d/%m/%Y %H:%M}"
               + (f" · modificado el {op.modificado_en:%d/%m/%Y %H:%M}" if op.modificado_en != op.creado_en else ""))

    if detalle.tipo is TipoOperacion.SALDO_INICIAL:
        st.info("El saldo inicial se cambia desde **Cuentas → Saldo inicial**.")
        return

    editar, repetir, eliminar = st.tabs(["Editar", "Repetir", "Eliminar"])
    with editar:
        _editar(detalle, tabla)
    with repetir:
        st.caption("Registra otra vez este mismo movimiento en otra fecha (la renta, una suscripción, la nómina…).")
        fecha = st.date_input("Fecha del nuevo", value=lib.hoy(), format="DD/MM/YYYY", key=f"repetir_fecha_{operacion_id}")
        if st.button("Repetir este movimiento", key=f"repetir_{operacion_id}"):
            if ejecutar(lambda lib: movimientos.duplicar(lib, operacion_id, fecha),
                        exito=f"Movimiento repetido el {formato.fecha(fecha)}"):
                st.session_state.pop(tabla, None)
                st.rerun()
    with eliminar:
        st.warning("Eliminar borra el movimiento completo (en una transferencia, los dos lados). "
                   "La bitácora conserva una copia.")
        confirmar = st.checkbox("Sí, quiero eliminar este movimiento", key=f"confirmar_{operacion_id}")
        if st.button("Eliminar movimiento", type="primary", disabled=not confirmar, key=f"eliminar_{operacion_id}"):
            if ejecutar(lambda lib: movimientos.eliminar(lib, operacion_id), exito="Movimiento eliminado"):
                st.session_state.pop(tabla, None)
                st.rerun()


def _editar(detalle: movimientos.Detalle, tabla: str = TABLA) -> None:
    lib = libro()
    ids = [c.id for c in cuentas.listar(lib)]
    for cuenta_id in (detalle.cuenta_id, detalle.cuenta_destino_id):
        if cuenta_id and cuenta_id not in ids:
            ids.append(cuenta_id)  # una cuenta archivada que ya estaba en el movimiento
    nombre = {i: lib.cuenta(i).nombre for i in ids}
    cambios: dict = {}
    with st.form(f"editar_{detalle.id}", border=False):
        izquierda, derecha = st.columns(2)
        fecha = izquierda.date_input("Fecha", value=detalle.fecha, format="DD/MM/YYYY")
        repartido = detalle.categoria_id is None and bool(detalle.reparto)
        monto = None
        if not repartido:
            monto = derecha.number_input(
                "Importe", value=float(detalle.monto), step=1.0, format="%.2f",
                min_value=None if detalle.tipo in CON_SIGNO else 0.01,
                help="Positivo si entró dinero a la cuenta, negativo si salió." if detalle.tipo in CON_SIGNO else None,
            )
        cuenta = izquierda.selectbox("Cuenta" if detalle.tipo not in CON_DESTINO else "Desde la cuenta", ids,
                                     index=ids.index(detalle.cuenta_id), format_func=nombre.get)
        destino = None
        if detalle.tipo in CON_DESTINO:
            destino = derecha.selectbox("Hacia la cuenta", ids, index=ids.index(detalle.cuenta_destino_id),
                                        format_func=nombre.get)
        categoria = None
        if detalle.categoria_id and detalle.tipo is not TipoOperacion.AJUSTE:
            opciones = categorias.para_tipo(lib, detalle.tipo)
            cat_ids = [c.id for c in opciones]
            if detalle.categoria_id not in cat_ids:
                cat_ids.append(detalle.categoria_id)
            categoria = derecha.selectbox("Subcategoría", cat_ids, index=cat_ids.index(detalle.categoria_id),
                                          format_func=lambda i: categorias.etiqueta(lib, i))
        if repartido:
            st.caption("Este movimiento está repartido en varias subcategorías: aquí puedes cambiar fecha, cuenta "
                       "y textos.")
        msi = None
        original = lib.operacion(detalle.id)
        if detalle.tipo is TipoOperacion.GASTO and (original.msi or lib.cuenta(detalle.cuenta_id).tipo is TipoCuenta.CREDITO):
            msi = derecha.number_input("Meses sin intereses", min_value=0, max_value=60, value=original.msi, step=1,
                                       help="0 = de contado. Solo para compras con tarjeta de crédito.")
        descripcion = st.text_input("Descripción", value=detalle.descripcion, max_chars=120)
        notas = st.text_input("Notas", value=detalle.notas, max_chars=300)
        if st.form_submit_button("Guardar cambios", type="primary"):
            propuestos = {"fecha": fecha, "cuenta_id": cuenta, "cuenta_destino_id": destino, "categoria_id": categoria,
                          "descripcion": descripcion, "notas": notas}
            actuales = {"fecha": detalle.fecha, "cuenta_id": detalle.cuenta_id,
                        "cuenta_destino_id": detalle.cuenta_destino_id, "categoria_id": detalle.categoria_id,
                        "descripcion": detalle.descripcion, "notas": detalle.notas}
            cambios = {k: v for k, v in propuestos.items() if v is not None and v != actuales[k]}
            if monto is not None and round(monto, 2) != float(detalle.monto):
                cambios["monto"] = monto
            if msi is not None and int(msi) != original.msi:
                cambios["msi"] = int(msi)
            if not cambios:
                st.info("No cambiaste nada.")
            elif ejecutar(lambda lib: movimientos.editar(lib, detalle.id, **cambios), exito="Movimiento actualizado"):
                st.session_state.pop(tabla, None)  # el orden pudo cambiar: no dejar seleccionado otro renglón
                st.rerun()
