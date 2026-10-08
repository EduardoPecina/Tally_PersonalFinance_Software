"""Cargar datos → «Desde tu banco»: el archivo de tu banca en línea (Excel o CSV), el PDF del estado de cuenta o
lo que copies de la página del banco. TALLY sugiere la subcategoría de cada movimiento y aparta lo que ya está
(motor/bancos.py). Nada sale de tu PC."""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from motor import bancos, categorias, importacion, reglas_categorias, respaldos
from motor.consultas import ETIQUETA_TIPO_OPERACION
from motor.dinero import a_pesos
from motor.errores import ErrorTally
from motor.modelo import ClaseCategoria, TipoCuenta
from portal.componentes import formato
from portal.componentes.sesion import aplicar, avisar, ejecutar, libro, sesion

SALE, ENTRA = "🔻 Sale", "🔺 Entra"
NINGUNA = "(ninguna)"
ELIGE = "❓ Elige…"
PLURALES = {"Gasto": "gastos", "Ingreso": "ingresos", "Reembolso": "reembolsos", "Transferencia": "transferencias",
            "Pago de tarjeta": "pagos de tarjeta", "Rendimiento": "rendimientos", "Ajuste de saldo": "ajustes de saldo"}
TIPOS = (TipoCuenta.DEBITO, TipoCuenta.CREDITO, TipoCuenta.AHORRO, TipoCuenta.INVERSION, TipoCuenta.EFECTIVO,
         TipoCuenta.OTRA, TipoCuenta.PRESTAMO, TipoCuenta.POR_COBRAR)


def mostrar() -> None:
    lib = libro()
    disponibles = [c for c in lib.cuentas() if c.activa and c.tipo in TIPOS]
    if not disponibles:
        st.info("Primero crea en **Cuentas** la cuenta o tarjeta de tu banco.")
        return
    version = st.session_state.setdefault("_banco_version", 0)

    st.subheader("1. ¿De qué cuenta son los movimientos?")
    ids = [c.id for c in disponibles]
    cuenta_id = st.selectbox("Cuenta o tarjeta", ids, format_func=lambda i: lib.cuenta(i).nombre, key="banco_cuenta",
                             label_visibility="collapsed")
    cuenta = lib.cuenta(cuenta_id)

    st.subheader("2. Sube el archivo de tu banco")
    _ayuda()
    fuente = _fuente(version)
    if fuente is None:
        return

    clave = f"{version}_{abs(hash((fuente, cuenta_id))) % 10 ** 10}"
    st.session_state["_banco_clave"] = clave              # (cambia con otro archivo u otra cuenta)
    lectura = _lectura(fuente, cuenta, clave)
    if lectura is None:
        return

    st.subheader("3. Revisa y elige en qué se gastó")
    propuestas = bancos.revisar(lib, cuenta_id, lectura.movimientos)
    elegidos = _tabla(lib, cuenta_id, propuestas, clave) or []
    elegidos += _agregados(lib, cuenta_id, lectura, clave)
    if not elegidos:
        return
    _cargar(lib, cuenta_id, elegidos)


def _ayuda() -> None:
    with st.expander("¿Dónde consigo el archivo?"):
        st.markdown(
            "- **Lo mejor:** entra a tu banca en línea → **Movimientos** → **Exportar** o **Descargar** en "
            "**Excel** o **CSV**. Casi todos los bancos lo tienen.\n"
            "- **El PDF de tu estado de cuenta** también sirve. TALLY lee los renglones que empiezan con una fecha "
            "y terminan con un importe; revisa bien el resultado.\n"
            "- O **copia la tabla** de movimientos de la página de tu banco (o de Excel) y pégala en el cuadro.\n\n"
            "Todo se queda en tu PC: TALLY no se conecta a tu banco ni manda el archivo a ningún lado.")


