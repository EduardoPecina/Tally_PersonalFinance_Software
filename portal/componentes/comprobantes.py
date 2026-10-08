"""📎 Comprobantes de un movimiento: verlos, descargarlos, quitarlos y adjuntar más (motor/comprobantes.py)."""

from __future__ import annotations

import streamlit as st

from motor import comprobantes
from portal.componentes import formato
from portal.componentes.sesion import ejecutar, libro, sesion

AYUDA = (f"Fotos (JPG, PNG, WEBP, HEIC), PDF o el XML de la factura, de hasta {comprobantes.MAXIMO_MB} MB cada uno. "
         "Se guardan dentro de tus datos (cifrados si tienes contraseña) y van en tus respaldos.")


def selector(clave: str, etiqueta: str = "📎 Comprobantes (opcional)"):
    """El selector de archivos (dentro o fuera de un formulario). Devuelve la lista elegida."""
    return st.file_uploader(etiqueta, type=comprobantes.ACEPTADAS, accept_multiple_files=True, key=clave,
                            help=AYUDA) or []


def adjuntar_todos(lib, operacion_id: str, archivos) -> int:
    """Adjunta los archivos del selector (dentro de un cambio: todo o nada)."""
    for archivo in archivos:
        comprobantes.adjuntar(lib, operacion_id, archivo.name, archivo.getvalue())
    return len(archivos)


def mostrar(operacion_id: str) -> None:
    lib = libro()
    lista = lib.comprobantes(operacion_id)
    if not lista:
        st.caption("Este movimiento no tiene comprobantes. Adjunta la foto del ticket, el PDF o el XML de la factura: "
                   "te sirven para aclaraciones, garantías y tus impuestos.")
    for c in lista:
        with st.container(border=True):
            texto, descargar, quitar = st.columns([6, 2, 2], vertical_alignment="center")
            agregado = f" · {c.agregado:%d/%m/%Y}" if c.agregado else ""
            texto.markdown(f"{comprobantes.icono(c)} **{formato.md(c.nombre)}**  \n"
                           f":gray[{comprobantes.tamano(c.tamano)}{agregado}]")
            descargar.download_button("Descargar", lambda cid=c.id: comprobantes.contenido(sesion(), cid),
                                      file_name=c.nombre, mime=c.tipo, key=f"comp_bajar_{c.id}", on_click="ignore",
                                      icon=":material/download:", width="stretch")
            with quitar.popover("Quitar", icon=":material/delete:", width="stretch"):
                st.caption("Se borra el archivo de tus datos (tus respaldos anteriores lo conservan).")
                if st.button("Sí, quitarlo", key=f"comp_quitar_{c.id}", type="primary"):
                    if ejecutar(lambda lib_, cid=c.id: comprobantes.quitar(lib_, cid),
                                exito=f"Comprobante «{c.nombre}» quitado"):
                        st.rerun()
            if comprobantes.es_imagen(c):
                try:
                    st.image(comprobantes.contenido(sesion(), c.id), width=360)
                except Exception:                     # noqa: BLE001 - una imagen que el navegador no sabe mostrar
                    st.caption("No se puede mostrar aquí; descárgala para verla.")
            otros = comprobantes.en_otros_movimientos(lib, c)
            if otros:
                op = lib.operacion(otros[0])
                st.caption(f"⚠️ Este mismo archivo está también en «{formato.md(op.descripcion or 'sin descripción')}» "
                           f"del {formato.fecha(op.fecha)}. ¿Registraste el mismo gasto dos veces?")
    version = st.session_state.get(f"_comp_version_{operacion_id}", 0)     # sube al adjuntar: el selector se vacía
    archivos = selector(f"comp_subir_{operacion_id}_{version}", "Adjuntar comprobantes")
    if archivos and st.button(f"Adjuntar {len(archivos)} archivo(s)", type="primary", key=f"comp_adjuntar_{operacion_id}",
                              icon=":material/attach_file:"):
        if ejecutar(lambda lib_: adjuntar_todos(lib_, operacion_id, archivos),
                    exito=f"{len(archivos)} comprobante(s) adjuntado(s)"):
            st.session_state[f"_comp_version_{operacion_id}"] = version + 1
            st.rerun()
