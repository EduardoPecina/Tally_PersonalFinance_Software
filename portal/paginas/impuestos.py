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
from portal.navegacion import enlace

SUBTOTAL = "(el subtotal)"
SUMA, RETIENE, CARGO = "Se suma", "Se retiene (se resta)", "Lo pagas tú aparte"
EFECTOS = (SUMA, RETIENE, CARGO)
AYUDA_EFECTO = ("Se suma: lo cobras aparte (el IVA). Se retiene: te lo quitan del pago y lo paga por ti quien te paga "
                "(retención de ISR). Lo pagas tú: no cambia el recibo, lo pagas tú directo al fisco (el ISR del "
                "RESICO cuando le cobras a una persona).")
ESTADOS = {impuestos.PENDIENTE: "Por pagar", impuestos.VENCIDO: "Venció", impuestos.PAGADO: "Pagado ✓",
           impuestos.EN_CURSO: "En curso", impuestos.SIN_PAGO: "Nada que pagar"}


def _efecto(i) -> str:
    return RETIENE if i.retenido else (CARGO if i.a_cargo else SUMA)


def mostrar() -> None:
    st.title("Impuestos")
    st.caption("Tus gastos deducibles del año y el cálculo de un recibo o factura, para cualquier país: tú pones las "
               "reglas, con ejemplos para guiarte. " + impuestos.AVISO)
    deducibles, recibo, fisco, configurar = st.tabs(["🧾 Gastos deducibles", "🧮 Calcular y revisar un recibo",
                                                     "📅 Pagos al fisco", "⚙️ Configurar"])
    with deducibles:
        _deducibles()
    with recibo:
        _recibo()
    with fisco:
        _pagos_al_fisco()
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
            (f"{'−' if i.retenido else '+'} {i.nombre}", -v if i.retenido else v) for i, v in desglose.lineas
            if not i.a_cargo]
        filas.append(("Total que recibes (o pagas)", desglose.total))
        st.dataframe(formato.pintar(pd.DataFrame({"Concepto": [n for n, _ in filas],
                                   "Importe": [formato.dinero(v) for _, v in filas]})),
                     hide_index=True, width="stretch")
        a_cargo = [(i, v) for i, v in desglose.lineas if i.a_cargo]
        if a_cargo:
            st.caption("Además, lo pagas tú al fisco (no está en el recibo): " + " · ".join(
                f"{i.nombre} {formato.dinero_md(v)}" for i, v in a_cargo) + ".")
    st.markdown("##### 🔎 Revisar un recibo o factura que te dieron")
    st.caption("Escribe el subtotal y lo que dice cada impuesto. TALLY te dice si cuadra con tu perfil.")
    with st.form("imp_revisar", border=False):
        subtotal = st.number_input("Subtotal del recibo", min_value=0.0, step=100.0, format="%.2f")
        en_el_recibo = [i for i in perfil.impuestos if not i.a_cargo]      # lo que pagas tú no viene ahí
        columnas = st.columns(max(min(len(en_el_recibo), 3), 1))
        reales = {}
        for n, i in enumerate(en_el_recibo):
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


# ------------------------------------------------------------- pagos al fisco

AVISO_ESTIMACION = ("Es una estimación con tus tasas: no resta el IVA de tus gastos ni otras deducciones. Lo oficial "
                    "lo dice tu autoridad fiscal o tu contador.")


def _periodo_texto(pago: impuestos.PagoAlFisco) -> str:
    if pago.desde.month == pago.hasta.month:
        return formato.mes(pago.desde.year, pago.desde.month).lower()
    if pago.desde.month == 1 and pago.hasta.month == 12:
        return str(pago.desde.year)
    cortos = formato.MESES_CORTOS
    return f"{cortos[pago.desde.month - 1]}–{cortos[pago.hasta.month - 1]} {pago.desde.year}"


def _desglose_texto(pago: impuestos.PagoAlFisco) -> str:
    return " · ".join(f"{i.nombre} {formato.dinero(i.a_pagar)}" for i in pago.impuestos if i.a_pagar)


