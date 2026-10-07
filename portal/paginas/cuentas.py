"""¿Cuánto tengo en cada cuenta? Crear, editar, actualizar saldo y eliminar cuentas (guardando su historial)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from motor import bienes, categorias, consultas, cuentas, movimientos, tarjetas
from motor.consultas import ETIQUETA_TIPO_CUENTA
from motor.modelo import TIPOS_DISPONIBLES_POR_DEFECTO, Cuenta, TipoCuenta
from portal.componentes import exportar, formato
from portal.componentes import tarjeta as estado_tarjeta
from portal.componentes.sesion import aplicar, avisar, ejecutar, libro
from portal.paginas import estado_cuenta

# Los bienes se agregan en Contabilidad Técnica y los préstamos en Deudas (necesitan sus datos).
TIPOS = [t for t in TipoCuenta if t not in (TipoCuenta.BIEN, TipoCuenta.PRESTAMO)]
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
            detalle += " · eliminada (su historial se conserva)"
        izquierda.markdown(f"**{cuenta.nombre}**  \n:gray[{detalle}]")
        ver, quitar = izquierda.columns(2)
        if ver.button("Ver movimientos", icon=":material/receipt_long:", key=f"ver_{cuenta.id}", width="stretch"):
            estado_cuenta.abrir(cuenta.id)
            st.rerun()
        if cuenta.activa:
            if quitar.button("Eliminar", icon=":material/delete:", key=f"eliminar_{cuenta.id}", width="stretch"):
                _dialogo_eliminar(cuenta.id)
        elif quitar.button("Restaurar", icon=":material/restore:", key=f"restaurar_{cuenta.id}", width="stretch"):
            if ejecutar(lambda lib: cuentas.reactivar(lib, cuenta.id), exito=f"«{cuenta.nombre}» restaurada"):
                st.rerun()
        if cuenta.tipo is TipoCuenta.BIEN and lib.bien(cuenta.id) is not None:
            valor = bienes.valuar(lib, cuenta.id, lib.hoy())
            derecha.metric("Valor hoy", formato.dinero(valor.valor),
                           help=f"Costo {formato.dinero(valor.costo)} − depreciación "
                                f"{formato.dinero(valor.depreciacion)} ± avalúos. Ajústalo en Contabilidad Técnica.")
            return
        if cuenta.tipo is TipoCuenta.PRESTAMO:
            derecha.metric("Debes", formato.dinero(max(-saldo, 0)), help="Sus pagos y simulaciones, en Deudas.")
            return
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
                "tasa_anual": izquierda.number_input(
                    "Tasa de interés anual (%) · opcional", min_value=0.0, max_value=1000.0, step=1.0,
                    format="%.2f", value=float(cuenta.tasa_anual) if cuenta.tasa_anual is not None else None,
                    help="La tasa ordinaria anual que dice tu contrato o estado de cuenta. Sirve para estimar "
                         "intereses y el pago mínimo."),
                "cat": derecha.number_input(
                    "CAT (%) · opcional", min_value=0.0, max_value=1000.0, step=1.0, format="%.2f",
                    value=float(cuenta.cat) if cuenta.cat is not None else None,
                    help="Costo Anual Total (México). En otros países: TAE (España), CAE (Chile), CFT (Argentina), "
                         "TEA (Perú, Colombia). Es informativo: los cálculos usan la tasa anual."),
                "tasa_incluye_iva": st.checkbox("La tasa ya incluye IVA", value=cuenta.tasa_incluye_iva,
                                                help="Si no lo incluye, TALLY le suma el IVA de tu país "
                                                     "(Configuración → Tu perfil)."),
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


def eliminar(cuenta: Cuenta, clave: str) -> None:
    """Eliminar una cuenta: si tiene movimientos se guarda su historial (archivada); si no, se borra."""
    lib = libro()
    if not cuenta.activa:
        st.info("Esta cuenta ya está eliminada; su historial se conserva.")
        if st.button("Restaurar cuenta", key=f"{clave}_restaurar"):
            if ejecutar(lambda lib: cuentas.reactivar(lib, cuenta.id), exito=f"«{cuenta.nombre}» restaurada"):
                st.rerun()
        return
    if not cuentas.tiene_movimientos(lib, cuenta.id):
        st.markdown(f"**{formato.md(cuenta.nombre)}** no tiene movimientos: se borrará por completo.")
    else:
        st.markdown(
            f"**{formato.md(cuenta.nombre)}** desaparecerá de tus cuentas y de los formularios, pero **su historial se "
            "guarda**: sus movimientos siguen en Historial, Tablas dinámicas y Gráficas. Si cambias de opinión, "
            "actívala de nuevo con «Mostrar eliminadas» → Restaurar.")
    saldo = cuentas.saldo(lib, cuenta.id)
    dejar_en_cero = False
    if saldo and cuentas.tiene_movimientos(lib, cuenta.id):
        es_credito = cuenta.tipo is TipoCuenta.CREDITO
        texto = (f"Todavía debes {formato.dinero_md(-saldo)} en esta tarjeta" if es_credito and saldo < 0
                 else f"Esta cuenta todavía tiene {formato.dinero_md(saldo)}")
        st.warning(f"{texto}. Si la eliminas así, ese saldo seguirá contando en tu patrimonio.", icon="⚠️")
        dejar_en_cero = st.checkbox(
            "Ya la pagué o la cancelé: dejar su saldo en cero", value=False, key=f"{clave}_cero",
            help="Registra un ajuste de saldo con fecha de hoy. Un ajuste no cuenta como ingreso ni como gasto. "
                 "Si todavía debes ese dinero, no lo marques.")
    if cuentas.tiene_movimientos(lib, cuenta.id):
        filas = consultas.movimientos_de_cuenta(lib, cuenta.id)
        st.download_button(
            "Descargar su historial a Excel (opcional)", on_click="ignore", key=f"{clave}_excel",
            data=exportar.excel({cuenta.nombre: pd.DataFrame({
                "Fecha": [f.fecha for f in filas], "Descripción": [f.descripcion for f in filas],
                "Subcategoría o cuenta": [f.detalle for f in filas], "Entrada": [float(f.abono) for f in filas],
                "Salida": [float(f.cargo) for f in filas], "Saldo": [float(f.saldo) for f in filas]})}),
            file_name=f"TALLY_{cuenta.nombre}_historial.xlsx", icon=":material/table_view:",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    confirmar = st.checkbox(f"Sí, quiero eliminar «{cuenta.nombre}»", key=f"{clave}_confirmar")
    if st.button("Eliminar cuenta", type="primary", disabled=not confirmar, key=f"{clave}_eliminar"):
        resultado = aplicar(lambda lib: cuentas.eliminar_cuenta(lib, cuenta.id, dejar_en_cero=dejar_en_cero))
        if resultado:
            avisar(f"«{cuenta.nombre}» eliminada" + (". Su historial se conserva." if resultado == cuentas.GUARDADA
                                                       else "."))
            st.session_state.pop("cuentas_elegida", None)
            st.rerun()


@st.dialog("Eliminar cuenta")
def _dialogo_eliminar(cuenta_id: str) -> None:
    eliminar(libro().cuenta(cuenta_id), f"dialogo_eliminar_{cuenta_id}")


def mostrar() -> None:
    abierta = estado_cuenta.abierta()
    if abierta:
        estado_cuenta.mostrar(abierta)
        return
    st.title("Cuentas")
    st.caption("¿Cuánto tengo en cada cuenta?")

    with st.expander("➕ Nueva cuenta", expanded=not cuentas.listar(libro())):
        formulario_nueva_cuenta()

    archivadas = st.toggle("Mostrar eliminadas", key="cuentas_mostrar_archivadas",
                           help="Las cuentas eliminadas que tenían movimientos: su historial se conserva y se pueden "
                                "restaurar.")
    lista = cuentas.listar(libro(), incluir_archivadas=archivadas)
    if not lista:
        st.info("Aún no tienes cuentas. Agrega la primera arriba.")
        return
    for tipo in TipoCuenta:
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
    if cuenta.tipo in (TipoCuenta.BIEN, TipoCuenta.PRESTAMO):
        donde = "Contabilidad Técnica → Bienes" if cuenta.tipo is TipoCuenta.BIEN else "Deudas"
        st.caption(f"Su valor, sus pagos y sus datos se manejan en **{donde}**.")
        editar, mas = st.tabs(["Editar", "Eliminar"])
        with editar:
            _editar(cuenta)
        with mas:
            eliminar(cuenta, f"pestana_eliminar_{cuenta.id}")
        return
    editar, actualizar, inicial, mas = st.tabs(["Editar", "Actualizar saldo", "Saldo inicial", "Eliminar"])
    with editar:
        _editar(cuenta)
    with actualizar:
        _actualizar_saldo(cuenta)
    with inicial:
        _saldo_inicial(cuenta)
    with mas:
        eliminar(cuenta, f"pestana_eliminar_{cuenta.id}")
