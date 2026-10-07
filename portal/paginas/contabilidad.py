"""Contabilidad técnica (motor/contabilidad.py): estados financieros y balanza, derivados de tus movimientos."""

from __future__ import annotations

import html
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import contabilidad as cb
from portal.componentes import exportar, formato
from portal.componentes.sesion import libro

ESTILO = """
<style>
table.tally-estado {width:100%; border-collapse:collapse; font-size:0.95rem; margin-bottom:0.5rem}
table.tally-estado th {text-align:right; font-weight:600; padding:6px 10px; opacity:0.75;
  border-bottom:1px solid rgba(128,128,128,0.35)}
table.tally-estado th:first-child {text-align:left}
table.tally-estado td {padding:4px 10px; text-align:right; white-space:nowrap}
table.tally-estado td:first-child {text-align:left; white-space:normal}
table.tally-estado tr.titulo td {font-weight:700; padding-top:14px; letter-spacing:0.02em}
table.tally-estado tr.grupo td {font-weight:600; padding-top:8px; opacity:0.85}
table.tally-estado tr.renglon td:first-child {padding-left:28px}
table.tally-estado tr.subtotal td {font-weight:600; border-top:1px solid rgba(128,128,128,0.35)}
table.tally-estado tr.total td {font-weight:700; border-top:2px solid rgba(128,128,128,0.6);
  border-bottom:2px solid rgba(128,128,128,0.6)}
table.tally-estado td.nota {opacity:0.7; font-size:0.85rem; text-align:left}
</style>
"""


def mostrar() -> None:
    st.title("Contabilidad Técnica")
    st.caption("Tus finanzas como las ve un contador, armadas solas con lo que ya registras. No tienes que capturar "
               "nada más: si corriges un movimiento, todos los reportes cambian y siempre cuadran entre sí.")
    st.markdown(ESTILO, unsafe_allow_html=True)
    lib = libro()
    hoy = lib.hoy()
    izquierda, centro, derecha = st.columns([1, 1, 1.2])
    claves = list(cb.PERIODOS)
    clave = izquierda.selectbox("Periodo", claves, format_func=cb.PERIODOS.get, key="conta_periodo")
    elegido = None
    if clave == "rango":
        fechas = centro.date_input("Del … al …", value=(date(hoy.year, 1, 1), hoy), format="DD/MM/YYYY",
                                   key="conta_fechas")
        if isinstance(fechas, (tuple, list)) and fechas:
            elegido = (fechas[0], fechas[-1])
    desde, hasta = cb.periodo(clave, hoy, elegido)
    modo = derecha.selectbox("Comparar con", list(cb.COMPARAR), format_func=cb.COMPARAR.get, key="conta_comparar")
    contra = cb.comparativo(desde, hasta, modo)
    periodos = [(desde, hasta)] + ([contra] if contra else [])
    if clave != "rango":
        centro.markdown(f"<div style='padding-top:2.1rem'>{formato.rango(desde, hasta)}</div>",
                        unsafe_allow_html=True)

    with st.expander("¿Cómo se lee? (sin ser contador)"):
        st.markdown(
            "- **Estado de Situación Financiera**: una foto de un día. **Activo** es lo que tienes (bancos, efectivo, "
            "inversiones, lo que te deben), **Pasivo** lo que debes (tarjetas) y **Patrimonio** lo que de verdad "
            "es tuyo: Activo − Pasivo.\n"
            "- **Estado de Resultados**: una película del periodo. Cuánto ganaste, cuánto gastaste y cuánto te "
            "quedó. Una compra con tarjeta ya es gasto aunque la pagues después.\n"
            "- **Flujo de Efectivo**: por dónde entró y salió el dinero de tus cuentas de débito, ahorro y "
            "efectivo. Aquí la compra con tarjeta aparece hasta que **pagas** la tarjeta.\n"
            "- **Balanza de Comprobación**: la vista técnica. Cada movimiento se anota dos veces, en el **Debe** "
            "(lo que entra a una cuenta o lo que gastas) y en el **Haber** (de dónde salió); por eso las sumas "
            "siempre son iguales.")

    situacion = cb.situacion(lib, [p[1] for p in periodos])
    resultados = cb.resultados(lib, periodos)
    flujo = cb.flujo(lib, periodos)
    balanza = cb.balanza(lib, desde, hasta)

    pestanas = st.tabs(["Situación financiera", "Resultados", "Flujo de efectivo", "Balanza de comprobación"])
    with pestanas[0]:
        _situacion(situacion)
    with pestanas[1]:
        _resultados(resultados)
    with pestanas[2]:
        _flujo(flujo)
    with pestanas[3]:
        _balanza(balanza)

    st.download_button(
        "Descargar los 4 reportes en Excel", on_click="ignore", icon=":material/table_view:",
        data=exportar.excel({"Situación financiera": _tabla_situacion(situacion),
                             "Resultados": _tabla_resultados(resultados), "Flujo de efectivo": _tabla_flujo(flujo),
                             "Balanza": _tabla_balanza(balanza)}),
        file_name=f"TALLY_contabilidad_{desde:%Y-%m-%d}_a_{hasta:%Y-%m-%d}.xlsx")


