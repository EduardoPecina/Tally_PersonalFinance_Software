"""Metas de ahorro y fondo de emergencia (motor/metas.py): cuánto llevas, cuánto apartar al mes y cuándo llegas."""

from __future__ import annotations

import streamlit as st

from motor import metas
from motor.dinero import a_pesos
from motor.modelo import Meta, TipoCuenta
from portal.componentes import formato
from portal.componentes.sesion import avisar, ejecutar, libro

CUENTAS_DE_AHORRO = (TipoCuenta.DEBITO, TipoCuenta.AHORRO, TipoCuenta.INVERSION, TipoCuenta.EFECTIVO, TipoCuenta.OTRA)
SIN_CUENTA = "(no la separo en una cuenta)"


def mostrar() -> None:
    st.title("Metas de ahorro")
    st.caption("Ponle nombre a tu ahorro: un viaje, una computadora, el enganche… TALLY te dice cuánto apartar al mes "
               "y cuándo llegas. Empieza por tu fondo de emergencia.")
    _fondo()
    st.divider()
    _metas()
    _avisos_de_cuentas()


# ------------------------------------------------------------- fondo de emergencia


def _fondo() -> None:
    lib = libro()
    f = metas.fondo(lib)
    st.subheader("🛟 Fondo de emergencia")
    if f.meta is None:
        st.markdown("Es dinero **solo para imprevistos**: si te quedas sin trabajo, te enfermas o se descompone el "
                    "auto. Con él no tienes que endeudarte con la tarjeta. Lo recomendable es tener de **3 a 6 meses** "
                    "de tus gastos esenciales, en una cuenta aparte que puedas sacar rápido.")
        if f.esencial_al_mes > 0:
            a, b, c = st.columns(3)
            a.metric("Gastos esenciales al mes", formato.dinero_metrica(f.esencial_al_mes),
                     help="Promedio de los últimos 3 meses de lo que clasificaste como Necesidad y Compromisos, más "
                          "los pagos de tus préstamos.")
            b.metric("Mínimo (3 meses)", formato.dinero_metrica(f.recomendado_minimo))
            c.metric("Ideal (6 meses)", formato.dinero_metrica(f.recomendado_ideal))
        else:
            st.info("Cuando registres tus gastos de algunos meses, TALLY calculará cuánto te conviene juntar. Mientras, "
                    "escribe tú el objetivo.", icon="💡")
        with st.expander("Crear mi fondo de emergencia", expanded=False):
            _formulario(None, emergencia=True, sugerido=f.recomendado_minimo)
        return
    _tarjeta(f.meta, cubiertos=f.meses_cubiertos, esencial=f.esencial_al_mes)


# ------------------------------------------------------------- metas


def _metas() -> None:
    lib = libro()
    activas = [m for m in lib.metas() if m.activa and not m.emergencia]
    ahorrado, objetivo = metas.totales(lib)
    st.subheader("🏆 Tus metas")
    if activas:
        st.caption(f"En todas tus metas llevas {formato.dinero_md(ahorrado)} de {formato.dinero_md(objetivo)}.")
        for m in activas:
            _tarjeta(m)
    else:
        st.caption("Aún no tienes metas. Crea la primera abajo.")
    with st.expander("➕ Nueva meta", expanded=not activas):
        _formulario(None)
    terminadas = [m for m in lib.metas() if not m.activa]
    if terminadas:
        with st.expander(f"Logradas y archivadas ({len(terminadas)})"):
            for m in terminadas:
                a, b = st.columns([4, 1], vertical_alignment="center")
                a.markdown(f"**{formato.md(m.nombre)}** · {formato.dinero_md(a_pesos(metas.ahorrado(m)))} de "
                           f"{formato.dinero_md(a_pesos(m.objetivo))}")
                if b.button("Reactivar", key=f"meta_reactivar_{m.id}"):
                    if ejecutar(lambda li, m=m: metas.editar(li, m.id, activa=True), "Meta reactivada"):
                        st.rerun()