def _fuente(version: int) -> bancos.Fuente | None:
    subido = st.file_uploader("Excel, CSV o PDF", type=list(bancos.TIPOS_DE_ARCHIVO), key=f"banco_archivo_{version}")
    pegado = st.text_area("…o pega aquí tus movimientos", key=f"banco_texto_{version}", height=110,
                          placeholder="15/07/2026\tWALMART SUPERCENTER\t850.00")
    contrasena = st.session_state.get(f"banco_pdf_{version}", "")
    try:
        if subido is not None:
            return _leer_cacheado(subido.name, subido.getvalue(), contrasena)
        if pegado.strip():
            return bancos.de_texto(pegado)
    except bancos.PdfConContrasena as error:
        st.warning(f"🔒 {error} Escríbela aquí; muchos bancos usan tu RFC o tu fecha de nacimiento. TALLY no "
                   "la guarda.")
        st.text_input("Contraseña del PDF", type="password", key=f"banco_pdf_{version}")
    except ErrorTally as error:
        st.error(str(error))
    return None


def _leer_cacheado(nombre: str, datos: bytes, contrasena: str) -> bancos.Fuente:
    """Leer un PDF grande tarda: se guarda lo leído mientras sea el mismo archivo."""
    llave = (nombre, len(datos), hash(datos), contrasena)
    guardado = st.session_state.get("_banco_fuente")
    if guardado and guardado[0] == llave:
        return guardado[1]
    fuente = bancos.leer(nombre, datos, contrasena_pdf=contrasena)
    st.session_state["_banco_fuente"] = (llave, fuente)
    return fuente


def _lectura(fuente: bancos.Fuente, cuenta, clave: str) -> bancos.Lectura | None:
    credito = cuenta.tipo is TipoCuenta.CREDITO
    columnas = None
    if fuente.es_tabla:
        try:
            detectadas = bancos.detectar(fuente.tabla)
        except ErrorTally:
            detectadas = None
        columnas = _columnas(fuente, detectadas, clave)
        if columnas is None:
            return None
    signo = st.session_state.get(f"banco_signo_{clave}")
    try:
        lectura = bancos.interpretar(fuente, credito=credito, columnas=columnas,
                                     cargos_negativos=None if signo is None else signo == 0)
    except ErrorTally as error:
        st.error(str(error))
        return None

    if lectura.cargos_negativos is not None:
        st.radio("En tu archivo, lo que **salió** (compras, pagos, retiros) tiene…", [0, 1],
                 index=0 if lectura.cargos_negativos else 1, horizontal=True, key=f"banco_signo_{clave}",
                 format_func=lambda v: "signo de menos (−850.00)" if v == 0 else "signo de más (850.00)",
                 help="Lo deduje del archivo. Si los totales de abajo no coinciden con tu estado de cuenta, "
                      "cámbialo.")
    a, b, c = st.columns(3)
    a.metric("Movimientos", len(lectura.movimientos))
    b.metric("Salió", formato.dinero_metrica(a_pesos(lectura.sale)))
    c.metric("Entró", formato.dinero_metrica(a_pesos(lectura.entra)))
    st.caption(f"Periodo: {formato.rango(lectura.desde, lectura.hasta)}. Compara estos totales con tu estado de "
               "cuenta: si coinciden, TALLY leyó bien tu archivo.")
    _comparar_con_el_banco(lectura)
    for aviso in lectura.avisos:
        st.warning(aviso, icon="🔍")
    if lectura.omitidos:
        st.warning(f"{lectura.omitidos} renglón(es) no los pude leer completos y no están en la tabla. Si falta "
                   "alguno, agrégalo abajo en «➕ ¿Falta algún movimiento?».", icon="⚠️")
    return lectura


