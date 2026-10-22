"""Cuentas en otra moneda en el portal (motor/divisas.py): elegir la moneda de una cuenta, mostrar lo que vale en la
tuya, la sección Configuración → Tipos de cambio y la consulta diaria por internet (opcional), en segundo plano."""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from motor import cotizaciones, divisas, monedas, perfil
from motor.modelo import Cuenta
from portal.componentes import formato
from portal.componentes.sesion import ejecutar, libro

COMUNES = ("USD", "EUR", "CAD")          # las primeras de la lista, después de la tuya
TRANSPARENCIA = (f"⚡ Los tipos de cambio vienen de **{cotizaciones.PROVEEDOR}**. La consulta solo envía el **par de "
                 "monedas** (por ejemplo USDMXN): no se envían saldos, movimientos ni datos personales. Son de "
                 "referencia; si tu banco te dio otro, escríbelo aquí y ese manda.")


def opciones(lib) -> list[str]:
    """Las monedas para una cuenta: la tuya primero (``""``), luego dólar, euro, dólar canadiense y las demás."""
    base = monedas.de(lib)
    resto = [c for c in monedas.MONEDAS if c != base and c not in COMUNES]
    return ["", *[c for c in COMUNES if c != base], *resto]


def etiqueta(lib, codigo: str) -> str:
    if not codigo:
        m = monedas.MONEDAS[monedas.de(lib)]
        return f"Tu moneda ({m.codigo} · {m.nombre})"
    m = monedas.MONEDAS[codigo]
    return f"{m.codigo} · {m.nombre} ({m.paises})"


def elegir(lib, clave: str, actual: str = "", *, contenedor=st, disabled: bool = False, ayuda: str | None = None
           ) -> str:
    """Selector de la moneda de una cuenta. Devuelve "" si es la tuya."""
    lista = opciones(lib)
    return contenedor.selectbox(
        "Moneda de la cuenta", lista, index=lista.index(actual) if actual in lista else 0, key=clave,
        format_func=lambda c: etiqueta(lib, c), disabled=disabled,
        help=ayuda or "Para una cuenta en dólares, euros… Su saldo y sus movimientos van en esa moneda; en tus "
                      "totales y reportes cuenta lo que vale en la tuya.")


def sugerido(lib, moneda: str, dia: date) -> float | None:
    """El tipo de cambio para prellenar: el guardado en TALLY o, si no hay, el último que se consultó en esta PC."""
    guardado = divisas.tipo(lib, moneda, dia)
    if guardado is not None:
        return float(guardado)
    consultado = cotizaciones.ultimos()[1].get(moneda)
    return float(consultado.valor) if consultado and consultado.moneda == monedas.de(lib) else None


def campo_tipo(lib, moneda: str, dia: date, contenedor=st, clave: str | None = None) -> float | None:
    base = monedas.de(lib)
    return contenedor.number_input(
        f"Tipo de cambio: cuántos {base} vale 1 {moneda}", min_value=0.0, value=sugerido(lib, moneda, dia),
        step=0.01, format="%.4f", key=clave,
        help="El de ese día. TALLY lo usa para saber cuánto vale la cuenta en tu moneda; puedes cambiarlo después "
             "en Configuración → Tipos de cambio.")


def guardar_si_cambio(lib, moneda: str, dia: date, valor) -> None:
    """Guarda el tipo de cambio que escribiste para ese día (si no es el que ya tenía TALLY)."""
    if valor and divisas.tipo(lib, moneda, dia) != divisas.leer_tipo(valor):
        divisas.guardar_tipo(lib, moneda, dia, valor)


def equivalente_md(lib, cuenta: Cuenta) -> str:
    """«≈ $20,640.00 · 1 USD = 17.20 MXN (del 22/10/2026)» para una cuenta en otra moneda."""
    cuadro = divisas.cuadro(lib, cuenta.id)
    fechas, _ = lib.serie_cambio(cuenta.moneda)
    if cuadro.tipo is None:
        return f"≈ {formato.dinero_md(Decimal(cuadro.valor) / 100)} · sin tipo de cambio: escríbelo en Configuración"
    cuando = fechas[-1] if fechas and fechas[-1] <= lib.hoy() else None
    texto = f"≈ {formato.dinero_md(Decimal(cuadro.valor) / 100)} · {formato.tipo_de_cambio(cuadro.tipo, cuenta.moneda)}"
    return texto + (f" (del {formato.fecha(cuando)})" if cuando else "")


# ------------------------------------------------------ Configuración → Tipos de cambio


