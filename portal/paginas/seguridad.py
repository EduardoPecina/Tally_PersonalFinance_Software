"""Configuración → Seguridad: poner, cambiar o quitar la contraseña de TALLY, paso a paso y sin sustos."""

from __future__ import annotations

import html
import tempfile
import urllib.parse
from datetime import date
from pathlib import Path

import streamlit as st

from motor import cifrado, respaldos, seguridad
from motor.errores import ErrorTally
from portal.componentes import candado, formato
from portal.componentes.sesion import avisar, sesion

PASO, CONTRASENA, PISTA, KIT = "_seg_paso", "_seg_contrasena", "_seg_pista", "_seg_kit"
OPCIONES_BLOQUEO = {5: "5 minutos", 10: "10 minutos", 15: "15 minutos", 30: "30 minutos", 60: "1 hora",
                    0: "Nunca (no lo recomiendo en una PC compartida)"}


def mostrar() -> None:
    config = candado.config()
    if config is None:
        _sin_contrasena()
    else:
        _con_contrasena(config)


# ------------------------------------------------------------ sin contraseña


def _sin_contrasena() -> None:
    st.subheader("Contraseña de TALLY")
    paso = st.session_state.get(PASO, 0)
    if paso == 0:
        _explicacion()
        if st.button("Establecer una contraseña para TALLY", type="primary", icon=":material/lock:"):
            st.session_state[PASO] = 1
            st.rerun()
        return
    st.progress(paso / 4, text=f"Paso {paso} de 4")
    {1: _paso_contrasena, 2: _paso_kit, 3: _paso_comprobar, 4: _paso_activar}[paso]()
    st.divider()
    if st.button("Cancelar (no se cambia nada)", key="seg_cancelar"):
        _limpiar()
        st.rerun()


def _explicacion() -> None:
    st.markdown(
        "Hoy **TALLY abre sin contraseña**. Si quieres, puedes ponerle una. Así funciona, explicado fácil:")
    a, b, c = st.columns(3)
    with a.container(border=True):
        st.markdown("#### 🔒 Tu candado\nTus datos se guardan **cifrados**: si alguien copia el archivo o tus "
                    "respaldos, solo ve letras sin sentido. Para entrar a TALLY escribes tu contraseña.")
    with b.container(border=True):
        st.markdown("#### 🔑 Tu llave de repuesto\nTALLY te da un **Kit de emergencia** con una llave. Si un día "
                    "olvidas tu contraseña, con esa llave entras y pones otra. **No pierdes nada.**")
    with c.container(border=True):
        st.markdown("#### 💾 Tus respaldos\nTambién salen cifrados, y se abren en **cualquier PC** con tu "
                    "contraseña o con tu llave. Si un día no te apetece, quitas la contraseña y todo vuelve a ser "
                    "como hoy.")
    st.info("**La única regla:** guarda bien tu Kit de emergencia. Si pierdes tu contraseña **y** tu Kit, nadie "
            "puede abrir tus datos (ni TALLY, ni un técnico). Por eso TALLY no te deja terminar hasta comprobar "
            "que lo guardaste.", icon="💡")
    st.caption("Son 4 pasos y toman unos 3 minutos: 1) tu contraseña, 2) guardar tu Kit, 3) comprobar, 4) activar. "
               "Antes de cambiar nada, TALLY hace un respaldo de tus datos.")


def _paso_contrasena() -> None:
    st.markdown("### 1. Elige tu contraseña")
    st.caption(f"Al menos {cifrado.MINIMO_CONTRASENA} caracteres. Lo mejor es una **frase** que recuerdes y nadie "
               "adivine, por ejemplo «mi perro come tacos los martes». Distingue mayúsculas y acentos.")
    with st.form("seg_contrasena", border=False):
        contrasena = st.text_input("Contraseña", type="password")
        otra_vez = st.text_input("Escríbela otra vez", type="password")
        pista = st.text_input("Pista (opcional)", max_chars=80,
                              help="Algo que te ayude a recordarla. ¡Ojo! La pista la puede ver cualquiera en la "
                                   "pantalla de entrada: que no revele tu contraseña.")
        if st.form_submit_button("Siguiente", type="primary"):
            try:
                cifrado.validar_contrasena(contrasena, otra_vez, pista)
            except ErrorTally as error:
                st.error(str(error))
                return
            st.session_state.update({CONTRASENA: contrasena, PISTA: pista.strip(), PASO: 2,
                                     KIT: st.session_state.get(KIT) or cifrado.nuevo_kit()})
            st.rerun()


