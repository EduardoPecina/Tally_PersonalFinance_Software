"""Categorías (las cajas), subcategorías (lo que lleva cada movimiento), clasificaciones y en qué rubro de tu
Contabilidad técnica va cada una."""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from motor import catalogo, categorias, reportes
from motor import rubros_contables as rc
from motor.errores import ErrorTally
from motor.modelo import Categoria, ClaseCategoria, Rubro
from motor.textos import clave
from portal.componentes import contabilidad_categorias, formato, reglas
from portal.componentes.sesion import aplicar, avisar, ejecutar, libro, sesion

SIN_CLASIFICACION = "— Sin clasificación —"
REGLA_NOMBRES = ("Los nombres se guardan en MAYÚSCULAS y sin acentos («Gastos médicos» → «GASTOS MEDICOS»). "
                 "No se puede agregar dos veces lo mismo, aunque cambien mayúsculas, acentos o espacios.")
AYUDA_CONTABLE = ("En qué renglón de tu Contabilidad técnica cae (Estado de Resultados, Flujo y Balanza). TALLY lo "
                  "elige solo por el nombre y la categoría; lo cambias aquí o en la pestaña Contabilidad. Solo cambia "
                  "cómo se agrupa: ningún total cambia.")


def _clasificaciones() -> dict[str | None, str]:
    return {None: SIN_CLASIFICACION, **{g.id: g.nombre for g in libro().grupos()}}


def _usos() -> Counter:
    return Counter(p.categoria_id for op in libro().operaciones() for p in op.partidas_de_categoria())


def _rubros(clase: ClaseCategoria) -> list[Rubro]:
    return [r for r in libro().rubros() if r.clase is clase]


def _tabla(subcategorias: list[Categoria], usos: Counter, clase: ClaseCategoria, con_categoria: bool,
           contables: dict) -> None:
    lib = libro()
    nombres = _clasificaciones()
    datos = {
        "Categoría": [categorias.nombre_rubro(lib, c.id) for c in subcategorias],
        "Subcategoría": [c.nombre for c in subcategorias],
        "Clasificación": [nombres.get(c.grupo_id, SIN_CLASIFICACION) for c in subcategorias],
        "Rubro contable": [contables[c.id].nombre for c in subcategorias],
        "Movimientos": [usos[c.id] for c in subcategorias],
        "Estado": ["Activa" if c.activa else "Archivada" for c in subcategorias],
        "Ingreso principal": ["Sí" if c.principal else "" for c in subcategorias],
    }
    columnas = (["Categoría"] if con_categoria else []) + ["Subcategoría", "Clasificación", "Rubro contable",
                                                           "Movimientos", "Estado"]
    if clase is ClaseCategoria.INGRESO:
        columnas.append("Ingreso principal")
    st.dataframe(formato.pintar(pd.DataFrame(datos)), hide_index=True, width="stretch", column_order=columnas,
                 column_config={"Rubro contable": st.column_config.TextColumn(help=AYUDA_CONTABLE)})


