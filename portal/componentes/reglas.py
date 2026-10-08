"""Categorías › ⚡ Reglas automáticas: «todo lo que diga OXXO va a SNACKS Y ANTOJOS» (motor/reglas_categorias.py)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import categorias, reglas_categorias
from motor.dinero import a_pesos
from motor.modelo import ClaseCategoria, Regla
from portal.componentes import formato
from portal.componentes.sesion import aplicar, avisar, ejecutar, libro

TODAS = "En todas mis cuentas"
MAXIMO_VISTA = 300                    # renglones de la vista previa de «Corregir mi historial»


def _subcategorias() -> dict[str, str]:
    """id → «SALUD › DENTISTA (gasto)», las de gasto primero."""
    lib = libro()
    activas = [c for c in lib.categorias() if c.activa and c.rubro_id]
    opciones = {}
    for clase, nombre in ((ClaseCategoria.GASTO, "gasto"), (ClaseCategoria.INGRESO, "ingreso")):
        for c in categorias.ordenadas(lib, [c for c in activas if c.clase is clase]):
            opciones[c.id] = f"{categorias.etiqueta(lib, c.id)} ({nombre})"
    return opciones


def _cuentas() -> dict[str | None, str]:
    return {None: TODAS, **{c.id: c.nombre for c in libro().cuentas() if c.activa}}


def _destino(regla: Regla) -> str:
    lib = libro()
    return categorias.etiqueta(lib, regla.categoria_id) + ("" if lib.categoria(regla.categoria_id).activa
                                                            else " (archivada: no aplica)")


def mostrar() -> None:
    st.caption("Una **regla** dice: si la descripción de un movimiento tiene este texto, va a esta subcategoría. "
               "TALLY la usa al **importar tu estado de cuenta** (antes que lo que aprende solo), al **registrar** un "
               "movimiento sin elegir subcategoría y en la **plantilla de Excel** cuando la subcategoría va vacía. "
               "Y puede corregir los movimientos que ya tienes.")
    _nueva()
    _lista()
    _sugerencias()
    cambios = reglas_categorias.pendientes(libro())
    izquierda, derecha = st.columns(2)
    with izquierda, st.container(border=True):
        _probar()
    with derecha, st.container(border=True):
        _historial_resumen(cambios)
    if cambios:
        _historial(cambios)


# ------------------------------------------------------------------ alta


def _nueva() -> None:
    with st.expander("➕ Nueva regla", expanded=not libro().reglas()):
        opciones, cuentas = _subcategorias(), _cuentas()
        with st.form("regla_nueva", clear_on_submit=True, border=False):
            izquierda, centro, derecha = st.columns(3)
            texto = izquierda.text_input(
                "Si la descripción dice…", max_chars=60, placeholder="Ej. OXXO, NETFLIX, UBER",
                help="Como aparece en tu banco. Da igual mayúsculas, acentos y signos. Busca palabras que empiecen "
                     "así: «UBER» encuentra «UBER EATS» y «UBERTRIP», pero no «SUBERO».")
            categoria = centro.selectbox("…va a la subcategoría", list(opciones), index=None,
                                         format_func=opciones.get, placeholder="Escribe para buscar…")
            cuenta = derecha.selectbox("¿En qué cuenta?", list(cuentas), format_func=cuentas.get,
                                       help="Por ejemplo, «AMAZON» en la tarjeta del trabajo puede ir a otra "
                                            "subcategoría que en tus demás cuentas.")
            if st.form_submit_button("Agregar regla", type="primary"):
                if categoria is None:
                    st.error("Elige a qué subcategoría va.")
                else:
                    _crear(texto, categoria, cuenta)


def _crear(texto: str, categoria_id: str, cuenta_id: str | None = None) -> None:
    regla = aplicar(lambda lib: reglas_categorias.crear(lib, texto, categoria_id, cuenta_id=cuenta_id))
    if regla is None:
        return
    mensaje = f"Regla agregada: «{regla.texto}» → {categorias.etiqueta(libro(), regla.categoria_id)}."
    if pendientes := len(reglas_categorias.pendientes(libro(), regla.id)):
        mensaje += (f" Encontró {pendientes} movimiento(s) que ya tienes en otra subcategoría: revísalos en "
                    "«Corregir mi historial».")
    avisar(mensaje, "⚡")
    st.rerun()


# ------------------------------------------------------------------ lista y cambios


def _lista() -> None:
    lib = libro()
    reglas = lib.reglas()
    if not reglas:
        st.info("Todavía no tienes reglas. Agrega una arriba, o crea alguna de las sugerencias de abajo.")
        return
    cuentas, usos = _cuentas(), reglas_categorias.contar(lib)
    st.markdown(f"**Tus reglas** · {len(reglas)}")
    tabla = pd.DataFrame({
        "Si dice": [r.texto for r in reglas],
        "Va a": [_destino(r) for r in reglas],
        "Cuenta": [cuentas.get(r.cuenta_id) or lib.cuenta(r.cuenta_id).nombre if r.cuenta_id else TODAS
                   for r in reglas],
        "Movimientos": [usos.get(r.id, 0) for r in reglas],
        "Estado": ["Activa" if r.activa else "⏸️ Pausada" for r in reglas],
    })
    st.dataframe(tabla, hide_index=True, width="stretch",
                 column_config={"Movimientos": st.column_config.NumberColumn(
                     help="Cuántos de tus movimientos encuentra hoy (gastos o ingresos de una sola subcategoría).")})
    ids = [r.id for r in reglas]
    elegida = st.selectbox("Modificar una regla", ids, index=None, placeholder="Elige una regla",
                           format_func=lambda i: f"«{lib.regla(i).texto}» → {_destino(lib.regla(i))}",
                           key="regla_elegida")
    if elegida is not None:
        with st.container(border=True):
            _modificar(lib.regla(elegida))


def _modificar(regla: Regla) -> None:
    opciones, cuentas = _subcategorias(), _cuentas()
    if regla.categoria_id not in opciones:                      # archivada: que se pueda ver y cambiar
        opciones[regla.categoria_id] = _destino(regla)
    if regla.cuenta_id not in cuentas:
        cuentas[regla.cuenta_id] = libro().cuenta(regla.cuenta_id).nombre
    with st.form(f"regla_{regla.id}", border=False):
        izquierda, centro, derecha = st.columns(3)
        texto = izquierda.text_input("Si la descripción dice…", value=regla.texto, max_chars=60)
        ids = list(opciones)
        categoria = centro.selectbox("…va a la subcategoría", ids, index=ids.index(regla.categoria_id),
                                     format_func=opciones.get)
        lista = list(cuentas)
        cuenta = derecha.selectbox("¿En qué cuenta?", lista, index=lista.index(regla.cuenta_id),
                                   format_func=cuentas.get)
        activa = st.checkbox("Activa", value=regla.activa,
                             help="Pausada: se queda guardada, pero no se usa hasta que la vuelvas a activar.")
        if st.form_submit_button("Guardar cambios", type="primary"):
            if ejecutar(lambda lib: reglas_categorias.editar(lib, regla.id, texto=texto, categoria_id=categoria,
                                                             cuenta_id=cuenta, activa=activa),
                        exito="Regla actualizada"):
                st.rerun()
    st.caption("Borrar la regla no cambia los movimientos que ya tienes.")
    izquierda, derecha = st.columns([1, 3], vertical_alignment="center")
    confirmar = derecha.checkbox("Quiero borrar esta regla", key=f"regla_confirmar_{regla.id}")
    if izquierda.button("Borrar regla", key=f"regla_borrar_{regla.id}", disabled=not confirmar):
        if ejecutar(lambda lib: reglas_categorias.eliminar(lib, regla.id), exito=f"Regla «{regla.texto}» borrada"):
            st.session_state.pop("regla_elegida", None)
            st.rerun()


# ------------------------------------------------------------------ probar


def _probar() -> None:
    st.markdown("**🔎 Probar**")
    texto = st.text_input("Escribe una descripción como viene en tu banco", key="regla_probar",
                          placeholder="Ej. COMPRA OXXO 1234 SUC CENTRO")
    if not texto.strip():
        st.caption("Te digo a qué subcategoría iría si fuera un gasto y si fuera un ingreso.")
        return
    lib = libro()
    for clase, resultado in reglas_categorias.probar(lib, texto).items():
        como = "Si es un gasto" if clase is ClaseCategoria.GASTO else "Si es un ingreso"
        if resultado is None:
            st.markdown(f"{como}: ninguna regla aplica.")
        else:
            st.markdown(f"{como}: va a **{formato.md(categorias.etiqueta(lib, resultado.categoria_id))}** "
                        f"por tu regla «{formato.md(resultado.texto)}»"
                        + (f" (solo en {formato.md(lib.cuenta(resultado.cuenta_id).nombre)})"
                           if resultado.cuenta_id else "") + ".")


# ------------------------------------------------------------------ corregir el historial


def _historial_resumen(cambios: list[reglas_categorias.Cambio]) -> None:
    st.markdown("**🧹 Corregir mi historial**")
    if not cambios:
        st.caption("Todos tus movimientos están donde dicen tus reglas." if libro().reglas()
                   else "Cuando tengas reglas, aquí verás los movimientos que ya tienes y que tus reglas mandarían a "
                        "otra subcategoría.")
        return
    st.markdown(f"**{len(cambios)}** movimiento(s) que ya tienes están en otra subcategoría de la que dicen tus "
                "reglas. Revísalos abajo antes de cambiarlos.")


def _historial(cambios: list[reglas_categorias.Cambio]) -> None:
    lib = libro()
    with st.expander(f"🧹 Revisar y corregir {len(cambios)} movimiento(s)"):
        reglas = {c.regla.id: c.regla for c in cambios}
        filtro = st.selectbox("De la regla", [None, *reglas], key="regla_historial_filtro",
                              format_func=lambda i: "Todas" if i is None else f"«{reglas[i].texto}»")
        if filtro is not None:
            cambios = [c for c in cambios if c.regla.id == filtro]
        nombres = {c.id: c.nombre for c in lib.cuentas()}
        vista = cambios[:MAXIMO_VISTA]
        tabla = pd.DataFrame({
            "Fecha": [formato.fecha(c.operacion.fecha) for c in vista],
            "Descripción": [c.operacion.descripcion for c in vista],
            "Cuenta": [nombres.get(c.operacion.partidas_de_cuenta()[0].cuenta_id, "") for c in vista],
            "Importe": [formato.dinero(a_pesos(c.operacion.partidas_de_cuenta()[0].importe)) for c in vista],
            "Ahora": [categorias.etiqueta(lib, c.categoria_actual) for c in vista],
            "Pasaría a": [categorias.etiqueta(lib, c.categoria_nueva) for c in vista],
            "Regla": [f"«{c.regla.texto}»" for c in vista],
        })
        st.dataframe(formato.pintar(tabla, ["Importe"]), hide_index=True, width="stretch")
        if len(cambios) > MAXIMO_VISTA:
            st.caption(f"Se muestran los {MAXIMO_VISTA} más recientes de {len(cambios)}.")
        st.caption("Solo cambia la subcategoría: fecha, importe, cuenta y descripción se quedan igual. Si un mes ya "
                   "lo cerraste, en su cierre aparecerá como cambio posterior.")
        confirmar = st.checkbox(f"Quiero pasar estos {len(cambios)} movimiento(s) a la subcategoría de su regla",
                                key="regla_historial_confirmar")
        if st.button(f"Corregir {len(cambios)} movimiento(s)", type="primary", disabled=not confirmar,
                     key="regla_historial_aplicar", icon=":material/auto_fix_high:"):
            hechos = aplicar(lambda lib_: reglas_categorias.aplicar(lib_, cambios))
            if hechos is not None:
                avisar(f"Se corrigieron {hechos} movimiento(s).", "🧹")
                st.session_state.pop("regla_historial_confirmar", None)
                st.rerun()


# ------------------------------------------------------------------ sugerencias


def _sugerencias() -> None:
    lib = libro()
    sugerencias = reglas_categorias.sugerencias(lib)
    if not sugerencias:
        return
    with st.expander(f"💡 Sugerencias de reglas · {len(sugerencias)}", expanded=not lib.reglas()):
        st.caption("Textos que se repiten en tus movimientos y casi siempre van a la misma subcategoría. Créalas con "
                   "un clic; luego puedes editarlas.")
        for n, s in enumerate(sugerencias):
            texto, boton = st.columns([4, 1], vertical_alignment="center")
            texto.markdown(f"«**{formato.md(s.texto)}**» → {formato.md(categorias.etiqueta(lib, s.categoria_id))} "
                           f"· {s.iguales} de {s.veces} movimiento(s)")
            if boton.button("Crear", key=f"regla_sugerida_{n}", icon=":material/bolt:"):
                _crear(s.texto, s.categoria_id)
