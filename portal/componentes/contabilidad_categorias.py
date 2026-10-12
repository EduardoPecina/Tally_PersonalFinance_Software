"""Categorías › Contabilidad: qué forma cada reporte de la Contabilidad técnica y en qué rubro contable va cada
subcategoría (motor/rubros_contables.py). Las cajas funcionan como las de Clasificaciones."""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from motor import categorias, reportes
from motor import contabilidad as cb
from motor import rubros_contables as rc
from motor.errores import ErrorTally
from motor.modelo import ClaseCategoria, RubroContable
from portal.componentes import formato
from portal.componentes.sesion import avisar, ejecutar, libro, sesion
from portal.navegacion import enlace

TIPOS = {ClaseCategoria.INGRESO: "De ingreso", ClaseCategoria.GASTO: "De gasto"}
AYUDA_RUBRO = ("Un rubro contable es un renglón de tus estados financieros que junta varias subcategorías. Por "
               "ejemplo, «Gastos financieros» junta INTERESES DE TARJETAS, COMISIONES BANCARIAS y ANUALIDADES: así ves "
               "de un vistazo cuánto le pagas al banco.")
AYUDA_CAJA = ("Escribe para buscar una subcategoría. Si la agregas aquí, sale de donde estaba: cada subcategoría "
              "está en un solo rubro. Con la ✕ regresa a donde TALLY la acomoda solo.")
AYUDA_AUTOMATICO = ("TALLY acomoda cada subcategoría por su nombre (INTERESES… → Gastos financieros, PREDIAL → "
                    "Impuestos, NOMINA → Ingresos por tu trabajo) o por el de su categoría (todo lo de FINANZAS → "
                    "Gastos financieros). Si nada lo dice, va a Gastos de vida u Otros ingresos. Las que mueves tú "
                    "se quedan donde las pusiste.")


def mostrar() -> None:
    st.caption("Aquí ves **qué usa TALLY para armar tu Contabilidad técnica** y decides en qué renglón cae cada "
               "subcategoría. Mover una no cambia ningún total ni hace que algo deje de cuadrar: solo cambia cómo se "
               "agrupa en el Estado de Resultados, el Flujo de efectivo y la Balanza.", help=AYUDA_RUBRO)
    _mapa()
    asignadas = rc.asignaciones(libro())
    _reparto(asignadas)
    version = st.session_state.setdefault("_rc_version", 0)
    for clase, titulo, ayuda in (
            (ClaseCategoria.INGRESO, "Ingresos", "Lo que entra: cada subcategoría de ingreso va en uno de estos "
                                                 "rubros. Se suman en «Total ingresos» del Estado de Resultados."),
            (ClaseCategoria.GASTO, "Gastos", "Lo que sale: cada subcategoría de gasto va en uno de estos rubros. "
                                             "Se suman en «Total gastos» del Estado de Resultados.")):
        st.subheader(titulo, help=ayuda)
        for rubro in rc.todos(libro(), clase):
            _caja(rubro, version, asignadas)
    st.divider()
    izquierda, derecha = st.columns(2)
    with izquierda:
        _nuevo()
    with derecha:
        _restablecer()
        _recuperar()


# ------------------------------------------------------------------ qué forma cada reporte


def _mapa() -> None:
    lib = libro()
    with st.expander("🗺️ ¿De dónde sale cada reporte? (y dónde se cambia)"):
        st.markdown(
            "| Reporte | Lo forman | Dónde se cambia |\n|---|---|---|\n"
            "| **Situación financiera** (lo que tienes, debes y vales) | Tus **cuentas**, según su tipo. Lo que es "
            "tuyo (patrimonio) es el saldo con el que empezaste más lo que has ganado menos lo que has gastado | "
            "Cuentas → Administrar cuenta → Editar (el tipo de cuenta) |\n"
            "| **Resultados** (cuánto ganaste y gastaste) | Tus **subcategorías**, juntas en los rubros de abajo | "
            "Aquí |\n"
            "| **Flujo de efectivo** (por dónde entró y salió tu dinero) | *Tu día a día*: los rubros de abajo. "
            "Lo demás (pagos de tarjeta, préstamos, inversiones, bienes): tus cuentas | Aquí y en Cuentas |\n"
            "| **Balanza de comprobación** | Todo lo anterior, renglón por renglón; la columna «Rubro» dice dónde cae "
            "cada uno | — |")
        st.markdown("**Tus cuentas en la Situación financiera**",
                    help="El grupo lo da el tipo de cada cuenta: débito, ahorro y efectivo son Efectivo y bancos; "
                         "una tarjeta es deuda a corto plazo; un préstamo, a corto o largo plazo según cuánto te falta "
                         "pagar. Una compra grande (auto, casa) va como bien: Historial → «Convertir en un bien».")
        grupos: dict[tuple[str, str], list[str]] = {}
        for cuenta in lib.cuentas():
            if cuenta.activa:
                naturaleza, grupo = cb.clasificar_cuenta(cuenta, lib, lib.hoy())
                grupos.setdefault((naturaleza, grupo), []).append(cuenta.nombre)
        if grupos:
            st.markdown("  \n".join(f"{naturaleza} · **{grupo}**: {' · '.join(nombres)}"
                                    for (naturaleza, grupo), nombres in grupos.items()))
        else:
            st.caption("Aún no tienes cuentas.")
        enlace("cuentas", "Ir a Cuentas", "🏦")