def aviso_en_el_resumen() -> None:
    """En el Resumen: lo que te toca pagar al fisco y hasta cuándo (desde que termina el periodo)."""
    lib = libro()
    hoy = lib.hoy()
    for pago in impuestos.por_pagar(lib, hoy):
        vencido = pago.estado(hoy) == impuestos.VENCIDO
        texto = (f"**{'Venció el' if vencido else 'Paga a más tardar el'} {formato.fecha_larga(pago.limite)}: "
                 f"{formato.dinero_md(pago.total)} al fisco** · {formato.md(pago.perfil.nombre)} "
                 f"({formato.md(_desglose_texto(pago))}), por lo que cobraste en {_periodo_texto(pago)}.")
        if pago.estimado:
            texto += " Estimado con tu Calendario: no registraste esos ingresos."
        (st.error if vencido else st.warning)(texto, icon="🧾")
        a, b, _ = st.columns([1.3, 1.6, 3], vertical_alignment="center")
        if a.button("Ya lo pagué", key=f"fisco_pagado_{pago.clave}", icon=":material/check:",
                    help="Deja de recordártelo. No registra nada: registra el pago como gasto en IMPUESTOS."):
            if ejecutar(lambda lib_, clave=pago.clave: impuestos.marcar_pagado(lib_, clave),
                        exito="Listo: ya no te lo recuerdo"):
                st.rerun()
        with b:
            enlace("registrar", "Registrar el pago", "➕")


def _pagos_al_fisco() -> None:
    lib = libro()
    hoy = lib.hoy()
    con_recordatorio = [p for p in lib.fiscal.perfiles if p.frecuencia]
    if not con_recordatorio:
        st.info("Para que TALLY te recuerde cuánto pagarle al fisco y hasta cuándo: en **⚙️ Configurar**, abre "
                "tu perfil de impuestos y llena **🔔 Recordatorio de pago al fisco** (cada cuándo pagas, sobre qué "
                "ingresos y la fecha límite). Te avisará en el Resumen.", icon="📅")
        return
    st.caption("Lo que te toca pagar en cada periodo con lo que registraste en esos ingresos: lo que trasladas (el IVA "
               "que cobraste) y lo que es a tu cargo, menos lo que ya te retuvieron. TALLY no registra nada: cuando "
               "pagues, regístralo como gasto en IMPUESTOS y márcalo como pagado. " + AVISO_ESTIMACION)
    for perfil in con_recordatorio:
        pagos = impuestos.pagos_al_fisco(lib, perfil, hoy)
        st.subheader(perfil.nombre, help=_describir(perfil))
        nombres = list(dict.fromkeys(i.nombre for pago in pagos for i in pago.impuestos))
        datos = {
            "Periodo": [_periodo_texto(x).capitalize() for x in pagos],
            "Cobrado": [formato.dinero(x.cobrado) + (" *" if x.estimado else "") for x in pagos],
            "Antes de impuestos": [formato.dinero(x.base) for x in pagos],
            **{n: [formato.dinero(next((i.a_pagar for i in x.impuestos if i.nombre == n), 0)) for x in pagos]
               for n in nombres},
            "A pagar": [formato.dinero(x.total) for x in pagos],
            "Fecha límite": [formato.fecha(x.limite) for x in pagos],
            "Estado": [ESTADOS[x.estado(hoy)] for x in pagos],
        }
        st.dataframe(formato.pintar(pd.DataFrame(datos)), hide_index=True, width="stretch", column_config={
            "Cobrado": st.column_config.TextColumn(help="Lo que registraste en esos ingresos. * = no registraste "
                                                        "nada: lo que esperas según tu Calendario."),
            "A pagar": st.column_config.TextColumn(help="Lo que trasladas o es a tu cargo, menos lo que ya te "
                                                        "retuvieron de ese mismo impuesto."),
        })
        if any(x.otras_retenciones for x in pagos):
            st.caption("Hay retenciones que no se restan de nada aquí (ya se pagaron por ti): por ejemplo, la "
                       "retención de ISR cuando el perfil no tiene un renglón de ISR «Lo pagas tú».")
        terminados = [x for x in pagos if x.estado(hoy) not in (impuestos.EN_CURSO, impuestos.SIN_PAGO)]
        if terminados:
            a, b = st.columns([2, 1], vertical_alignment="bottom")
            clave = a.selectbox("Marcar un periodo", [x.clave for x in terminados], key=f"fisco_periodo_{perfil.id}",
                                format_func=lambda c: next(f"{_periodo_texto(x).capitalize()} · "
                                                           f"{ESTADOS[x.estado(hoy)]}" for x in terminados
                                                           if x.clave == c))
            pagado = clave in lib.fiscal.pagados
            if b.button("Marcar como no pagado" if pagado else "Ya lo pagué", key=f"fisco_marcar_{perfil.id}",
                        width="stretch"):
                if ejecutar(lambda lib_: impuestos.marcar_pagado(lib_, clave, not pagado),
                            exito="Marcado como no pagado" if pagado else "Marcado como pagado"):
                    st.rerun()


