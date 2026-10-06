"""Cargar datos: muchos movimientos a la vez desde la plantilla de texto (motor/importacion.py)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import categorias, importacion, respaldos
from motor.consultas import ETIQUETA_TIPO_OPERACION
from motor.errores import ErrorTally
from motor.importacion import Desconocido, Destino
from motor.modelo import ClaseCategoria, TipoCuenta
from portal.componentes import formato
from portal.componentes.sesion import aplicar, avisar, libro, sesion

PLANTILLAS = {
    TipoCuenta.DEBITO: "Tarjeta de débito",
    TipoCuenta.CREDITO: "Tarjeta de crédito",
    TipoCuenta.AHORRO: "Cuenta de ahorro",
    TipoCuenta.INVERSION: "Inversión",
    None: "Todas en un archivo",
}
NUEVA, EXISTENTE, CUENTA = "Crear como subcategoría nueva", "Es una subcategoría que ya existe", "Es una de mis cuentas"
ESTADOS = {
    importacion.NUEVO: "✅ Se carga",
    importacion.YA_ESTABA: "⏭️ Ya estaba",
    importacion.CONTRAPARTE: "↔️ Viene en la otra cuenta",
    importacion.PENDIENTE: "❓ Falta decidir",
    importacion.ERROR: "❌ Error",
}


def _plantillas() -> None:
    st.subheader("1. Descarga una plantilla")
    st.caption("Es un archivo de texto con instrucciones y ejemplos. Ábrelo con el Bloc de notas, pega tus "
               "movimientos (copiados de Excel) y guárdalo. Una plantilla por cuenta, o todas en un archivo.")
    columnas = st.columns(len(PLANTILLAS))
    for columna, (tipo, etiqueta) in zip(columnas, PLANTILLAS.items()):
        columna.download_button(
            etiqueta, importacion.plantilla(tipo).encode("utf-8-sig"), file_name=importacion.nombre_de_plantilla(tipo),
            mime="text/plain", on_click="ignore", icon=":material/download:", width="stretch",
            key=f"plantilla_{tipo.value if tipo else 'todas'}",
        )
    with st.expander("¿Cómo funciona?"):
        st.markdown(
            "- Cada fila es un movimiento: **FECHA**, **DESCRIPCION**, **SUBCATEGORIA**, **CARGO** (salió dinero) "
            "o **ABONO** (entró dinero) y **NOTAS** (opcional).\n"
            "- En **SUBCATEGORIA** va una subcategoría de TALLY (DESPENSA, GASOLINA, NOMINA…) o, si el dinero fue a "
            "otra de tus cuentas, el nombre de esa cuenta: entonces es una transferencia y **no** cuenta como "
            "gasto. Pagar la tarjeta de crédito es un pago de tarjeta: el gasto ya se contó al comprar.\n"
            "- Si la misma transferencia viene en las dos cuentas, se carga una sola vez. Lo que ya está en TALLY "
            "no se vuelve a cargar, así que puedes subir el mismo archivo dos veces sin duplicar nada.\n"
            "- Si la cuenta no existe, TALLY la crea con el **TIPO** y el **SALDO INICIAL** del encabezado.\n"
            "- Antes de guardar ves una vista previa. Si algo está mal no se carga nada, y antes de cargar se crea "
            "un respaldo automático."
        )


def _archivo() -> str | None:
    st.subheader("2. Sube tu archivo")
    version = st.session_state.setdefault("_cargar_version", 0)
    subido = st.file_uploader("Archivo de texto (.txt)", type=["txt", "tsv", "csv"], key=f"cargar_archivo_{version}")
    pegado = st.text_area("…o pega aquí el contenido", key=f"cargar_texto_{version}", height=120,
                          placeholder="CUENTA: Mi tarjeta de débito\nTIPO: DEBITO\nFECHA\tDESCRIPCION\t…")
    if subido is not None:
        return importacion.decodificar(subido.getvalue())
    return pegado if pegado.strip() else None


def _mapeo(pendientes: list[Desconocido]) -> dict[str, Destino]:
    """Pregunta a qué corresponde cada nombre que TALLY no reconoce."""
    lib = libro()
    st.subheader("3. ¿Qué es cada cosa que TALLY no reconoce?")
    st.caption("Son nombres de la columna SUBCATEGORIA que no son una subcategoría ni una de tus cuentas. "
               "Decide una vez por nombre y se aplica a todas sus filas.")
    cuentas_ids = [c.id for c in lib.cuentas()]
    mapeo: dict[str, Destino] = {}
    for d in pendientes:
        vacia = d.nombre in importacion.SIN_SUBCATEGORIA.values()
        clase = d.sugerencia
        with st.container(border=True):
            st.markdown(f"**{formato.md(d.nombre)}** · {d.filas} fila(s): {d.cargos} cargo(s), {d.abonos} abono(s)")
            opciones = ([] if vacia else [NUEVA]) + [EXISTENTE] + ([CUENTA] if cuentas_ids else [])
            que = st.radio("¿Qué es?", opciones, horizontal=True, key=f"cargar_que_{d.clave}",
                           label_visibility="collapsed")
            if que == NUEVA:
                rubros = [r for r in lib.rubros() if r.clase is clase] + [r for r in lib.rubros() if r.clase is not clase]
                varios = next((i for i, r in enumerate(rubros) if r.nombre in ("VARIOS", "INGRESOS VARIOS")), 0)
                rubro = st.selectbox(
                    f"Crear «{categorias.estandarizar(d.nombre)}» dentro de la categoría", [r.id for r in rubros],
                    index=varios, format_func=lambda i: f"{lib.rubro(i).nombre} ({_clase(lib.rubro(i).clase)})",
                    key=f"cargar_rubro_{d.clave}")
                mapeo[d.clave] = Destino.nueva(rubro)
            elif que == EXISTENTE:
                subcategorias = categorias.ordenadas(lib, [c for c in lib.categorias() if c.rubro_id and c.activa])
                ids = [c.id for c in subcategorias]
                otros = categorias.buscar(lib, "OTROS INGRESOS" if clase is ClaseCategoria.INGRESO else "OTROS GASTOS")
                elegida = st.selectbox("Subcategoría", ids, index=ids.index(otros.id) if otros and otros.id in ids
                                       else None, placeholder="Escribe para buscar",
                                       format_func=lambda i: categorias.etiqueta(lib, i), key=f"cargar_sub_{d.clave}")
                if elegida:
                    mapeo[d.clave] = Destino.subcategoria(elegida)
            else:
                elegida = st.selectbox("Cuenta (será una transferencia)", cuentas_ids, index=None,
                                       placeholder="Elige la cuenta", format_func=lambda i: lib.cuenta(i).nombre,
                                       key=f"cargar_cuenta_{d.clave}")
                if elegida:
                    mapeo[d.clave] = Destino.cuenta(elegida)
    return mapeo


def _clase(clase: ClaseCategoria) -> str:
    return "ingreso" if clase is ClaseCategoria.INGRESO else "gasto"


def _vista_previa(resultado: importacion.Resultado) -> None:
    st.subheader("4. Revisa y carga")
    columnas = st.columns(4)
    columnas[0].metric("Se cargan", resultado.nuevos)
    columnas[1].metric("Ya estaban", resultado.contar(importacion.YA_ESTABA))
    columnas[2].metric("En las dos cuentas", resultado.contar(importacion.CONTRAPARTE),
                       help="Transferencias que vienen en los dos bloques: se cargan una vez.")
    columnas[3].metric("Con error", resultado.contar(importacion.ERROR) + len(resultado.errores))
    if resultado.cuentas_nuevas:
        st.caption("Cuentas nuevas: " + ", ".join(f"**{formato.md(n)}**" for n in resultado.cuentas_nuevas))
    if resultado.subcategorias_nuevas:
        st.caption("Subcategorías nuevas: " + ", ".join(f"**{n}**" for n in resultado.subcategorias_nuevas))
    problemas = resultado.errores + [f"Línea {f.numero}: {f.detalle}" for f in resultado.filas
                                     if f.estado == importacion.ERROR]
    if problemas:
        st.error("Corrige esto en tu archivo y vuelve a subirlo (no se carga nada mientras haya errores):\n\n"
                 + "\n".join(f"- {formato.md(p)}" for p in problemas[:30])
                 + (f"\n- … y {len(problemas) - 30} más" if len(problemas) > 30 else ""))
    if resultado.filas:
        st.dataframe(
            pd.DataFrame({
                "Línea": [f.numero for f in resultado.filas],
                "Estado": [ESTADOS[f.estado] for f in resultado.filas],
                "Cuenta": [f.cuenta for f in resultado.filas],
                "Fecha": [f.fecha for f in resultado.filas],
                "Descripción": [f.descripcion for f in resultado.filas],
                "Tipo": [ETIQUETA_TIPO_OPERACION[f.tipo] if f.tipo else "" for f in resultado.filas],
                "Subcategoría o cuenta": [f.destino for f in resultado.filas],
                "Importe": [formato.dinero_con_signo(f.monto, f.sentido) for f in resultado.filas],
                "Detalle": [f.detalle for f in resultado.filas],
            }),
            hide_index=True, width="stretch", height=min(38 + 35 * len(resultado.filas), 460),
            column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")},
        )


def mostrar() -> None:
    st.title("Cargar datos")
    st.caption("Pasa a TALLY los movimientos que ya tenías (por ejemplo, en Excel), muchos a la vez.")
    _plantillas()
    texto = _archivo()
    if texto is None:
        return
    archivo = importacion.leer(texto)
    if not archivo.bloques:
        st.error("\n".join(f"- {formato.md(e)}" for e in archivo.errores))
        return
    pendientes = importacion.desconocidos(libro(), archivo)
    mapeo = _mapeo(pendientes) if pendientes else {}
    if not pendientes:
        st.subheader("3. Todo reconocido")
        st.caption("Todas las subcategorías y cuentas del archivo ya existen en TALLY (o se van a crear).")
    resultado = importacion.vista_previa(libro(), archivo, mapeo)
    _vista_previa(resultado)
    if resultado.pendientes:
        st.info("Decide arriba qué es cada nombre que TALLY no reconoce.")
    if st.button(f"Cargar {resultado.nuevos} movimiento(s)", type="primary", disabled=not resultado.se_puede_cargar):
        try:
            respaldo = respaldos.crear(sesion(), prefijo="antes_de_cargar_datos")
        except (ErrorTally, OSError) as error:
            st.error(f"No se cargó nada: no se pudo crear el respaldo previo ({error}).")
            return
        hecho = aplicar(lambda lib: importacion.cargar(lib, archivo, mapeo))
        if hecho is not None:
            st.session_state["_cargar_version"] += 1          # deja el formulario vacío
            avisar(f"Se cargaron {hecho.nuevos} movimiento(s). Respaldo previo: {respaldo.name}")
            st.rerun()