def _tarjeta(m: Meta, *, cubiertos=None, esencial=None) -> None:
    lib = libro()
    e = metas.estado(m, lib.hoy())
    with st.container(border=True):
        cuenta = f" · en {lib.cuenta(m.cuenta_id).nombre}" if m.cuenta_id else ""
        st.markdown(f"#### {'🎉 ' if e.lograda else ''}{formato.md(m.nombre)}")
        st.progress(e.porcentaje / 100, text=f"{formato.dinero_md(e.ahorrado)} de "
                                             f"{formato.dinero_md(a_pesos(m.objetivo))} ({e.porcentaje} %)"
                                             f"{formato.md(cuenta)}")
        if e.lograda:
            st.success("¡Lo lograste! 🎉" + ("" if m.emergencia else " Puedes archivarla en «Editar»."), icon="🏆")
        else:
            partes = [f"Te faltan **{formato.dinero_md(e.falta)}**."]
            if e.por_mes is not None:
                partes.append(f"Para llegar al {formato.fecha_larga(m.fecha_limite)}, aparta "
                              f"**{formato.dinero_md(e.por_mes)} al mes** ({e.meses_restantes} mes(es)).")
            if e.ritmo > 0:
                partes.append(f"A tu ritmo ({formato.dinero_md(e.ritmo)} al mes) llegarías el "
                              f"{formato.fecha_larga(e.fecha_estimada)}.")
            elif m.aportes:
                partes.append("En los últimos 3 meses no le has aportado.")
            st.markdown(" ".join(partes))
            if e.a_tiempo is False:
                st.warning("A este ritmo no llegas a la fecha: aporta un poco más cada mes o mueve la fecha.",
                           icon="⏳")
            elif e.a_tiempo:
                st.caption("✅ Vas a tiempo.")
        if m.emergencia and cubiertos is not None:
            texto = f"Tu fondo te cubre **{cubiertos} meses** de gastos esenciales ({formato.dinero_md(esencial)} al mes)."
            if cubiertos >= metas.MESES_FONDO[1]:
                st.success(texto + " ¡Excelente!", icon="🛟")
            elif cubiertos >= metas.MESES_FONDO[0]:
                st.info(texto + " Ya tienes lo mínimo recomendado; lo ideal son 6.", icon="🛟")
            else:
                st.warning(texto + " Lo recomendable son al menos 3.", icon="🛟")
        with st.expander("Aportar, retirar o editar"):
            aportar, retirar, editar = st.tabs(["➕ Aportar", "➖ Retirar", "✏️ Editar"])
            with aportar:
                _movimiento(m, retiro=False)
            with retirar:
                _movimiento(m, retiro=True)
            with editar:
                _formulario(m, emergencia=m.emergencia)
                a, b = st.columns(2)
                if a.button("Archivar" if not e.lograda else "Archivar (lograda)", key=f"meta_archivar_{m.id}"):
                    if ejecutar(lambda li: metas.editar(li, m.id, activa=False), "Meta archivada"):
                        st.rerun()
                if b.button("Borrar", key=f"meta_borrar_{m.id}",
                            help="Borra la meta. Las transferencias que hiciste no se borran: el dinero sigue en su "
                                 "cuenta."):
                    if ejecutar(lambda li: metas.eliminar(li, m.id), f"Se borró «{m.nombre}»"):
                        st.rerun()


def _cuentas() -> list[str]:
    lib = libro()
    return [c.id for c in lib.cuentas() if c.activa and c.tipo in CUENTAS_DE_AHORRO]


