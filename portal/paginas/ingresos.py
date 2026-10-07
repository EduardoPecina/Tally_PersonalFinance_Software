"""Ingresos: tu ingreso principal (cada cuánto te pagan y cuánto), tus otros ingresos fijos, cuánto tiene que durarte
cada pago y tu ingreso esperado al mes (motor/ingresos.py y motor/planeacion.py)."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import categorias, ingresos, perfil, planeacion, recurrentes
from motor.dinero import a_pesos
from motor.modelo import ClaseCategoria, Recurrente, TipoCuenta
from portal.componentes import formato
from portal.componentes.sesion import ejecutar, libro

CADA = {"quincenal": "Quincena", "catorcenal": "Catorcena", "semanal": "Semana", "mensual": "Mes"}
TIPOS_DE_CUENTA = (TipoCuenta.DEBITO, TipoCuenta.AHORRO, TipoCuenta.EFECTIVO, TipoCuenta.INVERSION, TipoCuenta.OTRA,
                   TipoCuenta.CREDITO)


def mostrar() -> None:
    st.title("Ingresos")
    st.caption("Cuánto ganas, cada cuánto te pagan y cuánto tiene que durarte cada pago. Con esto TALLY te llena el "
               "importe al registrar tu nómina y calcula tu capacidad de pago y tus presupuestos.")
    durar, principal, otros, al_mes = st.tabs(["📆 ¿Cuánto te tiene que durar?", "💼 Tu ingreso principal",
                                               "➕ Otros ingresos fijos", "🎯 Tu ingreso al mes"])
    with durar:
        _durar()
    with principal:
        _principal()
    with otros:
        _otros()
    with al_mes:
        _al_mes()


# ------------------------------------------------------------- cuánto te tiene que durar


def _durar() -> None:
    lib = libro()
    r = ingresos.principal(lib)
    if r is None:
        st.info("Primero configura tu ingreso principal en la pestaña **💼 Tu ingreso principal**: cada cuánto te "
                "pagan, cuánto y a qué cuenta.", icon="💼")
        return
    if not r.activa:
        st.info("Tu ingreso principal está pausado (en el Calendario). Reanúdalo para ver cuánto te tiene que durar.")
        return
    hoy = lib.hoy()
    h = ingresos.hasta_el_proximo_pago(lib, hoy)
    if h is not None:
        st.subheader("Hasta tu próximo pago")
        a, b, c, d = st.columns(4)
        a.metric("Te pagan", formato.fecha_con_dia(h.proximo),
                 help=f"Te llegan unos {formato.dinero(h.monto)} a {lib.cuenta(r.cuenta_id).nombre}.")
        b.metric("Faltan", "mañana" if h.dias == 1 else f"{h.dias} días")
        c.metric("Te quedaría para gastar", formato.dinero(h.queda),
                 help=f"Tu dinero disponible hoy ({formato.dinero(h.disponible)}) menos lo que te toca pagar antes de "
                      f"tu pago, más lo que te toca cobrar ({formato.dinero(h.compromisos)} en total). Lo ves en el "
                      "Calendario.")
        d.metric("Al día", formato.dinero(h.por_dia), help="Lo que te quedaría, entre los días que faltan.")
        if h.queda < 0:
            st.error(f"Con lo que tienes y lo que te toca pagar, **no te alcanza** hasta el "
                     f"{formato.fecha_con_dia(h.proximo)}: te faltarían {formato.dinero_md(-h.queda)}. Revisa en el "
                     "Calendario qué pagos puedes mover.", icon="🔴")
        else:
            st.info(f"Para llegar bien al {formato.fecha_con_dia(h.proximo)}, trata de no gastar más de "
                    f"**{formato.dinero_md(h.por_dia)} al día**.", icon="💡")

    lista = ingresos.periodos(r, hoy)
    if not lista:
        return
    st.subheader("Tus próximos pagos")
    st.caption("No todos los periodos duran lo mismo. Lo que importa en el día a día es cuántos días tiene que "
               "durarte cada pago, no cuánto te pagan.")
    quincenal = r.frecuencia == "quincenal"
    st.dataframe(pd.DataFrame({
        "Te pagan": [formato.fecha_con_dia(p.pago) for p in lista],
        **({"Quincena": [f"{p.quincena}.ª" for p in lista]} if quincenal else {}),
        "Te llegan": [formato.dinero(p.monto) for p in lista],
        "Te tiene que durar hasta": [formato.fecha_con_dia(p.hasta) for p in lista],
        "Días": [p.dias for p in lista],
        "Al día": [formato.dinero(p.por_dia) for p in lista],
        "Aviso": [f"⚠️ +{p.dias_de_mas} días" if p.largo else "" for p in lista],
    }), hide_index=True, width="stretch")
    largo = next((p for p in lista if p.largo and p.siguiente > hoy), None)
    if largo is not None:
        cual = f"La {largo.quincena}.ª quincena" if quincenal else "El pago"
        corto = min(lista, key=lambda p: p.dias)
        st.warning(f"**{cual} que te pagan el {formato.fecha_con_dia(largo.pago)} tiene que durarte {largo.dias} "
                   f"días** (hasta el {formato.fecha_con_dia(largo.hasta)}), "
                   f"{largo.dias_de_mas} días más de lo normal. Son {formato.dinero_md(largo.por_dia)} al día"
                   + (f", contra {formato.dinero_md(corto.por_dia)} del periodo más corto"
                      if corto.dias < largo.dias else "")
                   + ". Apártalo desde el primer día para no batallar al final.", icon="⚠️")
    if quincenal and not r.fin_de_semana:
        st.caption("💡 ¿Tu empresa te paga el viernes cuando el 15 o el fin de mes caen en fin de semana? Indícalo en "
                   "**💼 Tu ingreso principal** para que TALLY calcule bien cuánto dura cada quincena.")
    else:
        st.caption("TALLY no conoce los días festivos: si te pagan antes por uno, cuenta un día más.")


# ------------------------------------------------------------- ingreso principal


def _principal() -> None:
    lib = libro()
    r = ingresos.principal(lib)
    st.caption("Tu ingreso **principal** es el que te sostiene, normalmente tu nómina. Dile a TALLY cada cuánto te "
               "pagan y cuánto te llega: lo usará para llenarte el importe al registrarlo, para avisarte en el "
               "Calendario y para decirte cuánto tiene que durarte cada pago.")
    if r is None:
        actual = next((c for c in lib.categorias() if c.principal), None)
        if actual is not None:
            st.caption(f"Ahora tu ingreso principal es **{formato.md(categorias.etiqueta(lib, actual.id))}**, pero aún "
                       "no le dices cada cuánto te pagan.")
    _formulario(r, principal=True)
    if r is not None:
        with st.popover("Quitar mi ingreso principal", icon=":material/delete:"):
            st.markdown(f"Se borra «{formato.md(r.nombre)}» (cada cuánto te pagan y cuánto). Tus ingresos ya "
                        "registrados no se tocan, y puedes volver a configurarlo cuando quieras.")
            if st.button("Sí, quitarlo", type="primary", key="ing_quitar_principal"):
                if ejecutar(lambda li: recurrentes.eliminar(li, r.id), f"Se quitó «{r.nombre}»"):
                    st.rerun()


def _formulario(r: Recurrente | None, *, principal: bool) -> None:
    lib = libro()
    clave = r.id if r else ("principal" if principal else "nuevo")
    cuentas_ = [c.id for c in lib.cuentas() if c.activa and c.tipo in TIPOS_DE_CUENTA]
    if not cuentas_:
        st.info("Primero crea la cuenta donde te depositan, en **Cuentas**.")
        return
    subs = categorias.ordenadas(lib, [c for c in lib.categorias()
                                      if c.rubro_id and c.activa and c.clase is ClaseCategoria.INGRESO])
    ids = [c.id for c in subs]
    sugerida = r.categoria_id if r else next((c.id for c in subs if c.principal), None) if principal else None
    if principal:
        frecuencia = st.segmented_control("¿Cada cuánto te pagan?", list(CADA), format_func=CADA.get, required=True,
                                          default=r.frecuencia if r and r.frecuencia in CADA else "quincenal",
                                          key=f"ing_frec_{clave}")
    else:
        opciones = list(recurrentes.FRECUENCIAS)
        frecuencia = st.selectbox("¿Cada cuánto?", opciones, format_func=recurrentes.FRECUENCIAS.get,
                                  index=opciones.index(r.frecuencia) if r else 0, key=f"ing_frec_{clave}")
    quincenal = frecuencia == "quincenal"
    with st.form(f"ing_form_{clave}_{frecuencia}", clear_on_submit=r is None and not principal, border=False):
        a, b = st.columns(2)
        categoria = a.selectbox("Subcategoría", ids, format_func=lambda i: categorias.etiqueta(lib, i),
                                index=ids.index(sugerida) if sugerida in ids else None,
                                placeholder="Escribe para buscar: nómina, renta…")
        nombre = b.text_input("Nombre", value=r.nombre if r else "", placeholder="Nómina, Renta del depa…",
                              help="Vacío = el de la subcategoría.")
        a, b = st.columns(2)
        monto_2 = None
        inicio = r.inicio if r else None
        if quincenal:
            monto = a.number_input("1.ª quincena (la del 15)", min_value=0.0, step=100.0, format="%.2f",
                                   value=float(a_pesos(r.monto)) if r else 0.0,
                                   help="Lo que te llega, ya con descuentos.")
            monto_2 = b.number_input("2.ª quincena (la de fin de mes)", min_value=0.0, step=100.0, format="%.2f",
                                     value=float(a_pesos(r.monto_2 or r.monto)) if r else 0.0,
                                     help="Si es igual a la 1.ª, pon lo mismo. Muchas veces cambia por centavos "
                                          "(retenciones, redondeos).")
        else:
            monto = a.number_input("¿Cuánto te llega cada vez?", min_value=0.0, step=100.0, format="%.2f",
                                   value=float(a_pesos(r.monto)) if r else 0.0,
                                   help="Lo que te llega, ya con descuentos.")
            inicio = b.date_input("Un día en que te pagan (el próximo o uno pasado)",
                                  value=r.inicio if r else lib.hoy(), format="DD/MM/YYYY",
                                  help="Marca el día: cada 14 días desde ahí, cada semana ese día, cada mes ese "
                                       "número de día…")
        a, b = st.columns(2)
        cuenta = a.selectbox("¿A qué cuenta te depositan?", cuentas_,
                             index=cuentas_.index(r.cuenta_id) if r and r.cuenta_id in cuentas_ else 0,
                             format_func=lambda i: lib.cuenta(i).nombre)
        opciones_fs = list(recurrentes.FIN_DE_SEMANA)
        fin_de_semana = b.selectbox("Si el día de pago cae en sábado o domingo", opciones_fs,
                                    format_func=recurrentes.FIN_DE_SEMANA.get,
                                    index=opciones_fs.index(r.fin_de_semana if r else "antes"),
                                    help="Casi todas las empresas pagan el viernes antes. Así TALLY sabe cuántos días "
                                         "tiene que durarte cada pago.")
        if st.form_submit_button("Guardar" if principal or r else "Agregar", type="primary"):
            hecho = ejecutar(lambda li: ingresos.guardar(
                li, nombre.strip(), categoria, monto, cuenta, frecuencia, monto_2=monto_2, inicio=inicio,
                fin_de_semana=fin_de_semana, es_principal=principal, recurrente_id=r.id if r else None),
                "Ingreso guardado")
            if hecho:
                st.rerun()


# ------------------------------------------------------------- otros ingresos


def _otros() -> None:
    lib = libro()
    p = ingresos.principal(lib)
    lista = [r for r in ingresos.fijos(lib) if p is None or r.id != p.id]
    st.caption("Otros ingresos que se repiten: una renta que cobras, honorarios de cada mes, una pensión… Cuentan en "
               "tu ingreso esperado y aparecen en tu Calendario.")
    if lista:
        hoy = lib.hoy()
        seleccion = st.dataframe(pd.DataFrame({
            "Nombre": [r.nombre for r in lista],
            "Subcategoría": [categorias.etiqueta(lib, r.categoria_id) if r.categoria_id
                             else "❓ Elige la subcategoría" for r in lista],      # la suya se borró
            "Te llegan": [_importe(r) for r in lista],
            "Cada cuánto": [recurrentes.FRECUENCIAS[r.frecuencia].split(" (")[0] for r in lista],
            "Al mes": [formato.dinero(recurrentes.al_mes(r)) for r in lista],
            "Próxima vez": [formato.fecha_con_dia(d) if r.activa and (d := recurrentes.siguiente(r, hoy)) else "—"
                            for r in lista],
        }), hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="ing_sel")
        st.caption("Haz clic en un renglón para editarlo o borrarlo.")
        filas = seleccion.selection.rows if seleccion else []
        if filas:
            r = lista[filas[0]]
            with st.container(border=True):
                st.markdown(f"#### Editar «{formato.md(r.nombre)}»")
                _formulario(r, principal=False)
                if st.button("Borrar", key=f"ing_borrar_{r.id}", help="Tus movimientos ya registrados no se borran."):
                    if ejecutar(lambda li: recurrentes.eliminar(li, r.id), f"Se borró «{r.nombre}»"):
                        st.session_state.pop("ing_sel", None)
                        st.rerun()
    with st.expander("➕ Agregar otro ingreso fijo", expanded=not lista):
        _formulario(None, principal=False)


def _importe(r: Recurrente) -> str:
    if r.monto_2:
        return f"{formato.dinero(a_pesos(r.monto))} / {formato.dinero(a_pesos(r.monto_2))}"
    return formato.dinero(a_pesos(r.monto))


# ------------------------------------------------------------- ingreso al mes


def _al_mes() -> None:
    lib = libro()
    st.caption("Tu ingreso **principal** y tus ingresos **secundarios fijos**. Su promedio de los últimos 3 meses "
               "completos es tu ingreso esperado; con él se calculan tu capacidad de pago (Deudas) y tus presupuestos "
               "sugeridos.")
    de_ingreso = {c.id: categorias.etiqueta(lib, c.id) for c in lib.categorias()
                  if c.clase is ClaseCategoria.INGRESO and c.activa and c.rubro_id}
    ids = list(de_ingreso)
    principal = next((c.id for c in lib.categorias() if c.principal and c.id in de_ingreso), None)
    secundarios = [c.id for c in lib.categorias() if c.secundario and c.id in de_ingreso]
    with st.form("ingresos_fijos", border=False):
        elegido = st.selectbox("Ingreso principal", ids, format_func=de_ingreso.get, placeholder="Elige uno",
                               index=ids.index(principal) if principal else None)
        otros = st.multiselect("Ingresos secundarios fijos", ids, default=secundarios, format_func=de_ingreso.get,
                               placeholder="Ninguno")
        if st.form_submit_button("Guardar", type="primary"):
            def guardar(lib):
                for c in lib.categorias():
                    if c.id in de_ingreso:
                        categorias.editar(lib, c.id, principal=c.id == elegido,
                                          secundario=c.id in otros and c.id != elegido)
            if ejecutar(guardar, exito="Ingresos guardados"):
                st.rerun()
    lista = planeacion.ingresos(lib)
    esperado = planeacion.ingreso_esperado(lib)
    if any(i.promedio for i in lista):
        st.dataframe(pd.DataFrame({"Ingreso": [i.nombre for i in lista],
                                   "Tipo": ["Principal" if i.tipo == "principal" else "Secundario" for i in lista],
                                   "Promedio al mes": [formato.dinero(i.promedio) for i in lista]}),
                     hide_index=True, width="stretch")
    ayuda = {"manual": "Escrito por ti",
             "configurado": "Aún no tienes meses completos registrados: es lo que configuraste en tus ingresos fijos.",
             }.get(esperado.fuente, f"Promedio de {esperado.meses} mes(es) completo(s)")
    st.metric("Ingreso esperado al mes", formato.dinero(esperado.monto), help=ayuda)
    with st.form("ingreso_manual", border=False):
        actual = lib.perfil.ingreso_esperado
        manual = st.number_input("¿Prefieres escribir cuánto ganas al mes? (vacío = el promedio)", min_value=0.0,
                                 value=float(Decimal(actual) / 100) if actual else None, step=500.0, format="%.2f")
        meta = st.slider("Meta de ahorro (% de tu ingreso)", 0, 50, value=lib.perfil.meta_ahorro, step=5)
        if st.form_submit_button("Guardar"):
            if ejecutar(lambda lib: perfil.ajustar(lib, ingreso_esperado=Decimal(str(manual)) if manual else None,
                                                   meta_ahorro=meta), exito="Guardado"):
                st.rerun()