def _arbol(clase: ClaseCategoria) -> None:
    lib = libro()
    usos = _usos()
    contables = rc.asignaciones(lib)
    rubros = _rubros(clase)
    propias = [c for c in lib.categorias() if c.clase is clase]
    st.caption(f"{len(rubros)} categorías · {len(propias)} subcategorías. {REGLA_NOMBRES}")

    buscado = st.text_input("Buscar", key=f"buscar_{clase.value}", placeholder="Ej. gym, dentista, uber…")
    if buscado.strip():
        encontradas = [c for c in categorias.ordenadas(lib, propias)
                       if clave(buscado) in clave(c.nombre) or clave(buscado) in clave(categorias.nombre_rubro(lib, c.id))]
        if encontradas:
            _tabla(encontradas, usos, clase, con_categoria=True, contables=contables)
        else:
            st.info("No hay ninguna con ese nombre. Puedes agregarla abajo.")
    else:
        for rubro in rubros:
            contenido = categorias.ordenadas(lib, categorias.subcategorias(lib, rubro.id))
            with st.expander(f"**{rubro.nombre}** · {len(contenido)}"):
                if contenido:
                    _tabla(contenido, usos, clase, con_categoria=False, contables=contables)
                else:
                    st.caption("Sin subcategorías todavía.")

    izquierda, derecha = st.columns(2)
    with izquierda, st.expander("➕ Nueva subcategoría"):
        _nueva_subcategoria(clase, rubros)
    with derecha, st.expander("➕ Nueva categoría (una caja que agrupa)"):
        _nueva_categoria(clase)

    st.markdown("**Modificar**")
    izquierda, derecha = st.columns(2)
    with izquierda:
        ids = [c.id for c in categorias.ordenadas(lib, propias)]
        elegida = st.selectbox("Una subcategoría", ids, index=None, placeholder="Elige una subcategoría",
                               format_func=lambda i: categorias.etiqueta(lib, i), key=f"elegida_{clase.value}")
    with derecha:
        elegido = st.selectbox("Una categoría", [r.id for r in rubros], index=None, placeholder="Elige una categoría",
                               format_func=lambda i: lib.rubro(i).nombre, key=f"rubro_elegido_{clase.value}")
    if elegida is not None:
        with st.container(border=True):
            _modificar(lib.categoria(elegida), rubros)
    if elegido is not None:
        with st.container(border=True):
            _modificar_rubro(lib.rubro(elegido), rubros)


def _nueva_subcategoria(clase: ClaseCategoria, rubros: list[Rubro]) -> None:
    clasificaciones = _clasificaciones()
    with st.form(f"nueva_{clase.value}", clear_on_submit=True, border=False):
        rubro = st.selectbox("Dentro de la categoría", [r.id for r in rubros], index=None,
                             placeholder="Elige la categoría", format_func=lambda i: libro().rubro(i).nombre)
        nombre = st.text_input("Nombre de la subcategoría", max_chars=60)
        grupo = st.selectbox("Clasificación", list(clasificaciones), format_func=clasificaciones.get)
        principal = False
        if clase is ClaseCategoria.INGRESO:
            principal = st.checkbox("Es mi ingreso principal (p. ej. la nómina)",
                                    help="Marca el inicio de cada quincena en los reportes.")
        if st.form_submit_button("Agregar subcategoría", type="primary"):
            if rubro is None:
                st.error("Elige en qué categoría va.")
            else:
                nueva = aplicar(lambda lib: categorias.crear(lib, nombre, rubro, grupo_id=grupo, principal=principal))
                if nueva is not None:
                    avisar(f"Subcategoría «{nueva.nombre}» agregada. En tu contabilidad va en "
                           f"«{rc.de(libro(), nueva.id).nombre}» (lo cambias en la pestaña Contabilidad).")
                    st.rerun()


def _nueva_categoria(clase: ClaseCategoria) -> None:
    with st.form(f"nuevo_rubro_{clase.value}", clear_on_submit=True, border=False):
        nombre = st.text_input("Nombre de la categoría", max_chars=40,
                               help="Por ejemplo: GASTOS MEDICOS, TECNOLOGIA, MASCOTAS… Es de "
                                    f"{'ingreso' if clase is ClaseCategoria.INGRESO else 'gasto'} (estás en esa "
                                    "pestaña). En tu Contabilidad técnica, TALLY acomoda sus subcategorías solo por "
                                    "su nombre; las puedes mover en la pestaña Contabilidad.")
        if st.form_submit_button("Agregar categoría", type="primary"):
            nueva = aplicar(lambda lib: categorias.crear_rubro(lib, nombre, clase))
            if nueva is not None:
                destino = libro().rubro_contable(rc.sugerencia(libro(), "", clase, nueva.id)[0]).nombre
                avisar(f"Categoría «{nueva.nombre}» agregada. En tu contabilidad, lo que agregues en ella irá a "
                       f"«{destino}» (salvo que su nombre diga otra cosa; lo cambias en la pestaña Contabilidad).")
                st.rerun()


def _vista_previa(nombre: str) -> str:
    try:
        return categorias.estandarizar(nombre)
    except Exception:  # noqa: BLE001 - solo es para el mensaje
        return nombre