def _comparar_con_el_banco(lectura: bancos.Lectura) -> None:
    """Si el estado de cuenta trae su saldo anterior y el del corte (o sus totales), la mejor prueba de que TALLY lo
    leyó bien."""
    if lectura.falta is not None:
        deuda = lectura.credito
        anterior, final = a_pesos(lectura.saldo_inicial), a_pesos(lectura.saldo_final)
        if lectura.falta == 0:
            st.success(f"Cuadra con tu estado de cuenta: {'debías' if deuda else 'tenías'} "
                       f"{formato.dinero_md(anterior)}, {'pagaste' if deuda else 'entró'} "
                       f"{formato.dinero_md(a_pesos(lectura.entra))}, {'gastaste' if deuda else 'salió'} "
                       f"{formato.dinero_md(a_pesos(lectura.sale))} y al corte "
                       f"{'debes' if deuda else 'tienes'} {formato.dinero_md(final)}.", icon="✅")
            if any(m.del_resumen for m in lectura.movimientos):
                st.info("Agregué los intereses, comisiones o IVA que solo venían en el resumen de tu estado de cuenta "
                        "(marcados con 📋): sin ellos no cuadraba.", icon="📋")
        else:
            st.warning(f"No cuadra con tu estado de cuenta: con {'tu deuda' if deuda else 'tu saldo'} anterior de "
                       f"{formato.dinero_md(anterior)} y los movimientos que leí, al corte "
                       f"{'deberías' if deuda else 'tendrías'} {formato.dinero_md(final + a_pesos(lectura.falta) * (1 if deuda else -1))}, "
                       f"pero tu estado de cuenta dice {formato.dinero_md(final)} (diferencia de "
                       f"{formato.dinero_md(a_pesos(abs(lectura.falta)))}). Puede faltar un movimiento o alguno estar "
                       "al revés (entra/sale): revisa la tabla contra tu PDF.", icon="⚠️")
        return
    comparaciones = [(que, dice, leido) for que, dice, leido in (("cargos", lectura.total_cargos, lectura.sale),
                                                                ("abonos", lectura.total_abonos, lectura.entra))
                     if dice is not None]
    if not comparaciones:
        return
    distintos = [(q, d, ld) for q, d, ld in comparaciones if d != ld]
    if not distintos:
        st.success("Coincide con los totales que imprime tu banco: "
                   + " y ".join(f"{q} {formato.dinero_md(a_pesos(d))}" for q, d, _ in comparaciones) + ".",
                   icon="✅")
        return
    for que, dice, leido in distintos:
        st.warning(f"Tu estado de cuenta dice que los {que} suman **{formato.dinero_md(a_pesos(dice))}** y TALLY "
                   f"leyó **{formato.dinero_md(a_pesos(leido))}**. Revisa la tabla: puede faltar o sobrar algún "
                   "movimiento, o alguno estar al revés (entra/sale).", icon="⚠️")