def _describir(perfil: PerfilImpuestos) -> str:
    partes = [f"{i.nombre} {impuestos.mostrar_tasa(i.tasa)}" + (f" de {i.sobre}" if i.sobre else "")
              + (" (retenido)" if i.retenido else "") + (" (lo pagas tú)" if i.a_cargo else "")
              for i in perfil.impuestos]
    texto = " · ".join(partes) + (f". {perfil.notas}" if perfil.notas else "")
    if perfil.frecuencia:
        texto += (f". 🔔 Te recuerda pagarlo {impuestos.FRECUENCIAS_PAGO[perfil.frecuencia].lower()}, a más tardar "
                  f"el día {perfil.dia_limite}" + (" del mes siguiente" if perfil.meses_despues == 1 else
                                                    f", {perfil.meses_despues} meses después del periodo") + ".")
    return texto


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
| México · RESICO a una persona | ISR · 1.25 (de 1 a 2.5 según lo que cobres al mes) · subtotal · lo pagas tú — IVA · 16 · subtotal · se suma |
| México · RESICO a una empresa | IVA · 16 · subtotal · se suma — ISR · 1.25 · subtotal · lo pagas tú — Retención ISR · 1.25 · subtotal · se retiene — Retención IVA · 2/3 · IVA · se retiene |
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
            "retención en la fuente); *lo pagas tú* si no cambia el recibo y lo pagas directo al fisco (el ISR del "
            "RESICO).\n"
            "5. **🔔 Recordatorio** (opcional): cada cuándo lo pagas, sobre qué ingresos y la fecha límite. TALLY te "
            "dice en el Resumen cuánto pagar y hasta cuándo (pestaña 📅 Pagos al fisco).")
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


AYUDA_RENGLONES = ("Un impuesto por renglón, en orden. Si uno se calcula sobre otro (la retención de 2/3 del IVA), "
                   "ponlo debajo de ese otro y elígelo en «Sobre». Los renglones sin nombre no se guardan.")