# ----------------------------------------------------------------- dibujar


def _dinero(valor: Decimal) -> str:
    return formato.dinero(valor) if valor else "—"


def _variacion(valores: tuple[Decimal, ...]) -> str:
    if len(valores) < 2:
        return ""
    cambio = valores[0] - valores[1]
    return ("+" if cambio > 0 else "") + formato.dinero(cambio) if cambio else "—"


def _estado(encabezados: list[str], filas: list[tuple[str, str, tuple, str]]) -> None:
    """Tabla con estilo de estado financiero. Cada fila: (clase, concepto, importes, nota)."""
    partes = ["<table class='tally-estado'><thead><tr>"]
    partes += [f"<th>{html.escape(e)}</th>" for e in encabezados]
    partes.append("</tr></thead><tbody>")
    for clase, concepto, importes, nota in filas:
        celdas = [f"<td>{html.escape(concepto)}</td>"]
        celdas += [f"<td>{html.escape(_dinero(v)) if clase != 'titulo' else ''}</td>" for v in importes]
        if len(encabezados) > len(importes) + 1:
            celdas.append(f"<td>{html.escape(_variacion(importes)) if clase != 'titulo' else ''}</td>")
        if len(encabezados) > len(importes) + 2:
            celdas.append(f"<td class='nota'>{html.escape(nota)}</td>")
        partes.append(f"<tr class='{clase}'>{''.join(celdas)}</tr>")
    partes.append("</tbody></table>")
    st.markdown("".join(partes), unsafe_allow_html=True)


def _columnas_fecha(fechas: tuple[date, ...]) -> list[str]:
    return [formato.fecha(f) for f in fechas]


def _columnas_periodo(periodos) -> list[str]:
    return [formato.rango(d, h) for d, h in periodos]


def _lectura(naturaleza: str, valores: tuple[Decimal, ...]) -> str:
    if len(valores) < 2 or valores[0] == valores[1]:
        return ""
    sube = valores[0] > valores[1]
    return {cb.ACTIVO: ("Tienes más", "Tienes menos"), cb.PASIVO: ("Debes más", "Debes menos ✓"),
            cb.PATRIMONIO: ("Vales más ✓", "Vales menos")}[naturaleza][0 if sube else 1]


# ------------------------------------------------- estado de situación financiera


def _situacion(s: cb.Situacion) -> None:
    st.subheader("Estado de Situación Financiera")
    st.caption(f"Lo que tienes, lo que debes y lo que vales · al {formato.fecha_larga(s.fechas[0])}")
    activo, pasivo, patrimonio = s.total(cb.ACTIVO), s.total(cb.PASIVO), s.total(cb.PATRIMONIO)
    a, b, c = st.columns(3)
    a.metric("Lo que tienes (Activo)", formato.dinero(activo[0]), delta=_delta(activo))
    b.metric("Lo que debes (Pasivo)", formato.dinero(pasivo[0]), delta=_delta(pasivo), delta_color="inverse")
    c.metric("Lo que vales (Patrimonio)", formato.dinero(patrimonio[0]), delta=_delta(patrimonio))
    if s.cuadra:
        st.success("Cuadra: Activo = Pasivo + Patrimonio.", icon="✅")
    else:
        st.error("No cuadra: Activo ≠ Pasivo + Patrimonio. Revisa la bitácora o restaura un respaldo.")
    _estado(["Concepto", *_columnas_fecha(s.fechas), *(["Variación", "Lectura"] if len(s.fechas) > 1 else [])],
            _filas_situacion(s))