def _columnas(fuente: bancos.Fuente, detectadas: bancos.Columnas | None, clave: str) -> bancos.Columnas | None:
    """Lo que TALLY entendió de las columnas, con la opción de corregirlo."""
    nombres = bancos.titulos(fuente.tabla, detectadas)
    indices = list(range(len(nombres)))
    with st.expander("¿Leí mal alguna columna? Corrígela aquí", expanded=detectadas is None):
        if detectadas is None:
            st.warning("No supe qué columna es cada cosa. Elígelas:")
        st.dataframe(formato.pintar(pd.DataFrame([list(f) + [""] * (len(nombres) - len(f)) for f in fuente.tabla[:8]],
                                  columns=[f"{i + 1}. {n}" for i, n in enumerate(nombres)])),
                     hide_index=True, width="stretch")
        etiqueta = {i: f"{i + 1}. {n}" for i, n in enumerate(nombres)}

        def elegir(texto, actual, *, opcional=True, columna=None):
            opciones = ([None] if opcional else []) + indices
            return columna.selectbox(texto, opciones, index=opciones.index(actual) if actual in opciones else 0,
                                     format_func=lambda i: NINGUNA if i is None else etiqueta[i],
                                     key=f"banco_col_{texto}_{clave}")

        d = detectadas
        a, b = st.columns(2)
        fecha = elegir("Fecha", d.fecha if d else None, columna=a)
        descripcion = b.multiselect("Descripción", indices, default=list(d.descripcion) if d else [],
                                    format_func=etiqueta.get, key=f"banco_col_desc_{clave}")
        a, b, c = st.columns(3)
        cargo = elegir("Cargos (lo que sale)", d.cargo if d else None, columna=a)
        abono = elegir("Abonos (lo que entra)", d.abono if d else None, columna=b)
        importe = elegir("Importe con signo", d.importe if d else None, columna=c)
        st.caption("Usa **Cargos y Abonos** si tu archivo los trae en columnas separadas, o **Importe con signo** "
                   "si viene en una sola.")
    if fecha is None:
        st.error("Elige la columna de la fecha.")
        return None
    if importe is None and (cargo is None or abono is None):
        if cargo is not None or abono is not None:
            importe, cargo, abono = cargo if cargo is not None else abono, None, None
        else:
            st.error("Elige la columna del importe (o las de cargos y abonos).")
            return None
    if importe is not None and cargo is not None and abono is not None:
        importe = None
    sin_cambios = d and (fecha, tuple(descripcion), cargo, abono, importe) == (
        d.fecha, d.descripcion, d.cargo, d.abono, d.importe)
    if sin_cambios:
        return d
    return bancos.Columnas(fecha, tuple(descripcion), cargo if importe is None else None,
                           abono if importe is None else None, importe, None, d.encabezado if d else None,
                           d.saldo if d else None)


def _opciones(lib, cuenta_id: str) -> dict[str, str]:
    """Etiqueta → destino, para la columna «Subcategoría o cuenta»."""
    subcategorias = categorias.ordenadas(lib, [c for c in lib.categorias() if c.rubro_id and c.activa])
    opciones = {categorias.etiqueta(lib, c.id): bancos.destino_subcategoria(c.id) for c in subcategorias}
    for c in lib.cuentas():
        if c.activa and c.id != cuenta_id:
            opciones[f"↔ {c.nombre}"] = bancos.destino_cuenta(c.id)
    return opciones


