"""¿Cuánto tengo en cada cuenta? Crear, editar, actualizar saldo y archivar cuentas."""

from __future__ import annotations

import streamlit as st

from motor import categorias, cuentas, movimientos, tarjetas
from motor.consultas import ETIQUETA_TIPO_CUENTA
from motor.modelo import TIPOS_DISPONIBLES_POR_DEFECTO, Cuenta, TipoCuenta
from portal.componentes import formato
from portal.componentes import tarjeta as estado_tarjeta
from portal.componentes.sesion import aplicar, avisar, ejecutar, libro

TIPOS = list(TipoCuenta)
SIN_CAMBIOS = "sin cambios"


def _etiqueta_tipo(tipo: TipoCuenta) -> str:
    return ETIQUETA_TIPO_CUENTA[TipoCuenta(tipo)]


MODO_FIJO, MODO_DIAS, MODO_NINGUNO = "fijo", "dias", "ninguno"
MODOS_PAGO = {
    MODO_DIAS: "N días después del corte",
    MODO_FIJO: "Un día fijo del mes",
    MODO_NINGUNO: "No lo sé / después",
}


def _elegir_modo_pago(clave: str, cuenta: Cuenta | None = None) -> str:
    """Cómo se calcula la fecha límite de pago (va fuera del formulario para que cambie los campos al momento)."""
    if cuenta is None:
        inicial = MODO_DIAS
    elif cuenta.dias_para_pagar is not None:
        inicial = MODO_DIAS
    elif cuenta.dia_pago is not None:
        inicial = MODO_FIJO
    else:
        inicial = MODO_NINGUNO
    return st.radio(
        "Fecha límite de pago", list(MODOS_PAGO), format_func=MODOS_PAGO.get, horizontal=True,
        index=list(MODOS_PAGO).index(inicial), key=clave,
        help="Búscalo en tu contrato o estado de cuenta. Ej.: «hasta 10 días naturales contados a partir de la "
             "fecha de corte» o «el día 23 de cada mes».",
    )


def _campos_regla_pago(modo: str, izquierda, derecha, cuenta: Cuenta | None = None) -> dict:
    """Campos de la regla de pago dentro del formulario. Devuelve los argumentos para el motor."""
    if modo == MODO_NINGUNO:
        return {"dia_pago": None, "dias_para_pagar": None}
    if modo == MODO_FIJO:
        regla = {"dias_para_pagar": None, "dia_pago": derecha.number_input(
            "Día de pago", min_value=1, max_value=31, step=1, value=cuenta.dia_pago if cuenta else None)}
    else:
        regla = {"dia_pago": None, "dias_para_pagar": derecha.number_input(
            "Días para pagar después del corte", min_value=1, max_value=60, step=1,
            value=(cuenta.dias_para_pagar if cuenta and cuenta.dias_para_pagar else 10)),
            "dias_habiles": izquierda.checkbox(
                "Contar solo días hábiles", value=bool(cuenta and cuenta.dias_habiles),
                help="Déjalo sin marcar si tu contrato dice «días naturales».")}
    regla["recorrer_inhabil"] = st.checkbox(
        "Si la fecha cae en fin de semana o día inhábil, se recorre al siguiente día hábil",
        value=cuenta.recorrer_inhabil if cuenta else True,
        help="Así lo dicen la mayoría de los contratos. Se usa el calendario de días inhábiles bancarios.")
    return regla


def formulario_nueva_cuenta(clave: str = "cuentas") -> None:
    """Formulario para crear una cuenta (se usa también en la bienvenida)."""
    tipo = st.selectbox("Tipo de cuenta", TIPOS, format_func=_etiqueta_tipo, key=f"{clave}_tipo_nueva")
    es_credito = tipo is TipoCuenta.CREDITO
    modo_pago = _elegir_modo_pago(f"{clave}_modo_pago") if es_credito else MODO_NINGUNO
    with st.form(f"{clave}_nueva_cuenta", clear_on_submit=True, border=False):
        izquierda, derecha = st.columns(2)
        nombre = izquierda.text_input("Nombre", placeholder="Ej. BBVA Débito, Mercado Pago, TDC Nu", max_chars=60)
        institucion = derecha.text_input("Banco o institución (opcional)", max_chars=60)
        datos: dict = {}
        if es_credito:
            datos["deuda_inicial"] = izquierda.number_input(
                "¿Cuánto debes hoy?", min_value=0.0, value=0.0, step=100.0, format="%.2f")
            datos["limite_credito"] = derecha.number_input(
                "Límite de crédito (opcional)", min_value=0.0, value=None, step=500.0, format="%.2f")
            datos["dia_corte"] = izquierda.number_input(
                "Día de corte (opcional)", min_value=1, max_value=31, value=None, step=1,
                help="El último día de cada ciclo de la tarjeta.")
            datos.update(_campos_regla_pago(modo_pago, izquierda, derecha))
        else:
            datos["saldo_inicial"] = izquierda.number_input(
                "¿Cuánto tienes hoy en esta cuenta?", value=0.0, step=100.0, format="%.2f")
        fecha_saldo = derecha.date_input(
            "Fecha de ese saldo", value=libro().hoy(), format="DD/MM/YYYY",
            help="Registra en TALLY solo los movimientos posteriores a esta fecha: "
                 "los anteriores ya están incluidos en el saldo.",
        )
        en_disponible = st.checkbox(
            "Cuenta como dinero disponible", value=tipo in TIPOS_DISPONIBLES_POR_DEFECTO,
            help="Dinero que puedes usar ya mismo (normalmente débito y efectivo).",
        )
        if st.form_submit_button("Agregar cuenta", type="primary"):
            if datos.get("limite_credito") == 0:
                datos["limite_credito"] = None
            datos.update(institucion=institucion, fecha_saldo_inicial=fecha_saldo, fecha_creacion=fecha_saldo,
                         en_disponible=en_disponible)
            if ejecutar(lambda lib: cuentas.crear(lib, nombre, tipo, **datos),
                        exito=f"Cuenta «{nombre.strip()}» agregada"):
                st.rerun()