def _delta(valores: tuple[Decimal, ...]) -> str | None:
    if len(valores) < 2 or valores[0] == valores[1]:
        return None
    cambio = valores[0] - valores[1]
    return ("+" if cambio > 0 else "−") + formato.dinero(abs(cambio))


def _filas_situacion(s: cb.Situacion) -> list:
    filas = []
    titulos = {cb.ACTIVO: "ACTIVO · lo que tienes", cb.PASIVO: "PASIVO · lo que debes",
               cb.PATRIMONIO: "PATRIMONIO · lo que es tuyo"}
    for naturaleza in (cb.ACTIVO, cb.PASIVO, cb.PATRIMONIO):
        filas.append(("titulo", titulos[naturaleza], s.total(naturaleza), ""))
        grupos = s.grupos(naturaleza)
        for grupo in grupos:
            if naturaleza != cb.PATRIMONIO:
                filas.append(("grupo", grupo, s.total(naturaleza, grupo), ""))
            for r in (r for r in s.renglones if r.naturaleza == naturaleza and r.grupo == grupo):
                filas.append(("renglon", r.nombre, r.importes, _lectura(naturaleza, r.importes)))
        if not grupos:
            filas.append(("renglon", "Sin saldo", s.total(naturaleza), ""))
        filas.append(("subtotal", f"Total {naturaleza.lower()}", s.total(naturaleza),
                      _lectura(naturaleza, s.total(naturaleza))))
    suma = tuple(p + c for p, c in zip(s.total(cb.PASIVO), s.total(cb.PATRIMONIO)))
    filas.append(("total", "PASIVO + PATRIMONIO", suma, ""))
    return filas


# ------------------------------------------------------- estado de resultados


def _resultados(r: cb.Resultados) -> None:
    st.subheader("Estado de Resultados")
    st.caption(f"¿Cuánto ganaste y cuánto gastaste? · {formato.rango(*r.periodos[0])}")
    a, b, c = st.columns(3)
    a.metric("Ingresos", formato.dinero(r.total_ingresos()[0]), delta=_delta(r.total_ingresos()))
    b.metric("Gastos", formato.dinero(r.total_gastos()[0]), delta=_delta(r.total_gastos()), delta_color="inverse")
    c.metric("Resultado del periodo", formato.dinero(r.resultado()[0]), delta=_delta(r.resultado()))
    encabezados = ["Concepto", *_columnas_periodo(r.periodos), *(["Variación"] if len(r.periodos) > 1 else [])]
    _estado(encabezados, _filas_resultados(r, detalle=False))
    st.caption("**Resultado del día a día**: lo que te quedó de lo que ganaste menos lo que gastaste. Los "
               "rendimientos de tus cuentas de inversión (cuando cuadras con el valor oficial) van aparte, para no "
               "mezclarlos con tu sueldo. Los saldos iniciales de cuentas nuevas no son resultado: son patrimonio.")
    with st.expander("Ver por subcategoría"):
        _estado(encabezados, _filas_resultados(r, detalle=True))


