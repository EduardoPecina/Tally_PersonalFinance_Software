"""Cierre de mes (motor/cierre.py): la boleta de un mes que terminó, con recomendaciones, lo que falta registrar y
la descarga en Excel. Cerrar no bloquea: si después cambias algo de ese mes, aquí aparece como cambio posterior."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import cierre, consultas
from motor.cierre import Reporte
from portal import navegacion
from portal.componentes import exportar, formato
from portal.componentes.sesion import ejecutar, libro

PENDIENTES = {"calendario": "📅", "temporal": "↩️", "tarjeta": "💳"}


def mostrar() -> None:
    lib = libro()
    st.title("Cierre de mes")
    st.caption("La boleta de cada mes: qué pasó con tu dinero, qué estuvo bien, qué no y qué hacer el mes siguiente. "
               "Cerrar un mes no lo bloquea: si después registras o corriges algo de ese mes, aquí te lo muestra.")
    lista = cierre.meses(lib)
    if not lista:
        st.info("Cuando registres tus movimientos, aquí verás el cierre de cada mes.", icon="📆")
        return
    hoy = lib.hoy()
    sugerido = cierre.anterior(hoy)
    elegido = st.selectbox(
        "Mes", lista, index=lista.index(sugerido) if sugerido in lista else 0, key="cierre_mes",
        format_func=lambda m: formato.mes(*m) + (" · ✅ cerrado" if lib.cierre(cierre.clave(*m)) else "")
        + (" · en curso" if (m[0], m[1]) == (hoy.year, hoy.month) else ""))
    r = cierre.reporte(lib, *elegido)
    _estado(r)
    _veredicto(r)
    _recomendaciones(r)
    gasto, presupuestos, ingresos, deudas, metas, pendientes = st.tabs([
        "💸 A dónde se fue", "🎯 Presupuestos", "💰 Ingresos", "💳 Deudas", "🏆 Metas y patrimonio",
        f"✅ Para cerrar bien ({len(r.pendientes)})" if r.pendientes else "✅ Para cerrar bien"])
    with gasto:
        _gasto(r)
    with presupuestos:
        _presupuestos(r)
    with ingresos:
        _ingresos(r)
    with deudas:
        _deudas(r)
    with metas:
        _metas(r)
    with pendientes:
        _pendientes(r)
    st.divider()
    _descargar(r)
    _historial(lista)


# ------------------------------------------------------------- estado del cierre


def _estado(r: Reporte) -> None:
    nombre = formato.mes(r.anio, r.mes)
    if r.en_curso:
        st.info(f"{nombre} aún no termina: los números van a cambiar. Podrás cerrarlo cuando acabe.", icon="⏳")
        return
    if r.cierre is None:
        a, b = st.columns([3, 1], vertical_alignment="center")
        a.markdown(f"**{nombre} ya terminó.** Revisa la boleta y lo que falta registrar; cuando todo cuadre, ciérralo. "
                   "No se bloquea nada: es tu marca de «ya lo revisé».")
        if b.button(f"Cerrar {nombre.split()[0].lower()}", type="primary", icon=":material/lock:", width="stretch",
                    key="cierre_cerrar"):
            if ejecutar(lambda li: cierre.cerrar(li, r.anio, r.mes), f"Cerraste {nombre.lower()}"):
                st.rerun()
        return
    c, cambios = r.cierre, r.cambios
    texto = f"Cerraste {nombre.lower()} el {formato.fecha(c.cerrado_en.date())}."
    if not cambios.hay:
        st.success(texto + " No ha cambiado nada desde entonces.", icon="✅")
    else:
        partes = []
        if cambios.nuevos:
            partes.append(f"{len(cambios.nuevos)} movimiento(s) nuevo(s)")
        if cambios.editados:
            partes.append(f"{len(cambios.editados)} corregido(s)")
        if cambios.borrados:
            partes.append(f"{cambios.borrados} borrado(s)")
        cifras = [f"{n} {formato.dinero_md(v)}" if v < 0 else f"{n} +{formato.dinero_md(v)}"
                  for n, v in (("ingresos", cambios.ingresos), ("gastos", cambios.gastos)) if v]
        st.warning(texto + " **Desde entonces cambió:** " + ", ".join(partes or ["algunos importes"])
                   + (f" ({'; '.join(cifras)})" if cifras else "") + ". Son ajustes posteriores al cierre: revísalos "
                   "y, si están bien, vuelve a cerrar el mes.", icon="🔒")
        ops = cambios.nuevos + cambios.editados
        if ops:
            with st.expander("Ver los movimientos que cambiaron"):
                filas = {f.id: f for f in consultas.buscar(libro(), desde=r.desde, hasta=r.hasta)}
                st.dataframe(pd.DataFrame({
                    "": ["Nuevo" if op in cambios.nuevos else "Corregido" for op in ops],
                    "Fecha": [op.fecha for op in ops],
                    "Descripción": [op.descripcion for op in ops],
                    "Importe": [formato.dinero_con_signo(filas[op.id].monto, filas[op.id].sentido)
                                if op.id in filas else "" for op in ops],
                }), hide_index=True, width="stretch",
                    column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})
    a, b, _ = st.columns([1, 1, 2])
    if cambios.hay and a.button("Volver a cerrar con los cambios", type="primary", key="cierre_volver",
                                width="stretch"):
        if ejecutar(lambda li: cierre.cerrar(li, r.anio, r.mes, c.notas), f"Cerraste otra vez {nombre.lower()}"):
            st.rerun()
    if (b if cambios.hay else a).button("Quitar el cierre", key="cierre_reabrir", width="stretch",
                help="Tus movimientos no se tocan: solo deja de estar marcado como cerrado."):
        if ejecutar(lambda li: cierre.reabrir(li, r.anio, r.mes), f"Se quitó el cierre de {nombre.lower()}"):
            st.rerun()


# ------------------------------------------------------------- veredicto


def _veredicto(r: Reporte) -> None:
    n = r.numeros
    st.subheader("El resultado del mes")
    a, b, c, d = st.columns(4)
    base = r.anterior
    a.metric("Entró", formato.dinero(n.ingresos), delta=_delta(n.ingresos, base and base.ingresos))
    b.metric("Salió (gastos)", formato.dinero(n.gastos), delta=_delta(n.gastos, base and base.gastos),
             delta_color="inverse")
    c.metric("Ahorraste", formato.dinero(n.ahorro), delta=_delta(n.ahorro, base and base.ahorro))
    d.metric("Parte ahorrada", f"{n.tasa} %" if n.tasa is not None else "—", help=f"Tu meta: {r.meta_ahorro} %.")
    if base is not None:
        st.caption("Las flechas comparan con el mes anterior."
                   + (f" Tu promedio de los meses previos: entra {formato.dinero_md(r.promedio.ingresos)} y salen "
                      f"{formato.dinero_md(r.promedio.gastos)}." if r.promedio else ""))
    if not n.ingresos and not n.gastos:
        st.caption("Sin ingresos ni gastos este mes.")
    elif n.ahorro < 0:
        st.error(f"Gastaste **{formato.dinero_md(-n.ahorro)} más** de lo que entró.", icon="🔴")
    elif n.tasa is not None and n.tasa >= r.meta_ahorro:
        st.success(f"Cumpliste tu meta: ahorraste el {n.tasa} % (tu meta es el {r.meta_ahorro} %).", icon="🎉")
    elif n.tasa is not None:
        st.warning(f"Ahorraste el {n.tasa} %; tu meta es el {r.meta_ahorro} %.", icon="⚠️")


def _delta(actual: Decimal, antes: Decimal | None) -> str | None:
    if antes is None or actual == antes:
        return None
    diferencia = actual - antes
    return ("+" if diferencia > 0 else "-") + formato.dinero(abs(diferencia))


def _recomendaciones(r: Reporte) -> None:
    if not r.recomendaciones:
        return
    with st.container(border=True):
        st.markdown("**💡 Para el mes siguiente**")
        st.markdown("\n".join(f"{i}. {formato.md(t)}" for i, t in enumerate(r.recomendaciones, start=1)))


# ------------------------------------------------------------- pestañas


def _gasto(r: Reporte) -> None:
    if not r.rubros:
        st.caption("Sin gastos este mes.")
        return
    st.dataframe(pd.DataFrame({
        "Categoría": [x.nombre for x in r.rubros],
        "Este mes": [formato.dinero(x.gastado) for x in r.rubros],
        "Tu promedio": [formato.dinero(x.promedio) if x.promedio is not None else "—" for x in r.rubros],
        "Diferencia": [_con_signo(x.diferencia) for x in r.rubros],
        "": ["⬆️ subió" if x.subio else "" for x in r.rubros],
    }), hide_index=True, width="stretch")
    minimo = r.rubros[0].minimo
    st.caption(f"Tu promedio: los meses anteriores con datos (hasta 3). «Subió»: {cierre.SUBE_PORCENTAJE} % más y al "
               f"menos {formato.dinero_md(minimo)} más.")
    h = r.hormiga
    if h.veces:
        st.markdown(f"**🐜 Gastos hormiga:** {h.veces} gastos de menos de {formato.dinero_md(h.umbral)} "
                    f"que sumaron **{formato.dinero_md(h.total)}**"
                    + (f" ({(h.total / r.numeros.gastos * 100).quantize(Decimal('0.1'))} % de tus gastos)."
                       if r.numeros.gastos else "."))
        st.caption(" · ".join(f"{formato.md(nombre)}: {veces} {'vez' if veces == 1 else 'veces'}, "
                              f"{formato.dinero_md(total)}"
                              for nombre, veces, total in h.ejemplos))
    if r.suscripciones:
        total = sum((m for _, m in r.suscripciones), Decimal(0))
        st.markdown(f"**⭐ Suscripciones que te cobraron:** {formato.dinero_md(total)} — "
                    + ", ".join(f"{formato.md(n)} {formato.dinero_md(m)}" for n, m in r.suscripciones))


def _con_signo(valor: Decimal | None) -> str:
    if valor is None:
        return "—"
    return ("+" if valor > 0 else "-" if valor < 0 else "") + formato.dinero(abs(valor))


def _presupuestos(r: Reporte) -> None:
    if not r.presupuestos:
        st.caption("No tienes presupuestos. Ponlos en **Presupuestos** para ver aquí si los cumpliste.")
        navegacion.enlace("presupuestos", "Ir a Presupuestos", "🎯")
        return
    cumplidos = sum(1 for p in r.presupuestos if p.restante >= 0)
    st.markdown(f"Cumpliste **{cumplidos} de {len(r.presupuestos)}** presupuestos.")
    st.dataframe(pd.DataFrame({
        "Categoría": [p.nombre for p in r.presupuestos],
        "Presupuesto": [formato.dinero(p.presupuesto) for p in r.presupuestos],
        "Gastaste": [formato.dinero(p.gastado) for p in r.presupuestos],
        "Resultado": [f"✅ te sobraron {formato.dinero(p.restante)}" if p.restante >= 0
                      else f"🔴 te pasaste por {formato.dinero(-p.restante)}" for p in r.presupuestos],
    }), hide_index=True, width="stretch")


def _ingresos(r: Reporte) -> None:
    if not r.ingresos_fijos:
        st.caption("No tienes ingresos fijos configurados. En **Ingresos** puedes decirle a TALLY cuánto y cuándo te "
                   "pagan, y aquí verás si te llegó todo.")
        navegacion.enlace("ingresos", "Ir a Ingresos", "💰")
        return
    st.dataframe(pd.DataFrame({
        "Ingreso": [i.nombre for i in r.ingresos_fijos],
        "Esperabas": [formato.dinero(i.esperado) for i in r.ingresos_fijos],
        "Registraste": [formato.dinero(i.recibido) for i in r.ingresos_fijos],
        "": ["✅" if not i.faltan else "⚠️ falta el del " + ", ".join(formato.fecha(d) for d in i.faltan)
             for i in r.ingresos_fijos],
    }), hide_index=True, width="stretch")


def _deudas(r: Reporte) -> None:
    if not r.deudas:
        st.caption("No debías nada en tus tarjetas ni préstamos. 👏")
        return
    antes = sum((d.al_inicio for d in r.deudas), Decimal(0))
    despues = sum((d.al_final for d in r.deudas), Decimal(0))
    a, b, c = st.columns(3)
    a.metric("Debías al empezar", formato.dinero(antes))
    b.metric("Debías al terminar", formato.dinero(despues), delta=_con_signo(despues - antes) if despues != antes
             else None, delta_color="inverse")
    c.metric("Intereses y comisiones", formato.dinero(r.intereses), help="Lo que te costó deber este mes.")
    st.dataframe(pd.DataFrame({
        "Tarjeta o préstamo": [d.nombre for d in r.deudas],
        "Al empezar": [formato.dinero(d.al_inicio) for d in r.deudas],
        "Al terminar": [formato.dinero(d.al_final) for d in r.deudas],
        "Cambio": [_con_signo(d.cambio) for d in r.deudas],
    }), hide_index=True, width="stretch")


def _metas(r: Reporte) -> None:
    a, b = st.columns(2)
    a.metric("Tu patrimonio al terminar", formato.dinero(r.patrimonio_fin),
             delta=_con_signo(r.patrimonio_fin - r.patrimonio_inicio) if r.patrimonio_fin != r.patrimonio_inicio
             else None, help="Todo lo que tienes (cuentas, inversiones, bienes) menos lo que debes. La flecha: cuánto "
                             "cambió en el mes.")
    if r.fondo_meses is not None:
        b.metric("Tu fondo de emergencia cubre", f"{r.fondo_meses} meses", help="De tus gastos esenciales.")
    if not r.metas:
        st.caption("No tienes metas de ahorro. Crea una en **Metas de ahorro**.")
        return
    st.dataframe(pd.DataFrame({
        "Meta": [("🛟 " if m.emergencia else "") + m.nombre for m in r.metas],
        "Aportaste este mes": [_con_signo(m.aportado) if m.aportado else "—" for m in r.metas],
        "Llevas": [f"{formato.dinero(m.ahorrado)} de {formato.dinero(m.objetivo)}" for m in r.metas],
        "": ["" if m.a_tiempo is None else ("✅ a tiempo" if m.a_tiempo else "⏳ vas atrasado") for m in r.metas],
    }), hide_index=True, width="stretch")


def _pendientes(r: Reporte) -> None:
    st.caption("Antes de cerrar, revisa que no falte nada. Marca lo que ya revisaste (es solo para ti).")
    for n, p in enumerate(r.pendientes):
        st.checkbox(f"{PENDIENTES[p.clase]} {p.texto}", key=f"cierre_pend_{r.anio}_{r.mes}_{n}")
    if not r.pendientes:
        st.success("TALLY no encontró nada pendiente de registrar.", icon="✅")
    st.checkbox("🏦 Compara el saldo de tus cuentas con tus estados de cuenta del banco (Cuentas → Cuadrar).",
                key=f"cierre_cuadrar_{r.anio}_{r.mes}")
    st.checkbox("💾 Haz un respaldo (Respaldos y bitácora).", key=f"cierre_respaldo_{r.anio}_{r.mes}")


# ------------------------------------------------------------- descargar e historial


def _descargar(r: Reporte) -> None:
    n = r.numeros
    resumen = pd.DataFrame({"Concepto": ["Entró", "Salió (gastos)", "Ahorraste", "Patrimonio al empezar",
                                         "Patrimonio al terminar", "Intereses y comisiones", "Gastos hormiga"],
                            "Importe": [float(n.ingresos), float(n.gastos), float(n.ahorro), float(r.patrimonio_inicio),
                                        float(r.patrimonio_fin), float(r.intereses), float(r.hormiga.total)]})
    hojas = {
        "Resumen": resumen,
        "Recomendaciones": pd.DataFrame({"Para el mes siguiente": r.recomendaciones or ["—"]}),
        "Categorías": pd.DataFrame({"Categoría": [x.nombre for x in r.rubros],
                                    "Este mes": [float(x.gastado) for x in r.rubros],
                                    "Tu promedio": [float(x.promedio) if x.promedio is not None else None
                                                    for x in r.rubros]}),
        "Presupuestos": pd.DataFrame({"Categoría": [p.nombre for p in r.presupuestos],
                                      "Presupuesto": [float(p.presupuesto) for p in r.presupuestos],
                                      "Gastaste": [float(p.gastado) for p in r.presupuestos]}),
        "Deudas": pd.DataFrame({"Tarjeta o préstamo": [d.nombre for d in r.deudas],
                                "Al empezar": [float(d.al_inicio) for d in r.deudas],
                                "Al terminar": [float(d.al_final) for d in r.deudas]}),
        "Pendientes": pd.DataFrame({"Fecha": [p.fecha for p in r.pendientes],
                                    "Qué falta": [p.texto for p in r.pendientes]}),
        "Movimientos": _movimientos(r),
    }
    st.download_button("Descargar el cierre en Excel", exportar.excel(hojas, columnas_dinero={"Importe"}),
                       file_name=f"TALLY_cierre_{cierre.clave(r.anio, r.mes)}.xlsx", icon=":material/download:",
                       on_click="ignore", key="cierre_excel")


def _movimientos(r: Reporte) -> pd.DataFrame:
    filas = consultas.buscar(libro(), desde=r.desde, hasta=r.hasta, orden="fecha_asc")
    return pd.DataFrame({
        "Fecha": [f.fecha for f in filas], "Tipo": [f.tipo_etiqueta for f in filas],
        "Descripción": [f.descripcion for f in filas], "Subcategoría": [f.categoria for f in filas],
        "Cuenta": [f.cuenta + (f" → {f.cuenta_destino}" if f.cuenta_destino else "") for f in filas],
        "Importe": [float(f.importe_con_signo) for f in filas],
    })


def _historial(lista: list[tuple[int, int]]) -> None:
    lib = libro()
    with st.expander("📚 Tus meses anteriores"):
        filas = []
        for anio, mes in lista[:24]:
            n = cierre.resultado(lib, *cierre.rango(anio, mes))
            c = lib.cierre(cierre.clave(anio, mes))
            filas.append({"Mes": formato.mes(anio, mes), "Entró": formato.dinero(n.ingresos),
                          "Salió": formato.dinero(n.gastos), "Ahorraste": formato.dinero(n.ahorro),
                          "%": f"{n.tasa} %" if n.tasa is not None else "—",
                          "Cierre": f"✅ {formato.fecha(c.cerrado_en.date())}" if c else ""})
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
        st.caption("Elige un mes arriba para ver su cierre completo.")
