"""Contabilidad técnica (motor/contabilidad.py): estados financieros, balanza y bienes, derivados de tus movimientos.

Da clic en cualquier renglón para ver los movimientos que lo forman.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import contabilidad as cb
from portal.componentes import bienes as bienes_ui
from portal.componentes import exportar, formato
from portal.componentes.sesion import libro

# Fondo de los renglones de título y total (con transparencia: se ve bien en tema claro y oscuro).
FONDOS = {"titulo": "background-color: rgba(107, 83, 241, 0.10); font-weight: 700",
          "grupo": "font-weight: 600",
          "subtotal": "background-color: rgba(128, 128, 128, 0.10); font-weight: 600",
          "total": "background-color: rgba(107, 83, 241, 0.18); font-weight: 700"}
SANGRIA = "  "
TIP = "Da clic en un renglón para ver de qué movimientos sale."


def mostrar() -> None:
    st.title("Contabilidad Técnica")
    st.caption("Tus finanzas como las ve un contador, armadas solas con lo que ya registras. No tienes que capturar "
               "nada más: si corriges un movimiento, todos los reportes cambian y siempre cuadran entre sí.")
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
            "inversiones, lo que te deben, tus bienes), **Pasivo** lo que debes (tarjetas) y **Patrimonio** lo que "
            "de verdad es tuyo: Activo − Pasivo.\n"
            "- **Estado de Resultados**: una película del periodo. Cuánto ganaste, cuánto gastaste y cuánto te "
            "quedó. Una compra con tarjeta ya es gasto aunque la pagues después. Los **cambios de valor** (tus "
            "inversiones, la depreciación de tus bienes) van aparte: no es dinero que entró o salió.\n"
            "- **Flujo de Efectivo**: por dónde entró y salió el dinero de tus cuentas de débito, ahorro y "
            "efectivo. Aquí la compra con tarjeta aparece hasta que **pagas** la tarjeta.\n"
            "- **Balanza de Comprobación**: la vista técnica. Cada movimiento se anota dos veces, en el **Debe** "
            "(lo que entra a una cuenta o lo que gastas) y en el **Haber** (de dónde salió); por eso las sumas "
            "siempre son iguales.\n"
            "- **Bienes**: tu casa, auto, laptop… lo que vale hoy, cuánto se ha depreciado y su plusvalía.\n\n"
            + TIP)

    situacion = cb.situacion(lib, [p[1] for p in periodos], desde)
    resultados = cb.resultados(lib, periodos)
    flujo = cb.flujo(lib, periodos)
    balanza = cb.balanza(lib, desde, hasta)

    pestanas = st.tabs(["Situación financiera", "Resultados", "Flujo de efectivo", "Balanza de comprobación",
                        "Bienes"])
    with pestanas[0]:
        _situacion(situacion)
    with pestanas[1]:
        _resultados(resultados)
    with pestanas[2]:
        _flujo(flujo)
    with pestanas[3]:
        _balanza(balanza)
    with pestanas[4]:
        bienes_ui.mostrar()

    st.download_button(
        "Descargar los 4 reportes en Excel", on_click="ignore", icon=":material/table_view:",
        data=lambda: exportar.excel({"Situación financiera": _exportable(_filas_situacion(situacion),
                                                                 _columnas_fecha(situacion.fechas)),
                             "Resultados": _exportable(_filas_resultados(resultados, detalle=True),
                                                       _columnas_periodo(resultados.periodos)),
                             "Flujo de efectivo": _exportable(_filas_flujo(flujo), _columnas_periodo(flujo.periodos)),
                             "Balanza": _tabla_balanza(balanza)}),
        file_name=f"TALLY_contabilidad_{desde:%Y-%m-%d}_a_{hasta:%Y-%m-%d}.xlsx")


# ------------------------------------------------------------ tabla y detalle

Fila = tuple[str, str, tuple, str, "cb.Origen | None"]     # (clase, concepto, importes, nota, origen)


def _dinero(valor: Decimal) -> str:
    return formato.dinero(valor) if valor else "—"


def _variacion(valores: tuple[Decimal, ...]) -> str:
    if len(valores) < 2:
        return ""
    cambio = valores[0] - valores[1]
    return ("+" if cambio > 0 else "") + formato.dinero(cambio) if cambio else "—"


def _estado(clave: str, columnas: list[str], filas: list[Fila], *, lectura: bool = False) -> None:
    """El estado financiero como tabla; al dar clic en un renglón, debajo aparece su detalle."""
    datos = {"Concepto": [(SANGRIA if f[0] == "renglon" else "") + f[1] for f in filas]}
    for i, nombre in enumerate(columnas):
        datos[nombre] = ["" if f[0] == "titulo" and not any(f[2]) else _dinero(f[2][i]) for f in filas]
    if len(columnas) > 1:
        datos["Variación"] = ["" if f[0] == "titulo" and not any(f[2]) else _variacion(f[2]) for f in filas]
    if lectura:
        datos["Lectura"] = [f[3] for f in filas]
    tabla = pd.DataFrame(datos)
    estilo = tabla.style.apply(lambda fila: [FONDOS.get(filas[fila.name][0], "")] * len(fila), axis=1)
    config = {c: st.column_config.TextColumn(alignment="right") for c in tabla.columns
              if c not in ("Concepto", "Lectura")}
    evento = st.dataframe(formato.pintar(estilo), column_config=config, hide_index=True, width="stretch", key=clave,
                          on_select="rerun", selection_mode="single-row", height=min(40 + 35 * len(tabla), 900))
    st.caption(TIP)
    seleccion = evento.selection.rows if evento else []
    if seleccion and seleccion[0] < len(filas):
        _detalle(filas[seleccion[0]])


def _detalle(fila: Fila, *, tecnico: bool = False) -> None:
    _, concepto, importes, _, origen = fila
    st.markdown(f"#### Detalle de {formato.md(concepto.strip())}")
    if origen is None:
        st.caption("Este renglón es una suma de otros: da clic en ellos para ver su detalle.")
        return
    lista = cb.movimientos(libro(), origen)
    if not lista:
        st.caption("No tuvo movimientos en el periodo: su saldo viene de antes.")
        return
    total = sum((m.importe for m in lista), Decimal(0))
    st.caption(f"{len(lista)} movimiento(s) en el periodo · suman {formato.dinero_md(total)}")
    tabla = pd.DataFrame({
        "Fecha": [m.fecha for m in lista], "Descripción": [m.descripcion for m in lista],
        "Tipo": [m.tipo for m in lista], "Contrapartida": [m.detalle for m in lista],
        **({"Debe": [float(m.debe) or None for m in lista], "Haber": [float(m.haber) or None for m in lista]}
           if tecnico else {"Importe": [float(m.importe) for m in lista]}),
    })
    vista, config = formato.tabla_en_pesos(tabla, ("Debe", "Haber") if tecnico else ("Importe",))
    config["Fecha"] = st.column_config.DateColumn(format="DD/MM/YYYY")
    st.dataframe(formato.pintar(vista), column_config=config, hide_index=True, width="stretch",
                 height=min(40 + 35 * len(tabla), 420))


def _columnas_fecha(fechas: tuple[date, ...]) -> list[str]:
    return [formato.fecha(f) for f in fechas]


def _columnas_periodo(periodos) -> list[str]:
    return [formato.rango(d, h) for d, h in periodos]


def _delta(valores: tuple[Decimal, ...]) -> str | None:
    if len(valores) < 2 or valores[0] == valores[1]:
        return None
    cambio = valores[0] - valores[1]
    return ("+" if cambio > 0 else "−") + formato.dinero(abs(cambio))


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
    a.metric("Lo que tienes (Activo)", formato.dinero_metrica(activo[0]), delta=_delta(activo))
    b.metric("Lo que debes (Pasivo)", formato.dinero_metrica(pasivo[0]), delta=_delta(pasivo), delta_color="inverse")
    c.metric("Lo que vales (Patrimonio)", formato.dinero_metrica(patrimonio[0]), delta=_delta(patrimonio))
    if s.cuadra:
        st.success("Cuadra: Activo = Pasivo + Patrimonio.", icon="✅")
    else:
        st.error("No cuadra: Activo ≠ Pasivo + Patrimonio. Revisa la bitácora o restaura un respaldo.")
    _estado("conta_sel_situacion", _columnas_fecha(s.fechas), _filas_situacion(s), lectura=len(s.fechas) > 1)


def _filas_situacion(s: cb.Situacion) -> list[Fila]:
    filas: list[Fila] = []
    titulos = {cb.ACTIVO: "ACTIVO · lo que tienes", cb.PASIVO: "PASIVO · lo que debes",
               cb.PATRIMONIO: "PATRIMONIO · lo que es tuyo"}
    for naturaleza in (cb.ACTIVO, cb.PASIVO, cb.PATRIMONIO):
        total = s.total(naturaleza)
        filas.append(("titulo", titulos[naturaleza], total, "", s.origen(naturaleza)))
        grupos = s.grupos(naturaleza)
        for grupo in grupos:
            if naturaleza != cb.PATRIMONIO:
                filas.append(("grupo", grupo, s.total(naturaleza, grupo), "", s.origen(naturaleza, grupo)))
            for r in (r for r in s.renglones if r.naturaleza == naturaleza and r.grupo == grupo):
                filas.append(("renglon", r.nombre, r.importes, _lectura(naturaleza, r.importes), r.origen))
        if not grupos:
            filas.append(("renglon", "Sin saldo", total, "", None))
        filas.append(("subtotal", f"Total {naturaleza.lower()}", total, _lectura(naturaleza, total),
                      s.origen(naturaleza)))
    suma = tuple(p + c for p, c in zip(s.total(cb.PASIVO), s.total(cb.PATRIMONIO)))
    filas.append(("total", "PASIVO + PATRIMONIO", suma, "", None))
    return filas


# ------------------------------------------------------- estado de resultados


def _resultados(r: cb.Resultados) -> None:
    st.subheader("Estado de Resultados")
    st.caption(f"¿Cuánto ganaste y cuánto gastaste? · {formato.rango(*r.periodos[0])}")
    a, b, c = st.columns(3)
    a.metric("Ingresos", formato.dinero_metrica(r.total_ingresos()[0]), delta=_delta(r.total_ingresos()))
    b.metric("Gastos", formato.dinero_metrica(r.total_gastos()[0]), delta=_delta(r.total_gastos()), delta_color="inverse")
    c.metric("Resultado del periodo", formato.dinero_metrica(r.resultado()[0]), delta=_delta(r.resultado()))
    detalle = st.toggle("Ver cada subcategoría", key="conta_resultados_sub")
    _estado("conta_sel_resultados", _columnas_periodo(r.periodos), _filas_resultados(r, detalle=detalle))
    st.caption("**Resultado del día a día**: lo que te quedó de lo que ganaste menos lo que gastaste. Los **cambios "
               "de valor** van aparte: rendimientos de tus inversiones (cuando cuadras con el valor oficial), "
               "depreciación y plusvalía de tus bienes, y lo que ganaste o perdiste al venderlos. Los saldos "
               "iniciales de cuentas nuevas no son resultado: son patrimonio.")


def _filas_resultados(r: cb.Resultados, *, detalle: bool) -> list[Fila]:
    filas: list[Fila] = []
    n = len(r.periodos)
    for titulo, renglones, total in (("INGRESOS", r.ingresos, r.total_ingresos()),
                                     ("GASTOS", r.gastos, r.total_gastos())):
        filas.append(("titulo", titulo, total, "", r.origen(renglones)))
        for grupo in dict.fromkeys(x.grupo for x in renglones):
            del_grupo = [x for x in renglones if x.grupo == grupo]
            filas.append(("grupo" if detalle else "renglon", grupo, cb._sumar_renglones(del_grupo, n), "",
                          r.origen(del_grupo)))
            if detalle:
                filas += [("renglon", x.nombre, x.importes, "", x.origen) for x in del_grupo]
        filas.append(("subtotal", f"Total {titulo.lower()}", total, "", r.origen(renglones)))
    filas.append(("total", "RESULTADO DE TU DÍA A DÍA", r.dia_a_dia(), "", r.origen(r.ingresos + r.gastos)))
    cambios = [x for x in r.cambios_de_valor if any(x.importes)]
    if cambios:
        filas.append(("titulo", "CAMBIOS DE VALOR (no es dinero que entró o salió)", r.total_cambios_de_valor(), "",
                      r.origen(cambios)))
        filas += [("renglon", x.nombre, x.importes, "", x.origen) for x in cambios]
    if any(r.ajustes.importes):
        filas.append(("renglon", r.ajustes.nombre, r.ajustes.importes, "", r.ajustes.origen))
    filas.append(("total", "RESULTADO DEL PERIODO", r.resultado(), "", None))
    return filas


# --------------------------------------------------------- flujo de efectivo


def _flujo(f: cb.Flujo) -> None:
    st.subheader("Estado de Flujo de Efectivo")
    st.caption(f"¿Por dónde entró y salió tu dinero? · {formato.rango(*f.periodos[0])} · método directo")
    a, b, c = st.columns(3)
    a.metric("Efectivo al inicio", formato.dinero_metrica(f.inicial[0]))
    b.metric("Entró − salió", formato.dinero_metrica(f.total()[0]))
    c.metric("Efectivo al final", formato.dinero_metrica(f.final[0]), delta=_delta(f.final))
    _estado("conta_sel_flujo", _columnas_periodo(f.periodos), _filas_flujo(f))
    if not f.cuadra:
        st.error("El flujo no cuadra con tus saldos: revisa la bitácora o restaura un respaldo.")
    st.caption("Cuenta como efectivo: " + (", ".join(f.cuentas) or "ninguna cuenta todavía") + ". Positivo = "
               "entró, negativo = salió. Pasar dinero entre esas cuentas no cambia tu efectivo.")
    if f.gasto_con_tarjeta[0]:
        st.info(f"Gastaste {formato.dinero_md(f.gasto_con_tarjeta[0])} con tarjeta de crédito en el periodo: ya es "
                "gasto en el Estado de Resultados, pero aquí aparece hasta que pagas la tarjeta. Por eso el "
                "resultado y el flujo no tienen que coincidir.", icon="💳")


def _filas_flujo(f: cb.Flujo) -> list[Fila]:
    filas: list[Fila] = [("subtotal", "Efectivo al inicio del periodo", f.inicial, "", None)]
    for seccion in f.secciones():
        filas.append(("titulo", seccion.upper(), f.total(seccion), "", f.origen(seccion)))
        filas += [("renglon", r.nombre, r.importes, "", r.origen) for r in f.renglones if r.naturaleza == seccion]
        filas.append(("subtotal", f"Neto de {seccion.lower()}", f.total(seccion), "", f.origen(seccion)))
    filas.append(("subtotal", "Aumento (o disminución) de efectivo", f.total(), "", f.origen()))
    filas.append(("total", "Efectivo al final del periodo", f.final, "", None))
    return filas


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
    evento = st.dataframe(formato.pintar(mostrada), column_config=config, hide_index=True, width="stretch", key="conta_sel_balanza",
                          on_select="rerun", selection_mode="single-row", height=min(40 + 35 * len(mostrada), 640))
    st.caption("**Deudor** es el saldo de lo que tienes o gastaste; **acreedor**, el de lo que debes, ganaste o es "
               "patrimonio. Las cuentas de ingresos y gastos empiezan cada periodo en ceros: lo de antes está en "
               "«Resultados de periodos anteriores». Una cuenta por cobrar que ya te pagaron queda en ceros "
               "(compensada). " + TIP)
    seleccion = evento.selection.rows if evento else []
    if seleccion and seleccion[0] < len(vista.cuentas):
        c = vista.cuentas[seleccion[0]]
        _detalle(("renglon", c.nombre, (), "", c.origen), tecnico=True)


# ------------------------------------------------------ tablas (y exportar)


def _exportable(filas: list[Fila], columnas: list[str]) -> pd.DataFrame:
    datos = {"Concepto": [f[1] for f in filas]}
    for i, nombre in enumerate(columnas):
        datos[nombre] = [float(f[2][i]) if f[2] and (f[0] != "titulo" or any(f[2])) else None for f in filas]
    return pd.DataFrame(datos)


def _tabla_balanza(b: cb.Balanza) -> pd.DataFrame:
    def deudor(v: Decimal) -> float | None:
        return float(v) if v > 0 else None

    def acreedor(v: Decimal) -> float | None:
        return float(-v) if v < 0 else None

    sumas = b.sumas()
    return pd.DataFrame({
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