def _tabla(lib, cuenta_id: str, propuestas: list[bancos.Propuesta], clave: str):
    opciones = _opciones(lib, cuenta_id)
    etiquetas = {destino: etiqueta for etiqueta, destino in opciones.items()}
    por_grupo = _desconocidos(propuestas, opciones, clave)
    notas = []
    for i, p in enumerate(propuestas):
        if p.duplicado is not None:
            op = p.duplicado
            nota = f"⏭️ Ya está en TALLY: «{op.descripcion or 'sin descripción'}» del {op.fecha:%d/%m/%Y}"
        elif i in por_grupo:
            nota = "👆 Lo elegiste arriba"
        else:
            nota = ("✨ " if p.destino else "❓ ") + p.motivo
        if p.movimiento.del_resumen:
            nota = "📋 No venía en la lista de movimientos: lo tomé del resumen de tu estado de cuenta · " + nota
        if p.movimiento.supuesto:
            nota = "🔍 " + nota
        notas.append(nota)
    datos = pd.DataFrame({
        "Cargar": [p.cargar for p in propuestas],
        "Fecha": [p.movimiento.fecha for p in propuestas],
        "Descripción": [p.movimiento.descripcion for p in propuestas],
        "Movimiento": [ENTRA if p.movimiento.centavos > 0 else SALE for p in propuestas],
        "Importe": [float(a_pesos(abs(p.movimiento.centavos))) for p in propuestas],
        "Subcategoría o cuenta": [etiquetas.get(p.destino or por_grupo.get(i, ""), ELIGE)
                                  for i, p in enumerate(propuestas)],
        "Nota de TALLY": notas,
    })
    duplicados = sum(not p.cargar for p in propuestas)
    sugeridas = sum(bool(p.destino) for p in propuestas)
    st.caption(f"TALLY sugirió la subcategoría de **{sugeridas} de {len(propuestas)}** movimientos (✨) por tus "
               "reglas automáticas, por lo que elegiste antes o por el nombre del comercio. Cámbiala donde no te "
               "convenza. "
               + (f"**{duplicados}** ya estaban en TALLY (⏭️): no se cargan, salvo que los marques. "
                  if duplicados else "")
               + "Si eliges la subcategoría de un movimiento, se usa también para los que se llaman igual o casi igual.")
    editada = st.data_editor(
        datos, key=f"banco_editor_{clave}", hide_index=True, width="stretch", num_rows="fixed",
        height=min(38 + 35 * len(datos), 520),
        column_config={
            "Cargar": st.column_config.CheckboxColumn(width="small"),
            "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY", disabled=True, width="small"),
            "Descripción": st.column_config.TextColumn(width="medium"),
            "Movimiento": st.column_config.SelectboxColumn(options=[SALE, ENTRA], required=True, width="small"),
            "Importe": st.column_config.NumberColumn(format=formato.columna_dinero(), disabled=True, width="small"),
            "Subcategoría o cuenta": st.column_config.SelectboxColumn(options=[ELIGE, *opciones], required=True,
                                                                         width="medium"),
            "Nota de TALLY": st.column_config.TextColumn(disabled=True, width="medium"),
        },
    )
    elegidos = []
    for p, (_, fila) in zip(propuestas, editada.iterrows()):
        if not fila["Cargar"]:
            continue
        monto = abs(p.movimiento.centavos)
        movimiento = bancos.Movimiento(p.movimiento.fila, p.movimiento.fecha,
                                       " ".join(str(fila["Descripción"] or "").split()),
                                       monto if fila["Movimiento"] == ENTRA else -monto)
        elegidos.append((movimiento, opciones.get(fila["Subcategoría o cuenta"] or "", "")))
    if not elegidos:
        st.info("No hay movimientos marcados para cargar.")
        return None
    elegidos = bancos.propagar(elegidos)
    faltan = sum(not destino for _, destino in elegidos)
    if faltan:
        st.warning(f"Te falta elegir la subcategoría (o cuenta) de **{faltan}** movimiento(s): búscalos con ❓ en la "
                   "tabla.", icon="❓")
        if st.checkbox("Mandar los que falten a OTROS GASTOS (lo que sale) y OTROS INGRESOS (lo que entra)",
                       key=f"banco_otros_{clave}"):
            elegidos = [(m, destino or bancos.de_respaldo(lib, m)) for m, destino in elegidos]
    return elegidos


def _desconocidos(propuestas: list[bancos.Propuesta], opciones: dict[str, str], clave: str) -> dict[int, str]:
    """Lo que TALLY no reconoce, agrupado (los iguales o casi iguales juntos): se elige una vez por grupo.
    Devuelve índice del movimiento → destino elegido."""
    grupos = bancos.sin_reconocer(propuestas)
    if not grupos:
        return {}
    elegidos: dict[int, str] = {}
    st.markdown(f"**❓ TALLY no reconoce {sum(len(g) for g in grupos)} movimiento(s).** Elige una vez por grupo y "
                "se aplica a todos los parecidos (o hazlo renglón por renglón en la tabla de abajo).")
    with st.container(border=True):
        for n, indices in enumerate(grupos[:40]):
            primero = propuestas[indices[0]].movimiento
            total = sum(abs(propuestas[i].movimiento.centavos) for i in indices)
            texto = (f"«{formato.md(primero.descripcion)}»" + (f" y {len(indices) - 1} más" if len(indices) > 1 else "")
                     + f" · {'entró' if primero.centavos > 0 else 'salió'} {formato.dinero_md(a_pesos(total))}")
            a, b, c = st.columns([6, 4, 1], vertical_alignment="center")
            a.markdown(texto)
            elegido = b.selectbox(texto, [ELIGE, *opciones], key=f"banco_grupo_{clave}_{n}",
                                  label_visibility="collapsed")
            if elegido != ELIGE:
                elegidos.update(dict.fromkeys(indices, opciones[elegido]))
            _boton_regla(c, [propuestas[i].movimiento for i in indices], opciones.get(elegido, ""), f"{clave}_{n}")
        if len(grupos) > 40:
            st.caption(f"…y {len(grupos) - 40} grupo(s) más: elígelos en la tabla.")
    return elegidos