def configuracion() -> None:
    lib = libro()
    base = monedas.de(lib)
    st.subheader("Tipos de cambio")
    usadas = divisas.monedas_en_uso(lib)
    if not usadas:
        st.caption("Si tienes una cuenta en dólares, euros u otra moneda, elígela al crear la cuenta (Cuentas → Nueva "
                   "cuenta) o en Administrar cuenta. Aquí ves y corriges el tipo de cambio de cada una.")
    else:
        st.caption(f"Cuántos {base} vale cada moneda de tus cuentas. Con él, TALLY suma esas cuentas en tu moneda; lo "
                   "que cambia su valor sale en tu patrimonio como «por tipo de cambio».")
        columnas = st.columns(min(len(usadas), 4))
        for i, moneda in enumerate(usadas):
            fechas, tipos = lib.serie_cambio(moneda)
            columna = columnas[i % len(columnas)]
            if not fechas:
                columna.metric(moneda, "Sin tipo de cambio", help="Escríbelo abajo.")
                continue
            ultimo = lib.tipo_cambio(f"{moneda}:{fechas[-1].isoformat()}")
            columna.metric(moneda, formato.tipo_de_cambio(tipos[-1], moneda))
            columna.caption(f"Del {formato.fecha(fechas[-1])} · " + ("escrito por ti" if ultimo and ultimo.manual
                                                                     else "de internet"))
    actual = bool(lib.perfil.tipos_por_internet)
    nuevo = st.toggle("Traerlos de internet cada día", value=actual, key="configuracion_tipos_internet",
                      help="Al abrir TALLY, si hace falta, en segundo plano: no te hace esperar. Los que escribas tú "
                           "no se reemplazan.")
    if nuevo != actual and ejecutar(lambda lib: perfil.ajustar(lib, tipos_por_internet=nuevo),
                                    exito="Listo: TALLY los traerá cada día" if nuevo else "Ya no se consultan solos"):
        st.rerun()
    if usadas and st.button("Traer ahora de internet", icon=":material/travel_explore:", key="configuracion_traer"):
        with st.spinner("Consultando tipos de cambio…"):
            consulta = divisas.consultar(divisas.pendientes(lib) or {m: lib.hoy() for m in usadas}, base, lib.hoy())
        if consulta.sin_conexion:
            st.warning(consulta.aviso)
        else:
            if consulta.series:
                ejecutar(lambda lib: divisas.de_internet(lib, consulta.series), exito="Tipos de cambio actualizados")
            if consulta.aviso:
                st.warning(consulta.aviso)
    st.caption(TRANSPARENCIA)

    with st.form("configuracion_tipo_manual", border=False):
        st.markdown("**Escribir un tipo de cambio**")
        izquierda, centro, derecha = st.columns(3)
        lista = [*usadas, *[c for c in opciones(lib)[1:] if c not in usadas]]
        moneda = izquierda.selectbox("Moneda", lista, format_func=lambda c: etiqueta(lib, c))
        dia = centro.date_input("Fecha", value=lib.hoy(), max_value=lib.hoy(), format="DD/MM/YYYY")
        valor = derecha.number_input(f"Cuántos {base} vale 1", min_value=0.0, value=None, step=0.01, format="%.4f")
        if st.form_submit_button("Guardar", type="primary"):
            if not valor:
                st.error("Escribe el tipo de cambio.")
            elif ejecutar(lambda lib: divisas.guardar_tipo(lib, moneda, dia, valor),
                          exito=f"Tipo de cambio de {moneda} del {formato.fecha(dia)} guardado"):
                st.rerun()
    for moneda in usadas:
        guardados = list(reversed(lib.tipos_cambio(moneda)))
        if guardados:
            with st.expander(f"Historial de {moneda} ({len(guardados):,} días)"):
                st.dataframe(pd.DataFrame({
                    "Fecha": [t.fecha for t in guardados[:400]],
                    f"{base} por 1 {moneda}": [float(t.tipo) for t in guardados[:400]],
                    "Origen": ["Escrito por ti" if t.manual else "Internet" for t in guardados[:400]],
                }), hide_index=True, width="stretch",
                    column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")})


# ------------------------------------------------------- cada día, en segundo plano

_HECHO = "_tipos_de_cambio_del_dia"


class _Consulta:
    """La consulta del día, en su hilo. Al terminar deja ``resultado`` (o nada, si falló)."""

    def __init__(self, pedidos: dict[str, date], base: str, hoy: date) -> None:
        self.resultado: divisas.Consulta | None = None
        self._hilo = threading.Thread(target=self._correr, args=(pedidos, base, hoy), daemon=True,
                                      name="tally-tipos-de-cambio")
        self._hilo.start()

    def _correr(self, pedidos, base, hoy) -> None:
        try:
            self.resultado = divisas.consultar(pedidos, base, hoy)
        except Exception:  # noqa: BLE001 - sin tipos de cambio nuevos TALLY sigue con los guardados
            self.resultado = divisas.Consulta({})

    @property
    def terminado(self) -> bool:
        return not self._hilo.is_alive()


def al_dia() -> None:
    """Una vez por sesión del navegador (y por día), si lo activaste: trae los tipos de cambio que falten en otro
    hilo; cuando llegan se guardan (al siguiente clic). Sin internet no pasa nada: se usan los guardados."""
    lib = libro()
    en_curso = st.session_state.get(_HECHO)
    if isinstance(en_curso, _Consulta):
        if en_curso.terminado:
            st.session_state[_HECHO] = lib.hoy()
            if en_curso.resultado and en_curso.resultado.series:
                ejecutar(lambda lib: divisas.de_internet(lib, en_curso.resultado.series))
        return
    if en_curso == lib.hoy() or not (lib.perfil and lib.perfil.tipos_por_internet):
        return
    pedidos = divisas.pendientes(lib)
    st.session_state[_HECHO] = _Consulta(pedidos, monedas.de(lib), lib.hoy()) if pedidos else lib.hoy()
