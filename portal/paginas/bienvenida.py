"""Primera vez: ¡Hola! Tu nombre y tus cuentas."""

from __future__ import annotations

import streamlit as st

from motor import cuentas, perfil, tarjetas
from motor.consultas import ETIQUETA_TIPO_CUENTA
from motor.modelo import TipoCuenta
from portal.componentes import formato, respaldo
from portal.componentes.sesion import ejecutar, libro
from portal.paginas.cuentas import formulario_nueva_cuenta


NUEVO, YA_USABA = "Soy nuevo", "Ya usaba TALLY: tengo un respaldo"


def _ya_usaba() -> None:
    st.subheader("Recupera tus datos")
    st.markdown(
        "Sube el respaldo que descargaste (**TALLY_respaldo_….zip**) y TALLY quedará exactamente como lo tenías: "
        "tu nombre, cuentas, movimientos, categorías y configuración.  \n"
        "¿No lo encuentras? En tu otra PC está en `C:\\Users\\<tu usuario>\\TALLY\\Respaldos` (si hiciste "
        "respaldos automáticos) o puedes usar directamente su archivo de datos, `…\\TALLY\\Datos\\tally.db`."
    )
    archivo = st.file_uploader("Tu respaldo (.zip) o archivo de datos (.db)", type=respaldo.TIPOS,
                               key="bienvenida_respaldo")
    if archivo is not None:
        respaldo.revisar_y_restaurar(respaldo.subido(archivo), "bienvenida", nombre=archivo.name,
                                     pedir_confirmacion=bool(cuentas.listar(libro())))


def mostrar() -> None:
    st.title("¡Hola! 👋")
    st.markdown(
        "Te damos la bienvenida a **TALLY**: tus finanzas, tus números, tu PC, tus datos.  \n"
        "Todo se guarda solo en esta computadora. No hay cuentas de usuario, ni nube, ni bancos conectados."
    )
    eleccion = st.segmented_control("¿Ya usabas TALLY?", [NUEVO, YA_USABA], default=NUEVO, required=True,
                                    key="bienvenida_eleccion")
    if eleccion == YA_USABA:
        _ya_usaba()
        return

    st.subheader("1. ¿Cómo te llamas?")
    nombre = st.text_input("Tu nombre", key="bienvenida_nombre", placeholder="Así te saludará TALLY",
                           max_chars=60)

    st.subheader("2. Agrega tus cuentas")
    st.caption(
        "Tarjetas de débito, tarjetas de crédito, ahorro, efectivo… Agrega todas las que quieras; "
        "también puedes hacerlo después desde **Cuentas**."
    )
    existentes = cuentas.listar(libro())
    if existentes:
        for cuenta in existentes:
            if cuenta.tipo is TipoCuenta.CREDITO:
                texto = f"Debes {formato.dinero_md(tarjetas.deuda(libro(), cuenta.id))}"
            else:
                texto = formato.dinero_md(cuentas.saldo(libro(), cuenta.id))
            st.markdown(f"- **{cuenta.nombre}** · {ETIQUETA_TIPO_CUENTA[cuenta.tipo]} · {texto}")
    with st.container(border=True):
        formulario_nueva_cuenta(clave="bienvenida")
    st.caption("¿Ya llevabas tus finanzas en Excel? Al terminar, ve a **Cargar datos**: con una plantilla subes "
               "todo tu historial de una vez (y TALLY crea las cuentas que falten).")

    st.subheader("3. ¡Listo!")
    if st.button("Empezar a usar TALLY", type="primary", disabled=not nombre.strip()):
        if ejecutar(lambda lib: perfil.configurar(lib, nombre), exito=f"¡Hola, {nombre.strip()}!"):
            st.rerun()
    if not nombre.strip():
        st.caption("Escribe tu nombre para continuar.")