def _tarjeta_de_cuenta(cuenta: Cuenta) -> None:
    lib = libro()
    saldo = cuentas.saldo(lib, cuenta.id)
    with st.container(border=True):
        izquierda, derecha = st.columns([3, 2])
        detalle = _etiqueta_tipo(cuenta.tipo) + (f" · {cuenta.institucion}" if cuenta.institucion else "")
        if not cuenta.activa:
            detalle += " · archivada"
        izquierda.markdown(f"**{cuenta.nombre}**  \n:gray[{detalle}]")
        if cuenta.tipo is not TipoCuenta.CREDITO:
            derecha.metric("Saldo", formato.dinero(saldo))
            return
        estado_tarjeta.mostrar(cuenta)


def _editar(cuenta: Cuenta) -> None:
    es_credito = cuenta.tipo is TipoCuenta.CREDITO
    modo_pago = _elegir_modo_pago(f"modo_pago_{cuenta.id}", cuenta) if es_credito else MODO_NINGUNO
    with st.form(f"editar_{cuenta.id}", border=False):
        izquierda, derecha = st.columns(2)
        nombre = izquierda.text_input("Nombre", value=cuenta.nombre, max_chars=60)
        institucion = derecha.text_input("Banco o institución", value=cuenta.institucion, max_chars=60)
        credito = {}
        if cuenta.tipo is TipoCuenta.CREDITO:
            limite = izquierda.number_input(
                "Límite de crédito", min_value=0.0, step=500.0, format="%.2f",
                value=cuenta.limite_credito / 100 if cuenta.limite_credito else None)
            credito = {
                "limite_credito": limite or None,
                "dia_corte": derecha.number_input("Día de corte", min_value=1, max_value=31, step=1,
                                                  value=cuenta.dia_corte),
                **_campos_regla_pago(modo_pago, izquierda, derecha, cuenta),
            }
        notas = st.text_area("Notas", value=cuenta.notas, height=80)
        en_disponible = st.checkbox("Cuenta como dinero disponible", value=cuenta.en_disponible)
        if st.form_submit_button("Guardar cambios", type="primary"):
            if ejecutar(lambda lib: cuentas.editar(lib, cuenta.id, nombre=nombre, institucion=institucion,
                                                   notas=notas, en_disponible=en_disponible, **credito),
                        exito="Cuenta actualizada"):
                st.rerun()


def _actualizar_saldo(cuenta: Cuenta) -> None:
    lib = libro()
    es_credito = cuenta.tipo is TipoCuenta.CREDITO
    st.caption(
        "Escribe lo que dice tu banco y TALLY registra la diferencia. Ideal para los intereses del ahorro: "
        "en lugar de anotarlos día por día, actualiza el saldo cada semana o cada mes."
    )
    razones = ["Intereses o rendimientos (cuenta como ingreso)", "Ajuste (no es ingreso ni gasto)"]
    de_ingreso = categorias.para_tipo(lib, "rendimiento")
    sugerida = next((i for i, c in enumerate(de_ingreso) if "inter" in c.nombre.casefold()), 0)
    with st.form(f"actualizar_{cuenta.id}", border=False):
        izquierda, derecha = st.columns(2)
        fecha = derecha.date_input("Fecha", value=lib.hoy(), format="DD/MM/YYYY")
        if es_credito:
            real = izquierda.number_input("Deuda que dice tu banco", min_value=0.0, step=100.0, format="%.2f",
                                          value=float(tarjetas.deuda(lib, cuenta.id)))
            razon = razones[1]
        else:
            real = izquierda.number_input("Saldo que dice tu banco", step=100.0, format="%.2f",
                                          value=float(cuentas.saldo(lib, cuenta.id)))
            razon = st.radio("¿Qué explica la diferencia?", razones)
            categoria = st.selectbox("Subcategoría del rendimiento", de_ingreso,
                                     format_func=lambda c: categorias.etiqueta(lib, c.id),
                                     index=sugerida if de_ingreso else None)
        if st.form_submit_button("Actualizar saldo", type="primary"):
            if es_credito:
                def accion(lib):
                    return tarjetas.actualizar_deuda(lib, cuenta.id, real, fecha) or SIN_CAMBIOS
            else:
                categoria_id = categoria.id if razon == razones[0] and categoria else None

                def accion(lib):
                    return movimientos.actualizar_saldo(lib, cuenta.id, real, fecha,
                                                        categoria_id=categoria_id) or SIN_CAMBIOS
            resultado = aplicar(accion)
            if resultado == SIN_CAMBIOS:
                st.info("El saldo ya coincidía: no hubo nada que registrar.")
            elif resultado is not None:
                avisar("Saldo actualizado")
                st.rerun()