def _filas_resultados(r: cb.Resultados, *, detalle: bool) -> list:
    filas = []
    for titulo, renglones, total in (("INGRESOS", r.ingresos, r.total_ingresos()),
                                     ("GASTOS", r.gastos, r.total_gastos())):
        filas.append(("titulo", titulo, total, ""))
        for grupo in dict.fromkeys(x.grupo for x in renglones):
            del_grupo = [x for x in renglones if x.grupo == grupo]
            filas.append(("grupo" if detalle else "renglon", grupo, cb._sumar_renglones(del_grupo, len(total)), ""))
            if detalle:
                filas += [("renglon", x.nombre, x.importes, "") for x in del_grupo]
        filas.append(("subtotal", f"Total {titulo.lower()}", total, ""))
    filas.append(("total", "RESULTADO DE TU DÍA A DÍA", r.dia_a_dia(), ""))
    if any(r.rendimientos_inversion):
        filas.append(("renglon", cb.RENDIMIENTOS_INVERSION, r.rendimientos_inversion, ""))
    if any(r.ajustes):
        filas.append(("renglon", cb.AJUSTES, r.ajustes, ""))
    filas.append(("total", "RESULTADO DEL PERIODO", r.resultado(), ""))
    return filas


# --------------------------------------------------------- flujo de efectivo


def _flujo(f: cb.Flujo) -> None:
    st.subheader("Estado de Flujo de Efectivo")
    st.caption(f"¿Por dónde entró y salió tu dinero? · {formato.rango(*f.periodos[0])} · método directo")
    a, b, c = st.columns(3)
    a.metric("Efectivo al inicio", formato.dinero(f.inicial[0]))
    b.metric("Entró − salió", formato.dinero(f.total()[0]))
    c.metric("Efectivo al final", formato.dinero(f.final[0]), delta=_delta(f.final))
    encabezados = ["Concepto", *_columnas_periodo(f.periodos), *(["Variación"] if len(f.periodos) > 1 else [])]
    filas = [("subtotal", "Efectivo al inicio del periodo", f.inicial, "")]
    for seccion in f.secciones():
        filas.append(("titulo", seccion.upper(), f.total(seccion), ""))
        filas += [("renglon", r.nombre, r.importes, "") for r in f.renglones if r.naturaleza == seccion]
        filas.append(("subtotal", f"Neto de {seccion.lower()}", f.total(seccion), ""))
    filas.append(("subtotal", "Aumento (o disminución) de efectivo", f.total(), ""))
    filas.append(("total", "Efectivo al final del periodo", f.final, ""))
    _estado(encabezados, filas)
    if not f.cuadra:
        st.error("El flujo no cuadra con tus saldos: revisa la bitácora o restaura un respaldo.")
    st.caption("Cuenta como efectivo: " + (", ".join(f.cuentas) or "ninguna cuenta todavía") + ". Positivo = "
               "entró, negativo = salió. Pasar dinero entre esas cuentas no cambia tu efectivo.")
    if f.gasto_con_tarjeta[0]:
        st.info(f"Gastaste {formato.dinero_md(f.gasto_con_tarjeta[0])} con tarjeta de crédito en el periodo: ya es "
                "gasto en el Estado de Resultados, pero aquí aparece hasta que pagas la tarjeta. Por eso el "
                "resultado y el flujo no tienen que coincidir.", icon="💳")


# ---------------------------------------------------- balanza de comprobación


def _balanza(b: cb.Balanza) -> None:
    st.subheader("Balanza de Comprobación")
    st.caption(f"Vista técnica · {formato.rango(b.desde, b.hasta)} · saldo al "
               f"{formato.fecha(b.desde - timedelta(days=1))} y al {formato.fecha(b.hasta)}")
    detalle = st.toggle("Ver cada subcategoría (subcuentas)", key="conta_subcuentas")
    vista = b if detalle else b.por_categoria()
    if vista.cuadra:
        st.success("Sumas iguales: el Debe es igual al Haber.", icon="✅")
    else:
        st.error("Las sumas no son iguales: revisa la bitácora o restaura un respaldo.")
    tabla = _tabla_balanza(vista)
    columnas = [c for c in tabla.columns if c not in ("Naturaleza", "Cuenta", "Origen / Aplicación", "Lectura")]
    mostrada, config = formato.tabla_en_pesos(tabla, columnas, fijar="Cuenta")
    config["Origen / Aplicación"] = st.column_config.TextColumn(
        help="Solo en cuentas de balance. Origen: de ahí salieron recursos (bajó un activo, o creció una deuda o "
             "tu patrimonio). Aplicación: ahí se usaron (creció un activo o bajó una deuda).")
    config["Debe"] = st.column_config.TextColumn(alignment="right", help="Lo que entró a la cuenta (en activos) o "
                                                 "lo que gastaste (en gastos).")
    config["Haber"] = st.column_config.TextColumn(alignment="right", help="De dónde salió: lo que salió de la "
                                                  "cuenta, lo que debes o lo que ganaste.")
    st.dataframe(mostrada, column_config=config, hide_index=True, width="stretch",
                 height=min(40 + 35 * len(mostrada), 640))
    st.caption("**Deudor** es el saldo de lo que tienes o gastaste; **acreedor**, el de lo que debes, ganaste o es "
               "patrimonio. Las cuentas de ingresos y gastos empiezan cada periodo en ceros: lo de antes está en "
               "«Resultados de periodos anteriores». Una cuenta por cobrar que ya te pagaron queda en ceros "
               "(compensada).")