def _boton_regla(columna, movimientos: list[bancos.Movimiento], destino: str, clave: str) -> None:
    """«⚡»: crea una regla automática con lo elegido para el grupo, para que la próxima vez TALLY lo haga solo."""
    tipo, _, categoria_id = destino.partition(":")
    texto = reglas_categorias.texto_para([m.descripcion for m in movimientos])
    if tipo != "sub" or texto is None:
        columna.button("⚡", key=f"banco_regla_{clave}", disabled=True,
                       help="Elige una subcategoría y te ofrezco crear una regla automática para la próxima vez."
                       if texto else "No encontré un texto que identifique a estos movimientos para una regla.")
        return
    lib = libro()
    clase = lib.categoria(categoria_id).clase
    if movimientos[0].centavos > 0 and clase is ClaseCategoria.GASTO:
        columna.button("⚡", key=f"banco_regla_{clave}", disabled=True,
                       help="Es una devolución: las reglas de gasto aplican a lo que sale.")
        return
    if columna.button("⚡", key=f"banco_regla_{clave}",
                      help=f"Siempre así: crear la regla «{texto}» → {categorias.etiqueta(lib, categoria_id)}. "
                           "La próxima vez TALLY lo hará solo (la editas en Categorías › ⚡ Reglas automáticas)."):
        if ejecutar(lambda lib_: reglas_categorias.crear(lib_, texto, categoria_id),
                    exito=f"Regla creada: «{texto}» → {categorias.etiqueta(lib, categoria_id)}"):
            st.rerun()


def _agregados(lib, cuenta_id: str, lectura: bancos.Lectura, clave: str) -> list[tuple[bancos.Movimiento, str]]:
    """Movimientos que TALLY no encontró en el archivo y el usuario agrega a mano (se cargan junto con los demás)."""
    llave = f"_banco_agregados_{clave}"
    agregados: list[dict] = st.session_state.setdefault(llave, [])
    opciones = _opciones(lib, cuenta_id)
    no_cuadra = lectura.falta not in (None, 0)
    with st.expander("➕ ¿Falta algún movimiento? Agrégalo aquí", expanded=no_cuadra or bool(agregados)):
        if no_cuadra and lectura.sueltos:
            st.markdown("Estos renglones de tu archivo tienen un importe pero **no los entendí como movimiento**. Si "
                        "alguno es el que falta, agrégalo abajo:")
            st.code("\n".join(f"Renglón {n}: {texto}" for n, texto in lectura.sueltos), language=None)
        elif no_cuadra:
            st.caption("Busca en tu estado de cuenta el movimiento que no aparece en la tabla y agrégalo abajo.")
        with st.form(f"banco_agregar_{clave}", clear_on_submit=True, border=False):
            a, b, c = st.columns([1, 2, 1])
            fecha = a.date_input("Fecha", value=lectura.hasta, format="DD/MM/YYYY")
            descripcion = b.text_input("Descripción", placeholder="Como viene en tu estado de cuenta")
            importe = c.number_input("Importe", min_value=0.0, step=1.0, format="%.2f")
            a, b = st.columns([1, 3])
            sentido = a.radio("Movimiento", [SALE, ENTRA], horizontal=True)
            destino = b.selectbox("Subcategoría o cuenta", list(opciones), index=None, placeholder="Escribe para buscar")
            if st.form_submit_button("Agregar", icon=":material/add:"):
                if not importe or not destino or not descripcion.strip():
                    st.error("Escribe la descripción, el importe y elige la subcategoría o cuenta.")
                else:
                    agregados.append({"fecha": fecha, "descripcion": " ".join(descripcion.split()),
                                      "centavos": round(importe * 100) * (1 if sentido == ENTRA else -1),
                                      "destino": opciones[destino], "etiqueta": destino})
                    st.rerun()
        for n, a in enumerate(list(agregados)):
            izquierda, derecha = st.columns([5, 1], vertical_alignment="center")
            izquierda.markdown(f"➕ {a['fecha']:%d/%m/%Y} · **{formato.md(a['descripcion'])}** · "
                               f"{'entró' if a['centavos'] > 0 else 'salió'} "
                               f"{formato.dinero_md(a_pesos(abs(a['centavos'])))} · {a['etiqueta']}")
            if derecha.button("Quitar", key=f"banco_quitar_{clave}_{n}"):
                agregados.pop(n)
                st.rerun()
    if lectura.falta not in (None, 0) and agregados:
        resta = lectura.falta - sum(a["centavos"] for a in agregados)
        if resta == 0:
            st.success("Con lo que agregaste, ya cuadra con tu estado de cuenta.", icon="✅")
        else:
            st.warning(f"Aún no cuadra: la diferencia ahora es de {formato.dinero_md(a_pesos(abs(resta)))}.", icon="⚠️")
    return [(bancos.Movimiento(900_000 + n, a["fecha"], a["descripcion"], a["centavos"]), a["destino"])
            for n, a in enumerate(agregados)]


