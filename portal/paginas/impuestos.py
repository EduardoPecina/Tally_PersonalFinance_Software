"""Impuestos (motor/impuestos.py): tus gastos deducibles del año y el cálculo/revisión de un recibo o factura. Para
cualquier país: tú defines las reglas, y hay plantillas para empezar."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import categorias, impuestos
from motor.dinero import a_pesos
from motor.modelo import ClaseCategoria, ConceptoDeducible, PerfilImpuestos
from portal.componentes import exportar, formato
from portal.componentes.sesion import aplicar, ejecutar, libro

SUBTOTAL = "(el subtotal)"
EFECTO = {False: "Se suma", True: "Se retiene (se resta)"}


def mostrar() -> None:
    st.title("Impuestos")
    st.caption("Tus gastos deducibles del año y el cálculo de un recibo o factura, para cualquier país: tú pones las "
               "reglas (o empiezas con una plantilla). " + impuestos.AVISO)
    deducibles, recibo, configurar = st.tabs(["🧾 Gastos deducibles", "🧮 Calcular y revisar un recibo",
                                              "⚙️ Configurar"])
    with deducibles:
        _deducibles()
    with recibo:
        _recibo()
    with configurar:
        _configurar()


# ------------------------------------------------------------- deducibles


def _deducibles() -> None:
    lib = libro()
    if not lib.fiscal.conceptos:
        st.info("Aún no tienes conceptos deducibles. En **⚙️ Configurar** agrega los tuyos (gastos médicos, "
                "colegiaturas, alquiler…) o empieza con la plantilla de tu país.", icon="🧾")
        return
    hoy = lib.hoy()
    anios = sorted({op.fecha.year for op in lib.operaciones()} | {hoy.year}, reverse=True)
    a, b = st.columns([1, 2])
    anio = a.selectbox("Año", anios, key="imp_anio")
    reporte = impuestos.deducibles(lib, anio)
    ingreso = reporte.ingreso
    if lib.fiscal.tope_porcentaje is not None:
        ingreso = Decimal(str(b.number_input(
            "Tus ingresos del año (para el tope)", min_value=0.0, step=1000.0, format="%.2f",
            value=float(reporte.ingreso), key=f"imp_ingreso_{anio}",
            help="Lo que registraste como ingreso en TALLY. Si tu ingreso para impuestos es otro, cámbialo.")))
        reporte = impuestos.deducibles(lib, anio, ingreso)
    x, y, z = st.columns(3)
    x.metric("Gastos deducibles", formato.dinero(reporte.suma))
    y.metric("Tope total", formato.dinero(reporte.tope) if reporte.tope is not None else "Sin tope",
             help=_explicar_tope(lib, ingreso))
    z.metric("Podrías deducir", formato.dinero(reporte.total))
    if reporte.tope is not None and reporte.suma - reporte.fuera_del_tope > reporte.tope:
        st.caption(f"Tus deducibles pasan del tope por "
                   f"{formato.dinero_md(reporte.suma - reporte.fuera_del_tope - reporte.tope)}: solo cuenta hasta el "
                   "tope.")
    if reporte.fuera_del_tope:
        st.caption(f"{formato.dinero_md(reporte.fuera_del_tope)} son de conceptos que no entran en el tope total.")
    st.dataframe(pd.DataFrame({
        "Concepto": [r.concepto.nombre for r in reporte.renglones],
        "Pagaste": [formato.dinero(r.pagado) for r in reporte.renglones],
        "En efectivo (no cuenta)": [formato.dinero(r.en_efectivo) if r.concepto.sin_efectivo else "—"
                                    for r in reporte.renglones],
        "Parte deducible": [f"{r.concepto.porcentaje.normalize():f} %" for r in reporte.renglones],
        "Tope": [formato.dinero(a_pesos(r.concepto.tope)) if r.concepto.tope else "—" for r in reporte.renglones],
        "Deducible": [formato.dinero(r.deducible) + (" (topado)" if r.topado else "") for r in reporte.renglones],
    }), hide_index=True, width="stretch")
    if any(r.en_efectivo for r in reporte.renglones):
        st.warning("Algunos pagos fueron **en efectivo** y no cuentan en los conceptos que lo piden. Para la próxima, "
                   "paga con tarjeta o transferencia.", icon="💵")
    for r in reporte.renglones:
        if not r.pagos:
            continue
        with st.expander(f"{r.concepto.nombre} · {len(r.pagos)} pago(s)"):
            if r.concepto.notas:
                st.caption(r.concepto.notas)
            st.dataframe(pd.DataFrame({
                "Fecha": [p.fecha for p in r.pagos], "Descripción": [p.descripcion for p in r.pagos],
                "Subcategoría": [p.subcategoria for p in r.pagos], "Cuenta": [p.cuenta for p in r.pagos],
                "Importe": [formato.dinero(p.importe) for p in r.pagos],
                "": ["💵 en efectivo" if p.en_efectivo and r.concepto.sin_efectivo else "" for p in r.pagos],
            }), hide_index=True, width="stretch",
                column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})
    filas = [{"Concepto": r.concepto.nombre, "Fecha": p.fecha, "Descripción": p.descripcion,
              "Subcategoría": p.subcategoria, "Cuenta": p.cuenta, "Importe": float(p.importe),
              "En efectivo": "Sí" if p.en_efectivo else ""} for r in reporte.renglones for p in r.pagos]
    if filas:
        st.download_button("Descargar en Excel (para tu declaración)", exportar.excel({"Deducibles": pd.DataFrame(filas)}, columnas_dinero={"Importe"}),
                           file_name=f"TALLY_deducibles_{anio}.xlsx", icon=":material/download:", on_click="ignore",
                           key="imp_excel")
    if lib.fiscal.notas:
        st.caption(f"📌 {lib.fiscal.notas}")


def _explicar_tope(lib, ingreso: Decimal) -> str:
    partes = []
    if lib.fiscal.tope_total is not None:
        partes.append(f"{formato.dinero(a_pesos(lib.fiscal.tope_total))} al año")
    if lib.fiscal.tope_porcentaje is not None:
        partes.append(f"el {lib.fiscal.tope_porcentaje.normalize():f} % de tus ingresos ({formato.dinero(ingreso)})")
    return ("El menor entre " + " y ".join(partes) + ".") if len(partes) > 1 else (
        (partes[0][0].upper() + partes[0][1:] + ".") if partes else "Sin tope total. Agrégalo en Configurar.")


# ------------------------------------------------------------- recibo


def _recibo() -> None:
    lib = libro()
    perfiles = lib.fiscal.perfiles
    if not perfiles:
        st.info("Primero agrega un perfil de impuestos en **⚙️ Configurar**: los tuyos o una plantilla (México, "
                "España, Argentina, Colombia…).", icon="🧮")
        return
    ids = [p.id for p in perfiles]
    perfil = next(p for p in perfiles if p.id == st.selectbox(
        "Perfil", ids, format_func=lambda i: next(p.nombre for p in perfiles if p.id == i), key="imp_perfil"))
    st.caption(_describir(perfil))
    a, b = st.columns(2)
    modo = a.radio("Lo que sé es…", ["El subtotal (antes de impuestos)", "Lo que recibo (o pago) en total"],
                   key="imp_modo")
    monto = b.number_input("Importe", min_value=0.0, step=100.0, format="%.2f", key="imp_monto")
    if monto:
        desglose = (impuestos.calcular(perfil, Decimal(str(monto))) if modo.startswith("El subtotal")
                    else impuestos.desde_total(perfil, Decimal(str(monto))))
        filas = [("Subtotal", desglose.subtotal)] + [
            (f"{'−' if i.retenido else '+'} {i.nombre}", -v if i.retenido else v) for i, v in desglose.lineas]
        filas.append(("Total que recibes (o pagas)", desglose.total))
        st.dataframe(pd.DataFrame({"Concepto": [n for n, _ in filas],
                                   "Importe": [formato.dinero(v) for _, v in filas]}),
                     hide_index=True, width="stretch")
    st.markdown("##### 🔎 Revisar un recibo o factura que te dieron")
    st.caption("Escribe el subtotal y lo que dice cada impuesto. TALLY te dice si cuadra con tu perfil.")
    with st.form("imp_revisar", border=False):
        subtotal = st.number_input("Subtotal del recibo", min_value=0.0, step=100.0, format="%.2f")
        columnas = st.columns(min(len(perfil.impuestos), 3))
        reales = {}
        for n, i in enumerate(perfil.impuestos):
            reales[i.nombre] = columnas[n % len(columnas)].number_input(i.nombre, min_value=0.0, step=1.0,
                                                                      format="%.2f", key=f"imp_real_{perfil.id}_{n}")
        if st.form_submit_button("Revisar", type="primary"):
            problemas = impuestos.revisar(perfil, Decimal(str(subtotal)),
                                          {k: Decimal(str(v)) for k, v in reales.items()})
            if not problemas:
                st.success("Cuadra: los impuestos del recibo son los que corresponden a tu perfil.", icon="✅")
            else:
                st.error(f"**{problemas[0]}**\n\n" + "\n".join(f"- {formato.md(p)}" for p in problemas[1:]),
                         icon="⚠️")


def _describir(perfil: PerfilImpuestos) -> str:
    partes = [f"{i.nombre} {impuestos.mostrar_tasa(i.tasa)}" + (f" de {i.sobre}" if i.sobre else "")
              + (" (retenido)" if i.retenido else "") for i in perfil.impuestos]
    return " · ".join(partes) + (f". {perfil.notas}" if perfil.notas else "")


# ------------------------------------------------------------- configurar


def _configurar() -> None:
    st.subheader("Gastos deducibles")
    _conceptos()
    st.divider()
    st.subheader("Perfiles de impuestos (para recibos y facturas)")
    _perfiles()


def _conceptos() -> None:
    lib = libro()
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    plantilla = a.selectbox("Empezar con una plantilla", list(impuestos.PLANTILLAS_DEDUCIBLES), index=None,
                            placeholder="Elige tu país (opcional)", key="imp_plantilla_ded")
    if b.button("Agregar plantilla", disabled=plantilla is None, key="imp_agregar_ded", width="stretch"):
        n = aplicar(lambda li: impuestos.agregar_plantilla_deducibles(li, plantilla))
        if n is not None:
            st.toast(f"Se agregaron {n} concepto(s). Revísalos: las reglas cambian cada año.", icon="🧾")
            st.rerun()
    for c in lib.fiscal.conceptos:
        with st.expander(f"{c.nombre} · {c.porcentaje.normalize():f} %"
                         + (f" · tope {formato.dinero(a_pesos(c.tope))}" if c.tope else "")
                         + (" · sin efectivo" if c.sin_efectivo else "")
                         + (" · fuera del tope total" if c.fuera_del_tope else "")):
            _formulario_concepto(c)
            if st.button("Borrar concepto", key=f"imp_borrar_ded_{c.id}"):
                if ejecutar(lambda li, c=c: impuestos.eliminar_concepto(li, c.id), f"Se borró «{c.nombre}»"):
                    st.rerun()
    with st.expander("➕ Nuevo concepto deducible", expanded=not lib.fiscal.conceptos):
        _formulario_concepto(None)
    with st.form("imp_topes", border=False):
        st.markdown("**Tope total** para todos tus deducibles juntos (opcional; si pones los dos, cuenta el menor)")
        a, b = st.columns(2)
        total = a.number_input("Monto al año", min_value=0.0, step=1000.0, format="%.2f",
                               value=float(a_pesos(lib.fiscal.tope_total)) if lib.fiscal.tope_total else 0.0)
        porcentaje = b.number_input("% de tus ingresos del año", min_value=0.0, max_value=100.0, step=1.0,
                                    value=float(lib.fiscal.tope_porcentaje or 0))
        if st.form_submit_button("Guardar tope"):
            if ejecutar(lambda li: impuestos.ajustar_topes(li, tope_total=total or None,
                                                           tope_porcentaje=porcentaje or None), "Tope guardado"):
                st.rerun()


def _formulario_concepto(c: ConceptoDeducible | None) -> None:
    lib = libro()
    clave = c.id if c else "nuevo"
    subs = categorias.ordenadas(lib, [x for x in lib.categorias()
                                      if x.rubro_id and x.clase is ClaseCategoria.GASTO
                                      and (x.activa or (c and x.id in c.subcategorias))])
    with st.form(f"imp_concepto_{clave}", clear_on_submit=c is None, border=False):
        nombre = st.text_input("Nombre", value=c.nombre if c else "", placeholder="Gastos médicos, colegiaturas…")
        opciones = [x.id for x in subs]
        elegidas = st.multiselect("Subcategorías que cuentan", opciones,   # una ya borrada no se ofrece
                                  default=[i for i in c.subcategorias if i in opciones] if c else [],
                                  format_func=lambda i: categorias.etiqueta(lib, i))
        a, b = st.columns(2)
        porcentaje = a.number_input("Parte deducible (%)", min_value=0.0, max_value=100.0, step=5.0,
                                    value=float(c.porcentaje) if c else 100.0,
                                    help="Casi siempre 100 %. En algunos países, ciertos gastos cuentan al 40 %.")
        tope = b.number_input("Tope al año (opcional)", min_value=0.0, step=500.0, format="%.2f",
                              value=float(a_pesos(c.tope)) if c and c.tope else 0.0)
        sin_efectivo = st.checkbox("No cuenta lo pagado en efectivo", value=c.sin_efectivo if c else False,
                                   help="En México, por ejemplo, los gastos médicos solo cuentan si los pagas con "
                                        "tarjeta o transferencia.")
        fuera = st.checkbox("No entra en el tope total", value=c.fuera_del_tope if c else False,
                            help="En México, por ejemplo, las colegiaturas y los donativos tienen su propio límite.")
        notas = st.text_input("Notas (requisitos, topes por nivel…)", value=c.notas if c else "")
        if st.form_submit_button("Guardar" if c else "Agregar concepto", type="primary"):
            if ejecutar(lambda li: impuestos.guardar_concepto(
                    li, nombre, elegidas, porcentaje=porcentaje, tope=tope or None, sin_efectivo=sin_efectivo,
                    notas=notas, fuera_del_tope=fuera, concepto_id=c.id if c else None), "Concepto guardado"):
                st.rerun()


def _perfiles() -> None:
    lib = libro()
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    plantilla = a.selectbox("Agregar una plantilla", list(impuestos.PLANTILLAS_IMPUESTOS), index=None,
                            placeholder="México, España, Argentina, Colombia…", key="imp_plantilla_imp")
    if b.button("Agregar", disabled=plantilla is None, key="imp_agregar_imp", width="stretch"):
        if ejecutar(lambda li: impuestos.agregar_plantilla_impuestos(li, plantilla), f"Se agregó «{plantilla}»"):
            st.rerun()
    for p in lib.fiscal.perfiles:
        with st.expander(p.nombre):
            st.caption(_describir(p))
            _formulario_perfil(p)
            if st.button("Borrar perfil", key=f"imp_borrar_perfil_{p.id}"):
                if ejecutar(lambda li, p=p: impuestos.eliminar_perfil(li, p.id), f"Se borró «{p.nombre}»"):
                    st.rerun()
    with st.expander("➕ Nuevo perfil (tus propias tasas)", expanded=not lib.fiscal.perfiles):
        _formulario_perfil(None)


def _formulario_perfil(p: PerfilImpuestos | None) -> None:
    clave = p.id if p else "nuevo"
    nombres = [i.nombre for i in p.impuestos] if p else []
    datos = pd.DataFrame({
        "Impuesto": nombres or ["IVA", ""],
        "Tasa (%)": [f"{i.tasa.normalize():f}" if i.tasa != impuestos._DOS_TERCIOS else "2/3" for i in p.impuestos]
        if p else ["16", ""],
        "Sobre": [i.sobre or SUBTOTAL for i in p.impuestos] if p else [SUBTOTAL, SUBTOTAL],
        "Efecto": [EFECTO[i.retenido] for i in p.impuestos] if p else [EFECTO[False], EFECTO[True]],
    })
    with st.form(f"imp_perfil_{clave}", border=False):
        nombre = st.text_input("Nombre del perfil", value=p.nombre if p else "",
                               placeholder="Honorarios, arrendamiento, mis ventas…")
        st.caption("Un impuesto por renglón, en orden. «Sobre»: el subtotal u otro impuesto de arriba (por ejemplo, "
                   "una retención de 2/3 del IVA). La tasa acepta fracciones: 2/3.")
        tabla = st.data_editor(datos, num_rows="dynamic", hide_index=True, width="stretch",
                               key=f"imp_tabla_{clave}",
                               column_config={
                                   "Sobre": st.column_config.SelectboxColumn(
                                       options=[SUBTOTAL, *[n for n in nombres if n]] if p else None, required=True)
                                   if p else st.column_config.TextColumn(
                                       help="Escribe «(el subtotal)» o el nombre de otro impuesto de arriba."),
                                   "Efecto": st.column_config.SelectboxColumn(options=list(EFECTO.values()),
                                                                              required=True)})
        notas = st.text_input("Notas", value=p.notas if p else "")
        if st.form_submit_button("Guardar perfil", type="primary"):
            filas = [{"nombre": str(f["Impuesto"] or "").strip(), "tasa": str(f["Tasa (%)"] or "0"),
                      "sobre": "" if (f["Sobre"] or SUBTOTAL) == SUBTOTAL else str(f["Sobre"]).strip(),
                      "retenido": f["Efecto"] == EFECTO[True]} for _, f in tabla.iterrows()]
            if ejecutar(lambda li: impuestos.guardar_perfil(li, nombre, filas, notas=notas,
                                                            perfil_id=p.id if p else None), "Perfil guardado"):
                st.rerun()