def _modificar(categoria: Categoria, rubros: list[Rubro]) -> None:
    lib = libro()
    clasificaciones = _clasificaciones()
    st.markdown(f"**{categorias.etiqueta(lib, categoria.id)}**")
    with st.form(f"editar_{categoria.id}", border=False):
        izquierda, centro, derecha, contable = st.columns(4)
        nombre = izquierda.text_input("Nombre", value=categoria.nombre, max_chars=60)
        ids = [r.id for r in rubros]
        rubro = centro.selectbox("Categoría", ids, format_func=lambda i: lib.rubro(i).nombre,
                                 index=ids.index(categoria.rubro_id) if categoria.rubro_id in ids else 0)
        opciones = list(clasificaciones)
        grupo = derecha.selectbox("Clasificación", opciones, format_func=clasificaciones.get,
                                  index=opciones.index(categoria.grupo_id) if categoria.grupo_id in opciones else 0)
        actual = rc.de(lib, categoria.id).id
        contables = [r.id for r in rc.todos(lib, categoria.clase)]
        elegido = contable.selectbox("Rubro contable", contables, index=contables.index(actual),
                                     format_func=lambda i: lib.rubro_contable(i).nombre, help=AYUDA_CONTABLE)
        principal = None
        if categoria.clase is ClaseCategoria.INGRESO:
            principal = st.checkbox("Es mi ingreso principal", value=categoria.principal)
        if st.form_submit_button("Guardar cambios", type="primary"):
            def guardar(lib_):
                categorias.editar(lib_, categoria.id, nombre=nombre, rubro_id=rubro, grupo_id=grupo,
                                  principal=principal)
                if elegido != actual:                      # si no lo tocó, que TALLY lo siga acomodando
                    rc.asignar(lib_, categoria.id, elegido)

            if ejecutar(guardar, exito="Subcategoría actualizada"):
                st.rerun()

    izquierda, derecha = st.columns(2)
    with izquierda:
        if categoria.activa:
            st.caption("Archivar la oculta al registrar movimientos nuevos; su historial se conserva.")
            if st.button("Archivar", key=f"archivar_{categoria.id}"):
                if ejecutar(lambda lib: categorias.archivar(lib, categoria.id), exito="Subcategoría archivada"):
                    st.rerun()
        elif st.button("Reactivar", key=f"reactivar_{categoria.id}"):
            if ejecutar(lambda lib: categorias.reactivar(lib, categoria.id), exito="Subcategoría reactivada"):
                st.rerun()
    with derecha:
        en_uso = categorias.en_uso(lib, categoria.id)
        destino = None
        if en_uso:
            otras = [c.id for c in categorias.ordenadas(lib, lib.categorias())
                     if c.clase is categoria.clase and c.id != categoria.id]
            destino = st.selectbox("Pasar sus movimientos a", otras, index=None, placeholder="Elige otra subcategoría",
                                   format_func=lambda i: categorias.etiqueta(lib, i), key=f"destino_{categoria.id}",
                                   help="Borrar una subcategoría con movimientos es juntarla con otra.")
        confirmar = st.checkbox("Quiero borrar esta subcategoría", key=f"confirmar_{categoria.id}")
        if st.button("Borrar subcategoría", key=f"borrar_{categoria.id}",
                     disabled=not confirmar or (en_uso and destino is None)):
            if ejecutar(lambda lib: categorias.eliminar(lib, categoria.id, reasignar_a=destino),
                        exito="Subcategoría borrada"):
                st.session_state.pop(f"elegida_{categoria.clase.value}", None)
                st.rerun()


