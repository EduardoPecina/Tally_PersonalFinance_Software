"""Estado de una tarjeta de crédito: línea, deuda, disponible, uso de la línea y el pago del último corte."""

from __future__ import annotations

import streamlit as st

from motor import tarjetas
from motor.modelo import Cuenta
from portal.componentes import formato
from portal.componentes.sesion import libro

USO_ALTO = 0.7      # a partir de aquí se avisa; la recomendación común es usar menos del 30 %


def _situacion(estado: tarjetas.EstadoTarjeta) -> None:
    corte = estado.corte
    if estado.situacion == tarjetas.SIN_CORTE:
        st.caption("Registra el **día de corte** (Cuentas → Editar) para ver cuánto pagar y hasta cuándo.")
    elif estado.situacion == tarjetas.AL_CORRIENTE:
        pagado = f" (pagaste {formato.dinero_md(corte.deuda_al_corte)})" if corte.deuda_al_corte else ""
        st.success(f"Al corriente: el corte del {formato.fecha(corte.fin)} ya está liquidado{pagado}.", icon="✅")
    else:
        monto = formato.dinero_md(corte.por_liquidar)
        if estado.situacion == tarjetas.VENCIDA:
            st.error(f"Pago vencido: faltan **{monto}** del corte del {formato.fecha(corte.fin)}. La fecha límite "
                     f"era el {formato.fecha(corte.fecha_limite_pago)}.", icon="🔴")
        elif estado.situacion == tarjetas.SIN_FECHA:
            st.warning(f"Paga **{monto}** del corte del {formato.fecha(corte.fin)}. Registra la regla de pago "
                       "(Cuentas → Editar) para saber la fecha límite.", icon="⏳")
        else:
            dias = estado.dias_para_pagar
            cuando = "hoy" if dias == 0 else "mañana" if dias == 1 else f"en {dias} días"
            st.warning(f"Paga **{monto}** antes del **{formato.fecha(corte.fecha_limite_pago)}** ({cuando}) para "
                       "no generar intereses.", icon="⏳")
        if corte.pagado_despues_del_corte:
            st.caption(f"Ya abonaste {formato.dinero_md(corte.pagado_despues_del_corte)} de "
                       f"{formato.dinero_md(corte.deuda_al_corte)} de ese corte.")


def mostrar(tarjeta: Cuenta) -> None:
    """El panel completo de una tarjeta (va dentro de un contenedor con borde)."""
    lib = libro()
    estado = tarjetas.estado(lib, tarjeta.id)
    columnas = st.columns(3)
    columnas[0].metric("Debes", formato.dinero_metrica(estado.deuda))
    if estado.limite is not None:
        columnas[1].metric("Disponible", formato.dinero_metrica(estado.disponible))
        columnas[2].metric("Línea de crédito", formato.dinero_metrica(estado.limite))
        uso = float(estado.uso)
        texto = f"Usas el {uso:.0%} de tu línea"
        if estado.excedida:
            texto += f" · te pasaste por {formato.dinero(estado.deuda - estado.limite)}"
        st.progress(min(uso, 1.0), text=texto)
        if uso >= USO_ALTO:
            st.caption(":orange[Usar mucho de tu línea puede afectar tu historial crediticio; lo recomendable es "
                       "menos del 30 %.]")
    else:
        columnas[1].metric("Disponible", "—")
        st.caption("Registra tu **línea de crédito** (Cuentas → Editar) para ver cuánto te queda disponible.")
    if estado.saldo_a_favor:
        st.caption(f"Saldo a favor: **{formato.dinero_md(estado.saldo_a_favor)}**")

    _situacion(estado)
    detalles = []
    if estado.actual is not None:
        detalles.append(f"Ciclo actual ({formato.rango(estado.actual.inicio, estado.actual.fin)}): cargos "
                        f"{formato.dinero_md(estado.actual.cargos)}, abonos {formato.dinero_md(estado.actual.abonos)}")
        detalles.append(f"próximo corte: {formato.fecha(estado.actual.fin)}")
    regla = tarjetas.describir_regla_pago(tarjeta)
    if regla:
        detalles.append(f"pago: {regla}")
    if detalles:
        st.caption(" · ".join(detalles))