def _formulario_perfil(p: PerfilImpuestos | None) -> None:
    """Un renglón por impuesto, con campos normales. (Antes era una tabla editable: había que dar clic en la celda
    para escribir, y la casilla de la izquierda seleccionaba el renglón y escondía el ➕.)"""
    clave = p.id if p else "nuevo"
    filas = _renglones_del_formulario(p, clave)
    st.text_input("Nombre del perfil", key=f"imp_{clave}_nombre_perfil", placeholder="Mis honorarios, ventas de la "
                  "tienda…", help="Para reconocerlo al calcular un recibo: «Honorarios a empresas», «RESICO»…")
    st.markdown("**Sus impuestos**", help=AYUDA_RENGLONES)
    arriba: list[str] = []
    for n in list(filas):
        a, b, c, d, e = st.columns([3, 1.4, 2.2, 2.6, 0.8], vertical_alignment="bottom")
        etiqueta = "visible" if n == filas[0] else "collapsed"
        nombre = a.text_input("Impuesto", key=f"imp_{clave}_{n}_nombre", placeholder="IVA, ISR, IRPF…",
                              label_visibility=etiqueta, help="Como aparece en tu recibo o factura.")
        b.text_input("Tasa (%)", key=f"imp_{clave}_{n}_tasa", placeholder="16", label_visibility=etiqueta,
                     help="En %: 16, 1.25, o una fracción como 2/3.")
        opciones = [SUBTOTAL, *dict.fromkeys(x for x in arriba if x)]
        sobre = f"imp_{clave}_{n}_sobre"
        if st.session_state.get(sobre) not in opciones:
            st.session_state[sobre] = SUBTOTAL                  # el de arriba cambió de nombre o se quitó
        c.selectbox("Sobre", opciones, key=sobre, label_visibility=etiqueta,
                    help="Casi siempre el subtotal. Si se calcula sobre otro impuesto (2/3 del IVA), elige ese "
                         "otro: aparece aquí cuando lo escribes en un renglón de arriba.")
        d.selectbox("Efecto", EFECTOS, key=f"imp_{clave}_{n}_efecto", label_visibility=etiqueta, help=AYUDA_EFECTO)
        if e.button("", key=f"imp_{clave}_{n}_quitar", icon=":material/delete:", disabled=len(filas) == 1,
                    help="Quitar este renglón"):
            filas.remove(n)
            st.rerun()
        arriba.append(nombre.strip())
    if st.button("Agregar otro impuesto", key=f"imp_{clave}_agregar", icon=":material/add:"):
        filas.append(_siguiente(clave))
        st.rerun()
    st.text_input("Notas", key=f"imp_{clave}_notas")
    _recordatorio(clave)
    if st.button("Guardar cambios" if p else "Guardar perfil", type="primary", key=f"imp_{clave}_guardar"):
        estado = st.session_state
        datos = [{"nombre": str(estado.get(f"imp_{clave}_{n}_nombre") or "").strip(),
                  "tasa": str(estado.get(f"imp_{clave}_{n}_tasa") or "0").strip() or "0",
                  "sobre": "" if estado.get(f"imp_{clave}_{n}_sobre", SUBTOTAL) == SUBTOTAL
                  else estado[f"imp_{clave}_{n}_sobre"],
                  "retenido": estado.get(f"imp_{clave}_{n}_efecto") == RETIENE,
                  "a_cargo": estado.get(f"imp_{clave}_{n}_efecto") == CARGO} for n in filas]
        frecuencia = estado.get(f"imp_{clave}_frecuencia", "")
        if ejecutar(lambda li: impuestos.guardar_perfil(
                li, estado.get(f"imp_{clave}_nombre_perfil", ""), datos, notas=estado.get(f"imp_{clave}_notas", ""),
                perfil_id=p.id if p else None, frecuencia=frecuencia,
                subcategorias=estado.get(f"imp_{clave}_subcategorias", []) if frecuencia else (),
                registro=estado.get(f"imp_{clave}_registro", "recibido"),
                dia_limite=estado.get(f"imp_{clave}_dia", 17), meses_despues=estado.get(f"imp_{clave}_meses", 1)),
                "Perfil guardado"):
            _olvidar_formulario(clave)                          # que se vuelva a llenar con lo guardado
            st.rerun()