def _modificar_rubro(rubro: Rubro, rubros: list[Rubro]) -> None:
    lib = libro()
    contenido = categorias.subcategorias(lib, rubro.id)
    st.markdown(f"**{rubro.nombre}** · {len(contenido)} subcategoría(s)")
    with st.form(f"renombrar_rubro_{rubro.id}", border=False):
        nombre = st.text_input("Nombre", value=rubro.nombre, max_chars=40)
        if st.form_submit_button("Renombrar", type="primary"):
            if ejecutar(lambda lib: categorias.renombrar_rubro(lib, rubro.id, nombre), exito="Categoría renombrada"):
                st.rerun()
    destino = None
    if contenido:
        otras = [r.id for r in rubros if r.id != rubro.id]
        destino = st.selectbox("Pasar sus subcategorías a", otras, index=None, placeholder="Elige otra categoría",
                               format_func=lambda i: lib.rubro(i).nombre, key=f"mover_rubro_{rubro.id}",
                               help="Sus subcategorías y movimientos no se pierden: solo cambian de caja.")
    confirmar = st.checkbox("Quiero borrar esta categoría", key=f"confirmar_rubro_{rubro.id}")
    if st.button("Borrar categoría", key=f"borrar_rubro_{rubro.id}",
                 disabled=not confirmar or (bool(contenido) and destino is None)):
        if ejecutar(lambda lib: categorias.eliminar_rubro(lib, rubro.id, mover_a=destino), exito="Categoría borrada"):
            st.session_state.pop(f"rubro_elegido_{rubro.clase.value}", None)
            st.rerun()


def _clasificaciones_editables() -> None:
    lib = libro()
    st.caption("La clasificación dice **para qué** es cada gasto según tus metas, sin importar su categoría. "
               "Cada subcategoría de gasto está en **una sola** clasificación: para pasarla a otra, quítala primero "
               "de donde está (la ✕ en su etiqueta) y luego agrégala en la nueva.")
    gastos = [c for c in categorias.ordenadas(lib, lib.categorias()) if c.clase is ClaseCategoria.GASTO]
    grupos = sorted(lib.grupos(), key=lambda g: g.orden)
    _reparto_del_gasto(grupos, gastos)
    version = st.session_state.setdefault("_clasif_version", 0)
    for grupo in grupos:
        _caja(grupo, gastos, version)
    sueltas = [c for c in gastos if c.grupo_id is None]
    if sueltas:
        with st.container(border=True):
            st.markdown(f"**Sin clasificación** · {len(sueltas)}")
            st.caption("No cuentan en ninguna meta. Agrégalas en la clasificación que les corresponda.")
            st.markdown(" · ".join(categorias.etiqueta(lib, c.id) for c in sueltas))
    with st.form("nuevo_grupo", clear_on_submit=True, border=False):
        izquierda, derecha = st.columns([3, 1], vertical_alignment="bottom")
        nombre = izquierda.text_input("Nueva clasificación", max_chars=40, placeholder="Ej. Mascotas, Proyecto…")
        if derecha.form_submit_button("Agregar"):
            if ejecutar(lambda lib: categorias.crear_grupo(lib, nombre),
                        exito=f"Clasificación «{nombre.strip()}» agregada"):
                st.rerun()


def _reparto_del_gasto(grupos, gastos: list[Categoria]) -> None:
    """Cuánto pesa cada clasificación en tu gasto de este año (lo que importa es el dinero, no cuántas tenga)."""
    lib = libro()
    desde, hasta = reportes.rango_periodo(lib, "anio")
    montos = reportes.gastos_por_grupo(lib, desde, hasta)
    total = sum(montos.values())
    cuantas = Counter(c.grupo_id for c in gastos)
    filas = [(g.nombre, cuantas[g.id], montos.get(g.nombre, 0)) for g in grupos]
    filas.append((reportes.SIN_GRUPO, cuantas[None], montos.get(reportes.SIN_GRUPO, 0)))
    with st.expander(f"¿Cómo se reparte tu gasto de {desde.year}?", expanded=bool(total)):
        st.dataframe(formato.pintar(pd.DataFrame({
            "Clasificación": [f[0] for f in filas],
            "Subcategorías": [f[1] for f in filas],
            "Gasto": [formato.dinero(f[2]) for f in filas],
            "% del gasto": [f"{f[2] / total:.0%}" if total else "—" for f in filas],
        })), hide_index=True, width="stretch")


