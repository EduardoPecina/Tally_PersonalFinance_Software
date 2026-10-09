"""Resumen: ¿cuánto dinero tengo, cuánto gasté y en qué?"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from motor import cierre, cuentas, ingresos, plan_deudas, reportes, tarjetas
from motor.modelo import TipoCuenta
from portal.componentes import estado, formato, graficas, por_recuperar
from portal.componentes import tarjeta as estado_tarjeta
from portal.componentes.sesion import libro
from portal.navegacion import enlace
from portal.paginas import ayuda, calendario, presupuestos, salud

PERSONALIZADO = "personalizado"
PERIODOS = {**reportes.PERIODOS, PERSONALIZADO: "Elegir fechas"}


def _periodo() -> tuple[date, date]:
    lib = libro()
    preferido = lib.perfil.periodo_inicial if lib.perfil else "mes_actual"
    clave = estado.control("inicio", "periodo", preferido, lambda k: st.segmented_control(
        "Periodo", list(PERIODOS), format_func=PERIODOS.get, key=k, required=True, label_visibility="collapsed"))
    if clave == PERSONALIZADO:
        inicial = reportes.rango_periodo(lib, "mes_actual")
        rango = estado.control("inicio", "rango", inicial, lambda k: st.date_input(
            "Fechas", key=k, format="DD/MM/YYYY"))
        if isinstance(rango, (tuple, list)) and len(rango) == 2:
            return rango[0], rango[1]
        st.caption("Elige la fecha final.")
        return inicial
    return reportes.rango_periodo(lib, clave)


def _situacion() -> None:
    ind = reportes.indicadores(libro())
    columnas = st.columns(5 if ind.te_deben else 4)
    columnas[0].metric("Dinero disponible", formato.dinero_metrica(ind.dinero_disponible),
                       help="Lo que puedes usar ya: tus cuentas marcadas como disponibles (débito, efectivo…).")
    columnas[1].metric("Total en cuentas", formato.dinero_metrica(ind.total_en_cuentas),
                       help="Débito, ahorro, efectivo, inversiones y otras cuentas.")
    columnas[2].metric("Deuda de tarjetas", formato.dinero_metrica(ind.deuda_tarjetas))
    columnas[3].metric("Patrimonio neto", formato.dinero_metrica(ind.patrimonio_neto),
                       help="Todo lo que tienes menos lo que debes (aproximado).")
    if ind.te_deben:
        columnas[4].metric("Te deben", formato.dinero_metrica(ind.te_deben))


def _delta(valor) -> str | None:
    return None if not valor else f"{'+' if valor > 0 else ''}{formato.dinero(valor)} vs. periodo anterior"


def _periodo_resumen(desde: date, hasta: date) -> None:
    comparacion = reportes.comparar(libro(), desde, hasta, hoy=libro().hoy())
    actual, diferencia = comparacion.actual, comparacion.diferencia
    columnas = st.columns(4)
    columnas[0].metric("Ingresos", formato.dinero_metrica(actual.ingresos), delta=_delta(diferencia.ingresos))
    columnas[1].metric("Gastos", formato.dinero_metrica(actual.gastos), delta=_delta(diferencia.gastos), delta_color="inverse")
    columnas[2].metric("Ahorro real", formato.dinero_metrica(actual.ahorro_real), delta=_delta(diferencia.ahorro_real),
                       help="Ingresos menos gastos del periodo.")
    columnas[3].metric("Apartado a ahorro", formato.dinero_metrica(actual.apartado_a_ahorro),
                       help="Lo que pasaste a tus cuentas de ahorro e inversión (neto).")
    if comparacion.al is not None:                          # el periodo va a la mitad
        st.caption(f"Comparado con los mismos días del periodo anterior: {formato.rango(desde, comparacion.al)} "
                   f"contra {formato.rango(comparacion.desde_anterior, comparacion.hasta_anterior)}.")
    if actual.ajustes:
        st.caption(f"Ajustes de saldo en el periodo: {formato.dinero_md(actual.ajustes)} "
                   "(no cuentan como ingreso ni gasto).")


def _avisos() -> None:
    """Pagos de tarjeta vencidos o que vencen en los próximos días, hasta arriba."""
    for tarjeta, actual in tarjetas.pagos_proximos(libro()):
        monto, limite = formato.dinero_md(actual.corte.por_liquidar), formato.fecha(actual.corte.fecha_limite_pago)
        if actual.situacion == tarjetas.VENCIDA:
            st.error(f"**{formato.md(tarjeta.nombre)}**: el pago de {monto} venció el {limite}.", icon="🔴")
        else:
            dias = actual.dias_para_pagar
            cuando = "hoy" if dias == 0 else "mañana" if dias == 1 else f"en {dias} días"
            st.warning(f"**{formato.md(tarjeta.nombre)}**: paga {monto} antes del {limite} ({cuando}).", icon="⏳")


def _recordar_cierre() -> None:
    """Los primeros días del mes: el mes anterior ya terminó y aún no lo cierras."""
    mes = cierre.recordar(libro())
    if mes is not None:
        st.info(f"**{formato.mes(*mes)} ya terminó.** Revisa su cierre: cómo te fue, qué falta registrar y qué hacer "
                "este mes.", icon="📆")
        enlace("cierre", "Ver el cierre de mes", "📆")


def _tarjetas() -> None:
    lib = libro()
    lista = cuentas.listar(lib, tipo=TipoCuenta.CREDITO)
    if not lista:
        return
    st.subheader("Tarjetas de crédito")
    columnas = st.columns(min(len(lista), 2))
    for i, tarjeta in enumerate(lista):
        with columnas[i % len(columnas)], st.container(border=True):
            st.markdown(f"**{tarjeta.nombre}**" + (f"  \n:gray[{tarjeta.institucion}]" if tarjeta.institucion else ""))
            estado_tarjeta.mostrar(tarjeta)


def _plan_de_deudas() -> None:
    """Tu plan para salir de deudas (Deudas › Plan), si lo guardaste: cuánto pagar a cada una y a cuál va lo extra."""
    lib = libro()
    av = plan_deudas.avance(lib)
    if av is None:
        return
    st.subheader("🎯 Tu plan para salir de deudas")
    with st.container(border=True):
        if not av.alcanza:
            st.warning(f"Con los {formato.dinero_md(av.presupuesto)} al mes de tu plan ya no alcanzas lo mínimo que "
                       "piden tus deudas. Revisa tu plan.", icon="🛑")
        else:
            nombres = {c.id: c.nombre for c in lib.cuentas()}
            lineas = [f"- **{formato.md(nombres[i])}**: {formato.dinero_md(monto)}"
                      + (" 🎯 *(aquí va lo extra)*" if av.objetivo and i == av.objetivo.cuenta_id else "")
                      for i, monto in sorted(av.pagos.items(), key=lambda x: -x[1])]
            fin = f"{formato.MESES[av.fin.month - 1]} de {av.fin.year}" if av.fin else ""
            st.markdown(f"Tus próximos pagos ({formato.dinero_md(av.presupuesto)} en total):\n" + "\n".join(lineas)
                        + (f"\n\nAsí terminas de pagar en **{fin}**." if fin else ""))
        enlace("deudas", "Ver mi plan de deudas", "🎯")


def _quincenas() -> None:
    """Lo que quedaba en la cuenta justo antes de cada pago de tu ingreso principal (sea nómina, honorarios, ventas…)."""
    lib = libro()
    nombre = ingresos.nombre_principal(lib)
    cada = f"cada pago de {nombre}" if nombre else "cada pago de tu ingreso principal"
    for cuenta in cuentas.listar(lib):
        sobrantes = reportes.sobrantes_de_quincena(lib, cuenta.id, lib.hoy() - timedelta(days=200))[-6:]
        if len(sobrantes) < 2:
            continue
        st.subheader(f"Lo que te sobró antes de {cada} · {cuenta.nombre}")
        graficas.barras([(formato.fecha(s.fecha), s.sobrante) for s in reversed(sobrantes)], "Sobrante",
                       "Pago del")


def mostrar() -> None:
    lib = libro()
    st.title(f"¡Hola, {lib.perfil.nombre}!" if lib.perfil else "Resumen")
    st.caption(f"Hoy es {formato.fecha_larga(lib.hoy())}.")
    if not cuentas.listar(lib):
        st.info("Agrega tu primera cuenta para empezar.")
        enlace("cuentas", "Ir a Cuentas", "🏦")
        return

    _avisos()
    _recordar_cierre()
    salud.aviso_en_el_resumen()
    ayuda.tarjeta_en_el_resumen()
    calendario.proximos_avisos()
    por_recuperar.avisos()
    st.subheader("Tu situación hoy")
    _situacion()
    por_recuperar.mostrar()

    st.divider()
    desde, hasta = _periodo()
    st.subheader(f"Periodo: {formato.rango(desde, hasta)}")
    _periodo_resumen(desde, hasta)

    izquierda, derecha = st.columns(2)
    with izquierda:
        st.markdown("**¿En qué gasté?** · por categoría")
        graficas.barras([(r, v) for r, v in reportes.gastos_por_rubro(lib, desde, hasta).items() if v > 0], "Gasto",
                        "Categoría")
    with derecha:
        st.markdown("**Por clasificación**")
        graficas.barras([(g, v) for g, v in reportes.gastos_por_grupo(lib, desde, hasta).items() if v > 0], "Gasto",
                        "Clasificación")
    with st.expander("Ver por subcategoría"):
        graficas.barras([(t.nombre, t.total) for t in reportes.gastos_por_categoria(lib, desde, hasta)
                         if t.total > 0], "Gasto", "Subcategoría")

    # Al menos tres meses de contexto, aunque el periodo elegido sea más corto.
    hasta_grafica = max(desde, min(hasta, lib.hoy()))
    desde_grafica = min(desde, hasta_grafica - timedelta(days=90))
    st.markdown(f"**Evolución de tu patrimonio** · {formato.rango(desde_grafica, hasta_grafica)}")
    graficas.linea([(p.fecha, p.patrimonio_neto) for p in reportes.evolucion(lib, desde_grafica, hasta_grafica)])

    presupuestos.avance(*reportes.rango_periodo(libro(), "mes_actual"))
    _tarjetas()
    _plan_de_deudas()
    _quincenas()
    st.divider()
    enlace("registrar", "Registrar un movimiento", "➕")