def _paso_kit() -> None:
    kit = st.session_state[KIT]
    st.markdown("### 2. Guarda tu Kit de emergencia")
    st.markdown("Esta es tu **llave de repuesto**. Con ella entras si olvidas tu contraseña. **Guárdala en al "
                "menos dos lugares** (por ejemplo: descárgala y mándatela a tu correo, o imprímela).")
    st.code(kit, language=None)
    hoy = date.today()
    a, b, c = st.columns(3)
    a.download_button("Descargar mi Kit (.txt)", _kit_texto(kit, hoy), file_name="Kit de emergencia TALLY.txt",
                      mime="text/plain", icon=":material/download:", on_click="ignore", width="stretch")
    b.download_button("Versión para imprimir (.html)", _kit_html(kit, hoy), file_name="Kit de emergencia TALLY.html",
                      mime="text/html", icon=":material/print:", on_click="ignore", width="stretch",
                      help="Ábrelo y usa Imprimir (Ctrl + P) para tenerlo en papel.")
    asunto = urllib.parse.quote("Kit de emergencia TALLY")
    cuerpo = urllib.parse.quote(_kit_texto(kit, hoy))
    c.link_button("Mandármelo a mi correo", f"mailto:?subject={asunto}&body={cuerpo}", icon=":material/mail:",
                  width="stretch", help="Abre tu programa de correo con el Kit listo: envíatelo a ti mismo.")
    st.caption("También puedes tomarle una foto con tu celular. Quien tenga esta llave **y** tu archivo de TALLY "
               "podría abrir tus datos: guárdala donde solo tú tengas acceso.")
    listo = st.checkbox("Ya guardé mi Kit de emergencia en un lugar seguro", key="seg_kit_guardado")
    if st.button("Siguiente", type="primary", disabled=not listo, key="seg_kit_siguiente"):
        st.session_state[PASO] = 3
        st.rerun()