def _reparto(asignadas: dict[str, RubroContable]) -> None:
    """Cuánto lleva cada rubro este año (lo que importa es el dinero, no cuántas subcategorías tenga)."""
    lib = libro()
    desde, hasta = reportes.rango_periodo(lib, "anio")
    r = cb.resultados(lib, [(desde, hasta)])
    montos = Counter()
    for renglon in [*r.ingresos, *r.gastos]:
        montos[renglon.seccion] += renglon.importes[0]
    rubros = rc.todos(lib)
    cuantas = Counter(r.id for r in asignadas.values())
    with st.expander(f"¿Cuánto llevas en {desde.year} en cada rubro?"):
        st.dataframe(formato.pintar(pd.DataFrame({
            "Rubro contable": [x.nombre for x in rubros],
            "Tipo": ["Ingreso" if x.clase is ClaseCategoria.INGRESO else "Gasto" for x in rubros],
            "Subcategorías": [cuantas[x.id] for x in rubros],
            "En el año": [formato.dinero(montos.get(x.nombre, 0)) for x in rubros],
        })), hide_index=True, width="stretch")
        st.caption("Sale del Estado de Resultados (sin los cambios de valor de tus inversiones y bienes).")


# ------------------------------------------------------------------ las cajas


def _caja(rubro: RubroContable, version: int, asignadas: dict[str, RubroContable]) -> None:
    lib = libro()
    de_la_clase = [c for c in categorias.ordenadas(lib, lib.categorias()) if c.clase is rubro.clase]
    dentro = [c.id for c in de_la_clase if asignadas[c.id].id == rubro.id]
    elegidas = sum(bool(lib.categoria(i).rubro_contable_id) for i in dentro)
    with st.container(border=True):
        cabeza, acciones = st.columns([5, 1], vertical_alignment="center")
        cabeza.markdown(f"**{rubro.nombre}** · {len(dentro)} subcategoría(s)",
                        help=rubro.descripcion or "Un rubro que creaste tú.")
        if rubro.descripcion:
            cabeza.caption(rubro.descripcion)
        # Con la clave de su rubro: al borrar uno, el «Editar» del siguiente no se queda abierto en su lugar.
        with acciones.popover("Editar", width="stretch", key=f"rc_editar_{rubro.id}_{version}"):
            _editar(rubro)
        por_categoria: dict[str, list[str]] = {}
        for i in dentro:
            nombre = lib.categoria(i).nombre + (" ✋" if lib.categoria(i).rubro_contable_id else "")
            por_categoria.setdefault(categorias.nombre_rubro(lib, i), []).append(nombre)
        if por_categoria:
            st.markdown("  \n".join(f"**{rubro_}**: {' · '.join(subs)}" for rubro_, subs in por_categoria.items()))
        else:
            st.caption("Vacío: agrega aquí las subcategorías que quieras ver en este renglón.")

        def etiqueta(i: str) -> str:                   # los nombres de subcategoría no se repiten en TALLY
            otro = asignadas[i]
            texto = lib.categoria(i).nombre
            return texto if otro.id == rubro.id else f"{texto} (ahora en {otro.nombre})"

        clave_widget = f"rc_{rubro.id}_{version}"
        st.multiselect(f"Subcategorías de {rubro.nombre}", [c.id for c in de_la_clase], default=dentro,
                       format_func=etiqueta, key=clave_widget, on_change=_al_cambiar, args=(rubro.id, clave_widget),
                       label_visibility="collapsed", placeholder="Agrega una subcategoría (escribe para buscar)",
                       help=AYUDA_CAJA)
        if dentro:
            st.caption(f"{len(dentro) - elegidas} acomodada(s) por TALLY · {elegidas} movida(s) por ti (✋)",
                       help=AYUDA_AUTOMATICO)
        for texto in st.session_state.pop(f"_rc_aviso_{rubro.id}", []):
            st.info(texto, icon="ℹ️")
        error = st.session_state.pop(f"_rc_error_{rubro.id}", None)
        if error:
            st.error(error)


def _al_cambiar(rubro_id: str, clave_widget: str) -> None:
    """Lo agregado entra a este rubro (y sale del otro); lo quitado regresa a donde lo acomoda TALLY."""
    lib = libro()
    asignadas = rc.asignaciones(lib)
    actuales = {i for i, r in asignadas.items() if r.id == rubro_id}
    elegidas = set(st.session_state.get(clave_widget, []))
    avisos = []
    try:
        with sesion().cambio() as lib_:
            for categoria_id in elegidas - actuales:
                rc.asignar(lib_, categoria_id, rubro_id)
            for categoria_id in actuales - elegidas:
                rc.asignar(lib_, categoria_id, None)
                if rc.de(lib_, categoria_id).id == rubro_id:
                    avisos.append(f"«{lib_.categoria(categoria_id).nombre}» se queda aquí: es donde TALLY la "
                                  "acomoda. Para cambiarla, agrégala en otro rubro.")
    except ErrorTally as error:
        st.session_state[f"_rc_error_{rubro_id}"] = str(error)
    if avisos:
        st.session_state[f"_rc_aviso_{rubro_id}"] = avisos
    _cajas_al_dia()


