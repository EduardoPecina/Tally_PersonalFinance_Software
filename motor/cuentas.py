"""Cuentas: débito, ahorro, crédito, efectivo, inversión, por cobrar y otras.

No hay límite en el número de cuentas de cada tipo.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import (
    CATEGORIA_SALDO_INICIAL,
    TIPOS_DISPONIBLES_POR_DEFECTO,
    Cuenta,
    Operacion,
    Partida,
    TipoCuenta,
    TipoOperacion,
)
from motor.textos import normalizar_nombre

Monto = Decimal | int | float | str


def crear(
    libro: Libro,
    nombre: str,
    tipo: TipoCuenta,
    *,
    saldo_inicial: Monto = 0,
    deuda_inicial: Monto | None = None,
    fecha_saldo_inicial: date | None = None,
    institucion: str = "",
    notas: str = "",
    en_disponible: bool | None = None,
    limite_credito: Monto | None = None,
    dia_corte: int | None = None,
    dia_pago: int | None = None,
    dias_para_pagar: int | None = None,
    dias_habiles: bool = False,
    recorrer_inhabil: bool = True,
    fecha_creacion: date | None = None,
) -> Cuenta:
    """Crea una cuenta y, si se indica, registra su saldo inicial.

    Para tarjetas de crédito lo natural es indicar ``deuda_inicial`` (lo que
    se debe hoy) en lugar de ``saldo_inicial``. La fecha límite de pago se
    indica con ``dia_pago`` (un día fijo del mes) o con ``dias_para_pagar``
    (días después del corte, naturales o hábiles según ``dias_habiles``).
    """
    tipo = TipoCuenta(tipo)
    nombre = normalizar_nombre(nombre)
    _nombre_libre(libro, nombre)
    if tipo is not TipoCuenta.CREDITO and any(
        v is not None for v in (deuda_inicial, limite_credito, dia_corte, dia_pago, dias_para_pagar)
    ):
        raise ErrorValidacion("Límite, día de corte, día de pago y deuda solo aplican a tarjetas de crédito.")

    inicial = a_centavos(saldo_inicial)
    if deuda_inicial is not None:
        if inicial:
            raise ErrorValidacion("Indica el saldo inicial o la deuda inicial, no ambos.")
        inicial = -a_centavos(deuda_inicial)

    fecha_creacion = fecha_creacion or libro.hoy()
    cuenta = Cuenta(
        id=libro.nuevo_id(),
        nombre=nombre,
        tipo=tipo,
        fecha_creacion=fecha_creacion,
        en_disponible=tipo in TIPOS_DISPONIBLES_POR_DEFECTO if en_disponible is None else en_disponible,
        institucion=institucion.strip(),
        notas=notas,
        orden=max((c.orden for c in libro.cuentas()), default=-1) + 1,
        limite_credito=_limite(limite_credito),
        dia_corte=_dia(dia_corte, "corte"),
        dia_pago=_dia(dia_pago, "pago"),
        dias_para_pagar=_dias_para_pagar(dias_para_pagar),
        dias_habiles=bool(dias_habiles),
        recorrer_inhabil=bool(recorrer_inhabil),
    )
    _validar_regla_de_pago(cuenta)
    libro.guardar_cuenta(cuenta)
    if inicial:
        _registrar_saldo_inicial(libro, cuenta.id, inicial, fecha_saldo_inicial or fecha_creacion)
    return cuenta


_SIN_CAMBIO = object()


def editar(
    libro: Libro,
    cuenta_id: str,
    *,
    nombre: str | None = None,
    institucion: str | None = None,
    notas: str | None = None,
    en_disponible: bool | None = None,
    orden: int | None = None,
    limite_credito: Monto | None | object = _SIN_CAMBIO,
    dia_corte: int | None | object = _SIN_CAMBIO,
    dia_pago: int | None | object = _SIN_CAMBIO,
    dias_para_pagar: int | None | object = _SIN_CAMBIO,
    dias_habiles: bool | None = None,
    recorrer_inhabil: bool | None = None,
    tasa_anual: object = _SIN_CAMBIO,
    cat: object = _SIN_CAMBIO,
    tasa_incluye_iva: bool | None = None,
) -> Cuenta:
    """Edita datos descriptivos. El tipo de cuenta no se cambia aquí."""
    cuenta = libro.cuenta(cuenta_id)
    cambios: dict = {}
    if nombre is not None:
        nombre = normalizar_nombre(nombre)
        _nombre_libre(libro, nombre, excepto=cuenta_id)
        cambios["nombre"] = nombre
    if institucion is not None:
        cambios["institucion"] = institucion.strip()
    if notas is not None:
        cambios["notas"] = notas
    if en_disponible is not None:
        cambios["en_disponible"] = en_disponible
    if orden is not None:
        cambios["orden"] = orden
    datos_credito = {
        "limite_credito": (limite_credito, _limite),
        "dia_corte": (dia_corte, lambda v: _dia(v, "corte")),
        "dia_pago": (dia_pago, lambda v: _dia(v, "pago")),
        "dias_para_pagar": (dias_para_pagar, _dias_para_pagar),
    }
    for campo, (valor, convertir) in datos_credito.items():
        if valor is _SIN_CAMBIO:
            continue
        if cuenta.tipo is not TipoCuenta.CREDITO and valor is not None:
            raise ErrorValidacion("Límite, día de corte y día de pago solo aplican a tarjetas de crédito.")
        cambios[campo] = convertir(valor)
    for campo, valor in (("tasa_anual", tasa_anual), ("cat", cat)):
        if valor is _SIN_CAMBIO:
            continue
        if cuenta.tipo is not TipoCuenta.CREDITO and valor is not None:
            raise ErrorValidacion("La tasa y el CAT de una tarjeta solo aplican a tarjetas de crédito.")
        cambios[campo] = _porcentaje(valor, "La tasa anual" if campo == "tasa_anual" else "El CAT")
    if tasa_incluye_iva is not None:
        cambios["tasa_incluye_iva"] = bool(tasa_incluye_iva)
    for campo, valor in (("dias_habiles", dias_habiles), ("recorrer_inhabil", recorrer_inhabil)):
        if valor is not None:
            if cuenta.tipo is not TipoCuenta.CREDITO:
                raise ErrorValidacion("La regla de la fecha de pago solo aplica a tarjetas de crédito.")
            cambios[campo] = bool(valor)
    nueva = replace(cuenta, **cambios)
    _validar_regla_de_pago(nueva)
    return libro.guardar_cuenta(nueva)


def cambiar_tipo(libro: Libro, cuenta_id: str, tipo: TipoCuenta) -> Cuenta:
    """Cambia el tipo de cuenta si sus movimientos siguen siendo válidos."""
    cuenta = libro.cuenta(cuenta_id)
    nueva = replace(cuenta, tipo=TipoCuenta(tipo))
    if nueva.tipo is not TipoCuenta.CREDITO:
        nueva = replace(nueva, limite_credito=None, dia_corte=None, dia_pago=None, dias_para_pagar=None,
                        dias_habiles=False, recorrer_inhabil=True)
        recibe_pagos = any(
            op.tipo is TipoOperacion.PAGO_TARJETA
            and any(p.cuenta_id == cuenta_id and p.importe > 0 for p in op.partidas)
            for op in libro.operaciones()
        )
        if recibe_pagos:
            raise ErrorValidacion("La cuenta tiene pagos de tarjeta registrados; no puede dejar de ser de crédito.")
    return libro.guardar_cuenta(nueva)


def archivar(libro: Libro, cuenta_id: str) -> Cuenta:
    """Oculta la cuenta para movimientos nuevos. Su saldo sigue contando."""
    return libro.guardar_cuenta(replace(libro.cuenta(cuenta_id), activa=False))


def reactivar(libro: Libro, cuenta_id: str) -> Cuenta:
    return libro.guardar_cuenta(replace(libro.cuenta(cuenta_id), activa=True))


def eliminar(libro: Libro, cuenta_id: str) -> None:
    """Borra una cuenta sin movimientos (su saldo inicial se borra con ella)."""
    inicial = _operacion_saldo_inicial(libro, cuenta_id)
    otras = [
        op
        for op in libro.operaciones()
        if op is not inicial and any(p.cuenta_id == cuenta_id for p in op.partidas)
    ]
    if otras:
        raise ErrorValidacion("La cuenta tiene movimientos; archívala en lugar de borrarla.")
    if inicial is not None:
        libro.eliminar_operacion(inicial.id)
    libro.quitar_cuenta(cuenta_id)


def cambiar_saldo_inicial(libro: Libro, cuenta_id: str, saldo: Monto, fecha: date | None = None) -> None:
    """Fija el saldo inicial de una cuenta (crea, edita o borra la operación)."""
    cuenta = libro.cuenta(cuenta_id)
    centavos = a_centavos(saldo)
    actual = _operacion_saldo_inicial(libro, cuenta_id)
    fecha = fecha or (actual.fecha if actual else cuenta.fecha_creacion)
    if actual is None:
        if centavos:
            _registrar_saldo_inicial(libro, cuenta_id, centavos, fecha)
    elif centavos == 0:
        libro.eliminar_operacion(actual.id)
    else:
        libro.reemplazar_operacion(actual.id, _operacion_inicial(cuenta_id, centavos, fecha))


def cambiar_deuda_inicial(libro: Libro, cuenta_id: str, deuda: Monto, fecha: date | None = None) -> None:
    """Como :func:`cambiar_saldo_inicial`, pero para tarjetas: indica lo que se debía (en positivo)."""
    if libro.cuenta(cuenta_id).tipo is not TipoCuenta.CREDITO:
        raise ErrorValidacion("La deuda inicial solo aplica a tarjetas de crédito.")
    cambiar_saldo_inicial(libro, cuenta_id, -a_pesos(a_centavos(deuda)), fecha)


def deuda_inicial(libro: Libro, cuenta_id: str) -> Decimal:
    """Lo que se debía en una tarjeta al empezar a usar TALLY (0 si no había deuda)."""
    registrado = saldo_inicial(libro, cuenta_id)
    return max(-registrado[0], Decimal("0.00")) if registrado else Decimal("0.00")


def saldo_inicial(libro: Libro, cuenta_id: str) -> tuple[Decimal, date] | None:
    """Saldo inicial registrado y su fecha (``None`` si la cuenta empezó en cero)."""
    op = _operacion_saldo_inicial(libro, cuenta_id)
    if op is None:
        return None
    (partida,) = op.partidas_de_cuenta()
    return a_pesos(partida.importe), op.fecha


BORRADA, GUARDADA = "borrada", "guardada"


def eliminar_cuenta(libro: Libro, cuenta_id: str, *, dejar_en_cero: bool = False, fecha: date | None = None) -> str:
    """Lo que hace el botón «Eliminar» del portal.

    - Sin movimientos: se borra por completo (``BORRADA``).
    - Con movimientos: se archiva (``GUARDADA``). Desaparece de las cuentas y de los formularios, pero su
      historial sigue en Historial, tablas dinámicas y gráficas, y se puede restaurar con :func:`reactivar`.
      Con ``dejar_en_cero``, antes se registra un ajuste (no es ingreso ni gasto) para que su saldo o deuda
      quede en 0 y deje de contar en el patrimonio.
    """
    cuenta = libro.cuenta(cuenta_id)
    if not tiene_movimientos(libro, cuenta_id) and not libro.tiene_titulos(cuenta_id):
        eliminar(libro, cuenta_id)
        return BORRADA
    if dejar_en_cero and libro.saldo_centavos(cuenta_id):
        if not cuenta.activa:
            libro.guardar_cuenta(replace(cuenta, activa=True))
        from motor.movimientos import actualizar_saldo

        actualizar_saldo(libro, cuenta_id, 0, fecha or libro.hoy(), descripcion="Cuenta eliminada: saldo en 0")
    archivar(libro, cuenta_id)
    return GUARDADA


def tiene_movimientos(libro: Libro, cuenta_id: str) -> bool:
    """True si la cuenta tiene movimientos además de su saldo inicial (entonces no se puede borrar)."""
    return any(
        op.tipo is not TipoOperacion.SALDO_INICIAL and any(p.cuenta_id == cuenta_id for p in op.partidas)
        for op in libro.operaciones()
    )


def saldo(libro: Libro, cuenta_id: str, al: date | None = None) -> Decimal:
    """Saldo de la cuenta. En crédito, negativo = deuda."""
    return a_pesos(libro.saldo_centavos(cuenta_id, al))


def saldos(libro: Libro, al: date | None = None, *, incluir_archivadas: bool = True) -> dict[str, Decimal]:
    return {c.id: saldo(libro, c.id, al) for c in listar(libro, incluir_archivadas=incluir_archivadas)}


def listar(
    libro: Libro, *, tipo: TipoCuenta | None = None, incluir_archivadas: bool = False
) -> list[Cuenta]:
    return [
        c
        for c in libro.cuentas()
        if (incluir_archivadas or c.activa) and (tipo is None or c.tipo is TipoCuenta(tipo))
    ]


def buscar(libro: Libro, nombre: str) -> Cuenta | None:
    clave = normalizar_nombre(nombre).casefold()
    return next((c for c in libro.cuentas() if c.nombre.casefold() == clave), None)


# ---------------------------------------------------------------- internos


def _nombre_libre(libro: Libro, nombre: str, excepto: str | None = None) -> None:
    if any(c.id != excepto and c.nombre.casefold() == nombre.casefold() for c in libro.cuentas()):
        raise ErrorValidacion(f"Ya existe una cuenta llamada «{nombre}».")


def _limite(valor: Monto | None) -> int | None:
    if valor is None:
        return None
    centavos = a_centavos(valor)
    if centavos <= 0:
        raise ErrorValidacion("El límite de crédito debe ser mayor que cero.")
    return centavos


def _dia(valor: int | None, que: str) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= 31:
        raise ErrorValidacion(f"El día de {que} debe estar entre 1 y 31.")
    return valor


def _dias_para_pagar(valor: int | None) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= 60:
        raise ErrorValidacion("Los días para pagar después del corte deben estar entre 1 y 60.")
    return valor


def _validar_regla_de_pago(cuenta: Cuenta) -> None:
    if cuenta.dia_pago is not None and cuenta.dias_para_pagar is not None:
        raise ErrorValidacion("Elige un día fijo de pago o un número de días después del corte, no ambos.")


def _operacion_inicial(cuenta_id: str, centavos: int, fecha: date) -> Operacion:
    return Operacion(
        fecha=fecha,
        tipo=TipoOperacion.SALDO_INICIAL,
        partidas=(
            Partida(centavos, cuenta_id=cuenta_id),
            Partida(-centavos, categoria_id=CATEGORIA_SALDO_INICIAL),
        ),
        descripcion="Saldo inicial",
    )


def _registrar_saldo_inicial(libro: Libro, cuenta_id: str, centavos: int, fecha: date) -> Operacion:
    return libro.agregar_operacion(_operacion_inicial(cuenta_id, centavos, fecha))


def _operacion_saldo_inicial(libro: Libro, cuenta_id: str) -> Operacion | None:
    libro.cuenta(cuenta_id)
    return next(
        (
            op
            for op in libro.operaciones()
            if op.tipo is TipoOperacion.SALDO_INICIAL and any(p.cuenta_id == cuenta_id for p in op.partidas)
        ),
        None,
    )


def _porcentaje(valor, que: str) -> Decimal | None:
    """Un % anual opcional (vacío o 0 = no registrado)."""
    if valor in (None, ""):
        return None
    try:
        numero = Decimal(str(valor))
    except (ArithmeticError, ValueError):
        raise ErrorValidacion(f"{que} debe ser un número (45.5 para 45.5 %).") from None
    if not numero.is_finite() or not 0 <= numero <= 1000:
        raise ErrorValidacion(f"{que} va de 0 a 1,000 %.")
    return numero or None