def _saldo_inicial(cuenta: Cuenta) -> None:
    registrado = cuentas.saldo_inicial(libro(), cuenta.id)
    es_credito = cuenta.tipo is TipoCuenta.CREDITO
    st.caption("Lo que había en la cuenta cuando empezaste a usar TALLY. No cuenta como ingreso.")
    with st.form(f"inicial_{cuenta.id}", border=False):
        izquierda, derecha = st.columns(2)
        if es_credito:
            monto = izquierda.number_input("Deuda inicial", min_value=0.0, step=100.0, format="%.2f",
                                           value=float(cuentas.deuda_inicial(libro(), cuenta.id)))
        else:
            monto = izquierda.number_input("Saldo inicial", step=100.0, format="%.2f",
                                           value=float(registrado[0]) if registrado else 0.0)
        fecha = derecha.date_input("Fecha", value=registrado[1] if registrado else cuenta.fecha_creacion,
                                   format="DD/MM/YYYY")
        if st.form_submit_button("Guardar saldo inicial", type="primary"):
            cambiar = cuentas.cambiar_deuda_inicial if es_credito else cuentas.cambiar_saldo_inicial
            if ejecutar(lambda lib: cambiar(lib, cuenta.id, monto, fecha), exito="Saldo inicial actualizado"):
                st.rerun()


def _archivar_o_borrar(cuenta: Cuenta) -> None:
    if cuenta.activa:
        st.caption("Archivar oculta la cuenta para movimientos nuevos. Su historial y su saldo se conservan.")
        if st.button("Archivar cuenta", key=f"archivar_{cuenta.id}"):
            if ejecutar(lambda lib: cuentas.archivar(lib, cuenta.id), exito="Cuenta archivada"):
                st.rerun()
    elif st.button("Reactivar cuenta", key=f"reactivar_{cuenta.id}"):
        if ejecutar(lambda lib: cuentas.reactivar(lib, cuenta.id), exito="Cuenta reactivada"):
            st.rerun()
    if cuentas.tiene_movimientos(libro(), cuenta.id):
        st.caption("Esta cuenta tiene movimientos, así que no se puede borrar; puedes archivarla.")
        return
    confirmar = st.checkbox("Quiero borrar esta cuenta", key=f"confirmar_borrar_{cuenta.id}")
    if st.button("Borrar cuenta", key=f"borrar_{cuenta.id}", disabled=not confirmar):
        if ejecutar(lambda lib: cuentas.eliminar(lib, cuenta.id), exito="Cuenta borrada"):
            st.rerun()


def mostrar() -> None:
    st.title("Cuentas")
    st.caption("¿Cuánto tengo en cada cuenta?")

    with st.expander("➕ Nueva cuenta", expanded=not cuentas.listar(libro())):
        formulario_nueva_cuenta()

    archivadas = st.toggle("Mostrar archivadas", key="cuentas_mostrar_archivadas")
    lista = cuentas.listar(libro(), incluir_archivadas=archivadas)
    if not lista:
        st.info("Aún no tienes cuentas. Agrega la primera arriba.")
        return
    for tipo in TIPOS:
        del_tipo = [c for c in lista if c.tipo is tipo]
        if del_tipo:
            st.subheader("Tarjetas de crédito" if tipo is TipoCuenta.CREDITO else _etiqueta_tipo(tipo))
            for cuenta in del_tipo:
                _tarjeta_de_cuenta(cuenta)

    st.divider()
    st.subheader("Administrar una cuenta")
    ids = [c.id for c in lista]
    elegida = st.selectbox("Cuenta", ids, format_func=lambda i: libro().cuenta(i).nombre, key="cuentas_elegida")
    if elegida is None:
        return
    cuenta = libro().cuenta(elegida)
    editar, actualizar, inicial, mas = st.tabs(["Editar", "Actualizar saldo", "Saldo inicial", "Archivar o borrar"])
    with editar:
        _editar(cuenta)
    with actualizar:
        _actualizar_saldo(cuenta)
    with inicial:
        _saldo_inicial(cuenta)
    with mas:
        _archivar_o_borrar(cuenta)