# ------------------------------------------------------ tablas (y exportar)


def _tabla_situacion(s: cb.Situacion) -> pd.DataFrame:
    filas = _filas_situacion(s)
    datos = {"Concepto": [f[1] for f in filas]}
    for i, nombre in enumerate(_columnas_fecha(s.fechas)):
        datos[nombre] = [float(f[2][i]) if f[0] != "titulo" else None for f in filas]
    return pd.DataFrame(datos)


def _tabla_resultados(r: cb.Resultados) -> pd.DataFrame:
    filas = _filas_resultados(r, detalle=True)
    datos = {"Concepto": [f[1] for f in filas]}
    for i, nombre in enumerate(_columnas_periodo(r.periodos)):
        datos[nombre] = [float(f[2][i]) for f in filas]
    return pd.DataFrame(datos)


def _tabla_flujo(f: cb.Flujo) -> pd.DataFrame:
    filas = [("Efectivo al inicio del periodo", f.inicial)]
    for seccion in f.secciones():
        filas += [(f"{seccion}: {r.nombre}", r.importes) for r in f.renglones if r.naturaleza == seccion]
    filas += [("Aumento (o disminución) de efectivo", f.total()), ("Efectivo al final del periodo", f.final)]
    datos = {"Concepto": [n for n, _ in filas]}
    for i, nombre in enumerate(_columnas_periodo(f.periodos)):
        datos[nombre] = [float(v[i]) for _, v in filas]
    return pd.DataFrame(datos)


def _tabla_balanza(b: cb.Balanza) -> pd.DataFrame:
    def deudor(v: Decimal) -> float | None:
        return float(v) if v > 0 else None

    def acreedor(v: Decimal) -> float | None:
        return float(-v) if v < 0 else None

    sumas = b.sumas()
    tabla = pd.DataFrame({
        "Naturaleza": [c.naturaleza for c in b.cuentas] + [""],
        "Cuenta": [c.nombre for c in b.cuentas] + ["SUMAS IGUALES"],
        "Saldo inicial deudor": [deudor(c.inicial) for c in b.cuentas] + [float(sumas.get("inicial_deudor", 0))],
        "Saldo inicial acreedor": [acreedor(c.inicial) for c in b.cuentas]
        + [float(sumas.get("inicial_acreedor", 0))],
        "Debe": [float(c.debe) or None for c in b.cuentas] + [float(sumas.get("debe", 0))],
        "Haber": [float(c.haber) or None for c in b.cuentas] + [float(sumas.get("haber", 0))],
        "Saldo final deudor": [deudor(c.final) for c in b.cuentas] + [float(sumas.get("final_deudor", 0))],
        "Saldo final acreedor": [acreedor(c.final) for c in b.cuentas] + [float(sumas.get("final_acreedor", 0))],
        "Variación": [float(c.variacion) or None for c in b.cuentas] + [None],
        "Origen / Aplicación": [c.origen_aplicacion for c in b.cuentas] + [""],
        "Lectura": [c.lectura for c in b.cuentas] + [""],
    })
    return tabla
