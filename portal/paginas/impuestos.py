"""Impuestos (motor/impuestos.py): tus gastos deducibles del año y el cálculo/revisión de un recibo o factura. Para
cualquier país: tú defines las reglas (con ejemplos por país para guiarte) y todo se edita o se borra."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import categorias, comprobantes, impuestos
from motor.dinero import a_pesos
from motor.modelo import ClaseCategoria, ConceptoDeducible, PerfilImpuestos
from portal.componentes import exportar, formato
from portal.componentes.sesion import ejecutar, libro, sesion

SUBTOTAL = "(el subtotal)"
EFECTO = {False: "Se suma", True: "Se retiene (se resta)"}


def mostrar() -> None:
    st.title("Impuestos")
    st.caption("Tus gastos deducibles del año y el cálculo de un recibo o factura, para cualquier país: tú pones las "
               "reglas, con ejemplos para guiarte. " + impuestos.AVISO)
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
                "colegiaturas, alquiler…); ahí hay ejemplos por país.", icon="🧾")
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
    x.metric("Gastos deducibles", formato.dinero_metrica(reporte.suma))
    y.metric("Tope total", formato.dinero(reporte.tope) if reporte.tope is not None else "Sin tope",
             help=_explicar_tope(lib, ingreso))
    z.metric("Podrías deducir", formato.dinero_metrica(reporte.total))
    if reporte.tope is not None and reporte.suma - reporte.fuera_del_tope > reporte.tope:
        st.caption(f"Tus deducibles pasan del tope por "
                   f"{formato.dinero_md(reporte.suma - reporte.fuera_del_tope - reporte.tope)}: solo cuenta hasta el "
                   "tope.")
    if reporte.fuera_del_tope:
        st.caption(f"{formato.dinero_md(reporte.fuera_del_tope)} son de conceptos que no entran en el tope total.")
    st.dataframe(formato.pintar(pd.DataFrame({
        "Concepto": [r.concepto.nombre for r in reporte.renglones],
        "Pagaste": [formato.dinero(r.pagado) for r in reporte.renglones],
        "En efectivo (no cuenta)": [formato.dinero(r.en_efectivo) if r.concepto.sin_efectivo else "—"
                                    for r in reporte.renglones],
        "Parte deducible": [f"{r.concepto.porcentaje.normalize():f} %" for r in reporte.renglones],
        "Tope": [formato.dinero(a_pesos(r.concepto.tope)) if r.concepto.tope else "—" for r in reporte.renglones],
        "Deducible": [formato.dinero(r.deducible) + (" (topado)" if r.topado else "") for r in reporte.renglones],
    })), hide_index=True, width="stretch")
    if any(r.en_efectivo for r in reporte.renglones):
        st.warning("Algunos pagos fueron **en efectivo** y no cuentan en los conceptos que lo piden. Para la próxima, "
                   "paga con tarjeta o transferencia.", icon="💵")
    adjuntos = comprobantes.por_movimiento(lib)
    for r in reporte.renglones:
        if not r.pagos:
            continue
        with st.expander(f"{r.concepto.nombre} · {len(r.pagos)} pago(s)"):
            if r.concepto.notas:
                st.caption(r.concepto.notas)
            st.dataframe(formato.pintar(pd.DataFrame({
                "Fecha": [p.fecha for p in r.pagos], "Descripción": [p.descripcion for p in r.pagos],
                "Subcategoría": [p.subcategoria for p in r.pagos], "Cuenta": [p.cuenta for p in r.pagos],
                "Importe": [formato.dinero(p.importe) for p in r.pagos],
                "📎": [str(adjuntos.get(p.operacion_id, "")) for p in r.pagos],
                "": ["💵 en efectivo" if p.en_efectivo and r.concepto.sin_efectivo else "" for p in r.pagos],
            })), hide_index=True, width="stretch",
                column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})
    filas = [{"Concepto": r.concepto.nombre, "Fecha": p.fecha, "Descripción": p.descripcion,
              "Subcategoría": p.subcategoria, "Cuenta": p.cuenta, "Importe": float(p.importe),
              "En efectivo": "Sí" if p.en_efectivo else ""} for r in reporte.renglones for p in r.pagos]
    if filas:
        st.download_button("Descargar en Excel (para tu declaración)", lambda: exportar.excel({"Deducibles": pd.DataFrame(filas)}, columnas_dinero={"Importe"}),
                           file_name=f"TALLY_deducibles_{anio}.xlsx", icon=":material/download:", on_click="ignore",
                           key="imp_excel")
    _comprobantes_del_anio(anio)
    if lib.fiscal.notas:
        st.caption(f"📌 {lib.fiscal.notas}")


def _comprobantes_del_anio(anio: int) -> None:
    """Cuántos de tus pagos deducibles tienen su comprobante, cuáles no, y todos en un .zip."""
    lib = libro()
    lista = comprobantes.deducibles(lib, anio)
    if not lista:
        return
    faltan = [d for d in lista if not d.comprobantes]
    with st.container(border=True):
        st.markdown(f"**📎 Comprobantes de {anio}** · {len(lista) - len(faltan)} de {len(lista)} pago(s) deducibles "
                    "tienen su comprobante.")
        if faltan:
            st.caption("Sin comprobante, tu autoridad fiscal puede no aceptar el deducible. Adjúntalo desde "
                       "**Historial** (elige el movimiento → 📎 Comprobantes).")
            with st.expander(f"Ver los {len(faltan)} sin comprobante"):
                st.dataframe(formato.pintar(pd.DataFrame({
                    "Concepto": [d.concepto for d in faltan], "Fecha": [d.pago.fecha for d in faltan],
                    "Descripción": [d.pago.descripcion for d in faltan], "Cuenta": [d.pago.cuenta for d in faltan],
                    "Importe": [formato.dinero(d.pago.importe) for d in faltan],
                })), hide_index=True, width="stretch",
                    column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})
        if len(faltan) < len(lista):
            st.download_button(
                "Descargar los comprobantes del año (.zip)", lambda: comprobantes.zip_de_deducibles(sesion(), anio),
                file_name=f"TALLY_comprobantes_deducibles_{anio}.zip", mime="application/zip", on_click="ignore",
                icon=":material/folder_zip:", key="imp_zip_comprobantes",
                help="Una carpeta por concepto y un índice (indice.csv, se abre en Excel) con cada pago y su archivo. "
                     "Para tu contador o tu declaración.")


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
        st.info("Primero arma un perfil de impuestos en **⚙️ Configurar** con tus tasas (IVA, retenciones…); ahí hay "
                "ejemplos de México, España, Argentina, Colombia y más.", icon="🧮")
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
        st.dataframe(formato.pintar(pd.DataFrame({"Concepto": [n for n, _ in filas],
                                   "Importe": [formato.dinero(v) for _, v in filas]})),
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

EJEMPLOS_DEDUCIBLES = """
| País | Conceptos que la gente suele poner | Tope total |
|---|---|---|
| México (declaración anual) | Médicos, dentista y psicólogo (100 %, sin efectivo) · lentes graduados (tope de 2,500 al año) · seguro de gastos médicos · colegiaturas y donativos (marca «No entra en el tope total») | 15 % de tus ingresos o 5 UMA, lo que sea menor |
| Argentina (Ganancias) | Médicos (40 %) · prepaga · alquiler (40 %) · servicio doméstico | Cada uno con su tope: revisa ARCA |
| España (IRPF) | Casi todo son deducciones de tu comunidad autónoma: alquiler, guardería, gastos de estudios… | Según tu comunidad |
| Colombia (renta) | Dependientes · medicina prepagada · intereses de vivienda | Un % de tu ingreso con límite en UVT: revisa la DIAN |
| Otro país | Lo que tu autoridad fiscal permita deducir | Si hay uno |
"""

EJEMPLOS_PERFILES = """
| Caso | Renglones del perfil (Impuesto · Tasa · Sobre · Efecto) |
|---|---|
| México · honorarios a una empresa | IVA · 16 · subtotal · se suma — Retención ISR · 10 · subtotal · se retiene — Retención IVA · 2/3 · IVA · se retiene |
| México · RESICO a una empresa | IVA · 16 · subtotal · se suma — Retención ISR · 1.25 · subtotal · se retiene — Retención IVA · 2/3 · IVA · se retiene |
| México · venta al público | IVA · 16 (8 en la frontera) · subtotal · se suma |
| España · autónomo | IVA · 21 · subtotal · se suma — IRPF · 15 (7 los primeros años) · subtotal · se retiene |
| Argentina · responsable inscripto | IVA · 21 · subtotal · se suma |
| Colombia · servicios | IVA · 19 · subtotal · se suma — Retención en la fuente · 11 · subtotal · se retiene — ReteIVA · 15 · IVA · se retiene |
| Perú · recibo por honorarios | Retención de cuarta categoría · 8 · subtotal · se retiene |
| Chile · boleta de honorarios | Retención · la de este año (revísala en el SII) · subtotal · se retiene |
"""


def _configurar() -> None:
    st.caption("Aquí todo lo pones tú y todo se puede **editar o borrar**. Los ejemplos son solo una guía: TALLY no "
               "agrega nada por su cuenta. " + impuestos.AVISO)
    st.subheader("Gastos deducibles")
    _conceptos()
    st.divider()
    st.subheader("Perfiles de impuestos (para recibos y facturas)")
    _perfiles()


def _conceptos() -> None:
    lib = libro()
    with st.expander("💡 ¿Cómo armo mis deducibles? Ejemplos por país"):
        st.markdown(
            "1. **Crea un concepto** por cada gasto que tu país te deja deducir (por ejemplo «Gastos médicos»).\n"
            "2. **Elige las subcategorías** de TALLY donde registras esos gastos (CONSULTAS MEDICAS, DENTISTA…).\n"
            "3. Si solo cuenta **una parte**, pon el porcentaje (40 %). Si tiene **tope al año**, ponlo.\n"
            "4. Marca **«No cuenta lo pagado en efectivo»** si tu país lo pide.\n"
            "5. Si hay un **tope para todos juntos**, ponlo abajo (un monto, un % de tus ingresos o los dos).")
        st.markdown(formato.md(EJEMPLOS_DEDUCIBLES))
    for c in lib.fiscal.conceptos:
        a, b = st.columns([6, 1])
        with a.expander(f"✏️ {c.nombre} · {c.porcentaje.normalize():f} %"
                        + (f" · tope {formato.dinero(a_pesos(c.tope))}" if c.tope else "")
                        + (" · sin efectivo" if c.sin_efectivo else "")
                        + (" · fuera del tope total" if c.fuera_del_tope else "")):
            _formulario_concepto(c)
        if b.button("Borrar", key=f"imp_borrar_ded_{c.id}", icon=":material/delete:", width="stretch",
                    help=f"Borra «{c.nombre}». Tus gastos no se tocan."):
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
        notas = st.text_input("Notas (requisitos, dónde revisar los topes de tu país…)", value=lib.fiscal.notas)
        if st.form_submit_button("Guardar tope y notas"):
            def guardar(li):
                impuestos.ajustar_topes(li, tope_total=total or None, tope_porcentaje=porcentaje or None)
                impuestos.ajustar_notas(li, notas)
            if ejecutar(guardar, "Guardado"):
                st.rerun()
    if lib.fiscal.conceptos or lib.fiscal.tope_total or lib.fiscal.tope_porcentaje or lib.fiscal.notas:
        with st.popover("Borrar todos mis deducibles", icon=":material/delete_sweep:"):
            st.markdown(f"Se borran tus **{len(lib.fiscal.conceptos)} concepto(s)**, el tope total y las notas. Tus "
                        "gastos no se tocan.")
            if st.button("Sí, borrar todo", type="primary", key="imp_quitar_deducibles"):
                if ejecutar(impuestos.quitar_deducibles, "Se borraron tus deducibles"):
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
        if st.form_submit_button("Guardar cambios" if c else "Agregar concepto", type="primary"):
            if ejecutar(lambda li: impuestos.guardar_concepto(
                    li, nombre, elegidas, porcentaje=porcentaje, tope=tope or None, sin_efectivo=sin_efectivo,
                    notas=notas, fuera_del_tope=fuera, concepto_id=c.id if c else None), "Concepto guardado"):
                st.rerun()


def _perfiles() -> None:
    lib = libro()
    st.caption("Un **perfil** son los impuestos de un tipo de recibo o factura que das o recibes: con él TALLY "
               "calcula cuánto te llega y revisa si un recibo cuadra.")
    with st.expander("💡 ¿Cómo armo un perfil? Ejemplos por país"):
        st.markdown(
            "1. **Ponle nombre**: «Mis honorarios», «Ventas en la tienda»…\n"
            "2. **Un impuesto por renglón**, en orden. **Tasa** en %: 16, 1.25, o una fracción como 2/3.\n"
            "3. **Sobre**: casi siempre el subtotal. Si un impuesto se calcula sobre otro (la retención de 2/3 del IVA "
            "en México, la ReteIVA en Colombia), elige ese otro: tiene que ir arriba.\n"
            "4. **Efecto**: *se suma* si lo cobras aparte (IVA); *se retiene* si te lo quitan del pago (ISR, IRPF, "
            "retención en la fuente).")
        st.markdown(formato.md(EJEMPLOS_PERFILES))
        st.markdown("**¿No sabes cuánto pagas de ISR o IRPF?** Usa una tasa aproximada: lo que pagaste (o te "
                    "retuvieron) en el año entre tus ingresos del año.")
        a, b, c = st.columns(3)
        pagado = a.number_input("Impuesto del año", min_value=0.0, step=1000.0, format="%.2f", key="imp_aprox_isr")
        ingreso = b.number_input("Ingresos del año", min_value=0.0, step=1000.0, format="%.2f",
                                 key="imp_aprox_ingreso")
        c.metric("Tu tasa aproximada", f"{pagado / ingreso * 100:.2f} %" if ingreso else "—")
    for p in lib.fiscal.perfiles:
        a, b = st.columns([6, 1])
        with a.expander(f"✏️ {p.nombre}"):
            st.caption(_describir(p))
            _formulario_perfil(p)
        if b.button("Borrar", key=f"imp_borrar_perfil_{p.id}", icon=":material/delete:", width="stretch",
                    help=f"Borra el perfil «{p.nombre}»."):
            if ejecutar(lambda li, p=p: impuestos.eliminar_perfil(li, p.id), f"Se borró «{p.nombre}»"):
                st.rerun()
    with st.expander("➕ Nuevo perfil", expanded=not lib.fiscal.perfiles):
        _formulario_perfil(None)


def _tasa_texto(tasa: Decimal) -> str:
    """Para editar: 66.666… → «2/3»; 16 → «16»."""
    mostrada = impuestos.mostrar_tasa(tasa)
    return mostrada.split(" ")[0] if "/" in mostrada else f"{tasa.normalize():f}"


def _formulario_perfil(p: PerfilImpuestos | None) -> None:
    clave = p.id if p else "nuevo"
    lista = list(p.impuestos) if p else []
    datos = pd.DataFrame({
        "Impuesto": [i.nombre for i in lista] or [""],
        "Tasa (%)": [_tasa_texto(i.tasa) for i in lista] or [""],
        "Sobre": [i.sobre or SUBTOTAL for i in lista] or [SUBTOTAL],
        "Efecto": [EFECTO[i.retenido] for i in lista] or [EFECTO[False]],
    })
    with st.form(f"imp_perfil_{clave}", border=False):
        nombre = st.text_input("Nombre del perfil", value=p.nombre if p else "",
                               placeholder="Mis honorarios, ventas de la tienda…")
        st.caption("Un impuesto por renglón, en orden (agrega renglones con el ➕ de la tabla). «Sobre»: escribe "
                   "«(el subtotal)» o el nombre de otro impuesto de arriba. Renglones sin nombre no se guardan.")
        tabla = st.data_editor(datos, num_rows="dynamic", hide_index=True, width="stretch",
                               key=f"imp_tabla_{clave}",
                               column_config={
                                   "Impuesto": st.column_config.TextColumn(help="IVA, Retención ISR, IRPF…"),
                                   "Tasa (%)": st.column_config.TextColumn(help="16, 1.25 o una fracción: 2/3"),
                                   "Sobre": st.column_config.TextColumn(
                                       default=SUBTOTAL,
                                       help="«(el subtotal)» o el nombre de otro impuesto de arriba."),
                                   "Efecto": st.column_config.SelectboxColumn(options=list(EFECTO.values()),
                                                                              default=EFECTO[False])})
        notas = st.text_input("Notas", value=p.notas if p else "")
        if st.form_submit_button("Guardar cambios" if p else "Guardar perfil", type="primary"):
            filas = [{"nombre": str(f["Impuesto"] or "").strip(), "tasa": str(f["Tasa (%)"] or "0"),
                      "sobre": "" if str(f["Sobre"] or SUBTOTAL).strip() in (SUBTOTAL, "subtotal", "el subtotal")
                      else str(f["Sobre"]).strip(),
                      "retenido": f["Efecto"] == EFECTO[True]} for _, f in tabla.iterrows()]
            if ejecutar(lambda li: impuestos.guardar_perfil(li, nombre, filas, notas=notas,
                                                            perfil_id=p.id if p else None), "Perfil guardado"):
                st.rerun()
