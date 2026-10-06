"""Títulos e inversiones a plazo de una cuenta de inversión (motor/portafolio.py), con la consulta opcional del
valor aproximado actual (motor/cotizaciones.py). Se muestra dentro del estado de cuenta."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import cotizaciones, perfil, portafolio
from motor.dinero import a_pesos
from motor.modelo import Cuenta, TipoOperacionValor
from portal.componentes import formato
from portal.componentes.sesion import ejecutar, libro

TRANSPARENCIA = (f"⚡ Precios obtenidos desde **{cotizaciones.PROVEEDOR}**. La consulta solo envía los **símbolos "
                 "bursátiles** (por ejemplo IVV o IVVPESO.MX) para obtener cotizaciones públicas: no se envían "
                 "movimientos, saldos, cantidades ni datos personales. Todo el cálculo se hace en tu PC. Los precios "
                 "pueden tener retraso: son aproximados.")
VIGENCIA = timedelta(hours=1)


def mostrar(cuenta: Cuenta) -> None:
    lib = libro()
    st.subheader("Tus títulos e inversiones a plazo")
    st.caption("Acciones, ETFs, cripto, CETES, pagarés… lo que compraste **dentro** de esta cuenta. Registrarlos no "
               "cambia el saldo (el dinero ya estaba en la cuenta); sirve para saber cuánto vale hoy lo que tienes "
               "y, si quieres, pasar la ganancia a tu contabilidad.")
    if cuenta.activa:
        izquierda, derecha = st.columns(2)
        with izquierda, st.expander("➕ Compra o venta de títulos"):
            _formulario_valor(cuenta)
        with derecha, st.expander("➕ CETES, pagaré o certificado"):
            _formulario_plazo(cuenta)

    abiertas = [p for p in portafolio.posiciones(lib, cuenta.id) if p.titulos]
    plazos = lib.plazos(cuenta.id)
    if not lib.valores(cuenta.id) and not plazos:
        st.caption("Aún no registras títulos en esta cuenta.")
        return

    precios, tipos = _precios(cuenta, abiertas)
    valuacion = portafolio.valuar(lib, cuenta.id, precios, tipos)
    _resumen(valuacion)
    if valuacion.filas:
        _tabla_titulos(valuacion)
    if valuacion.plazos:
        _tabla_plazos(valuacion)
    if cuenta.activa:
        _registrar(cuenta, valuacion)
    _historial(cuenta)


# ----------------------------------------------------------------- precios


def _precios(cuenta: Cuenta, abiertas) -> tuple[dict, dict]:
    """Los últimos guardados en tu PC (de esta consulta o de antes), más los que escribas a mano (estos mandan)."""
    clave = f"_cotizacion_{cuenta.id}"
    lib = libro()
    if abiertas:
        simbolos = [p.simbolo for p in abiertas]
        boton, auto = st.columns([1, 1.3], vertical_alignment="center")
        pedido = boton.button("Consultar valor aproximado actual", type="primary", icon=":material/travel_explore:",
                              key=f"consultar_{cuenta.id}")
        actual = bool(lib.perfil and lib.perfil.actualizar_precios)
        automatico = auto.toggle(
            "Actualizar precios automáticamente", value=actual, key=f"auto_precios_{cuenta.id}",
            help="Al abrir una cuenta de inversión, si los precios guardados tienen más de una hora, TALLY los "
                 "consulta solo. Igual que el botón: envía solo los símbolos.")
        if lib.perfil and automatico != actual:
            ejecutar(lambda lib: perfil.ajustar(lib, actualizar_precios=automatico))
        guardados, _ = cotizaciones.ultimos()
        ahora = datetime.now()
        viejos = any(s not in guardados or ahora - guardados[s].actualizado > VIGENCIA for s in simbolos)
        bandera = f"_auto_hecho_{cuenta.id}"
        if pedido or (automatico and viejos and not st.session_state.get(bandera)):
            st.session_state[bandera] = True          # lo automático, una vez por visita
            with st.spinner("Consultando precios…"):
                consulta = cotizaciones.consultar(simbolos)
            cotizaciones.guardar(consulta)
            st.session_state[clave] = consulta
        st.caption(TRANSPARENCIA)

    consulta: cotizaciones.Consulta | None = st.session_state.get(clave)
    guardados, tipos_guardados = cotizaciones.ultimos()
    precios = {s: (g.valor, g.moneda) for s, g in guardados.items()}
    tipos = {m: g.valor for m, g in tipos_guardados.items()}
    if consulta and consulta.falla_proveedor:
        st.error(f"⚠️ {cotizaciones.PROVEEDOR} no está respondiendo como antes: puede que haya cambiado o dejado de "
                 "funcionar. **TALLY sigue funcionando**: usa tus últimos precios guardados o escríbelos a mano. Si "
                 "sigue así, una actualización de TALLY cambiará a otro proveedor gratuito.")
    elif consulta and consulta.sin_conexion:
        st.warning(consulta.aviso)
    elif consulta and consulta.aviso:
        st.warning(f"No se pudo todo: {consulta.aviso}")
    if abiertas:
        fechas = [guardados[p.simbolo].actualizado for p in abiertas if p.simbolo in guardados]
        if fechas:
            texto = f"Última actualización: {min(fechas):%d/%m/%Y %H:%M}"
            if consulta and (consulta.sin_conexion or consulta.falla_proveedor):
                texto += " · sin conexión: se muestran los últimos precios guardados en tu PC"
            st.caption(texto)
    if abiertas:
        with st.expander("Escribir precios a mano (sin internet)"):
            st.caption("Si no hay conexión o el precio no te convence, escríbelo aquí (0 = no usar). Manda sobre el "
                       "consultado.")
            monedas = sorted({p.moneda for p in abiertas} - {"MXN"})
            columnas = st.columns(min(len(abiertas) + len(monedas), 3))
            for i, posicion in enumerate(abiertas):
                valor = columnas[i % len(columnas)].number_input(
                    f"{posicion.simbolo} ({posicion.moneda} por título)", min_value=0.0, value=0.0, step=1.0,
                    format="%.4f", key=f"manual_{cuenta.id}_{posicion.simbolo}")
                if valor:
                    precios[posicion.simbolo] = (Decimal(str(valor)), posicion.moneda)
            for j, moneda in enumerate(monedas, start=len(abiertas)):
                valor = columnas[j % len(columnas)].number_input(
                    f"Tipo de cambio {moneda} (pesos por 1 {moneda})", min_value=0.0, value=0.0, step=0.1,
                    format="%.4f", key=f"manual_{cuenta.id}_fx_{moneda}")
                if valor:
                    tipos[moneda] = Decimal(str(valor))
    return precios, tipos


# ------------------------------------------------------------------- vistas


def _resumen(v: portafolio.Valuacion) -> None:
    columnas = st.columns(4)
    columnas[0].metric("Valor aproximado hoy", formato.dinero(v.valor_total) if v.valor_total is not None else "—",
                       help="Títulos a precio actual + inversiones a plazo con su interés a la fecha.")
    columnas[1].metric("Ganancia sin vender", formato.dinero(v.ganancia_no_realizada)
                       if v.ganancia_no_realizada is not None else "—",
                       help="Valor actual de lo que tienes menos lo que te costó.")
    columnas[2].metric("Ganancia de lo vendido", formato.dinero(v.ganancia_realizada))
    columnas[3].metric("Interés de inversiones a plazo", formato.dinero(v.interes_plazos))
    if v.faltan:
        st.caption("Sin precio todavía: " + ", ".join(v.faltan) + ". Usa «Consultar valor aproximado actual» o "
                   "escríbelo a mano.")


def _tabla_titulos(v: portafolio.Valuacion) -> None:
    tabla = pd.DataFrame({
        "Símbolo": [f.posicion.simbolo for f in v.filas],
        "Títulos": [f"{f.posicion.titulos.normalize():f}" for f in v.filas],
        "Costo promedio": [formato.dinero(f.posicion.costo_promedio) for f in v.filas],
        "Costo": [formato.dinero(f.posicion.costo) for f in v.filas],
        "Precio actual": [f"{f.precio:,.4f} {f.moneda_precio}" if f.precio is not None else "—" for f in v.filas],
        "Valor actual": [formato.dinero(f.valor) if f.valor is not None else "—" for f in v.filas],
        "Ganancia": [formato.dinero(f.ganancia) if f.ganancia is not None else "—" for f in v.filas],
        "%": [f"{f.porcentaje:+.1f} %" if f.porcentaje is not None else "—" for f in v.filas],
    })
    st.dataframe(tabla, hide_index=True, width="stretch")


def _tabla_plazos(v: portafolio.Valuacion) -> None:
    st.dataframe(pd.DataFrame({
        "Inversión": [p.plazo.nombre for p in v.plazos],
        "Monto": [formato.dinero(a_pesos(p.plazo.monto)) for p in v.plazos],
        "Tasa anual": [f"{p.plazo.tasa_anual.normalize():f} %" for p in v.plazos],
        "Inicio": [formato.fecha(p.plazo.fecha_inicio) for p in v.plazos],
        "Vence": [formato.fecha(p.vence) + (" ✓" if p.vencido else "") for p in v.plazos],
        "Interés a hoy": [formato.dinero(p.interes_hoy) for p in v.plazos],
        "Valor hoy": [formato.dinero(p.valor_hoy) for p in v.plazos],
        "Al vencer": [formato.dinero(p.valor_al_vencer) for p in v.plazos],
    }), hide_index=True, width="stretch")
    st.caption("Interés simple, año de 360 días, antes de impuestos (aproximado).")


def _registrar(cuenta: Cuenta, v: portafolio.Valuacion) -> None:
    if v.por_registrar is None:
        return
    with st.container(border=True):
        st.markdown(f"**¿Pasar la ganancia a tu contabilidad?** Ya registrada: {formato.dinero_md(v.registrada)} · "
                    f"Ganancia total hoy: {formato.dinero_md(v.ganancia_total)}")
        if not v.por_registrar:
            st.caption("Tu saldo ya refleja esta valuación: no hay nada nuevo que registrar.")
            return
        st.caption("Se registra la diferencia como **rendimiento** en esta cuenta (cuenta como ingreso de "
                   "INTERESES Y RENDIMIENTOS; si es negativa, lo resta). Consultar no cambia nada: solo este botón.")
        signo = "+" if v.por_registrar > 0 else "−"
        if st.button(f"Registrar como rendimiento ({signo}{formato.dinero(abs(v.por_registrar))})",
                     key=f"registrar_rendimiento_{cuenta.id}"):
            if ejecutar(lambda lib: portafolio.registrar_rendimiento(lib, cuenta.id, v),
                        exito="Rendimiento registrado"):
                st.rerun()


def _historial(cuenta: Cuenta) -> None:
    lib = libro()
    valores = lib.valores(cuenta.id)
    plazos = lib.plazos(cuenta.id)
    with st.expander(f"Compras, ventas e inversiones a plazo registradas ({len(valores) + len(plazos)})"):
        if valores:
            st.dataframe(pd.DataFrame({
                "Fecha": [formato.fecha(v.fecha) for v in valores],
                "Operación": ["Compra" if v.tipo is TipoOperacionValor.COMPRA else "Venta" for v in valores],
                "Símbolo": [v.simbolo for v in valores],
                "Títulos": [f"{v.titulos.normalize():f}" for v in valores],
                "Precio": [f"{v.precio:,.4f} {v.moneda}" for v in valores],
                "Tipo de cambio": [f"{v.tipo_cambio.normalize():f}" if v.moneda != "MXN" else "" for v in valores],
                "Comisión": [f"{v.comision:,.2f}" if v.comision else "" for v in valores],
                "Notas": [v.notas for v in valores],
            }), hide_index=True, width="stretch")
        if not cuenta.activa:
            return
        opciones = {**{v.id: f"{formato.fecha(v.fecha)} · {'Compra' if v.tipo is TipoOperacionValor.COMPRA else 'Venta'} "
                             f"{v.titulos.normalize():f} {v.simbolo}" for v in valores},
                    **{p.id: f"{formato.fecha(p.fecha_inicio)} · {p.nombre}" for p in plazos}}
        elegido = st.selectbox("Borrar un registro", list(opciones), index=None, format_func=opciones.get,
                               placeholder="Elige uno para borrarlo", key=f"borrar_valor_{cuenta.id}")
        if elegido and st.button("Borrar", key=f"borrar_valor_boton_{cuenta.id}"):
            accion = portafolio.eliminar_plazo if elegido in {p.id for p in plazos} else portafolio.eliminar_valor
            if ejecutar(lambda lib: accion(lib, elegido), exito="Registro borrado"):
                st.rerun()


# --------------------------------------------------------------- formularios


def _formulario_valor(cuenta: Cuenta) -> None:
    lib = libro()
    with st.form(f"valor_{cuenta.id}", clear_on_submit=True, border=False):
        operacion = st.radio("Operación", ["Compra", "Venta"], horizontal=True, key=f"valor_operacion_{cuenta.id}")
        izquierda, derecha = st.columns(2)
        simbolo = izquierda.text_input("Símbolo (como en Yahoo Finance)", placeholder="IVVPESO.MX, AAPL, BTC-USD",
                                       max_chars=20)
        fecha = derecha.date_input("Fecha", value=lib.hoy(), format="DD/MM/YYYY")
        titulos = izquierda.number_input("Títulos", min_value=0.0, value=None, step=1.0, format="%.6f",
                                         placeholder="Ej. 3 o 0.0025")
        precio = derecha.number_input("Precio por título", min_value=0.0, value=None, step=1.0, format="%.4f")
        moneda = izquierda.selectbox("Moneda del precio", ["MXN", "USD", "EUR"])
        tipo_cambio = derecha.number_input("Tipo de cambio ese día (solo si no es MXN)", min_value=0.0, value=None,
                                           step=0.1, format="%.4f", placeholder="Ej. 18.45")
        comision = izquierda.number_input("Comisión (opcional, en la misma moneda)", min_value=0.0, value=0.0,
                                          step=1.0, format="%.2f")
        notas = derecha.text_input("Notas (opcional)", max_chars=200)
        if st.form_submit_button("Guardar", type="primary"):
            if not titulos or not precio:
                st.error("Escribe los títulos y el precio.")
                return
            registrar = portafolio.registrar_compra if operacion == "Compra" else portafolio.registrar_venta
            if ejecutar(lambda lib: registrar(lib, cuenta.id, fecha, simbolo, Decimal(str(titulos)),
                                              Decimal(str(precio)), moneda=moneda,
                                              tipo_cambio=Decimal(str(tipo_cambio)) if tipo_cambio else None,
                                              comision=Decimal(str(comision)), notas=notas),
                        exito=f"{operacion} de {simbolo.strip().upper()} guardada"):
                st.rerun()
    st.caption("¿No sabes el símbolo? Búscalo en finance.yahoo.com: las de la BMV terminan en .MX (WALMEX.MX), "
               "las de EE. UU. van solas (AAPL, VOO) y la cripto lleva la moneda (BTC-USD).")


def _formulario_plazo(cuenta: Cuenta) -> None:
    lib = libro()
    with st.form(f"plazo_{cuenta.id}", clear_on_submit=True, border=False):
        nombre = st.text_input("Nombre", placeholder="Ej. CETES 28 días, Pagaré BBVA 91 días", max_chars=60)
        izquierda, derecha = st.columns(2)
        monto = izquierda.number_input("Monto invertido (MXN)", min_value=0.0, value=None, step=100.0, format="%.2f")
        tasa = derecha.number_input("Tasa anual (%)", min_value=0.0, max_value=100.0, value=None, step=0.1,
                                    format="%.2f", placeholder="Ej. 10.5")
        fecha = izquierda.date_input("Fecha de inicio", value=lib.hoy(), format="DD/MM/YYYY")
        plazo = derecha.number_input("Plazo (días)", min_value=1, max_value=3650, value=28, step=1)
        notas = st.text_input("Notas (opcional)", max_chars=200)
        if st.form_submit_button("Guardar", type="primary"):
            if not monto or not tasa:
                st.error("Escribe el monto y la tasa.")
                return
            if ejecutar(lambda lib: portafolio.registrar_plazo(lib, cuenta.id, nombre or "Inversión a plazo", fecha,
                                                               Decimal(str(monto)), Decimal(str(tasa)), int(plazo),
                                                               notas),
                        exito="Inversión a plazo guardada"):
                st.rerun()