def _cargar(lib, cuenta_id: str, elegidos) -> None:
    st.subheader("4. Carga")
    if any(not destino for _, destino in elegidos):
        st.button("Importar movimientos", type="primary", disabled=True, key="banco_importar")
        return
    try:
        archivo, mapeo = bancos.para_cargar(lib, cuenta_id, elegidos)
    except ErrorTally as error:
        st.error(str(error))
        return
    vista = importacion.vista_previa(lib, archivo, mapeo)
    nuevos = [f for f in vista.filas if f.estado == importacion.NUEVO]
    tipos = Counter(ETIQUETA_TIPO_OPERACION[f.tipo] for f in nuevos if f.tipo)
    if nuevos:
        st.markdown(f"Se van a cargar **{len(nuevos)}** movimiento(s) a **{formato.md(lib.cuenta(cuenta_id).nombre)}**: "
                    + ", ".join(f"{n} {t.lower() if n == 1 else PLURALES.get(t, t.lower())}"
                                for t, n in tipos.most_common()) + ".")
    if (ya := vista.contar(importacion.YA_ESTABA)):
        st.caption(f"{ya} movimiento(s) idénticos a uno que ya está en TALLY no se duplican.")
    problemas = vista.errores + [f"Renglón {f.numero} ({f.descripcion}): {f.detalle}" for f in vista.filas
                                 if f.estado == importacion.ERROR]
    if problemas:
        st.error("No se puede cargar mientras haya errores (no se carga nada a medias):\n\n"
                 + "\n".join(f"- {formato.md(p)}" for p in problemas[:20]))
    if st.button(f"Importar {len(nuevos)} movimiento(s)", type="primary", key="banco_importar",
                 disabled=not vista.se_puede_cargar, icon=":material/download_done:"):
        try:
            respaldo = respaldos.de_seguridad(sesion(), "antes_de_importar_del_banco")
        except (ErrorTally, OSError) as error:
            st.error(f"No se cargó nada: no se pudo crear el respaldo previo ({error}).")
            return
        hecho = aplicar(lambda libro_: importacion.cargar(libro_, archivo, mapeo))
        if hecho is not None:
            st.session_state["_banco_version"] += 1
            st.session_state.pop("_banco_fuente", None)
            avisar(f"Se importaron {hecho.nuevos} movimiento(s). La próxima vez TALLY sugerirá lo mismo para "
                   f"descripciones iguales. Respaldo previo: {respaldo.name}")
            st.rerun()
