"""Deudas: tus tarjetas y préstamos, cuánto pagar, cuánto te cuesta y cómo salir sin ahogarte."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import categorias, cuentas, planeacion, prestamos, tarjetas
from motor.modelo import ClaseCategoria, TipoCuenta
from portal import navegacion
from portal.componentes import formato, graficas
from portal.componentes.sesion import ejecutar, libro

ELEGIDO = "deuda_elegida"
NIVELES = {"sana": ("✅", "success", "Vas bien: tus deudas son menos del 30 % de tu ingreso."),
           "alta": ("⚠️", "warning", "Cuidado: entre 30 % y 40 % de tu ingreso se va en deudas. Evita deudas nuevas."),
           "riesgo": ("🔴", "error", "Más del 40 % de tu ingreso se va en deudas: te puedes quedar sin para lo "
                                    "básico. Prioriza pagar y no contrates más.")}


def mostrar() -> None:
    st.title("Deudas")
    st.caption("Tus tarjetas y préstamos: cuánto debes, cuánto pagar, cuánto te cuestan en intereses y cómo terminar "
               "antes. Los cálculos son **estimaciones**; lo oficial es tu estado de cuenta.")
    _capacidad()
    st.divider()
    _tarjetas()
    st.divider()
    _prestamos()


# --------------------------------------------------------- capacidad de pago


def _capacidad() -> None:
    lib = libro()
    cap = planeacion.capacidad(lib)
    st.subheader("¿Cuánto de tu ingreso se va en deudas?")
    if not cap.ingreso:
        st.info("Para saberlo, marca tu **ingreso principal** (y tus ingresos fijos) en **Presupuestos → Tus "
                "ingresos**, o escribe cuánto ganas al mes.")
        navegacion.enlace("presupuestos", "Ir a Presupuestos", "🎯")
        return
    a, b, c, d = st.columns(4)
    a.metric("Ingreso esperado al mes", formato.dinero(cap.ingreso))
    b.metric("Pagos de deudas al mes", formato.dinero(cap.compromisos),
             help=f"Préstamos {formato.dinero(cap.prestamos)} + pagos mínimos de tarjetas "
                  f"{formato.dinero(cap.minimos_tarjetas)}.")
    c.metric("Parte de tu ingreso", f"{cap.porcentaje} %")
    d.metric("Te queda para vivir", formato.dinero(cap.libre))
    st.progress(min(float(cap.porcentaje) / 100, 1.0))
    icono, tipo, texto = NIVELES[cap.nivel]
    getattr(st, tipo)(f"{texto} Lo máximo sano serían {formato.dinero_md(cap.maximo_sano)} al mes.", icon=icono)
    if cap.para_no_generar_intereses > cap.minimos_tarjetas:
        st.caption(f"De tus tarjetas, para **no pagar intereses** necesitas pagar "
                   f"{formato.dinero_md(cap.para_no_generar_intereses)}, no solo el mínimo.")


# ------------------------------------------------------------------ tarjetas


def _tarjetas() -> None:
    lib = libro()
    st.subheader("Tarjetas de crédito")
    lista = [c for c in cuentas.listar(lib) if c.tipo is TipoCuenta.CREDITO]
    if not lista:
        st.caption("No tienes tarjetas de crédito registradas.")
        return
    for tarjeta in lista:
        estado = tarjetas.estado(lib, tarjeta.id)
        minimo = tarjetas.pago_minimo_estimado(lib, tarjeta.id)
        with st.container(border=True):
            st.markdown(f"**{formato.md(tarjeta.nombre)}**" + (f" · CAT {tarjeta.cat.normalize():f} %"
                                                               if tarjeta.cat else ""))
            a, b, c = st.columns(3)
            a.metric("Debes hoy", formato.dinero(estado.deuda))
            if minimo is None:
                b.metric("Para no generar intereses", formato.dinero(0))
                c.metric("Pago mínimo estimado", "—")
                st.caption("Nada por pagar del último corte." if estado.corte else
                           "Registra su día de corte (Cuentas → Editar) para calcular sus pagos.")
            else:
                b.metric("Para no generar intereses", formato.dinero(minimo.para_no_generar_intereses))
                c.metric("Pago mínimo estimado", formato.dinero(minimo.minimo),
                         help="Regla del Banco de México: el mayor entre 1.5 % del saldo más intereses e IVA, y "
                              "1.25 % de tu línea. Cada banco lo calcula a su manera: el oficial es el de tu "
                              "estado de cuenta.")
                if minimo.meses_solo_minimo is not None:
                    st.warning(f"Si pagas **solo el mínimo** (y no compras más), tardarías **"
                               f"{_tiempo(minimo.meses_solo_minimo)}** en liquidarla y pagarías cerca de "
                               f"**{formato.dinero_md(minimo.intereses_solo_minimo)} de intereses**. Paga "
                               f"{formato.dinero_md(minimo.para_no_generar_intereses)} y no pagas nada.", icon="💸")
                elif not minimo.con_tasa:
                    st.caption("Registra su **tasa anual** abajo para estimar intereses y cuánto te costaría pagar "
                               "solo el mínimo.")
            _tasa_de_tarjeta(tarjeta)


def _tasa_de_tarjeta(tarjeta) -> None:
    with st.expander("Tasa, CAT e IVA de esta tarjeta"):
        with st.form(f"tasa_{tarjeta.id}", border=False):
            a, b = st.columns(2)
            tasa = a.number_input("Tasa de interés anual (%)", min_value=0.0, max_value=1000.0, step=1.0,
                                  format="%.2f", value=float(tarjeta.tasa_anual) if tarjeta.tasa_anual else None,
                                  help="La tasa ordinaria anual de tu contrato o estado de cuenta.")
            cat = b.number_input("CAT (%) · informativo", min_value=0.0, max_value=1000.0, step=1.0, format="%.2f",
                                 value=float(tarjeta.cat) if tarjeta.cat else None,
                                 help="Costo Anual Total (México). En otros países: TAE (España), CAE (Chile), CFT "
                                      "(Argentina), TEA (Perú, Colombia).")
            incluye = st.checkbox("La tasa ya incluye IVA", value=tarjeta.tasa_incluye_iva)
            if st.form_submit_button("Guardar"):
                if ejecutar(lambda lib: cuentas.editar(lib, tarjeta.id, tasa_anual=tasa, cat=cat,
                                                       tasa_incluye_iva=incluye), exito="Tasa guardada"):
                    st.rerun()


def _tiempo(meses: int) -> str:
    anios, resto = divmod(meses, 12)
    if not anios:
        return f"{meses} meses"
    return f"{anios} año{'s' if anios > 1 else ''}" + (f" y {resto} meses" if resto else "")


# ------------------------------------------------------------------ préstamos


def _prestamos() -> None:
    lib = libro()
    st.subheader("Préstamos")
    with st.expander("➕ Agregar un préstamo", expanded=not lib.prestamos()):
        _formulario_nuevo()
    todos = [p for p in lib.prestamos() if lib.cuenta(p.cuenta_id).activa]
    if not todos:
        return
    resumen = []
    for p in todos:
        e = prestamos.estado(lib, p.cuenta_id)
        resumen.append({"Préstamo": lib.cuenta(p.cuenta_id).nombre,
                        "Tipo": prestamos.CLASES.get(p.clase, prestamos.CLASES["otro"]).nombre,
                        "Debes": formato.dinero(e.deuda), "Pago mensual": formato.dinero(e.pago_mensual),
                        "Tasa anual": f"{p.tasa_anual.normalize():f} %",
                        "Te faltan": "Liquidado ✓" if e.liquidado else (_tiempo(e.proyeccion.meses)
                                                                        if e.proyeccion.alcanza else "—")})
    st.dataframe(pd.DataFrame(resumen), hide_index=True, width="stretch")
    nombres = {p.cuenta_id: lib.cuenta(p.cuenta_id).nombre for p in todos}
    if st.session_state.get(ELEGIDO) not in nombres:
        st.session_state[ELEGIDO] = todos[0].cuenta_id
    cuenta_id = st.selectbox("Ver y administrar", list(nombres), format_func=nombres.get, key=ELEGIDO)
    _detalle(cuenta_id)


def _detalle(cuenta_id: str) -> None:
    lib = libro()
    p = lib.prestamo(cuenta_id)
    e = prestamos.estado(lib, cuenta_id)
    st.markdown(f"#### {formato.md(lib.cuenta(cuenta_id).nombre)}")
    st.caption(f"{prestamos.CLASES.get(p.clase, prestamos.CLASES['otro']).nombre} · solicitaste "
               f"{formato.dinero_md(Decimal(p.monto) / 100)} al {p.tasa_anual.normalize():f} % anual"
               f"{' + IVA' if prestamos.iva_de(lib, p) else ''} a {p.plazo_meses} meses, desde el "
               f"{formato.fecha(p.fecha_inicio)}" + (f" · CAT {p.cat.normalize():f} %" if p.cat else ""))
    a, b, c, d = st.columns(4)
    a.metric("Debes hoy", formato.dinero(e.deuda))
    b.metric("Pago mensual", formato.dinero(e.pago_mensual),
             help="El pactado si lo registraste; si no, el que da la tabla del contrato.")
    c.metric("Intereses + IVA de este mes", formato.dinero(e.interes_del_mes),
             help="Lo que se come el interés de tu pago este mes; el resto baja tu deuda.")
    if e.liquidado:
        d.metric("Te faltan", "Liquidado ✓")
    elif e.proyeccion.alcanza:
        d.metric("Te faltan", _tiempo(e.proyeccion.meses), help=f"Terminarías el {formato.fecha(e.proyeccion.fin)} "
                 f"y pagarías {formato.dinero(e.proyeccion.intereses)} más de intereses.")
    else:
        d.metric("Te faltan", "Nunca")
        st.error("Con ese pago **no cubres ni los intereses**: tu deuda no baja. Aumenta tu pago o habla con tu "
                 "banco para reestructurar.", icon="🔴")
    st.caption(f"Has pagado {formato.dinero_md(e.pagado)} · intereses, IVA y cargos sumados: "
               f"{formato.dinero_md(e.intereses_pagados)}" + (f" · próximo pago: {formato.fecha(e.proximo_pago)}"
                                                              if e.proximo_pago else ""))
    if not e.liquidado:
        _recomendaciones(cuenta_id, e)
    pagar, cargo, simular, tabla, datos = st.tabs(["Registrar pago", "Cargo o mora", "Simulador",
                                                   "Tabla de amortización", "Datos del contrato"])
    with pagar:
        _pagar(cuenta_id)
    with cargo:
        _cargo(cuenta_id)
    with simular:
        _simulador(cuenta_id, e)
    with tabla:
        _tabla(cuenta_id)
    with datos:
        _datos(cuenta_id)


def _recomendaciones(cuenta_id: str, e: prestamos.Estado) -> None:
    lib = libro()
    filas = []
    if e.proyeccion.alcanza:
        filas.append(("Tu pago actual", e.proyeccion))
    filas += e.sugerencias
    if e.meses_contrato_restantes and e.proyeccion.alcanza and e.proyeccion.meses > e.meses_contrato_restantes:
        pago = prestamos.pago_para_terminar_en(lib, cuenta_id, e.meses_contrato_restantes)
        filas.append((f"Terminar en el plazo del contrato ({e.meses_contrato_restantes} meses)",
                      prestamos.proyectar(lib, cuenta_id, pago=pago)))
    if not filas:
        return
    base = e.proyeccion.intereses if e.proyeccion.alcanza else None
    st.markdown("**¿Cuánto pagar para salir antes?**")
    st.dataframe(pd.DataFrame({
        "Si pagas al mes": [f"{n} · {formato.dinero(p.pago)}" for n, p in filas],
        "Terminas en": [_tiempo(p.meses) if p.alcanza else "Nunca" for _, p in filas],
        "Intereses + IVA por pagar": [formato.dinero(p.intereses) for _, p in filas],
        "Te ahorras": [formato.dinero(base - p.intereses) if base is not None and p.alcanza and base > p.intereses
                       else "—" for _, p in filas],
    }), hide_index=True, width="stretch")
    cap = planeacion.capacidad(lib)
    if cap.ingreso and cap.libre > 0:
        st.caption(f"Antes de subir tu pago, revisa que te quede para lo básico: después de tus deudas te quedan "
                   f"{formato.dinero_md(cap.libre)} al mes. Prueba otras cantidades en el **Simulador**.")


def _cuentas_de_pago() -> dict[str, str]:
    lib = libro()
    return {c.id: c.nombre for c in cuentas.listar(lib)
            if c.tipo not in (TipoCuenta.PRESTAMO, TipoCuenta.BIEN, TipoCuenta.CREDITO)}


def _subcategorias_gasto() -> dict[str, str]:
    lib = libro()
    return {c.id: categorias.etiqueta(lib, c.id) for c in categorias.para_tipo(lib, "gasto")}


def _pagar(cuenta_id: str) -> None:
    lib = libro()
    interes, iva = prestamos.estimar_interes(lib, cuenta_id)
    st.caption("Copia de tu estado de cuenta cuánto fue de intereses, IVA y cargos (traemos una estimación). Lo "
               "demás de tu pago baja tu deuda (capital). Para un **abono extra a capital**, pon intereses e IVA "
               "en 0.")
    pago = _cuentas_de_pago()
    subcategorias = _subcategorias_gasto()
    sugerida = categorias.buscar(lib, prestamos.SUBCATEGORIA_CARGOS, ClaseCategoria.GASTO)
    with st.form(f"pago_{cuenta_id}", clear_on_submit=True, border=False):
        a, b = st.columns(2)
        total = a.number_input("Pagaste en total", min_value=0.0, value=float(prestamos.estado(
            lib, cuenta_id).pago_mensual), step=100.0, format="%.2f")
        fecha = b.date_input("Fecha", value=lib.hoy(), max_value=lib.hoy(), format="DD/MM/YYYY")
        origen = a.selectbox("Con qué cuenta", list(pago), format_func=pago.get)
        intereses = b.number_input("De eso, intereses", min_value=0.0, value=float(interes), step=10.0,
                                   format="%.2f")
        impuesto = a.number_input("IVA de los intereses", min_value=0.0, value=float(iva), step=1.0, format="%.2f")
        cargos = b.number_input("Cargos (mora, retraso, comisión, seguro)", min_value=0.0, value=0.0, step=10.0,
                                format="%.2f")
        ids = list(subcategorias)
        categoria = st.selectbox("Subcategoría de los cargos", ids, format_func=subcategorias.get,
                                 index=ids.index(sugerida.id) if sugerida and sugerida.id in ids else 0)
        if st.form_submit_button("Registrar pago", type="primary"):
            capital = Decimal(str(total)) - Decimal(str(intereses)) - Decimal(str(impuesto)) - Decimal(str(cargos))
            if ejecutar(lambda lib: prestamos.registrar_pago(
                    lib, cuenta_id, fecha, Decimal(str(total)), origen, interes=Decimal(str(intereses)),
                    iva=Decimal(str(impuesto)), cargos=Decimal(str(cargos)), categoria_cargos=categoria),
                    exito=f"Pago registrado: {formato.dinero(capital)} a capital"):
                st.rerun()


def _cargo(cuenta_id: str) -> None:
    lib = libro()
    st.caption("¿El banco te cobró una mora, un cargo por pago tardío o una comisión **sin que pagaras**? Regístralo "
               "aquí: es gasto y sube lo que debes.")
    subcategorias = _subcategorias_gasto()
    sugerida = categorias.buscar(lib, prestamos.SUBCATEGORIA_CARGOS, ClaseCategoria.GASTO)
    with st.form(f"cargo_{cuenta_id}", clear_on_submit=True, border=False):
        a, b = st.columns(2)
        monto = a.number_input("Monto", min_value=0.0, value=None, step=10.0, format="%.2f")
        fecha = b.date_input("Fecha", value=lib.hoy(), max_value=lib.hoy(), format="DD/MM/YYYY")
        descripcion = a.text_input("Qué fue", placeholder="Ej. Mora de julio", max_chars=80)
        ids = list(subcategorias)
        categoria = b.selectbox("Subcategoría", ids, format_func=subcategorias.get,
                                index=ids.index(sugerida.id) if sugerida and sugerida.id in ids else 0)
        if st.form_submit_button("Registrar cargo", type="primary"):
            if not monto:
                st.error("Escribe el monto.")
                return
            if ejecutar(lambda lib: prestamos.registrar_cargo(lib, cuenta_id, fecha, Decimal(str(monto)),
                                                               categoria_id=categoria, descripcion=descripcion),
                        exito="Cargo registrado"):
                st.rerun()


def _simulador(cuenta_id: str, e: prestamos.Estado) -> None:
    lib = libro()
    st.caption("Prueba cuánto pagar sin registrar nada: es solo una simulación.")
    a, b, c = st.columns(3)
    pago = a.number_input("Pago mensual", min_value=0.0, value=float(e.pago_mensual), step=100.0, format="%.2f",
                          key=f"sim_pago_{cuenta_id}")
    extra = b.number_input("Extra cada mes", min_value=0.0, value=0.0, step=100.0, format="%.2f",
                           key=f"sim_extra_{cuenta_id}")
    abono = c.number_input("Abono único hoy", min_value=0.0, value=0.0, step=1000.0, format="%.2f",
                           key=f"sim_abono_{cuenta_id}", help="Un aguinaldo, un bono, una venta…")
    simulada = prestamos.proyectar(lib, cuenta_id, pago=Decimal(str(pago)), extra_mensual=Decimal(str(extra)),
                                   abono_unico=Decimal(str(abono)))
    x, y, z = st.columns(3)
    if not simulada.alcanza:
        st.error("Con ese pago no cubres los intereses: la deuda nunca baja.", icon="🔴")
        return
    x.metric("Terminas en", _tiempo(simulada.meses) if simulada.meses else "Hoy",
             delta=(f"{e.proyeccion.meses - simulada.meses} meses antes" if e.proyeccion.alcanza
                    and e.proyeccion.meses > simulada.meses else None))
    y.metric("Intereses + IVA por pagar", formato.dinero(simulada.intereses),
             delta=(f"−{formato.dinero(e.proyeccion.intereses - simulada.intereses)}" if e.proyeccion.alcanza
                    and e.proyeccion.intereses > simulada.intereses else None), delta_color="inverse")
    z.metric("Terminarías el", formato.fecha(simulada.fin) if simulada.fin else "—")
    cap = planeacion.capacidad(lib)
    total_mes = simulada.pago
    if cap.ingreso and cap.compromisos - e.pago_mensual + total_mes > cap.ingreso * prestamos.CAPACIDAD_LIMITE / 100:
        st.warning("Con ese pago tus deudas pasarían del 40 % de tu ingreso: revisa que te alcance para lo básico.",
                   icon="⚠️")
    if simulada.tabla:
        graficas.linea([(m.fecha, m.saldo) for m in simulada.tabla], titulo_valor="Debes")


def _tabla(cuenta_id: str) -> None:
    lib = libro()
    p = lib.prestamo(cuenta_id)
    tabla = prestamos.amortizacion(lib, p)
    st.caption("La tabla del contrato: desde el monto que solicitaste, pagando el pago mensual a tiempo. Tu "
               "deuda real puede variar si pagaste de más, de menos o con retraso.")
    datos = pd.DataFrame({
        "#": [m.numero for m in tabla], "Fecha": [m.fecha for m in tabla],
        "Pago": [float(m.pago) for m in tabla], "Intereses": [float(m.interes) for m in tabla],
        "IVA": [float(m.iva) for m in tabla], "Capital": [float(m.capital) for m in tabla],
        "Debes después": [float(m.saldo) for m in tabla],
    })
    vista, config = formato.tabla_en_pesos(datos, ("Pago", "Intereses", "IVA", "Capital", "Debes después"))
    config["Fecha"] = st.column_config.DateColumn(format="DD/MM/YYYY")
    st.dataframe(vista, column_config=config, hide_index=True, width="stretch", height=min(40 + 35 * len(tabla), 460))
    st.caption(f"Total de intereses + IVA del contrato: "
               f"{formato.dinero_md(sum((m.interes + m.iva for m in tabla), Decimal(0)))}")


def _datos(cuenta_id: str) -> None:
    lib = libro()
    p = lib.prestamo(cuenta_id)
    st.caption("Corrige los datos de tu contrato: solo cambian los cálculos, no tus movimientos.")
    with st.form(f"datos_{cuenta_id}", border=False):
        a, b = st.columns(2)
        monto = a.number_input("Monto que solicitaste", min_value=0.0, value=float(Decimal(p.monto) / 100),
                               step=1000.0, format="%.2f")
        tasa = b.number_input("Tasa de interés anual (%)", min_value=0.0, max_value=1000.0,
                              value=float(p.tasa_anual), step=0.5, format="%.2f")
        plazo = a.number_input("Plazo (meses)", min_value=1, max_value=prestamos.MAXIMO_MESES, value=p.plazo_meses)
        inicio = b.date_input("Fecha en que empezó", value=p.fecha_inicio, format="DD/MM/YYYY")
        pactado = a.number_input("Pago mensual pactado (opcional)", min_value=0.0, step=100.0, format="%.2f",
                                 value=float(Decimal(p.pago_pactado) / 100) if p.pago_pactado else None,
                                 help="Si tu contrato dice un pago distinto (por ejemplo, con seguros incluidos).")
        dia = b.number_input("Día de pago (opcional)", min_value=1, max_value=31, value=p.dia_pago)
        iva = a.number_input("IVA de los intereses (%)", min_value=0.0, max_value=50.0, step=1.0, format="%.2f",
                             value=float(prestamos.iva_de(lib, p)),
                             help="En México: 16 % en préstamos personales y de auto; 0 % en hipotecas.")
        cat = b.number_input("CAT (%) · informativo", min_value=0.0, max_value=1000.0, step=1.0, format="%.2f",
                             value=float(p.cat) if p.cat else None)
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: prestamos.configurar(
                    lib, cuenta_id, monto=Decimal(str(monto)), tasa_anual=Decimal(str(tasa)), plazo_meses=int(plazo),
                    fecha_inicio=inicio, iva=Decimal(str(iva)), pago_pactado=Decimal(str(pactado)) if pactado else None,
                    dia_pago=int(dia) if dia else None, cat=Decimal(str(cat)) if cat else None),
                    exito="Datos guardados"):
                st.rerun()


def _formulario_nuevo() -> None:
    lib = libro()
    clases = list(prestamos.CLASES)
    clase = st.selectbox("Qué tipo de préstamo", clases, format_func=lambda c: prestamos.CLASES[c].nombre,
                         key="prestamo_nuevo_clase")
    if prestamos.CLASES[clase].ayuda:
        st.caption(prestamos.CLASES[clase].ayuda)
    como = st.radio("¿Cómo lo registras?", ["Lo acabo de recibir", "Ya lo tenía"], horizontal=True,
                    key="prestamo_nuevo_como",
                    help="Lo acabo de recibir: el dinero llegó a una de tus cuentas (o a un bien, como tu auto). "
                         "Ya lo tenía: escribe cuánto debes hoy.")
    destinos = {c.id: c.nombre for c in cuentas.listar(lib) if c.tipo is not TipoCuenta.PRESTAMO}
    with st.form("prestamo_nuevo", clear_on_submit=True, border=False):
        a, b = st.columns(2)
        nombre = a.text_input("Nombre", placeholder="Ej. Préstamo BBVA, Crédito auto Versa", max_chars=60)
        institucion = b.text_input("Banco o institución (opcional)", max_chars=60)
        monto = a.number_input("Monto que solicitaste", min_value=0.0, value=None, step=1000.0, format="%.2f")
        tasa = b.number_input("Tasa de interés anual (%)", min_value=0.0, max_value=1000.0, value=None, step=0.5,
                              format="%.2f", help="La tasa ordinaria anual de tu contrato (no el CAT).")
        plazo = a.number_input("Plazo (meses)", min_value=1, max_value=prestamos.MAXIMO_MESES, value=12)
        inicio = b.date_input("Fecha en que lo recibiste", value=lib.hoy(), max_value=lib.hoy(), format="DD/MM/YYYY")
        if como == "Lo acabo de recibir":
            destino = a.selectbox("¿A dónde llegó el dinero?", list(destinos), format_func=destinos.get)
            comision = b.number_input("Comisión por apertura (opcional)", min_value=0.0, value=0.0, step=100.0,
                                      format="%.2f", help="Si te la descontaron de lo que recibiste.")
            deuda = None
        else:
            destino, comision = None, 0.0
            deuda = a.number_input("¿Cuánto debes hoy?", min_value=0.0, value=None, step=1000.0, format="%.2f",
                                   help="Vacío: TALLY lo estima con la tabla del contrato.")
        pactado = b.number_input("Pago mensual pactado (opcional)", min_value=0.0, value=None, step=100.0,
                                 format="%.2f", help="Si lo sabes. Si no, TALLY lo calcula.")
        dia = a.number_input("Día de pago (opcional)", min_value=1, max_value=31, value=None)
        cat = b.number_input("CAT (%) · opcional", min_value=0.0, max_value=1000.0, value=None, step=1.0,
                             format="%.2f")
        if st.form_submit_button("Agregar préstamo", type="primary"):
            if not nombre.strip() or not monto or tasa is None:
                st.error("Escribe el nombre, el monto y la tasa (0 si no cobra intereses).")
                return
            if ejecutar(lambda lib: prestamos.crear(
                    lib, nombre, clase, Decimal(str(monto)), Decimal(str(tasa)), int(plazo), inicio, destino=destino,
                    deuda_actual=Decimal(str(deuda)) if deuda is not None else None,
                    pago_pactado=Decimal(str(pactado)) if pactado else None, dia_pago=int(dia) if dia else None,
                    cat=Decimal(str(cat)) if cat else None, comision_apertura=Decimal(str(comision)),
                    institucion=institucion), exito=f"«{nombre.strip()}» agregado"):
                st.session_state.pop(ELEGIDO, None)
                st.rerun()
