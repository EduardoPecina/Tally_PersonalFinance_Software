"""Registrar un movimiento, rápido."""

from __future__ import annotations

import streamlit as st

from motor import categorias, consultas, cuentas, movimientos, tarjetas
from motor.consultas import ETIQUETA_TIPO_OPERACION
from motor.modelo import TipoCuenta, TipoOperacion
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia
from portal.componentes import formato
from portal.componentes.sesion import ejecutar, libro
from portal.navegacion import enlace

TIPOS = [TipoOperacion.GASTO, TipoOperacion.INGRESO, TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA,
         TipoOperacion.REEMBOLSO]
AYUDA = {
    TipoOperacion.GASTO: "Dinero que gastaste, con cualquier cuenta o tarjeta (también la de crédito).",
    TipoOperacion.INGRESO: "Dinero que recibiste: nómina, ventas, freelance…",
    TipoOperacion.TRANSFERENCIA: "Mover dinero entre tus cuentas (p. ej. al ahorro). No es gasto.",
    TipoOperacion.PAGO_TARJETA: "Pagar tu tarjeta de crédito. No es otro gasto: el gasto se contó al comprar.",
    TipoOperacion.REEMBOLSO: "Te devolvieron dinero de una compra: resta del gasto de esa subcategoría.",
}


def _indice(opciones: list, recordado) -> int | None:
    return opciones.index(recordado) if recordado in opciones else (0 if opciones else None)


def mostrar() -> None:
    st.title("Registrar movimiento")
    lib = libro()
    activas = cuentas.listar(lib)
    if not activas:
        st.info("Primero agrega una cuenta.")
        enlace("cuentas", "Ir a Cuentas", "🏦")
        return

    tipo = st.segmented_control(
        "¿Qué quieres registrar?", TIPOS, default=TipoOperacion.GASTO, required=True,
        format_func=lambda t: ETIQUETA_TIPO_OPERACION[t], key="registrar_tipo",
    )
    st.caption(AYUDA[tipo])

    ids = [c.id for c in activas]
    nombre = {c.id: c.nombre for c in activas}
    recordadas = st.session_state.setdefault("_registrar_ultimas", {})

    with st.form(f"registrar_{tipo.value}", clear_on_submit=True):
        izquierda, derecha = st.columns(2)
        destino = categoria_id = None
        if tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
            if tipo is TipoOperacion.PAGO_TARJETA:
                tarjetas_ids = [c.id for c in activas if c.tipo is TipoCuenta.CREDITO]
                if not tarjetas_ids:
                    st.warning("No tienes tarjetas de crédito registradas.")
                destino = izquierda.selectbox("Tarjeta que pagas", tarjetas_ids, format_func=nombre.get,
                                              index=_indice(tarjetas_ids, recordadas.get("tarjeta")))
                origenes = [i for i in ids if i not in tarjetas_ids] or ids
            else:
                destino = izquierda.selectbox("Hacia la cuenta", ids, format_func=nombre.get,
                                              index=_indice(ids, recordadas.get("destino")))
                origenes = ids
            origen = derecha.selectbox("Desde la cuenta", origenes, format_func=nombre.get,
                                       index=_indice(origenes, recordadas.get("origen")))
        else:
            opciones = categorias.para_tipo(lib, tipo)
            cat_ids = [c.id for c in opciones]
            cat_nombre = {c.id: categorias.etiqueta(lib, c.id) for c in opciones}
            categoria_id = izquierda.selectbox("Subcategoría", cat_ids, format_func=cat_nombre.get, index=None,
                                               placeholder="Escribe para buscar: gym, súper, uber…")
            origen = derecha.selectbox("Cuenta" if tipo is not TipoOperacion.GASTO else "Pagado con", ids,
                                       format_func=nombre.get, index=_indice(ids, recordadas.get("cuenta")))
        monto = izquierda.number_input("Importe", min_value=0.0, value=None, step=1.0, format="%.2f",
                                       placeholder="0.00")
        fecha = derecha.date_input("Fecha", value=lib.hoy(), format="DD/MM/YYYY")
        descripcion = st.text_input("Descripción", placeholder="Ej. Pizza, Uber, Nómina…", max_chars=120)
        notas = st.text_input("Notas (opcional)", max_chars=300)
        guardar = st.form_submit_button("Guardar", type="primary")

    if tipo is TipoOperacion.PAGO_TARJETA and destino:
        _ayuda_pago(destino)

    if guardar:
        if not monto:
            st.error("Escribe el importe.")
        else:
            if tipo is TipoOperacion.TRANSFERENCIA:
                recordadas.update(origen=origen, destino=destino)

                def accion(lib):
                    return registrar_transferencia(lib, fecha, origen, destino, monto, descripcion, notas)
            elif tipo is TipoOperacion.PAGO_TARJETA:
                recordadas.update(origen=origen, tarjeta=destino)

                def accion(lib):
                    return registrar_pago_tarjeta(lib, fecha, origen, destino, monto, descripcion, notas)
            else:
                recordadas.update(cuenta=origen)
                registrar = {
                    TipoOperacion.GASTO: movimientos.registrar_gasto,
                    TipoOperacion.INGRESO: movimientos.registrar_ingreso,
                    TipoOperacion.REEMBOLSO: movimientos.registrar_reembolso,
                }[tipo]

                def accion(lib):
                    return registrar(lib, fecha, origen, categoria_id, monto, descripcion, notas)
            etiqueta = ETIQUETA_TIPO_OPERACION[tipo]
            if ejecutar(accion, exito=f"{etiqueta} de {formato.dinero(monto)} guardado"):
                st.rerun()

    _ultimos()


def _ayuda_pago(tarjeta_id: str) -> None:
    lib = libro()
    deuda = tarjetas.deuda(lib, tarjeta_id)
    texto = f"Deuda actual de la tarjeta: **{formato.dinero_md(deuda)}**"
    por_pagar = tarjetas.ciclo_por_pagar(lib, tarjeta_id)
    if por_pagar is not None and por_pagar.por_liquidar:
        texto += f" · Por liquidar del corte del {formato.fecha(por_pagar.fin)}: **{formato.dinero_md(por_pagar.por_liquidar)}**"
    st.caption(texto)


def _ultimos() -> None:
    filas = consultas.buscar(libro())[:5]
    if not filas:
        return
    st.subheader("Últimos movimientos")
    for f in filas:
        destino = f" → {f.cuenta_destino}" if f.cuenta_destino else ""
        detalle = " · ".join(x for x in (f.categoria, f.cuenta + destino) if x)
        st.markdown(
            f"{formato.fecha(f.fecha)} · **{formato.md(f.descripcion or f.tipo_etiqueta)}** · "
            f"{formato.dinero_con_signo_md(f.monto, f.sentido)}  \n:gray[{f.tipo_etiqueta} · {formato.md(detalle)}]"
        )
    enlace("historial", "Ver todo el historial", "📋")
