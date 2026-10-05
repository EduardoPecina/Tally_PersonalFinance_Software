"""Categorías y grupos: completamente personalizables."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import categorias
from motor.modelo import Categoria, ClaseCategoria
from portal.componentes.sesion import ejecutar, libro

SIN_GRUPO = "— Sin grupo —"


def _grupos() -> dict[str | None, str]:
    return {None: SIN_GRUPO, **{g.id: g.nombre for g in libro().grupos()}}


def _lista(clase: ClaseCategoria) -> None:
    lib = libro()
    grupos = _grupos()
    propias = [c for c in lib.categorias() if c.clase is clase]
    st.dataframe(
        pd.DataFrame({
            "Categoría": [c.nombre for c in propias],
            "Grupo": [grupos.get(c.grupo_id, SIN_GRUPO) for c in propias],
            "Estado": ["Activa" if c.activa else "Archivada" for c in propias],
            "Ingreso principal": ["Sí" if c.principal else "" for c in propias],
        }),
        hide_index=True, width="stretch",
        column_order=["Categoría", "Grupo", "Estado"] + (["Ingreso principal"] if clase is ClaseCategoria.INGRESO else []),
    )

    with st.expander("➕ Nueva categoría"):
        with st.form(f"nueva_{clase.value}", clear_on_submit=True, border=False):
            izquierda, derecha = st.columns(2)
            nombre = izquierda.text_input("Nombre", max_chars=60)
            grupo = derecha.selectbox("Grupo", list(grupos), format_func=grupos.get)
            principal = False
            if clase is ClaseCategoria.INGRESO:
                principal = st.checkbox("Es mi ingreso principal (p. ej. la nómina)",
                                        help="Marca el inicio de cada quincena en los reportes.")
            if st.form_submit_button("Agregar categoría", type="primary"):
                if ejecutar(lambda lib: categorias.crear(lib, nombre, clase, grupo_id=grupo, principal=principal),
                            exito=f"Categoría «{nombre.strip()}» agregada"):
                    st.rerun()

    if not propias:
        return
    ids = [c.id for c in propias]
    elegida = st.selectbox("Modificar una categoría", ids, index=None, placeholder="Elige una categoría",
                           format_func=lambda i: lib.categoria(i).nombre, key=f"elegida_{clase.value}")
    if elegida is not None:
        _modificar(lib.categoria(elegida), grupos)


def _modificar(categoria: Categoria, grupos: dict) -> None:
    lib = libro()
    with st.form(f"editar_{categoria.id}", border=False):
        izquierda, derecha = st.columns(2)
        nombre = izquierda.text_input("Nombre", value=categoria.nombre, max_chars=60)
        opciones = list(grupos)
        grupo = derecha.selectbox("Grupo", opciones, format_func=grupos.get,
                                  index=opciones.index(categoria.grupo_id) if categoria.grupo_id in opciones else 0)
        principal = None
        if categoria.clase is ClaseCategoria.INGRESO:
            principal = st.checkbox("Es mi ingreso principal", value=categoria.principal)
        if st.form_submit_button("Guardar cambios", type="primary"):
            if ejecutar(lambda lib: categorias.editar(lib, categoria.id, nombre=nombre, grupo_id=grupo,
                                                      principal=principal),
                        exito="Categoría actualizada"):
                st.rerun()

    izquierda, derecha = st.columns(2)
    with izquierda:
        if categoria.activa:
            st.caption("Archivar la oculta al registrar movimientos nuevos; su historial se conserva.")
            if st.button("Archivar", key=f"archivar_{categoria.id}"):
                if ejecutar(lambda lib: categorias.archivar(lib, categoria.id), exito="Categoría archivada"):
                    st.rerun()
        elif st.button("Reactivar", key=f"reactivar_{categoria.id}"):
            if ejecutar(lambda lib: categorias.reactivar(lib, categoria.id), exito="Categoría reactivada"):
                st.rerun()
    with derecha:
        en_uso = categorias.en_uso(lib, categoria.id)
        destino = None
        if en_uso:
            otras = [c.id for c in lib.categorias() if c.clase is categoria.clase and c.id != categoria.id]
            destino = st.selectbox("Pasar sus movimientos a", otras, index=None, placeholder="Elige otra categoría",
                                   format_func=lambda i: lib.categoria(i).nombre, key=f"destino_{categoria.id}",
                                   help="Borrar una categoría con movimientos es juntarla con otra.")
        confirmar = st.checkbox("Quiero borrar esta categoría", key=f"confirmar_{categoria.id}")
        if st.button("Borrar categoría", key=f"borrar_{categoria.id}",
                     disabled=not confirmar or (en_uso and destino is None)):
            if ejecutar(lambda lib: categorias.eliminar(lib, categoria.id, reasignar_a=destino),
                        exito="Categoría borrada"):
                st.session_state.pop(f"elegida_{categoria.clase.value}", None)
                st.rerun()


def _grupos_editables() -> None:
    lib = libro()
    st.caption("Los grupos agrupan tus categorías según tus metas (por ejemplo: Necesidad, Disfrute, "
               "Estabilidad). Puedes crear, renombrar o borrar los que quieras.")
    for grupo in lib.grupos():
        cuantas = sum(1 for c in lib.categorias() if c.grupo_id == grupo.id)
        with st.container(border=True):
            izquierda, centro, derecha = st.columns([3, 2, 1], vertical_alignment="bottom")
            nuevo = izquierda.text_input("Nombre del grupo", value=grupo.nombre, key=f"grupo_{grupo.id}",
                                         label_visibility="collapsed")
            centro.caption(f"{cuantas} categoría(s)")
            if nuevo.strip() != grupo.nombre and centro.button("Renombrar", key=f"renombrar_{grupo.id}"):
                if ejecutar(lambda lib: categorias.renombrar_grupo(lib, grupo.id, nuevo), exito="Grupo renombrado"):
                    st.rerun()
            if derecha.button("Borrar", key=f"borrar_grupo_{grupo.id}",
                              help="Sus categorías quedan sin grupo; no se pierde nada."):
                if ejecutar(lambda lib: categorias.eliminar_grupo(lib, grupo.id), exito="Grupo borrado"):
                    st.rerun()
    with st.form("nuevo_grupo", clear_on_submit=True, border=False):
        izquierda, derecha = st.columns([3, 1], vertical_alignment="bottom")
        nombre = izquierda.text_input("Nuevo grupo", max_chars=40)
        if derecha.form_submit_button("Agregar grupo"):
            if ejecutar(lambda lib: categorias.crear_grupo(lib, nombre), exito=f"Grupo «{nombre.strip()}» agregado"):
                st.rerun()


def mostrar() -> None:
    st.title("Categorías")
    st.caption("Organiza tus gastos e ingresos a tu manera.")
    gastos, ingresos, grupos = st.tabs(["Gastos", "Ingresos", "Grupos"])
    with gastos:
        _lista(ClaseCategoria.GASTO)
    with ingresos:
        _lista(ClaseCategoria.INGRESO)
    with grupos:
        _grupos_editables()
