"""⚙️ Configuración: tu nombre, respaldos, cómo se ve el Resumen y datos de esta instalación."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from decimal import Decimal

import streamlit as st

from motor import copia_externa, monedas, perfil, reportes, rutas
from motor.config import LEMA, MAC, VERSION
from motor.errores import ErrorTally
from motor.perfil import MAXIMO_RESPALDOS
from portal import accesos
from portal.componentes import candado, carpetas, formato, respaldo
from portal.componentes.sesion import avisar, ejecutar, libro, sesion
from portal.navegacion import enlace


def _perfil() -> None:
    actual = libro().perfil
    st.subheader("Tu nombre")
    st.caption("Así te saluda TALLY. Puede ser tu nombre o un apodo.")
    with st.form("configuracion_perfil", border=False):
        nombre = st.text_input("Nombre", value=actual.nombre, max_chars=60)
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: perfil.ajustar(lib, nombre=nombre), exito=f"¡Listo, {nombre.strip()}!"):
                st.rerun()


def _moneda() -> None:
    actual = libro().perfil
    st.subheader("Tu moneda")
    st.caption("TALLY muestra todos tus importes con el símbolo y el formato de tu moneda. En Inversiones, es contra "
               "la que se calcula el tipo de cambio.")
    codigos = list(monedas.MONEDAS)
    with st.form("configuracion_moneda", border=False):
        elegida = st.selectbox("Moneda", codigos, index=codigos.index(monedas.de(libro())),
                               format_func=lambda c: f"{monedas.MONEDAS[c].etiqueta} · {monedas.MONEDAS[c].ejemplo}")
        st.caption("⚠️ Cambiarla **no convierte** tus importes (no es un tipo de cambio): solo cambia cómo se ven. "
                   "Elígela al empezar.")
        if st.form_submit_button("Guardar", type="primary"):
            if elegida == actual.moneda:
                st.info("Ya es tu moneda.")
            elif ejecutar(lambda lib: perfil.ajustar(lib, moneda=elegida),
                          exito=f"Ahora ves todo en {monedas.MONEDAS[elegida].nombre.lower()}"):
                st.rerun()


def _impuestos() -> None:
    actual = libro().perfil
    st.subheader("IVA de tu país")
    st.caption("El IVA que tu banco cobra sobre los intereses de tarjetas y préstamos. En México es 16 %; en muchos "
               "países los intereses no llevan IVA: revisa tu estado de cuenta y, si no aparece, pon 0. TALLY lo usa "
               "para estimar intereses, pagos mínimos y tablas de préstamos.")
    with st.form("configuracion_iva", border=False):
        iva = st.number_input("IVA / VAT (%)", min_value=0.0, max_value=50.0, value=float(actual.iva), step=1.0,
                              format="%.2f")
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: perfil.ajustar(lib, iva=Decimal(str(iva))), exito="IVA guardado"):
                st.rerun()


def _respaldos() -> None:
    actual = libro().perfil
    st.subheader("Respaldo para llevar")
    st.caption("Tu información completa en un archivo .zip. Si cambias de PC o empiezas de cero, súbelo en la "
               "bienvenida («Ya usaba TALLY») o en Respaldos → Restaurar.")
    respaldo.boton_descargar("configuracion")

    st.subheader("Respaldo automático")
    with st.form("configuracion_respaldos", border=False):
        diario = st.toggle("Hacer un respaldo automático al abrir TALLY (uno por día)", value=actual.respaldo_diario)
        conservar = st.number_input("Cuántos respaldos automáticos conservar", min_value=1, max_value=MAXIMO_RESPALDOS,
                                    value=actual.respaldos_a_conservar, step=1,
                                    help="Los más viejos se borran solos. Los que descargas o creas tú no se tocan.")
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: perfil.ajustar(lib, respaldo_diario=diario, respaldos_a_conservar=int(conservar)),
                        exito="Respaldo automático actualizado"):
                st.rerun()
    st.caption(f"Se guardan en **{rutas.carpeta_respaldos()}** (solo en esta PC).")
    enlace("respaldos", "Restaurar un respaldo o empezar de cero", "💾")
    st.divider()
    _copia_externa()


CARPETA = "copia_carpeta"
SIN_VENTANA = "_copia_sin_ventana"
RELEER = "_copia_releer"                      # tras guardar, la caja muestra la ruta como quedó
CUANDO = {"diaria": "Se copia una vez al día", "semanal": "Se copia una vez por semana",
          "mensual": "Se copia una vez al mes"}


def _texto(mensaje: str) -> str:
    """Un mensaje con rutas de Windows para Markdown: ``\\\\MiNAS\\Respaldos`` se ve tal cual."""
    return formato.md(mensaje.replace("\\", "\\\\"))


def _elegir_carpeta() -> None:
    elegida = carpetas.elegir_carpeta("Elige dónde guardar las copias de TALLY", st.session_state.get(CARPETA, ""))
    if elegida is None:
        st.session_state[SIN_VENTANA] = True
    elif elegida:
        st.session_state[CARPETA] = elegida


def _copia_externa() -> None:
    ruta = sesion().almacen.ruta
    actual = copia_externa.leer(ruta)
    st.subheader("Copia en tu NAS o disco externo")
    st.caption("Además de los respaldos de esta PC, TALLY puede dejar una copia en otra carpeta: tu NAS, un disco "
               "externo o una USB. Si a tu PC le pasa algo, ahí la tienes. Nada sale a internet: es una carpeta de "
               "tu casa.")
    if st.session_state.pop(RELEER, False) or CARPETA not in st.session_state:
        st.session_state[CARPETA] = actual.carpeta
    texto, boton = st.columns([4, 1], vertical_alignment="bottom")
    if MAC:
        ejemplo, ayuda = "/Volumes/MiNAS/Respaldos", ("Elígela con el botón o pega la ruta. Tu NAS aparece cuando lo "
                                                      "conectas en Finder (Ir → Conectarse al servidor). Déjala vacía "
                                                      "para ya no copiar.")
    else:
        ejemplo, ayuda = "\\\\MiNAS\\Respaldos   o   E:\\Respaldos TALLY", (
            "Elígela con el botón o pega la ruta. Si tu NAS no aparece en la ventana, conéctalo como unidad en Windows "
            "(Z:) o pega su ruta, como `\\\\MiNAS\\Carpeta`. Déjala vacía para ya no copiar.")
    texto.text_input("Carpeta", key=CARPETA, placeholder=ejemplo, help=ayuda)
    boton.button("Elegir carpeta…", icon=":material/folder_open:", width="stretch", on_click=_elegir_carpeta,
                 key="copia_elegir",
                 help=f"Abre la ventana {'de la Mac' if MAC else 'de Windows'} para escoger la carpeta.")
    if st.session_state.pop(SIN_VENTANA, False):
        st.warning("No se pudo abrir la ventana para elegir la carpeta. Escribe o pega su ruta.", icon="📁")
    frecuencia = st.segmented_control(
        "¿Cada cuánto?", list(copia_externa.FRECUENCIAS), format_func=copia_externa.FRECUENCIAS.get,
        default=actual.frecuencia, required=True, key="copia_frecuencia")
    if frecuencia == "nunca":
        st.caption("Solo se copia cuando le das «Copiar ahora».")
    else:
        st.caption(f"{CUANDO[frecuencia]}, al cerrar TALLY (o al abrirlo, si quedó pendiente) y solo si cambiaste algo "
                   "desde la última copia.")
    conservar = st.number_input("Cuántas copias conservar", min_value=1, max_value=copia_externa.MAXIMO_CONSERVAR,
                                value=actual.conservar, step=1, key="copia_conservar",
                                help="Las más viejas se borran solas, pero solo cuando la nueva ya quedó completa y "
                                     "revisada. Más de una te protege si un error tuyo alcanza a copiarse.")
    escrita = copia_externa.normalizar(st.session_state.get(CARPETA, ""))
    guardar, probar, copiar = st.columns(3)
    if guardar.button("Guardar", type="primary", width="stretch", key="copia_guardar"):
        with st.spinner("Revisando la carpeta…"):
            try:
                nueva = copia_externa.configurar(ruta, escrita, frecuencia, int(conservar))
            except ErrorTally as error:
                st.error(_texto(str(error)))
            else:
                st.session_state[RELEER] = True
                avisar("Listo: TALLY copiará tus respaldos ahí" if nueva.activa else "Ya no se copia a otra carpeta")
                st.rerun()
    if probar.button("Probar la carpeta", width="stretch", key="copia_probar", disabled=not escrita):
        with st.spinner("Revisando la carpeta…"):
            try:
                copia_externa.probar(escrita)
            except ErrorTally as error:
                st.error(_texto(str(error)))
            else:
                st.success("Listo: TALLY puede guardar en esta carpeta.", icon="✅")
    pendiente = escrita != actual.carpeta
    if copiar.button("Copiar ahora", icon=":material/backup:", width="stretch", key="copia_ahora",
                     disabled=not actual.activa or pendiente,
                     help="Primero guarda la carpeta." if pendiente else "Hace una copia en este momento."):
        with st.spinner("Copiando… en un NAS puede tardar unos segundos."):
            try:
                hecha = copia_externa.copiar(ruta, datetime.now())
            except ErrorTally as error:
                st.error(_texto(str(error)))
            else:
                avisar(f"Copia lista: {hecha.name}")
                st.rerun()
    _estado_de_la_copia(copia_externa.leer(ruta))


def _estado_de_la_copia(c: copia_externa.Copia) -> None:
    if not c.activa:
        return
    hoy = datetime.now().date()
    if c.error and c.intento is not None:
        st.warning(f"No se pudo hacer la última copia ({formato.cuando(c.intento, hoy)}): {_texto(c.error)}",
                   icon="⚠️")
    if c.ultima is not None:
        st.caption(f"✅ Última copia: {formato.cuando(c.ultima, hoy)} · {c.archivo}")
    elif not c.error:
        st.caption("Todavía no hay ninguna copia: se hará la próxima vez que cierres TALLY, o dale «Copiar ahora».")
    if candado.config() is not None:
        st.caption("🔒 Las copias van cifradas con tu contraseña, igual que tus respaldos.")
    else:
        st.caption("⚠️ Tus datos no tienen contraseña: quien pueda abrir esa carpeta podría leer tus finanzas. Si "
                   "otras personas usan tu NAS, ponle contraseña a TALLY en la pestaña **Seguridad**; las copias que "
                   "ya estaban siguen sin ella hasta que se reemplacen (o bórralas del NAS).")


def _apariencia() -> None:
    actual = libro().perfil
    st.subheader("Tema")
    st.caption("El tema oscuro descansa la vista de noche o si te cansa el blanco (como Dark Reader).")
    temas = list(perfil.TEMAS)
    elegido = st.radio("Tema", temas, format_func=perfil.TEMAS.get, index=temas.index(actual.tema), horizontal=True,
                       key="configuracion_tema", label_visibility="collapsed")
    if elegido != actual.tema and ejecutar(lambda lib: perfil.ajustar(lib, tema=elegido), exito="Tema cambiado"):
        st.rerun()

    st.subheader("Ícono de TALLY")
    st.caption("El color del ícono de la app TALLY (en Aplicaciones y en el Dock) y de la pestaña del navegador."
               if MAC else "El color del ícono del acceso directo del Escritorio y de la pestaña del navegador.")
    columnas = st.columns(len(perfil.ICONOS))
    for columna, (variante, nombre) in zip(columnas, perfil.ICONOS.items()):
        with columna, st.container(border=True):
            st.image(str(accesos.imagen_pestana(variante)), width=56)
            en_uso = variante == actual.icono
            if st.button("En uso ✓" if en_uso else f"Usar {nombre.lower()}", disabled=en_uso,
                         key=f"configuracion_icono_{variante}", width="stretch"):
                if ejecutar(lambda lib: perfil.ajustar(lib, icono=variante)):
                    cambiados, mensaje = accesos.cambiar_icono(variante)
                    avisar(mensaje, "✅" if cambiados else "ℹ️")
                    st.rerun()


def _resumen() -> None:
    actual = libro().perfil
    st.subheader("Resumen")
    with st.form("configuracion_resumen", border=False):
        periodos = list(reportes.PERIODOS)
        periodo = st.selectbox("Periodo que se muestra al abrir", periodos, format_func=reportes.PERIODOS.get,
                               index=periodos.index(actual.periodo_inicial) if actual.periodo_inicial in periodos else 0)
        dias = st.number_input("Avisarme de un cargo temporal sin devolver después de (días)", min_value=1,
                               max_value=perfil.MAXIMO_DIAS_PARA_RECLAMAR, value=actual.dias_para_reclamar, step=1,
                               help="Cargos temporales: lo que te cobran para verificar tu tarjeta y te devuelven "
                                    "después. Pasado este plazo, el Resumen te avisa para que lo reclames.")
        if st.form_submit_button("Guardar", type="primary"):
            if ejecutar(lambda lib: perfil.ajustar(lib, periodo_inicial=periodo, dias_para_reclamar=int(dias)),
                        exito="Preferencia guardada"):
                st.session_state.pop("_mem_inicio", None)          # el Resumen toma el nuevo periodo
                st.session_state.pop("_w_inicio_periodo", None)
                st.rerun()


def _acerca() -> None:
    lib = libro()
    ruta = sesion().almacen.ruta
    st.subheader("Esta instalación")
    tamano = ruta.stat().st_size / 1024 if ruta.exists() else 0
    st.markdown(
        f"- **TALLY {VERSION}** · *{LEMA}* · software libre (licencia MIT).\n"
        f"- Tus datos: `{ruta}` ({tamano:,.0f} KB) · {len(lib.cuentas())} cuenta(s), "
        f"{len(lib.operaciones())} movimiento(s).\n"
        f"- Usuario desde el {lib.perfil.creado_en:%d/%m/%Y}.\n"
        "- Nada sale de esta PC: sin nube, sin bancos conectados, sin telemetría. La única excepción es opcional: "
        "«Consultar valor aproximado actual» en una cuenta de inversión envía solo el símbolo del título "
        "(p. ej. IVVPESO.MX), y solo cuando lo aprietas."
    )
    if sys.platform in ("win32", "darwin") and st.button("Abrir la carpeta de mis datos",
                                                         icon=":material/folder_open:"):
        if sys.platform == "win32":
            os.startfile(rutas.carpeta_usuario())  # noqa: S606 - abre el Explorador en la carpeta local del usuario
        else:
            subprocess.Popen(["open", str(rutas.carpeta_usuario())])   # Finder, en la carpeta de tus datos
    enlace("cargar", "Cargar datos desde Excel", "📥")
    enlace("categorias", "Categorías y subcategorías", "🏷️")


def mostrar() -> None:
    st.title("Configuración")
    tu, seguridad_tab, apariencia, respaldos, resumen, acerca = st.tabs(
        ["Tu perfil", "Seguridad", "Apariencia", "Respaldos", "Resumen", "Acerca de TALLY"])
    with seguridad_tab:
        from portal.paginas import seguridad

        seguridad.mostrar()
    with tu:
        _perfil()
        st.divider()
        _moneda()
        st.divider()
        _impuestos()
    with apariencia:
        _apariencia()
    with respaldos:
        _respaldos()
    with resumen:
        _resumen()
    with acerca:
        _acerca()
