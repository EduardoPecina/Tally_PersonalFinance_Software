"""Bienes (motor/bienes.py): casa, auto, laptop… lo que valen, su depreciación, mejoras, avalúos y venta.

Es la pestaña «Bienes» de Contabilidad Técnica.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import bienes, cuentas
from motor.modelo import MetodoDepreciacion, TipoCuenta
from portal.componentes import formato, graficas
from portal.componentes.sesion import ejecutar, libro

ELEGIDO = "bien_elegido"


def mostrar() -> None:
    lib = libro()
    st.subheader("Bienes")
    st.caption("Tu casa, auto, laptop, muebles… lo que tienes y no es dinero. Comprarlo no es gasto (cambias dinero "
               "por una cosa); con el tiempo pierde valor (**depreciación**) o lo gana (**plusvalía**, con un "
               "avalúo). Todo se calcula solo: no llena tu Historial ni cuenta como gasto en tu Resumen.")
    with st.expander("➕ Agregar un bien", expanded=not lib.bienes()):
        _formulario_nuevo()
    st.caption("¿Ya lo habías registrado como gasto? Búscalo en **Historial**, ábrelo y usa «Convertir en un bien».")
    todos = lib.bienes()
    if not todos:
        return

    hoy = lib.hoy()
    valuaciones = {b.cuenta_id: bienes.valuar(lib, b.cuenta_id, hoy) for b in todos}
    st.dataframe(pd.DataFrame({
        "Bien": [lib.cuenta(b.cuenta_id).nombre for b in todos],
        "Tipo": [bienes.CLASES.get(b.clase, bienes.CLASES["otro"]).nombre for b in todos],
        "Costo (compra + mejoras)": [formato.dinero(valuaciones[b.cuenta_id].costo) if not b.fecha_baja else "—"
                                     for b in todos],
        "Depreciación": [formato.dinero(valuaciones[b.cuenta_id].depreciacion) for b in todos],
        "Plusvalía": [formato.dinero(valuaciones[b.cuenta_id].revaluacion) for b in todos],
        "Valor hoy": [formato.dinero(valuaciones[b.cuenta_id].valor) if not b.fecha_baja
                      else f"Vendido el {formato.fecha(b.fecha_baja)}" for b in todos],
    }), hide_index=True, width="stretch")
    activos = [b for b in todos if not b.fecha_baja]
    st.metric("Tus bienes valen hoy", formato.dinero(sum((valuaciones[b.cuenta_id].valor for b in activos),
                                                         Decimal(0))))

    nombres = {b.cuenta_id: lib.cuenta(b.cuenta_id).nombre for b in todos}
    if st.session_state.get(ELEGIDO) not in nombres:
        st.session_state[ELEGIDO] = todos[0].cuenta_id
    cuenta_id = st.selectbox("Ver y ajustar", list(nombres), format_func=nombres.get, key=ELEGIDO)
    _detalle(cuenta_id)


# ---------------------------------------------------------------- un bien


def _detalle(cuenta_id: str) -> None:
    lib = libro()
    bien = lib.bien(cuenta_id)
    cuenta = lib.cuenta(cuenta_id)
    hoy = lib.hoy()
    v = bienes.valuar(lib, cuenta_id, hoy)
    clase = bienes.CLASES.get(bien.clase, bienes.CLASES["otro"])
    st.markdown(f"#### {formato.md(cuenta.nombre)}")
    st.caption(f"{clase.nombre} · {bienes.METODOS[bien.metodo]}" + (f" · vendido el {formato.fecha(bien.fecha_baja)}"
                                                                  if bien.fecha_baja else ""))
    a, b, c, d = st.columns(4)
    a.metric("Costo", formato.dinero(v.costo if not bien.fecha_baja else _costo_antes_de_vender(cuenta_id)))
    b.metric("Depreciación acumulada", formato.dinero(v.depreciacion))
    c.metric("Plusvalía por avalúos", formato.dinero(v.revaluacion))
    d.metric("Valor hoy", formato.dinero(v.valor))
    _grafica(cuenta_id)
    activo = bien.fecha_baja is None and cuenta.activa

    if activo:
        configurar, mejora, avaluo, venta = st.tabs(["Depreciación", "Mejora", "Avalúo", "Vender"])
        with configurar:
            _configurar(cuenta_id)
        with mejora:
            _mejora(cuenta_id)
        with avaluo:
            _avaluo(cuenta_id)
        with venta:
            _venta(cuenta_id, v.valor)
    elif bien.fecha_baja:
        st.info("Este bien ya se vendió: su cuenta quedó en ceros y la diferencia contra su valor ese día está en "
                "«Ganancia o pérdida al vender bienes».")
        if st.button("Deshacer la venta", key=f"bien_deshacer_{cuenta_id}"):
            if ejecutar(lambda lib: bienes.deshacer_venta(lib, cuenta_id), exito="Venta deshecha"):
                st.rerun()


def _costo_antes_de_vender(cuenta_id: str) -> Decimal:
    lib = libro()
    return bienes.valuar(lib, cuenta_id, lib.bien(cuenta_id).fecha_baja - timedelta(days=1)).costo


def _grafica(cuenta_id: str) -> None:
    lib = libro()
    bien = lib.bien(cuenta_id)
    inicio = lib.cuenta(cuenta_id).fecha_creacion
    fin = min(bien.fecha_baja or lib.hoy(), lib.hoy())
    if fin <= inicio:
        return
    dias = (fin - inicio).days
    paso = max(1, dias // 120)
    fechas = [inicio + timedelta(days=i) for i in range(0, dias, paso)] + [fin]
    puntos = [(f, bienes.valuar(lib, cuenta_id, f).valor) for f in fechas]
    graficas.linea(puntos, titulo_valor="Valor")


def _configurar(cuenta_id: str) -> None:
    lib = libro()
    bien = lib.bien(cuenta_id)
    clase = bienes.CLASES.get(bien.clase, bienes.CLASES["otro"])
    if clase.ayuda:
        st.caption(clase.ayuda)
    with st.form(f"bien_config_{cuenta_id}", border=False):
        metodos = list(bienes.METODOS)
        metodo = st.radio("Cómo pierde valor", metodos, format_func=bienes.METODOS.get,
                          index=metodos.index(bien.metodo))
        izquierda, centro, derecha = st.columns(3)
        vida = izquierda.number_input("Vida útil (años) · línea recta", min_value=0.0, max_value=100.0,
                                      value=float(bien.vida_anios), step=1.0,
                                      help="Cuántos años te va a servir. Laptop 4, celular 3, muebles 10…")
        tasa = centro.number_input("% que pierde al año · decreciente", min_value=0.0, max_value=99.0,
                                   value=float(bien.tasa_anual), step=1.0,
                                   help="Un auto pierde cerca de 15 % de lo que vale cada año.")
        rescate = derecha.number_input("Valor de rescate (% del costo)", min_value=0.0, max_value=99.0,
                                       value=float(bien.rescate), step=1.0,
                                       help="Lo que vale cuando ya está viejo; nunca baja de ahí.")
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: bienes.configurar(lib, cuenta_id, metodo=metodo, vida_anios=Decimal(str(vida)),
                                                      tasa_anual=Decimal(str(tasa)), rescate=Decimal(str(rescate))),
                        exito="Listo: se recalculó su depreciación"):
                st.rerun()
    st.caption("Son valores sugeridos para una persona, no tasas fiscales. Cámbialos cuando quieras: todo se "
               "recalcula, no hay movimientos que corregir.")


def _cuentas_de_pago() -> dict[str, str]:
    lib = libro()
    return {c.id: c.nombre for c in cuentas.listar(lib) if c.tipo is not TipoCuenta.BIEN}


def _mejora(cuenta_id: str) -> None:
    st.caption("Remodelación, ampliación, motor nuevo… lo que **sube el valor** del bien. Se registra como "
               "transferencia de tu cuenta al bien: no es gasto. (Las reparaciones y el mantenimiento sí son gasto).")
    pago = _cuentas_de_pago()
    lib = libro()
    with st.form(f"bien_mejora_{cuenta_id}", clear_on_submit=True, border=False):
        izquierda, derecha = st.columns(2)
        monto = izquierda.number_input("Cuánto costó", min_value=0.0, value=None, step=100.0, format="%.2f")
        fecha = derecha.date_input("Fecha", value=lib.hoy(), max_value=lib.hoy(), format="DD/MM/YYYY")
        origen = izquierda.selectbox("Con qué cuenta la pagaste", list(pago), format_func=pago.get)
        descripcion = derecha.text_input("Descripción (opcional)", max_chars=80)
        if st.form_submit_button("Guardar mejora", type="primary"):
            if not monto or origen is None:
                st.error("Escribe cuánto costó y con qué cuenta la pagaste.")
                return
            if ejecutar(lambda lib: bienes.registrar_mejora(lib, cuenta_id, fecha, Decimal(str(monto)), origen,
                                                            descripcion), exito="Mejora guardada"):
                st.rerun()


def _avaluo(cuenta_id: str) -> None:
    lib = libro()
    bien = lib.bien(cuenta_id)
    st.caption("¿Cuánto vale hoy según un avalúo, una agencia o el mercado? TALLY ajusta su valor a esa cifra: la "
               "diferencia es **plusvalía** (si subió) o minusvalía (si bajó). Desde ahí sigue depreciándose lo que "
               "le queda de vida.")
    with st.form(f"bien_avaluo_{cuenta_id}", clear_on_submit=True, border=False):
        izquierda, derecha = st.columns(2)
        valor = izquierda.number_input("Valor según el avalúo", min_value=0.0, value=None, step=1000.0,
                                       format="%.2f")
        fecha = derecha.date_input("Fecha del avalúo", value=lib.hoy(), max_value=lib.hoy(), format="DD/MM/YYYY")
        if st.form_submit_button("Guardar avalúo", type="primary"):
            if valor is None:
                st.error("Escribe el valor del avalúo.")
                return
            if ejecutar(lambda lib: bienes.registrar_avaluo(lib, cuenta_id, fecha, Decimal(str(valor))),
                        exito="Avalúo guardado"):
                st.rerun()
    if bien.avaluos:
        opciones = {a.fecha: f"{formato.fecha(a.fecha)} · {formato.dinero(Decimal(a.valor) / 100)}"
                    for a in reversed(bien.avaluos)}
        st.markdown("**Avalúos registrados**")
        for texto in opciones.values():
            st.markdown(f"- {texto}")
        quitar = st.selectbox("Borrar un avalúo", list(opciones), index=None, format_func=opciones.get,
                              placeholder="Elige uno para borrarlo", key=f"bien_quitar_avaluo_{cuenta_id}")
        if quitar and st.button("Borrar avalúo", key=f"bien_quitar_avaluo_boton_{cuenta_id}"):
            if ejecutar(lambda lib: bienes.quitar_avaluo(lib, cuenta_id, quitar), exito="Avalúo borrado"):
                st.rerun()


def _venta(cuenta_id: str, valor_hoy: Decimal) -> None:
    lib = libro()
    st.caption(f"Hoy vale {formato.dinero_md(valor_hoy)} en TALLY. Si lo vendes en más, es ganancia; en menos, "
               "pérdida. Si lo regalaste, lo tiraste o se perdió, pon precio 0. La cuenta del bien queda en ceros.")
    destino = _cuentas_de_pago()
    with st.form(f"bien_venta_{cuenta_id}", border=False):
        izquierda, derecha = st.columns(2)
        precio = izquierda.number_input("Precio de venta", min_value=0.0, value=None, step=1000.0, format="%.2f")
        fecha = derecha.date_input("Fecha", value=lib.hoy(), max_value=lib.hoy(), format="DD/MM/YYYY")
        cuenta = izquierda.selectbox("A qué cuenta llegó el dinero", list(destino), format_func=destino.get)
        confirmar = derecha.checkbox("Sí, lo vendí (o ya no lo tengo)")
        if st.form_submit_button("Registrar venta", type="primary"):
            if precio is None or not confirmar:
                st.error("Escribe el precio (0 si no recibiste dinero) y confirma.")
                return
            if ejecutar(lambda lib: bienes.vender(lib, cuenta_id, fecha, Decimal(str(precio)), cuenta),
                        exito="Venta registrada"):
                st.rerun()


# ------------------------------------------------------------------- nuevo


def _formulario_nuevo() -> None:
    lib = libro()
    clases = list(bienes.CLASES)
    clase = st.selectbox("Qué es", clases, format_func=lambda c: bienes.CLASES[c].nombre, key="bien_nuevo_clase")
    sugerido = bienes.CLASES[clase]
    detalle = (f"{sugerido.vida_anios.normalize():f} años de vida útil"
               if sugerido.metodo is MetodoDepreciacion.LINEA_RECTA else
               f"pierde {sugerido.tasa_anual.normalize():f} % de su valor al año"
               if sugerido.metodo is MetodoDepreciacion.DECRECIENTE else "no se deprecia")
    st.caption(f"Sugerido: {detalle}" + (f", rescate {sugerido.rescate.normalize():f} %" if sugerido.rescate else "")
               + ". Lo puedes cambiar después.")
    como = st.radio("¿Cómo lo registras?", ["Ya lo tenía", "Lo compré"], horizontal=True, key="bien_nuevo_como",
                    help="Ya lo tenía: escribe lo que vale hoy (entra a tu patrimonio). Lo compré: lo pagaste con "
                         "una de tus cuentas (transferencia, no gasto).")
    pago = _cuentas_de_pago()
    with st.form("bien_nuevo", clear_on_submit=True, border=False):
        izquierda, derecha = st.columns(2)
        nombre = izquierda.text_input("Nombre", placeholder="Ej. Auto Versa 2022, MacBook Air, Mi casa",
                                      max_chars=60)
        valor = derecha.number_input("Lo que vale hoy" if como == "Ya lo tenía" else "Precio de compra",
                                     min_value=0.0, value=None, step=1000.0, format="%.2f")
        fecha = izquierda.date_input("Fecha" if como == "Ya lo tenía" else "Fecha de compra", value=lib.hoy(),
                                     max_value=lib.hoy(), format="DD/MM/YYYY")
        origen = (derecha.selectbox("Con qué cuenta lo pagaste", list(pago), format_func=pago.get)
                  if como == "Lo compré" else None)
        if st.form_submit_button("Agregar bien", type="primary"):
            if not valor or not nombre.strip():
                st.error("Escribe el nombre y el valor.")
                return
            if ejecutar(lambda lib: bienes.crear(lib, nombre, clase, fecha, Decimal(str(valor)), cuenta_pago=origen),
                        exito=f"«{nombre.strip()}» agregado"):
                st.session_state.pop(ELEGIDO, None)
                st.rerun()
