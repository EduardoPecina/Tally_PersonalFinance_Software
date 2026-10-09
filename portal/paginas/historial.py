"""Historial: buscar, filtrar, ordenar, ver, editar y eliminar movimientos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import bienes, categorias, comprobantes, consultas, cuentas, efectivo, metas, movimientos
from motor.consultas import ETIQUETA_TIPO_OPERACION, ORDENES
from motor.modelo import TipoCuenta, TipoOperacion
from portal.componentes import comprobantes as panel_comprobantes
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
            "Desde", key=k, format="DD/MM/YYYY", **formato.limites_de_fecha(lib)))
    with col2:
        hasta = estado.control(FILTROS, "hasta", None, lambda k: st.date_input(
            "Hasta", key=k, format="DD/MM/YYYY", **formato.limites_de_fecha(lib)))
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

    filas = filas[:formato.cuantos_mostrar(len(filas), "historial_todos")]
    adjuntos = comprobantes.por_movimiento(libro())
    tabla = pd.DataFrame(
        {
            "Fecha": [f.fecha for f in filas],
            "Tipo": [f.tipo_etiqueta for f in filas],
            "Descripción": [f.descripcion for f in filas],
            "Cuenta": [f.cuenta + (f" → {f.cuenta_destino}" if f.cuenta_destino else "") for f in filas],
            "Categoría": [f.rubro for f in filas],
            "Subcategoría": [f.categoria for f in filas],
            "Importe": [formato.dinero_con_signo(f.monto, f.sentido) for f in filas],
            "📎": [str(adjuntos.get(f.id, "")) for f in filas],
        }
    )
    if not adjuntos:
        tabla = tabla.drop(columns="📎")
    evento = st.dataframe(
        formato.pintar(tabla), hide_index=True, on_select="rerun", selection_mode="single-row", key=TABLA,
        column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                       "📎": st.column_config.TextColumn(width="small", help="Comprobantes adjuntos")},
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
    _retiro_de_efectivo(op, tabla)

    es_gasto = detalle.tipo is TipoOperacion.GASTO
    adjuntos = len(lib.comprobantes(operacion_id))
    entre_cuentas = detalle.tipo in movimientos.CON_CUENTA_Y_CATEGORIA and not op.msi and not op.liquida
    extras = (["↔ Entre mis cuentas"] if entre_cuentas else []) + (["Convertir en un bien"] if es_gasto else [])
    pestanas = st.tabs(["Editar", f"📎 Comprobantes ({adjuntos})" if adjuntos else "📎 Comprobantes", "Repetir",
                        "Eliminar", *extras])
    editar, adjuntar, repetir, eliminar = pestanas[:4]
    for pestana, nombre in zip(pestanas[4:], extras, strict=True):
        with pestana:
            if nombre == "Convertir en un bien":
                _convertir_en_bien(operacion_id, tabla)
            else:
                _a_transferencia(op, tabla)
    with editar:
        _editar(detalle, tabla)
    with adjuntar:
        panel_comprobantes.mostrar(operacion_id)
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
        if adjuntos:
            st.caption(f"📎 Tiene {adjuntos} comprobante(s): también se borran (tus respaldos anteriores los "
                       "conservan).")
        for meta in metas.de_operacion(lib, operacion_id):
            st.caption(f"🏆 Es parte de tu meta **{formato.md(meta.nombre)}**: al eliminarlo, también se quita de "
                       "la meta.")
        confirmar = st.checkbox("Sí, quiero eliminar este movimiento", key=f"confirmar_{operacion_id}")
        if st.button("Eliminar movimiento", type="primary", disabled=not confirmar, key=f"eliminar_{operacion_id}"):
            if ejecutar(lambda lib: movimientos.eliminar(lib, operacion_id), exito="Movimiento eliminado"):
                st.session_state.pop(tabla, None)
                st.rerun()


def _a_transferencia(op, tabla: str) -> None:
    """Un gasto o ingreso que en realidad fue mover dinero entre tus cuentas: pásalo a transferencia."""
    lib = libro()
    (partida,) = op.partidas_de_cuenta()
    sale = partida.importe < 0
    st.caption(("¿En realidad **mandaste este dinero a otra de tus cuentas** (al ahorro, a tu efectivo, a pagar tu "
                "tarjeta)? Pásalo a transferencia: deja de contar como gasto y el dinero aparece en la otra cuenta."
                if sale else
                "¿Este dinero en realidad **vino de otra de tus cuentas** (del ahorro, de tu inversión…)? Pásalo a "
                "transferencia: deja de contar como ingreso y sale de la otra cuenta.")
               + " Fecha, importe, descripción y comprobantes se quedan igual.")
    otras = [c for c in cuentas.listar(lib) if c.id != partida.cuenta_id]
    if not otras:
        st.info("Primero agrega tu otra cuenta en **Cuentas**.")
        return
    nombres = {c.id: c.nombre for c in otras}
    otra = st.selectbox("¿A qué cuenta fue?" if sale else "¿De qué cuenta vino?", list(nombres), index=None,
                        format_func=nombres.get, placeholder="Elige la cuenta", key=f"a_transferencia_{op.id}")
    if otra is not None and sale and lib.cuenta(otra).tipo is TipoCuenta.CREDITO:
        st.caption("💳 Quedará como **pago de tarjeta**.")
    if st.button("Pasar a transferencia entre mis cuentas", type="primary", disabled=otra is None,
                 key=f"a_transferencia_boton_{op.id}", icon=":material/sync_alt:"):
        if ejecutar(lambda lib_: movimientos.a_transferencia(lib_, op.id, otra),
                    exito=f"Listo: ahora es una transferencia {'a' if sale else 'desde'} {nombres[otra]}"):
            st.session_state.pop(tabla, None)
            st.rerun()


def _retiro_de_efectivo(op, tabla: str) -> None:
    """Un retiro de efectivo guardado como gasto: con cuenta de efectivo, ese dinero pasó a tu cartera."""
    destino = efectivo.convertible(libro(), op)
    if destino is None:
        return
    izquierda, derecha = st.columns([3, 1], vertical_alignment="center")
    izquierda.info(f"💵 Esto fue **sacar efectivo**: no es un gasto. Pásalo a tu cuenta **{formato.md(destino.nombre)}** "
                   "y su saldo subirá (el gasto será lo que pagues con ese efectivo).", icon="💵")
    if derecha.button(f"Pasarlo a {destino.nombre}", key=f"a_efectivo_{op.id}", type="primary"):
        if ejecutar(lambda lib: efectivo.convertir(lib, op.id),
                    exito=f"Listo: el retiro pasó a {destino.nombre} y ya no cuenta como gasto"):
            st.session_state.pop(tabla, None)
            st.rerun()


def _convertir_en_bien(operacion_id: str, tabla: str) -> None:
    """Un gasto que en realidad fue comprar (o mejorar) un bien: laptop, auto, remodelación…"""
    lib = libro()
    st.caption("¿Fue la compra de algo que conservas y tiene valor (laptop, auto, muebles) o una mejora a tu casa? "
               "Conviértelo en un **bien**: deja de contar como gasto y su valor se va depreciando con el tiempo. "
               "Ves y ajustas tus bienes en **Contabilidad Técnica → Bienes**.")
    op = lib.operacion(operacion_id)
    existentes = {b.cuenta_id: lib.cuenta(b.cuenta_id).nombre for b in lib.bienes()
                  if b.fecha_baja is None and lib.cuenta(b.cuenta_id).activa}
    NUEVO = "__nuevo__"
    destino = st.selectbox("¿A qué bien?", [NUEVO, *existentes], key=f"bien_destino_{operacion_id}",
                           format_func=lambda c: "Un bien nuevo" if c == NUEVO else f"{existentes[c]} (como mejora)")
    if destino == NUEVO:
        izquierda, derecha = st.columns(2)
        nombre = izquierda.text_input("Nombre del bien", value=op.descripcion[:60], max_chars=60,
                                      key=f"bien_nombre_{operacion_id}")
        clase = derecha.selectbox("Tipo de bien", list(bienes.CLASES), format_func=lambda c: bienes.CLASES[c].nombre,
                                  key=f"bien_clase_{operacion_id}")
    if st.button("Convertir en un bien", type="primary", key=f"convertir_bien_{operacion_id}"):
        def convertir(lib):
            if destino == NUEVO:
                return bienes.crear_desde_gasto(lib, operacion_id, nombre, clase)
            return bienes.convertir_gasto(lib, operacion_id, destino)

        if ejecutar(convertir, exito="Listo: ya es un bien y dejó de contar como gasto"):
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
