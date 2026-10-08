"""Rendimiento de tus inversiones en el tiempo (motor/evolucion.py): eliges cuentas, títulos y periodo."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from motor import cotizaciones, evolucion, monedas
from motor.evolucion import Evolucion
from motor.libro import Libro
from portal import navegacion
from portal.componentes import formato, graficas
from portal.componentes.portafolio import TRANSPARENCIA
from portal.componentes.sesion import libro

VISTAS = {"titulo": "Por título (precios de mercado)", "oficial": "Oficial (tu saldo con los valores oficiales)"}
CONSULTA = "_inversiones_consulta"
AUTO_HECHO = "_inversiones_auto_hecho"
VIGENCIA = timedelta(hours=12)


def mostrar() -> None:
    st.title("Inversiones")
    st.caption("Cuánto valen tus inversiones, cuánto metiste y cuánto ganaste en el periodo que elijas. Pasa el "
               "cursor sobre las gráficas para ver los importes.")
    lib = libro()
    todas = evolucion.cuentas_de_inversion(lib)
    if not todas:
        st.info("Aún no tienes cuentas de inversión. Crea una de tipo **Inversión** (GBM, CETES, tu casa de "
                "bolsa…) y registra ahí tus títulos y CETES.")
        navegacion.enlace("cuentas", "Ir a Cuentas", "🏦")
        return

    nombres = {c: lib.cuenta(c).nombre for c in todas}
    izquierda, derecha = st.columns([1.1, 2])
    vista = izquierda.radio("Cómo verlo", list(VISTAS), format_func=VISTAS.get, key="inv_vista",
                            help="Por título: estimado con precios de cierre diarios, para comparar IVV, VT, CETES… "
                                 "Oficial: exacto, el saldo de la cuenta con lo que registraste en «Cuadrar con tu "
                                 "estado de cuenta».")
    elegidas = derecha.multiselect("Cuentas", todas, format_func=nombres.get, placeholder="Todas",
                                   key="inv_cuentas") or todas
    elegidos = None
    if vista == "titulo":
        opciones = {i.etiqueta: i for i in evolucion.instrumentos(lib, elegidas)}
        _limpiar("inv_instrumentos", opciones)
        marcados = derecha.multiselect("Títulos e inversiones a plazo", list(opciones), placeholder="Todos",
                                       key="inv_instrumentos")
        elegidos = {opciones[m] for m in marcados} or None

    desde, hasta = _periodo(lib, elegidas, oficial=vista == "oficial")
    if vista == "titulo":
        _historial_de_precios(lib, elegidas)
        evo = evolucion.por_titulo(lib, elegidas, desde, hasta, cotizaciones.mercado_guardado(base=monedas.de(lib)),
                                   elegidos)
        if not evo.nombres:
            st.info("Aún no registras títulos ni inversiones a plazo en estas cuentas. Regístralos en **Cuentas → "
                    "Ver movimientos** de tu cuenta de inversión.")
            return
    else:
        evo = evolucion.oficial(lib, elegidas, desde, hasta)
    _mostrar(evo, vista)


def _limpiar(clave: str, opciones) -> None:
    """Quita de lo elegido lo que ya no existe (p. ej. al cambiar de cuentas)."""
    if clave in st.session_state:
        st.session_state[clave] = [o for o in st.session_state[clave] if o in opciones]


def _periodo(lib: Libro, cuenta_ids: list[str], *, oficial: bool):
    hoy = lib.hoy()
    inicio = evolucion.primera_fecha(lib, cuenta_ids, oficial=oficial)
    claves = list(evolucion.PERIODOS)
    izquierda, derecha = st.columns(2)
    clave = izquierda.selectbox("Periodo", claves, format_func=evolucion.PERIODOS.get, index=claves.index("1a"),
                                key="inv_periodo")
    elegido = None
    if clave == "rango":
        fechas = derecha.date_input("Del … al …", value=(inicio or hoy, hoy), max_value=hoy, format="DD/MM/YYYY",
                                    key="inv_fechas")
        if isinstance(fechas, (tuple, list)) and len(fechas) == 2:
            elegido = tuple(fechas)
        elif isinstance(fechas, (tuple, list)) and fechas:
            elegido = (fechas[0], fechas[0])
    desde, hasta = evolucion.rango(clave, hoy, inicio, elegido)
    if clave != "rango":
        derecha.markdown(f"<div style='padding-top:2.1rem'>{formato.rango(desde, hasta)}</div>",
                         unsafe_allow_html=True)
    return desde, hasta


# ---------------------------------------------------------- precios de mercado


def _historial_de_precios(lib: Libro, cuenta_ids: list[str]) -> None:
    """El botón para traer los cierres diarios (y, si el usuario lo activó, la actualización automática)."""
    pedidos: dict = {}
    for cuenta_id in cuenta_ids:
        for v in lib.valores(cuenta_id):
            pedidos[v.simbolo] = min(pedidos.get(v.simbolo, v.fecha), v.fecha)
    if not pedidos:
        return
    guardado = cotizaciones.historial_guardado()
    boton, nota = st.columns([1, 2], vertical_alignment="center")
    pedido = boton.button("Actualizar historial de precios", icon=":material/travel_explore:", key="inv_actualizar")
    automatico = bool(lib.perfil and lib.perfil.actualizar_precios)
    nota.caption("Se actualiza solo al abrir esta página si activaste «Actualizar precios automáticamente» en tu "
                 "cuenta de inversión." if automatico else "Solo se consulta cuando presionas el botón.")
    ahora = datetime.now()
    viejos = any(s not in guardado or ahora - guardado[s].actualizado > VIGENCIA for s in pedidos)
    if pedido or (automatico and viejos and not st.session_state.get(AUTO_HECHO)):
        st.session_state[AUTO_HECHO] = True                   # lo automático, una vez por visita
        faltan = {s: cotizaciones.desde_pendiente(s, d, guardado) for s, d in pedidos.items()}
        with st.spinner("Consultando el historial de precios…"):
            consulta = cotizaciones.consultar_historial(faltan, lib.hoy(), base=monedas.de(lib))
        cotizaciones.guardar_historial(consulta)
        st.session_state[CONSULTA] = consulta
        guardado = cotizaciones.historial_guardado()
    st.caption(TRANSPARENCIA.replace("**símbolos bursátiles** (por ejemplo IVV o IVVPESO.MX)",
                                     "**símbolos bursátiles** y un periodo estándar (por ejemplo «IVV, 5 años»)"))
    consulta: cotizaciones.ConsultaHistorial | None = st.session_state.get(CONSULTA)
    if consulta and consulta.falla_proveedor:
        st.error(f"⚠️ {cotizaciones.PROVEEDOR} no está respondiendo como antes: puede que haya cambiado o dejado de "
                 "funcionar. **TALLY sigue funcionando** con los precios que ya tienes guardados y tus precios de "
                 "compra.")
    elif consulta and consulta.sin_conexion:
        st.warning(consulta.aviso)
    elif consulta and consulta.aviso:
        st.warning(f"No se pudo todo: {consulta.aviso}")
    fechas = [guardado[s].actualizado for s in pedidos if s in guardado]
    if fechas:
        st.caption(f"Historial actualizado: {min(fechas):%d/%m/%Y %H:%M}")


# ------------------------------------------------------------------- vistas


def _mostrar(evo: Evolucion, vista: str) -> None:
    total = evolucion.resultado(evo)
    columnas = st.columns(5)
    columnas[0].metric("Valor al inicio", formato.dinero_metrica(total.valor_inicial),
                       help=f"Al cierre del {formato.fecha(evo.fechas[0])}, un día antes del periodo.")
    columnas[1].metric("Metiste", formato.dinero_metrica(total.entradas),
                       help="Compras e inversiones a plazo nuevas." if vista == "titulo" else
                       "Transferencias y depósitos a la cuenta.")
    columnas[2].metric("Sacaste", formato.dinero_metrica(total.salidas),
                       help="Ventas y vencimientos (el dinero vuelve a la cuenta)." if vista == "titulo" else
                       "Transferencias y retiros de la cuenta.")
    columnas[3].metric("Valor al final", formato.dinero_metrica(total.valor_final))
    columnas[4].metric("Ganancia del periodo", formato.dinero_metrica(total.ganancia),
                       delta=f"{total.rendimiento:+.2f} %" if total.rendimiento is not None else None,
                       help="Valor final − valor inicial − (lo que metiste − lo que sacaste). El % toma en cuenta "
                            "cuándo metiste o sacaste el dinero.")

    st.subheader("Valor en el tiempo")
    separar = len(evo.nombres) > 1 and st.toggle(
        "Ver cada uno por separado" if vista == "titulo" else "Ver cada cuenta por separado", key="inv_separar")
    if separar:
        graficas.valor_por_serie({n: list(zip(evo.fechas, evo.valores[n])) for n in evo.nombres})
    else:
        graficas.valor_y_lo_invertido(evolucion.serie_total(evo))
        st.caption("La distancia entre la línea de color y la gris es lo que llevas ganado (o perdido) en el "
                   "periodo.")

    meses = (evo.hasta.year - evo.desde.year) * 12 + evo.hasta.month - evo.desde.month + 1
    titulo, agrupar = st.columns([2, 1], vertical_alignment="bottom")
    titulo.subheader("Ganancia por periodo")
    por_anio = agrupar.segmented_control("Agrupar", ["Por mes", "Por año"], key="inv_agrupar",
                                         default="Por año" if meses > 24 else "Por mes",
                                         label_visibility="collapsed") == "Por año"
    filas = evolucion.ganancia_por_periodo(evo, por_anio=por_anio)
    graficas.ganancias([(str(d.year) if por_anio else formato.mes(d.year, d.month), g) for d, g in filas])

    st.subheader("Detalle" if vista == "titulo" else "Por cuenta")
    detalle = evolucion.por_serie(evo)
    st.dataframe(formato.pintar(pd.DataFrame({
        "Título o inversión" if vista == "titulo" else "Cuenta": [n for n, _ in detalle],
        "Valor al inicio": [formato.dinero(r.valor_inicial) for _, r in detalle],
        "Metiste": [formato.dinero(r.entradas) for _, r in detalle],
        "Sacaste": [formato.dinero(r.salidas) for _, r in detalle],
        "Valor al final": [formato.dinero(r.valor_final) for _, r in detalle],
        "Ganancia": [formato.dinero(r.ganancia) for _, r in detalle],
        "Rendimiento": [f"{r.rendimiento:+.2f} %" if r.rendimiento is not None else "—" for _, r in detalle],
    })), hide_index=True, width="stretch")

    if vista == "titulo":
        st.caption("Estimado: precio de cierre de cada día por los títulos que tenías, en tu moneda al tipo de cambio de "
                   "ese día; las inversiones a plazo, con interés simple. Lo oficial es lo que registras con "
                   "«Cuadrar con tu estado de cuenta» en cada cuenta (vista «Oficial»).")
        if evo.estimados:
            st.caption("Sin historial de precios todavía: " + ", ".join(sorted(evo.estimados)) + ". Se usó tu "
                       "precio de compra o el último consultado; presiona «Actualizar historial de precios».")
    else:
        st.caption("Exacto: el saldo de cada cuenta en TALLY. La ganancia son los rendimientos que registraste "
                   "(«Cuadrar con tu estado de cuenta»); las transferencias son dinero que metiste o sacaste.")