def _caja(grupo, gastos: list[Categoria], version: int) -> None:
    lib = libro()
    nombres = {g.id: g.nombre for g in lib.grupos()}
    dentro = [c.id for c in gastos if c.grupo_id == grupo.id]
    with st.container(border=True):
        cabeza, acciones = st.columns([5, 1], vertical_alignment="center")
        cabeza.markdown(f"**{grupo.nombre}** · {len(dentro)} subcategoría(s)")
        if grupo.nombre in catalogo.DESCRIPCIONES:
            cabeza.caption(catalogo.DESCRIPCIONES[grupo.nombre])
        with acciones.popover("Editar", width="stretch"):
            nuevo = st.text_input("Nombre", value=grupo.nombre, key=f"grupo_{grupo.id}", max_chars=40)
            if st.button("Renombrar", key=f"renombrar_{grupo.id}", disabled=nuevo.strip() == grupo.nombre):
                if ejecutar(lambda lib: categorias.renombrar_grupo(lib, grupo.id, nuevo),
                            exito="Clasificación renombrada"):
                    st.rerun()
            st.caption("Al borrarla, sus subcategorías quedan sin clasificación; no se pierde nada.")
            if st.button("Borrar clasificación", key=f"borrar_grupo_{grupo.id}"):
                if ejecutar(lambda lib: categorias.eliminar_grupo(lib, grupo.id), exito="Clasificación borrada"):
                    st.rerun()

        por_rubro: dict[str, list[str]] = {}
        for i in dentro:
            por_rubro.setdefault(categorias.nombre_rubro(lib, i), []).append(lib.categoria(i).nombre)
        if por_rubro:
            st.markdown("  \n".join(f"**{rubro}**: {' · '.join(subs)}" for rubro, subs in por_rubro.items()))

        def etiqueta(i: str) -> str:
            texto = lib.categoria(i).nombre
            otra = lib.categoria(i).grupo_id
            return texto if otra in (None, grupo.id) else f"{texto} (ya está en {nombres.get(otra, '?')})"

        clave_widget = f"clasif_{grupo.id}_{version}"
        st.multiselect(
            f"Subcategorías de {grupo.nombre}", [c.id for c in gastos], default=dentro, format_func=etiqueta,
            key=clave_widget, on_change=_al_cambiar, args=(grupo.id, clave_widget), label_visibility="collapsed",
            placeholder="Agrega una subcategoría (escribe para buscar)",
        )
        error = st.session_state.pop(f"_clasif_error_{grupo.id}", None)
        if error:
            st.error(error)


def _al_cambiar(grupo_id: str, clave_widget: str) -> None:
    """Aplica lo que el usuario agregó o quitó en una caja. Si algo no se puede, no cambia nada y lo explica."""
    actuales = {c.id for c in libro().categorias() if c.grupo_id == grupo_id and c.clase is ClaseCategoria.GASTO}
    elegidas = set(st.session_state.get(clave_widget, []))
    try:
        with sesion().cambio() as lib:
            for categoria_id in actuales - elegidas:
                categorias.clasificar(lib, categoria_id, None)
            for categoria_id in elegidas - actuales:
                categorias.clasificar(lib, categoria_id, grupo_id)
    except ErrorTally as error:
        st.session_state[f"_clasif_error_{grupo_id}"] = str(error)
    st.session_state["_clasif_version"] = st.session_state.get("_clasif_version", 0) + 1   # todas las cajas al día


def mostrar() -> None:
    st.title("Categorías")
    st.caption("Las **categorías** son cajas que agrupan **subcategorías** (por ejemplo, SALUD agrupa DENTISTA y "
               "MEDICINAS Y FARMACIA). A cada movimiento le pones una subcategoría y los reportes suman por ambas.")
    gastos, ingresos, clasificaciones, contabilidad, automaticas = st.tabs(
        ["Gastos", "Ingresos", "Clasificaciones", "Contabilidad", "⚡ Reglas automáticas"])
    with gastos:
        _arbol(ClaseCategoria.GASTO)
    with ingresos:
        _arbol(ClaseCategoria.INGRESO)
    with clasificaciones:
        _clasificaciones_editables()
    with contabilidad:
        contabilidad_categorias.mostrar()
    with automaticas:
        reglas.mostrar()