def _paso_comprobar() -> None:
    st.markdown("### 3. Comprobemos que todo está bien")
    st.caption("Así nos aseguramos de que guardaste tu llave y recuerdas tu contraseña **antes** de proteger "
               "nada. Copia la llave **desde donde la guardaste** (no desde la pantalla anterior).")
    with st.form("seg_comprobar", border=False):
        kit = st.text_input("Escribe la llave de tu Kit", placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
        contrasena = st.text_input("Escribe tu contraseña otra vez", type="password")
        if st.form_submit_button("Comprobar", type="primary"):
            try:
                if cifrado.normalizar_kit(kit) != cifrado.normalizar_kit(st.session_state[KIT]):
                    st.error("Esa llave no es la de tu Kit. Revisa dónde la guardaste: debe ser idéntica. Si la "
                             "perdiste, regresa al paso anterior con «Cancelar» y empieza de nuevo.")
                    return
            except ErrorTally as error:
                st.error(str(error))
                return
            if contrasena.strip() != st.session_state[CONTRASENA].strip():
                st.error("Esa no es la contraseña que elegiste en el paso 1.")
                return
            st.session_state[PASO] = 4
            st.rerun()


def _paso_activar() -> None:
    st.markdown("### 4. ¡Todo listo para activar!")
    st.success("✅ Tu contraseña está elegida  \n✅ Tu Kit está guardado y comprobado", icon="🎉")
    st.markdown("Al presionar el botón, TALLY:\n"
                "1. Hace un **respaldo de seguridad** de tus datos.\n"
                "2. **Cifra** tus datos y tus respaldos guardados.\n"
                "3. **Comprueba** que todo quedó idéntico (si no, lo deshace solo).\n\n"
                "Después, cada vez que abras TALLY te pedirá tu contraseña.")
    with st.expander("Opcional: una copia sin contraseña para tu USB"):
        st.caption("Si quieres una red de seguridad extra, descarga una copia **sin contraseña** y guárdala en una "
                   "USB en tu casa. Ojo: quien tenga esa USB puede ver tus datos.")
        from portal.componentes import respaldo

        respaldo.boton_descargar("seg_copia", principal=False)
    if st.button("Poner la contraseña", type="primary", icon=":material/lock:", key="seg_activar"):
        with st.spinner("Protegiendo tus datos… no cierres TALLY"):
            try:
                resultado = seguridad.activar(sesion(), st.session_state[CONTRASENA], st.session_state[CONTRASENA],
                                              st.session_state[KIT], st.session_state[KIT],
                                              pista=st.session_state.get(PISTA, ""))
            except ErrorTally as error:
                st.error(f"No se activó la contraseña y tus datos siguen como estaban: {error}")
                return
        llave = sesion().almacen.llave
        _limpiar()
        candado.refrescar()
        candado.entrar(llave)
        aviso = "¡Listo! TALLY ya tiene contraseña."
        if resultado.respaldos_convertidos:
            aviso += f" También se cifraron {resultado.respaldos_convertidos} respaldo(s) guardados."
        avisar(aviso, "🔒")
        if resultado.respaldos_con_problemas:
            avisar("No se pudieron cifrar algunos respaldos (quizá dañados): " +
                   ", ".join(resultado.respaldos_con_problemas), "⚠️")
        st.rerun()


def _limpiar() -> None:
    for clave in (PASO, CONTRASENA, PISTA, KIT, "seg_kit_guardado"):
        st.session_state.pop(clave, None)


# ------------------------------------------------------------ con contraseña


def _con_contrasena(config: cifrado.Config) -> None:
    st.subheader("Contraseña de TALLY")
    st.success(f"🔒 Tus datos tienen contraseña desde el {cifrado._fecha(config.creado)}. Tu Kit de emergencia es "
               f"del {cifrado._fecha(config.kit_creado)} y su llave termina en **…{config.kit_final}**.")
    if config.recordatorio_kit(date.today()):
        st.warning("Hace tiempo que no compruebas tu Kit de emergencia. Pruébalo abajo: toma 10 segundos.", icon="🔑")

    bloqueo, kit, cambiar, copia, quitar = st.tabs(["Bloqueo automático", "Comprobar mi Kit", "Cambiar contraseña",
                                                    "Copia sin contraseña", "Quitar la contraseña"])
    with bloqueo:
        _bloqueo(config)
    with kit:
        _comprobar_kit()
    with cambiar:
        _cambiar(config)
    with copia:
        _copia_sin_contrasena()
    with quitar:
        _quitar()


def _bloqueo(config: cifrado.Config) -> None:
    st.caption("Si dejas TALLY abierto sin usarlo, se cierra solo y pide tu contraseña otra vez. También puedes "
               "usar «Bloquear ahora» en el menú de la izquierda.")
    claves = list(OPCIONES_BLOQUEO)
    actual = config.bloqueo_minutos if config.bloqueo_minutos in claves else 10
    elegido = st.selectbox("Bloquear después de", claves, format_func=OPCIONES_BLOQUEO.get,
                           index=claves.index(actual), key="seg_bloqueo")
    if elegido != config.bloqueo_minutos:
        try:
            seguridad.ajustar_bloqueo(sesion(), elegido)
        except ErrorTally as error:
            st.error(str(error))
            return
        candado.refrescar()
        avisar("Bloqueo automático guardado", "🔒")
        st.rerun()


def _comprobar_kit() -> None:
    st.caption("Escribe la llave de tu Kit para confirmar que aún la tienes. No cambia nada.")
    with st.form("seg_probar_kit", clear_on_submit=True, border=False):
        kit = st.text_input("Llave de tu Kit", placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
        if st.form_submit_button("Comprobar"):
            try:
                bien = seguridad.comprobar_kit(sesion(), kit)
            except ErrorTally as error:
                st.error(str(error))
                return
            candado.refrescar()
            if bien:
                st.success("¡Perfecto! Tu Kit abre tus datos. Guárdalo donde está.", icon="✅")
            else:
                st.error("Esa llave no abre tus datos. Busca tu Kit original (termina en …"
                         f"{candado.config().kit_final}) y vuelve a intentar.")


def _cambiar(config: cifrado.Config) -> None:
    st.caption("Tu Kit de emergencia **no cambia**: sigue abriendo tus datos y todos tus respaldos.")
    with st.form("seg_cambiar", clear_on_submit=True, border=False):
        actual = st.text_input("Contraseña actual (o la llave de tu Kit)", type="password")
        nueva = st.text_input("Contraseña nueva", type="password")
        otra_vez = st.text_input("Escríbela otra vez", type="password")
        pista = st.text_input("Pista (opcional)", value=config.pista, max_chars=80)
        if st.form_submit_button("Cambiar contraseña", type="primary"):
            try:
                seguridad.cambiar_contrasena(sesion(), actual, nueva, otra_vez, pista=pista)
            except ErrorTally as error:
                st.error(str(error))
                return
            candado.refrescar()
            avisar("Contraseña cambiada. Tu Kit de emergencia sigue siendo el mismo.", "🔑")
            st.rerun()


def _copia_sin_contrasena() -> None:
    st.caption("Un respaldo **sin cifrar**, para guardarlo en una USB en tu casa o abrirlo con otro programa. "
               "**Cuidado:** quien tenga este archivo puede ver tus datos.")
    entiendo = st.checkbox("Entiendo que esta copia no tendrá contraseña", key="seg_entiendo_copia")
    if entiendo:
        actual = sesion()

        def contenido() -> bytes:
            with tempfile.TemporaryDirectory() as temporal:
                return respaldos.crear(actual, Path(temporal), prefijo="sin_contrasena",
                                       sin_contrasena=True).read_bytes()

        st.download_button("Descargar copia sin contraseña", contenido,
                           file_name=f"TALLY_sin_contrasena_{actual.libro.ahora():%Y-%m-%d_%H%M%S}.zip",
                           mime="application/zip", icon=":material/download:", on_click="ignore")


def _quitar() -> None:
    st.markdown("Tus datos y tus respaldos guardados vuelven a quedar **sin cifrar**, como antes de poner la "
                "contraseña, y TALLY ya no la pedirá al abrir.")
    st.caption("Los respaldos cifrados que tengas fuera de la carpeta de TALLY (en una USB, en tu correo) se siguen "
               "abriendo con tu contraseña de ese día o con tu Kit: no lo tires.")
    with st.form("seg_quitar", border=False):
        contrasena = st.text_input("Escribe tu contraseña (o la llave de tu Kit)", type="password")
        seguro = st.checkbox("Sí, quiero quitar la contraseña")
        if st.form_submit_button("Quitar la contraseña", disabled=False):
            if not seguro:
                st.error("Marca la casilla para confirmar.")
                return
            with st.spinner("Quitando la contraseña…"):
                try:
                    resultado = seguridad.desactivar(sesion(), contrasena)
                except ErrorTally as error:
                    st.error(f"No se quitó la contraseña: {error}")
                    return
            candado.refrescar()
            candado.bloquear()             # se reabre sin llave
            avisar(f"Listo: TALLY ya no tiene contraseña ({resultado.respaldos_convertidos} respaldo(s) sin cifrar).",
                   "🔓")
            st.rerun()


# --------------------------------------------------------------------- el Kit


def _kit_texto(kit: str, hoy: date) -> str:
    return (
        "KIT DE EMERGENCIA DE TALLY\n"
        "==========================\n\n"
        f"Tu llave de recuperación:\n\n    {kit}\n\n"
        f"Creado el {formato.fecha(hoy)}.\n\n"
        "¿Para qué sirve?\n"
        "Si olvidas tu contraseña de TALLY, con esta llave entras y pones una nueva. No pierdes nada.\n"
        "También abre todos tus respaldos de TALLY en cualquier PC.\n\n"
        "¿Cómo se usa?\n"
        "1. Abre TALLY. En la pantalla de la contraseña, abre «¿Olvidaste tu contraseña?».\n"
        "2. Escribe esta llave (con o sin guiones, en mayúsculas o minúsculas).\n"
        "3. Elige una contraseña nueva. ¡Listo!\n\n"
        "Guárdala en un lugar seguro y privado. Quien tenga esta llave y tu archivo de TALLY podría abrir tus datos.\n"
        "Esta llave no cambia aunque cambies tu contraseña.\n"
    )


def _kit_html(kit: str, hoy: date) -> str:
    llave = html.escape(kit)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Kit de emergencia de TALLY</title>
<style>
 body {{font-family: Segoe UI, Arial, sans-serif; max-width: 680px; margin: 40px auto; color: #222; padding: 0 16px}}
 h1 {{font-size: 26px; margin-bottom: 4px}} .sub {{color: #666; margin-top: 0}}
 .llave {{font-family: Consolas, monospace; font-size: 30px; letter-spacing: 2px; border: 3px solid #6B53F1;
          border-radius: 12px; padding: 18px; text-align: center; margin: 24px 0}}
 li {{margin-bottom: 6px}} .aviso {{background: #FFF6DB; border-radius: 8px; padding: 12px 16px}}
</style></head><body>
<h1>🔑 Kit de emergencia de TALLY</h1>
<p class="sub">Creado el {formato.fecha(hoy)} · guárdalo en un lugar seguro</p>
<div class="llave">{llave}</div>
<h3>¿Para qué sirve?</h3>
<p>Si olvidas tu contraseña de TALLY, con esta llave entras y pones una nueva. <b>No pierdes nada.</b> También abre
todos tus respaldos de TALLY en cualquier computadora.</p>
<h3>¿Cómo se usa?</h3>
<ol><li>Abre TALLY. En la pantalla de la contraseña, abre <b>«¿Olvidaste tu contraseña?»</b>.</li>
<li>Escribe esta llave (con o sin guiones, en mayúsculas o minúsculas).</li>
<li>Elige una contraseña nueva. ¡Listo!</li></ol>
<p class="aviso">Quien tenga esta llave <b>y</b> tu archivo de TALLY podría abrir tus datos. Guárdala donde solo
tú tengas acceso. Esta llave no cambia aunque cambies tu contraseña.</p>
</body></html>"""