def _cajas_al_dia() -> None:
    """Las cajas se vuelven a armar con lo guardado (si no, un multiselect conserva lo que tenía)."""
    st.session_state["_rc_version"] = st.session_state.get("_rc_version", 0) + 1


# ------------------------------------------------------------------ los tuyos


def _editar(rubro: RubroContable) -> None:
    original = rc.nombre_de_tally(rubro)
    if original and original != rubro.nombre:
        st.caption(f"Rubro de TALLY; su nombre original es «{original}».")
    elif original:
        st.caption("Rubro de TALLY.")
    nuevo = st.text_input("Nombre", value=rubro.nombre, key=f"rc_nombre_{rubro.id}", max_chars=50)
    if st.button("Renombrar", key=f"rc_renombrar_{rubro.id}", disabled=nuevo.strip() == rubro.nombre):
        if ejecutar(lambda lib: rc.renombrar(lib, rubro.id, nuevo), exito="Rubro contable renombrado"):
            _cajas_al_dia()
            st.rerun()
    if not rc.se_puede_borrar(rubro):
        st.caption("Este no se puede borrar: aquí va todo lo que no está en otro rubro (como «Sin clasificación» "
                   "en Clasificaciones).")
        return
    st.caption("Al borrarlo, sus subcategorías regresan a donde TALLY las acomoda. No se pierde nada."
               + (" Si te arrepientes, lo recuperas abajo." if original else ""))
    if st.button("Borrar rubro", key=f"rc_borrar_{rubro.id}"):
        if ejecutar(lambda lib: rc.eliminar(lib, rubro.id), exito="Rubro contable borrado"):
            _cajas_al_dia()
            st.rerun()


def _nuevo() -> None:
    with st.form("rc_nuevo", clear_on_submit=True, border=True):
        st.markdown("**➕ Nuevo rubro contable**",
                    help="Para ver aparte algo que te importa: «Negocio», «Hijos», «Vivienda»… Después agrégale sus "
                         "subcategorías en su caja.")
        nombre = st.text_input("Nombre", max_chars=50, placeholder="Ej. Gastos del negocio, Vivienda…")
        clase = st.radio("¿Es de ingreso o de gasto?", list(TIPOS), format_func=TIPOS.get, horizontal=True,
                         index=1, help="Solo puede juntar subcategorías de ese tipo: un rubro de gasto suma en "
                                       "«Total gastos» y uno de ingreso en «Total ingresos».")
        if st.form_submit_button("Agregar rubro", type="primary"):
            if ejecutar(lambda lib: rc.crear(lib, nombre, clase),
                        exito=f"Rubro «{nombre.strip()}» agregado: ya puedes agregarle subcategorías"):
                st.rerun()


def _recuperar() -> None:
    """Los rubros de TALLY que borraste, para traerlos de vuelta."""
    borrados = rc.borrados(libro())
    if not borrados:
        return
    with st.container(border=True):
        st.markdown("**↩️ Rubros de TALLY que borraste**",
                    help="Vuelven con su nombre original y TALLY vuelve a acomodar ahí lo que les toca. Lo que "
                         "moviste tú (✋) se queda donde lo pusiste.")
        for rubro in borrados:
            nombre = rc.nombre_de_tally(rubro)
            if st.button(f"Recuperar «{nombre}»", key=f"rc_recuperar_{rubro.id}", icon=":material/undo:"):
                if ejecutar(lambda lib, i=rubro.id: rc.recuperar(lib, i), exito=f"«{nombre}» recuperado"):
                    _cajas_al_dia()
                    st.rerun()


def _restablecer() -> None:
    lib = libro()
    movidas = sum(bool(c.rubro_contable_id) for c in lib.categorias())
    with st.container(border=True):
        st.markdown("**↺ Que TALLY vuelva a acomodar todo**", help=AYUDA_AUTOMATICO)
        st.caption(f"{movidas} subcategoría(s) movida(s) por ti. Regresan a donde TALLY las acomoda; tus rubros "
                   "propios se quedan, pero vacíos.")
        confirmar = st.checkbox("Sí, quiero que TALLY las acomode", key="rc_confirmar_restablecer",
                                disabled=not movidas)
        if st.button("Acomodar todo de nuevo", key="rc_restablecer", disabled=not (movidas and confirmar)):
            if ejecutar(rc.restablecer):
                avisar("Listo: TALLY volvió a acomodar todas tus subcategorías.", "↺")
                _cajas_al_dia()
                st.rerun()