def _recordatorio(clave: str) -> None:
    """Cada cuándo pagas estos impuestos al fisco y sobre qué ingresos: TALLY te lo recuerda en el Resumen."""
    lib = libro()
    with st.container(border=True):
        st.markdown("**🔔 Recordatorio de pago al fisco** (opcional)",
                    help="TALLY suma lo que cobraste en esos ingresos en cada periodo, calcula lo que te toca pagar "
                         "con este perfil y te lo recuerda en el Resumen antes de la fecha límite. No registra nada: "
                         "cuando pagues, regístralo como gasto en IMPUESTOS.")
        frecuencia = st.selectbox(
            "¿Cada cuándo pagas estos impuestos?", list(impuestos.FRECUENCIAS_PAGO),
            format_func=impuestos.FRECUENCIAS_PAGO.get, key=f"imp_{clave}_frecuencia",
            help="En México, el RESICO y las personas con actividad empresarial pagan cada mes. La declaración "
                 "anual es aparte: puedes hacer otro perfil para ella.")
        if not frecuencia:
            return
        ingresos = [c.id for c in categorias.ordenadas(lib, lib.categorias()) if c.clase is ClaseCategoria.INGRESO]
        st.multiselect("¿Sobre qué ingresos?", ingresos, format_func=lambda i: categorias.etiqueta(lib, i),
                       key=f"imp_{clave}_subcategorias", placeholder="Elige las subcategorías (HONORARIOS, VENTAS…)",
                       help="Las subcategorías donde registras los ingresos a los que aplican estos impuestos. Si no "
                            "registraste nada en un periodo, TALLY usa lo que esperas según tu Calendario.")
        st.radio("¿Cómo registras esos ingresos en TALLY?", list(impuestos.REGISTRO),
                 format_func=impuestos.REGISTRO.get, key=f"imp_{clave}_registro",
                 help="Lo que te llega: TALLY saca de ahí el monto antes de impuestos con este perfil. El subtotal: "
                      "usa tal cual lo que registraste.")
        a, b = st.columns(2)
        a.number_input("Fecha límite: el día…", min_value=1, max_value=31, step=1, key=f"imp_{clave}_dia",
                       help="En México, el pago mensual vence el día 17.")
        b.number_input("…de cuántos meses después de que termina el periodo", min_value=0, max_value=12, step=1,
                       key=f"imp_{clave}_meses",
                       help="1 = el mes siguiente (lo de octubre, en noviembre). La declaración anual en México: 4 "
                            "(lo del año, en abril).")
        ejemplo = impuestos.limite(PerfilImpuestos("", "", (), frecuencia=frecuencia,
                                                   dia_limite=int(st.session_state[f"imp_{clave}_dia"]),
                                                   meses_despues=int(st.session_state[f"imp_{clave}_meses"])),
                                   impuestos.periodo(PerfilImpuestos("", "", (), frecuencia=frecuencia),
                                                     lib.hoy())[1])
        st.caption("Por ejemplo: lo del periodo que va en curso se paga a más tardar el "
                   f"{formato.fecha_larga(ejemplo)}.")


def _renglones_del_formulario(p: PerfilImpuestos | None, clave: str) -> list[int]:
    """Los renglones del formulario (se llenan una vez con lo guardado y luego se quedan como los dejes)."""
    estado = st.session_state
    if f"imp_{clave}_filas" not in estado:
        lista = list(p.impuestos) if p else []
        estado[f"imp_{clave}_nombre_perfil"] = p.nombre if p else ""
        estado[f"imp_{clave}_notas"] = p.notas if p else ""
        for n, i in enumerate(lista):
            estado[f"imp_{clave}_{n}_nombre"] = i.nombre
            estado[f"imp_{clave}_{n}_tasa"] = _tasa_texto(i.tasa)
            estado[f"imp_{clave}_{n}_sobre"] = i.sobre or SUBTOTAL
            estado[f"imp_{clave}_{n}_efecto"] = _efecto(i)
        estado[f"imp_{clave}_frecuencia"] = p.frecuencia if p else ""
        estado[f"imp_{clave}_subcategorias"] = [i for i in (p.subcategorias if p else ()) if _existe(i)]
        estado[f"imp_{clave}_registro"] = p.registro if p else "recibido"
        estado[f"imp_{clave}_dia"] = p.dia_limite if p else 17
        estado[f"imp_{clave}_meses"] = p.meses_despues if p else 1
        estado[f"imp_{clave}_filas"] = list(range(max(len(lista), 1)))
        estado[f"imp_{clave}_siguiente"] = max(len(lista), 1)
    return estado[f"imp_{clave}_filas"]


def _existe(categoria_id: str) -> bool:
    return any(c.id == categoria_id for c in libro().categorias())


def _siguiente(clave: str) -> int:
    n = st.session_state[f"imp_{clave}_siguiente"]
    st.session_state[f"imp_{clave}_siguiente"] = n + 1
    return n


def _olvidar_formulario(clave: str) -> None:
    for k in [k for k in st.session_state if str(k).startswith(f"imp_{clave}_")]:
        del st.session_state[k]