def _movimiento(m: Meta, *, retiro: bool) -> None:
    lib = libro()
    cuentas = _cuentas()
    with st.form(f"meta_{'retiro' if retiro else 'aporte'}_{m.id}", clear_on_submit=True, border=False):
        a, b, c = st.columns(3)
        monto = a.number_input("¿Cuánto?", min_value=0.0, step=100.0, format="%.2f")
        fecha = b.date_input("Fecha", value=lib.hoy(), format="DD/MM/YYYY")
        otra = None
        if m.cuenta_id:
            opciones = [None, *[i for i in cuentas if i != m.cuenta_id]]
            if retiro:
                otra = c.selectbox("¿A qué cuenta lo pasas?", opciones,
                                   format_func=lambda i: "Lo dejo ahí (solo lo marco)" if i is None
                                   else lib.cuenta(i).nombre,
                                   help="Si eliges una cuenta, TALLY registra la transferencia.")
            else:
                otra = c.selectbox("¿De qué cuenta sale?", opciones,
                                   format_func=lambda i: f"Ya está en {lib.cuenta(m.cuenta_id).nombre}" if i is None
                                   else lib.cuenta(i).nombre,
                                   help=f"Si eliges otra cuenta, TALLY registra la transferencia a "
                                        f"{lib.cuenta(m.cuenta_id).nombre}.")
        if st.form_submit_button("Retirar" if retiro else "Aportar", type="primary"):
            antes = metas.estado(m, lib.hoy()).lograda
            if retiro:
                hecho = ejecutar(lambda li: metas.retirar(li, m.id, monto, fecha, hacia=otra),
                                 f"Retiraste de «{m.nombre}»")
            else:
                hecho = ejecutar(lambda li: metas.aportar(li, m.id, monto, fecha, desde=otra),
                                 f"Aportaste a «{m.nombre}»")
            if hecho:
                if not retiro and not antes and metas.estado(libro().meta(m.id), lib.hoy()).lograda:
                    avisar(f"¡Lograste tu meta «{m.nombre}»!", "🎉")
                st.rerun()


def _formulario(m: Meta | None, *, emergencia: bool = False, sugerido=None) -> None:
    lib = libro()
    clave = m.id if m else ("emergencia" if emergencia else "nueva")
    cuentas = _cuentas()
    with st.form(f"meta_form_{clave}", clear_on_submit=m is None, border=False):
        a, b = st.columns([2, 1])
        nombre = a.text_input("Nombre", value=m.nombre if m else ("Fondo de emergencia" if emergencia else ""),
                              placeholder="Viaje, computadora, enganche…")
        objetivo = b.number_input("¿Cuánto quieres juntar?", min_value=0.0, step=500.0, format="%.2f",
                                  value=float(a_pesos(m.objetivo)) if m else float(sugerido or 0))
        a, b, c = st.columns(3)
        opciones = [None, *cuentas]
        cuenta = a.selectbox("¿Dónde guardas ese dinero?", opciones,
                             index=opciones.index(m.cuenta_id) if m and m.cuenta_id in opciones else 0,
                             format_func=lambda i: SIN_CUENTA if i is None else lib.cuenta(i).nombre,
                             help="Lo ideal: una cuenta de ahorro aparte. Así no te lo gastas sin querer.")
        fecha = b.date_input("¿Para cuándo? (opcional)", value=m.fecha_limite if m else None, format="DD/MM/YYYY")
        ya_tengo = 0.0
        if m is None:
            ya_tengo = c.number_input("¿Ya tienes algo apartado?", min_value=0.0, step=100.0, format="%.2f",
                                      help="No mueve dinero: solo lo cuenta para tu meta.")
        if st.form_submit_button("Guardar cambios" if m else "Crear meta", type="primary"):
            if m:
                hecho = ejecutar(lambda li: metas.editar(li, m.id, nombre=nombre, objetivo=objetivo,
                                                         cuenta_id=cuenta, fecha_limite=fecha), "Cambios guardados")
            else:
                hecho = ejecutar(lambda li: metas.crear(li, nombre, objetivo, cuenta_id=cuenta, fecha_limite=fecha,
                                                        emergencia=emergencia, ya_tengo=ya_tengo),
                                 f"Se creó «{nombre.strip()}»")
            if hecho:
                st.rerun()


def _avisos_de_cuentas() -> None:
    lib = libro()
    for c in metas.por_cuenta(lib):
        if c.libre < 0:
            st.warning(f"Tus metas dicen que tienes {formato.dinero_md(c.apartado)} en "
                       f"**{formato.md(lib.cuenta(c.cuenta_id).nombre)}**, pero la cuenta tiene "
                       f"{formato.dinero_md(c.saldo)}. Quizá sacaste dinero de ahí: registra un retiro en la meta o "
                       "vuelve a poner ese dinero.", icon="⚠️")
