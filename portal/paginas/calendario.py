"""Calendario: lo que te toca pagar (y cobrar) en los próximos 30 días, cómo quedaría tu dinero disponible día con día,
tus pagos fijos y suscripciones, y lo que TALLY detecta que se repite (motor/recurrentes.py)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import categorias, recurrentes
from motor.dinero import a_pesos
from motor.modelo import ClaseCategoria, Recurrente, TipoCuenta, TipoOperacion
from portal import navegacion
from portal.componentes import formato, graficas
from portal.componentes.sesion import aplicar, ejecutar, libro

ESTADOS = {recurrentes.PAGADO: "✅ Pagado", recurrentes.PENDIENTE: "⏳ Pendiente", recurrentes.VENCIDO: "🔴 Vencido"}
TIPOS = {TipoOperacion.GASTO: "Un pago o gasto", TipoOperacion.INGRESO: "Un ingreso",
         TipoOperacion.TRANSFERENCIA: "Pasar dinero a otra de mis cuentas"}
ICONOS = {recurrentes.RECURRENTE: "🔁", recurrentes.TARJETA: "💳", recurrentes.PRESTAMO: "🏦"}
TIPOS_DE_CUENTA = (TipoCuenta.DEBITO, TipoCuenta.CREDITO, TipoCuenta.AHORRO, TipoCuenta.EFECTIVO, TipoCuenta.OTRA,
                   TipoCuenta.INVERSION, TipoCuenta.PRESTAMO, TipoCuenta.POR_COBRAR)


def mostrar() -> None:
    st.title("Calendario de pagos")
    st.caption("Lo que te toca pagar y cobrar, y cómo quedaría tu dinero día con día. TALLY junta tus pagos fijos y "
               "suscripciones con los pagos de tus tarjetas y préstamos.")
    sugerencias = recurrentes.detectar(libro())
    proximos, fijos, sugeridos = st.tabs(["📅 Próximos 30 días", "🔁 Mis pagos fijos y suscripciones",
                                          f"✨ Sugerencias ({len(sugerencias)})" if sugerencias else "✨ Sugerencias"])
    with proximos:
        _proximos()
    with fijos:
        _fijos()
    with sugeridos:
        _sugerencias(sugerencias)


# ------------------------------------------------------------- próximos 30 días


def _proximos() -> None:
    lib = libro()
    f = recurrentes.flujo(lib)
    if not f.eventos:
        st.info("Aún no hay nada en tu calendario. Agrega tus pagos fijos (renta, luz, internet, suscripciones…) en "
                "**Mis pagos fijos y suscripciones**, o revisa **Sugerencias**: TALLY busca en tu historial lo que "
                "se repite cada mes. Los pagos de tus tarjetas y préstamos aparecen solos.", icon="📅")
        return
    a, b, c, d = st.columns(4)
    a.metric("Disponible hoy", formato.dinero(a_pesos(f.disponible)),
             help="Tu dinero disponible (las cuentas que marcaste como disponibles).")
    b.metric("Entra en 30 días", formato.dinero(a_pesos(f.entra)), help="Ingresos pendientes que esperas.")
    c.metric("Sale en 30 días", formato.dinero(a_pesos(f.sale)),
             help="Pagos pendientes: fijos, suscripciones de débito, tarjetas y préstamos.")
    d.metric("En 30 días tendrías", formato.dinero(a_pesos(f.final)))
    dia_minimo, minimo = f.minimo
    if f.negativo:
        st.error(f"**Ojo:** el **{formato.fecha_larga(dia_minimo)}** te quedarías en "
                 f"**{formato.dinero_md(a_pesos(minimo))}**. Revisa qué pagos puedes mover, o aparta dinero antes.",
                 icon="🔴")
    else:
        st.success(f"Te alcanza: lo más bajo que llegarías es {formato.dinero_md(a_pesos(minimo))} el "
                   f"{formato.fecha_larga(dia_minimo)}.", icon="✅")
    graficas.linea([(dia, a_pesos(centavos)) for dia, centavos in f.dias], "Dinero disponible")
    st.caption("Es una estimación con los importes de tus pagos fijos. Las compras con tarjeta no bajan tu dinero el "
               "día que compras: cuentan en el pago de la tarjeta.")

    vencidos = [e for e in f.eventos if e.estado == recurrentes.VENCIDO]
    if vencidos:
        st.warning("**Pendientes de días pasados:** "
                   + "; ".join(f"{formato.md(e.nombre)} ({formato.fecha(e.fecha)})" for e in vencidos)
                   + ". Si ya los pagaste, regístralos abajo; si no, págalos pronto.", icon="⏳")
    st.dataframe(pd.DataFrame({
        "Fecha": [e.fecha for e in f.eventos],
        "Qué": [f"{ICONOS[e.clase]} {e.nombre}" for e in f.eventos],
        "Cuenta": [lib.cuenta(e.cuenta_id).nombre for e in f.eventos],
        "Importe": [formato.dinero_con_signo(a_pesos(abs(e.centavos)), "+" if e.centavos > 0 else "-")
                    for e in f.eventos],
        "Estado": [ESTADOS[e.estado] for e in f.eventos],
        "Detalle": [("⭐ Suscripción · " if e.suscripcion else "") + e.detalle for e in f.eventos],
    }), hide_index=True, width="stretch", height=min(38 + 35 * len(f.eventos), 560),
        column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})
    _registrar([e for e in f.eventos if e.clase == recurrentes.RECURRENTE and e.estado != recurrentes.PAGADO])
    if any(e.clase in (recurrentes.TARJETA, recurrentes.PRESTAMO) and e.estado != recurrentes.PAGADO
           for e in f.eventos):
        st.caption("Los pagos de tarjetas y préstamos se registran en **Deudas** (o como transferencia en Registrar).")
        navegacion.enlace("deudas", "Ir a Deudas", "💳")


def _registrar(eventos) -> None:
    if not eventos:
        return
    lib = libro()
    st.markdown("##### ✍️ Registrar un pago del calendario")
    st.caption("Elige cuál y TALLY lo registra con su importe y su subcategoría (cámbialo si este mes fue distinto).")
    opciones = {f"{formato.fecha(e.fecha)} · {e.nombre} · {formato.dinero(a_pesos(abs(e.centavos)))}": e
                for e in eventos}
    elegido = st.selectbox("¿Cuál?", list(opciones), key="cal_registrar")
    evento = opciones[elegido]
    hoy = lib.hoy()
    with st.form("cal_registrar_form", border=False):
        a, b, c = st.columns(3)
        fecha = a.date_input("Fecha", value=min(evento.fecha, hoy), format="DD/MM/YYYY")
        monto = b.number_input("Importe", min_value=0.01, value=float(a_pesos(abs(evento.centavos))), step=1.0,
                               format="%.2f")
        cuentas_ = [cu.id for cu in lib.cuentas() if cu.activa and cu.tipo in TIPOS_DE_CUENTA]
        cuenta = c.selectbox("Cuenta", cuentas_, index=cuentas_.index(evento.cuenta_id)
                             if evento.cuenta_id in cuentas_ else 0, format_func=lambda i: lib.cuenta(i).nombre)
        if st.form_submit_button("Registrar", type="primary", icon=":material/check:"):
            if aplicar(lambda li: recurrentes.registrar(li, evento.recurrente_id, fecha, monto, cuenta_id=cuenta),
                       f"Registrado: {evento.nombre}"):
                st.rerun()


# ------------------------------------------------------------- pagos fijos


def _fijos() -> None:
    lib = libro()
    t = recurrentes.totales(lib)
    a, b, c, d = st.columns(4)
    a.metric("Suscripciones al mes", formato.dinero(t.suscripciones_al_mes), help=f"{t.suscripciones} suscripción(es).")
    b.metric("Suscripciones al año", formato.dinero(t.suscripciones_al_anio))
    c.metric("Pagos fijos al mes", formato.dinero(t.gastos_al_mes), help="Todos tus gastos fijos, con suscripciones.")
    d.metric("Ingresos fijos al mes", formato.dinero(t.ingresos_al_mes))
    if t.suscripciones_al_anio:
        st.caption(f"💡 Tus suscripciones te cuestan **{formato.dinero_md(t.suscripciones_al_anio)} al año**. ¿Usas "
                   "todas? Cancelar una que no usas es ahorro seguro.")
    lista = lib.recurrentes()
    if lista:
        hoy = lib.hoy()
        tabla = pd.DataFrame({
            "Nombre": [("⭐ " if r.suscripcion else "") + r.nombre for r in lista],
            "Qué es": [TIPOS[r.tipo] for r in lista],
            "Cuenta": [lib.cuenta(r.cuenta_id).nombre for r in lista],
            "Subcategoría o destino": [_destino(lib, r) for r in lista],
            "Importe": [formato.dinero(a_pesos(r.monto)) + (f" / {formato.dinero(a_pesos(r.monto_2))}" if r.monto_2 else "")
                        for r in lista],
            "Cada cuánto": [recurrentes.FRECUENCIAS[r.frecuencia].split(" (")[0] for r in lista],
            "Al mes": [formato.dinero(recurrentes.al_mes(r)) for r in lista],
            "Próxima vez": [recurrentes.siguiente(r, hoy) if r.activa else None for r in lista],
            "Activo": ["Sí" if r.activa else "Pausado" for r in lista],
        })
        st.caption("Haz clic en un renglón para editarlo, pausarlo o borrarlo.")
        seleccion = st.dataframe(tabla, hide_index=True, width="stretch", on_select="rerun",
                                 selection_mode="single-row", key="cal_sel",
                                 column_config={"Próxima vez": st.column_config.DateColumn(format="DD/MM/YYYY")})
        filas = seleccion.selection.rows if seleccion else []
        if filas:
            _editar(lista[filas[0]])
    with st.expander("➕ Agregar un pago fijo, suscripción o ingreso", expanded=not lista):
        _formulario(None)


def _destino(lib, r: Recurrente) -> str:
    if r.tipo is TipoOperacion.TRANSFERENCIA:
        return f"↔ {lib.cuenta(r.destino_id).nombre}"
    return categorias.etiqueta(lib, r.categoria_id) if r.categoria_id else "❓ Elige la subcategoría"


def _editar(r: Recurrente) -> None:
    with st.container(border=True):
        st.markdown(f"#### Editar «{formato.md(r.nombre)}»")
        _formulario(r)
        a, b, _ = st.columns([1, 1, 3])
        if a.button("Reanudar" if not r.activa else "Pausar", key=f"cal_pausar_{r.id}",
                    help="Pausado no aparece en el calendario, pero no se borra."):
            if ejecutar(lambda li: recurrentes.editar(li, r.id, activa=not r.activa),
                        "Reanudado" if not r.activa else "Pausado"):
                st.rerun()
        if b.button("Borrar", key=f"cal_borrar_{r.id}", help="Tus movimientos ya registrados no se borran."):
            if ejecutar(lambda li: recurrentes.eliminar(li, r.id), f"Se borró «{r.nombre}»"):
                st.session_state.pop("cal_sel", None)
                st.rerun()


def _formulario(r: Recurrente | None) -> None:
    lib = libro()
    clave = r.id if r else "nuevo"
    tipo = st.radio("¿Qué es?", list(TIPOS), format_func=TIPOS.get, horizontal=True, key=f"cal_tipo_{clave}",
                    index=list(TIPOS).index(r.tipo) if r else 0)
    cuentas_ = [c.id for c in lib.cuentas() if c.activa and c.tipo in TIPOS_DE_CUENTA]
    if not cuentas_:
        st.info("Primero crea una cuenta en **Cuentas**.")
        return
    with st.form(f"cal_form_{clave}", clear_on_submit=r is None, border=False):
        a, b = st.columns([2, 1])
        nombre = a.text_input("Nombre", value=r.nombre if r else "",
                              placeholder="Renta, Luz, Netflix, Nómina…")
        monto = b.number_input("Importe (aproximado)", min_value=0.0, step=10.0, format="%.2f",
                               value=float(a_pesos(r.monto)) if r else 0.0,
                               help="Si cambia cada vez (como la luz), pon lo usual: es para planear.")
        a, b = st.columns(2)
        cuenta = a.selectbox("Entra a la cuenta" if tipo is TipoOperacion.INGRESO else "Sale de la cuenta", cuentas_,
                             index=cuentas_.index(r.cuenta_id) if r and r.cuenta_id in cuentas_ else 0,
                             format_func=lambda i: lib.cuenta(i).nombre,
                             help="Si lo pagas con tarjeta de crédito, elige la tarjeta.")
        categoria = destino = None
        if tipo is TipoOperacion.TRANSFERENCIA:
            destino = b.selectbox("A la cuenta", cuentas_, format_func=lambda i: lib.cuenta(i).nombre,
                                  index=cuentas_.index(r.destino_id) if r and r.destino_id in cuentas_ else None,
                                  placeholder="Elige la cuenta")
        else:
            clase = ClaseCategoria.GASTO if tipo is TipoOperacion.GASTO else ClaseCategoria.INGRESO
            subs = categorias.ordenadas(lib, [c for c in lib.categorias()
                                              if c.rubro_id and c.activa and c.clase is clase])
            ids = [c.id for c in subs]
            categoria = b.selectbox("Subcategoría", ids, format_func=lambda i: categorias.etiqueta(lib, i),
                                    index=ids.index(r.categoria_id) if r and r.categoria_id in ids else None,
                                    placeholder="Escribe para buscar")
        a, b, c = st.columns(3)
        frecuencias = list(recurrentes.FRECUENCIAS)
        frecuencia = a.selectbox("Cada cuánto", frecuencias, format_func=recurrentes.FRECUENCIAS.get,
                                 index=frecuencias.index(r.frecuencia) if r else 0)
        inicio = b.date_input("La próxima vez (o la primera)", value=r.inicio if r else lib.hoy(),
                              format="DD/MM/YYYY", help="Marca el día: si es el 5, se repite cada día 5.")
        fin = c.date_input("Termina (opcional)", value=r.fin if r else None, format="DD/MM/YYYY",
                           help="Por ejemplo, la última mensualidad. Vacío si no termina.")
        a, b = st.columns([2, 1], vertical_alignment="bottom")
        suscripcion = a.checkbox("Es una suscripción (Netflix, Spotify, gimnasio, apps…)",
                                 value=r.suscripcion if r else False,
                                 disabled=tipo is not TipoOperacion.GASTO)
        opciones_fs = list(recurrentes.FIN_DE_SEMANA)
        fin_de_semana = b.selectbox("Si cae en sábado o domingo", opciones_fs, format_func=recurrentes.FIN_DE_SEMANA.get,
                                    index=opciones_fs.index(r.fin_de_semana) if r else 0)
        if st.form_submit_button("Guardar cambios" if r else "Agregar", type="primary"):
            datos = dict(nombre=nombre, tipo=tipo, monto=monto, cuenta_id=cuenta, frecuencia=frecuencia,
                         inicio=inicio, categoria_id=categoria, destino_id=destino, fin=fin,
                         suscripcion=suscripcion and tipo is TipoOperacion.GASTO, fin_de_semana=fin_de_semana)
            if r:
                hecho = ejecutar(lambda li: recurrentes.editar(li, r.id, **datos), "Cambios guardados")
            else:
                hecho = ejecutar(lambda li: recurrentes.crear(li, **datos), f"Se agregó «{nombre.strip()}»")
            if hecho:
                st.rerun()


# ------------------------------------------------------------- sugerencias


def _sugerencias(sugerencias) -> None:
    lib = libro()
    if not sugerencias:
        st.info("Por ahora no encontré nada nuevo que se repita. TALLY busca en los últimos 6 meses los gastos e "
                "ingresos que se repiten cada mes (o cada quincena) casi igual, al menos 3 veces.", icon="✨")
        return
    st.caption("En tu historial, esto se repite cada mes (o cada quincena) casi igual. Agrégalo y aparecerá en tu "
               "calendario.")
    for n, s in enumerate(sugerencias):
        with st.container(border=True):
            a, b = st.columns([4, 1], vertical_alignment="center")
            sentido = "Entra" if s.tipo is TipoOperacion.INGRESO else "Sale"
            a.markdown(f"{'⭐ ' if s.suscripcion else ''}**{formato.md(s.nombre)}** · {sentido} "
                       f"{formato.dinero_md(s.monto)} {recurrentes.FRECUENCIAS[s.frecuencia].lower()}  \n"
                       f":gray[{categorias.etiqueta(lib, s.categoria_id)} · {lib.cuenta(s.cuenta_id).nombre} · "
                       f"se repitió {s.veces} veces · la próxima sería el {formato.fecha(s.siguiente)}]")
            if b.button("Agregar", key=f"cal_sugerencia_{n}", type="primary", width="stretch"):
                if ejecutar(lambda li, s=s: recurrentes.agregar_sugerencia(li, s), f"Se agregó «{s.nombre}»"):
                    st.rerun()


def proximos_avisos(dias: int = 3) -> None:
    """Para el Resumen: pagos fijos vencidos o que tocan en los próximos días (las tarjetas ya tienen su aviso)."""
    lib = libro()
    hoy = lib.hoy()
    eventos = [e for e in recurrentes.calendario(lib, hoy, dias)
               if e.clase == recurrentes.RECURRENTE and e.estado != recurrentes.PAGADO]
    if not eventos:
        return
    partes = []
    for e in eventos:
        dias_ = (e.fecha - hoy).days
        cuando = ("venció el " + formato.fecha(e.fecha) if dias_ < 0 else "hoy" if dias_ == 0
                  else "mañana" if dias_ == 1 else f"en {dias_} días")
        partes.append(f"**{formato.md(e.nombre)}** {formato.dinero_md(a_pesos(abs(e.centavos)))} ({cuando})")
    vencido = any(e.estado == recurrentes.VENCIDO for e in eventos)
    (st.warning if vencido else st.info)("Próximos pagos: " + "; ".join(partes) + ".", icon="📅")
    navegacion.enlace("calendario", "Ver calendario", "📅")
