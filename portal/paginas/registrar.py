"""Registrar un movimiento, rápido. El formulario también se abre desde cada cuenta (Cuentas → Agregar)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import categorias, consultas, cuentas, ingresos, movimientos, recurrentes, tarjetas, temporales
from motor.consultas import ETIQUETA_TIPO_OPERACION
from motor.dinero import a_pesos
from motor.modelo import Recurrente, TipoCuenta, TipoOperacion
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
CON_CATEGORIA = (TipoOperacion.GASTO, TipoOperacion.INGRESO, TipoOperacion.REEMBOLSO)


def _indice(opciones: list, recordado) -> int | None:
    return opciones.index(recordado) if recordado in opciones else (0 if opciones else None)


def _reparto(clave: str, etiquetas: dict[str, str]) -> list[tuple[str, float]]:
    """Tabla para repartir un movimiento entre varias subcategorías (súper: despensa + limpieza…)."""
    por_etiqueta = {v: k for k, v in etiquetas.items()}
    tabla = st.data_editor(
        pd.DataFrame({"Subcategoría": pd.Series([None, None], dtype="object"),
                      "Importe": pd.Series([None, None], dtype="float")}),
        num_rows="dynamic", hide_index=True, width="stretch", key=f"{clave}_reparto",
        column_config={
            "Subcategoría": st.column_config.SelectboxColumn(options=list(por_etiqueta), required=True),
            "Importe": st.column_config.NumberColumn(min_value=0.01, format="$%.2f", required=True),
        },
    )
    return [(por_etiqueta[f["Subcategoría"]], f["Importe"]) for f in tabla.to_dict("records")
            if f["Subcategoría"] in por_etiqueta and f["Importe"]]


def formulario(clave: str = "registrar", cuenta_fija: str | None = None) -> bool:
    """El formulario completo. ``cuenta_fija`` la deja elegida (al abrirlo desde una cuenta).
    Devuelve True si se guardó algo."""
    lib = libro()
    activas = cuentas.listar(lib)
    if not activas:
        st.info("Primero agrega una cuenta.")
        enlace("cuentas", "Ir a Cuentas", "🏦")
        return False

    tipo = st.segmented_control(
        "¿Qué quieres registrar?", TIPOS, default=TipoOperacion.GASTO, required=True,
        format_func=lambda t: ETIQUETA_TIPO_OPERACION[t], key=f"{clave}_tipo",
    )
    st.caption(AYUDA[tipo])

    ids = [c.id for c in activas]
    nombre = {c.id: c.nombre for c in activas}
    tdc_ids = [c.id for c in activas if c.tipo is TipoCuenta.CREDITO]
    recordadas = dict(st.session_state.setdefault("_registrar_ultimas", {}))
    if cuenta_fija:
        recordadas.update(cuenta=cuenta_fija, origen=cuenta_fija)
        if cuenta_fija in tdc_ids:
            recordadas["tarjeta"] = cuenta_fija

    repartir = temporal = False
    etiquetas: dict[str, str] = {}
    if tipo is TipoOperacion.GASTO:
        temporal = st.toggle("Cargo temporal: me lo van a devolver", key=f"{clave}_temporal",
                             help="Lo que te cobran para verificar tu tarjeta (Amazon, Uber, un hotel…) y te "
                                  "regresan después. No cuenta como gasto: queda en «Te deben» hasta que vuelva.")
    if temporal:
        ids_temporal = [i for i in ids if i != getattr(temporales.cuenta(lib), "id", None)]
        st.caption("Se guarda en la cuenta **POR RECUPERAR** (se crea sola). Cuando te lo devuelvan, márcalo en "
                   "el Resumen con «Ya me lo devolvieron».")
    elif tipo in CON_CATEGORIA:
        etiquetas = {c.id: categorias.etiqueta(lib, c.id) for c in categorias.para_tipo(lib, tipo)}
        repartir = st.toggle("Repartir entre varias subcategorías", key=f"{clave}_repartir",
                             help="Por ejemplo, una compra del súper que fue despensa y artículos de limpieza.")
    fijo, fecha_fija = None, None
    if tipo is TipoOperacion.INGRESO and not repartir:
        fijo, fecha_fija = _ingreso_fijo(clave, cuenta_fija)
    sufijo = f"_{fijo.id}_{fecha_fija.isoformat()}" if fijo else ""

    with st.form(f"{clave}_{tipo.value}{sufijo}", clear_on_submit=True):
        izquierda, derecha = st.columns(2)
        destino = categoria_id = None
        reparto: list[tuple[str, float]] = []
        msi = 0
        if tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
            if tipo is TipoOperacion.PAGO_TARJETA:
                if not tdc_ids:
                    st.warning("No tienes tarjetas de crédito registradas.")
                destino = izquierda.selectbox("Tarjeta que pagas", tdc_ids, format_func=nombre.get,
                                              index=_indice(tdc_ids, recordadas.get("tarjeta")))
                origenes = [i for i in ids if i not in tdc_ids] or ids
                recordado_origen = recordadas.get("origen") if recordadas.get("origen") not in tdc_ids else None
            else:
                destino = izquierda.selectbox("Hacia la cuenta", ids, format_func=nombre.get,
                                              index=_indice(ids, recordadas.get("destino")))
                origenes, recordado_origen = ids, recordadas.get("origen")
            origen = derecha.selectbox("Desde la cuenta", origenes, format_func=nombre.get,
                                       index=_indice(origenes, recordado_origen))
        elif temporal:
            origen = izquierda.selectbox("¿Dónde te lo cobraron?", ids_temporal, format_func=nombre.get,
                                         index=_indice(ids_temporal, recordadas.get("cuenta")))
        else:
            if repartir:
                with izquierda:
                    reparto = _reparto(f"{clave}_{tipo.value}", etiquetas)
            else:
                cat_ids = list(etiquetas)
                categoria_id = izquierda.selectbox(
                    "Subcategoría", cat_ids, format_func=etiquetas.get,
                    index=cat_ids.index(fijo.categoria_id) if fijo and fijo.categoria_id in cat_ids else None,
                    placeholder="Escribe para buscar: gym, súper, uber…")
            cuenta_sugerida = fijo.cuenta_id if fijo and not cuenta_fija else recordadas.get("cuenta")
            origen = derecha.selectbox("Cuenta" if tipo is not TipoOperacion.GASTO else "Pagado con", ids,
                                       format_func=nombre.get, index=_indice(ids, cuenta_sugerida))
        monto = None
        if not repartir:
            sugerido = float(a_pesos(recurrentes.monto_en(fijo, fecha_fija))) if fijo else None
            monto = izquierda.number_input("Importe", min_value=0.0, value=sugerido, step=1.0, format="%.2f",
                                           placeholder="0.00")
        fecha = fecha_fija or derecha.date_input("Fecha", value=lib.hoy(), format="DD/MM/YYYY")
        if tipo is TipoOperacion.GASTO and tdc_ids and not temporal:
            msi = derecha.number_input("Meses sin intereses", min_value=0, max_value=60, value=0, step=1,
                                       help="Solo para compras con tarjeta de crédito. 0 = de contado. El gasto "
                                            "cuenta completo hoy; tu tarjeta solo te pedirá una mensualidad por corte.")
        descripcion = st.text_input("Descripción", value=fijo.nombre if fijo else "", max_chars=120, placeholder="Ej. Verificación de Amazon"
                                    if temporal else "Ej. Pizza, Uber, Nómina…")
        notas = st.text_input("Notas (opcional)", max_chars=300)
        guardar = st.form_submit_button("Guardar", type="primary")

    if tipo is TipoOperacion.PAGO_TARJETA and destino:
        _ayuda_pago(destino)
    if not guardar:
        return False
    if repartir and not reparto:
        st.error("Agrega al menos una subcategoría con su importe.")
        return False
    if not repartir and not monto:
        st.error("Escribe el importe.")
        return False

    memoria = st.session_state["_registrar_ultimas"]
    if temporal:
        memoria.update(cuenta=origen)
        return ejecutar(lambda lib: temporales.registrar(lib, fecha, origen, monto, descripcion, notas),
                        exito=f"Cargo temporal de {formato.dinero(monto)} guardado: no cuenta como gasto")
    if tipo is TipoOperacion.TRANSFERENCIA:
        memoria.update(origen=origen, destino=destino)

        def accion(lib):
            return registrar_transferencia(lib, fecha, origen, destino, monto, descripcion, notas)
    elif tipo is TipoOperacion.PAGO_TARJETA:
        memoria.update(origen=origen, tarjeta=destino)

        def accion(lib):
            return registrar_pago_tarjeta(lib, fecha, origen, destino, monto, descripcion, notas)
    else:
        memoria.update(cuenta=origen)
        registrar = {
            TipoOperacion.GASTO: movimientos.registrar_gasto,
            TipoOperacion.INGRESO: movimientos.registrar_ingreso,
            TipoOperacion.REEMBOLSO: movimientos.registrar_reembolso,
        }[tipo]
        extra = {"msi": int(msi)} if tipo is TipoOperacion.GASTO else {}

        def accion(lib):
            if repartir:
                return registrar(lib, fecha, origen, descripcion=descripcion, notas=notas, reparto=reparto, **extra)
            return registrar(lib, fecha, origen, categoria_id, monto, descripcion, notas, **extra)
    total = monto if not repartir else sum(m for _, m in reparto)
    texto = f"{ETIQUETA_TIPO_OPERACION[tipo]} de {formato.dinero(total)} guardado"
    if msi:
        texto += f" a {int(msi)} meses sin intereses"
    return ejecutar(accion, exito=texto)


def _ingreso_fijo(clave: str, cuenta_fija: str | None) -> tuple[Recurrente | None, object]:
    """¿Es uno de tus ingresos fijos (Ingresos)? Si sí, la fecha va fuera del formulario para llenar el importe de
    esa quincena (la 1.ª y la 2.ª pueden ser distintas)."""
    lib = libro()
    lista = [r for r in ingresos.fijos(lib) if r.activa and lib.cuenta(r.cuenta_id).activa
             and (cuenta_fija is None or r.cuenta_id == cuenta_fija)]
    if not lista:
        return None, None
    por_id = {r.id: r for r in lista}
    principal = ingresos.principal(lib)
    opciones = [None, *por_id]
    a, b = st.columns(2)
    elegido = a.selectbox(
        "¿Es uno de tus ingresos fijos?", opciones, key=f"{clave}_fijo",
        index=opciones.index(principal.id) if principal and principal.id in por_id else 0,
        format_func=lambda i: "No, es otro ingreso" if i is None else
        f"{por_id[i].nombre} ({recurrentes.FRECUENCIAS[por_id[i].frecuencia].split(' (')[0].lower()})",
        help="TALLY llena el importe que configuraste en Ingresos según la fecha. Puedes corregirlo antes de guardar.")
    if elegido is None:
        return None, None
    r = por_id[elegido]
    fecha = b.date_input("Fecha", value=lib.hoy(), format="DD/MM/YYYY", key=f"{clave}_fecha_fijo")
    cual = f"Es tu **{recurrentes.quincena(r, fecha)}.ª quincena**: te" if r.frecuencia == "quincenal" else "Te"
    st.caption(f"💡 {cual} llegan {formato.dinero_md(a_pesos(recurrentes.monto_en(r, fecha)))} según lo que "
               "configuraste en Ingresos. Si esta vez fue distinto (unos centavos, un bono…), corrígelo abajo.")
    return r, fecha


def mostrar() -> None:
    st.title("Registrar movimiento")
    if formulario():
        st.rerun()
    _ultimos()


def _ayuda_pago(tarjeta_id: str) -> None:
    lib = libro()
    deuda = tarjetas.deuda(lib, tarjeta_id)
    texto = f"Deuda actual de la tarjeta: **{formato.dinero_md(deuda)}**"
    por_pagar = tarjetas.ciclo_por_pagar(lib, tarjeta_id)
    if por_pagar is not None and por_pagar.por_liquidar:
        texto += (f" · Para no generar intereses (corte del {formato.fecha(por_pagar.fin)}): "
                  f"**{formato.dinero_md(por_pagar.por_liquidar)}**")
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
