"""Cuentas: débito, ahorro, crédito, efectivo, inversión, por cobrar y otras.

No hay límite en el número de cuentas de cada tipo.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from motor.categorias import normalizar_nombre
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
    fecha_creacion: date | None = None,
) -> Cuenta:
    """Crea una cuenta y, si se indica, registra su saldo inicial.

    Para tarjetas de crédito lo natural es indicar ``deuda_inicial`` (lo que
    se debe hoy) en lugar de ``saldo_inicial``.
    """
    tipo = TipoCuenta(tipo)
    nombre = normalizar_nombre(nombre)
    _nombre_libre(libro, nombre)
    if tipo is not TipoCuenta.CREDITO and any(v is not None for v in (deuda_inicial, limite_credito, dia_corte, dia_pago)):
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
    )
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
    }
    for campo, (valor, convertir) in datos_credito.items():
        if valor is _SIN_CAMBIO:
            continue
        if cuenta.tipo is not TipoCuenta.CREDITO and valor is not None:
            raise ErrorValidacion("Límite, día de corte y día de pago solo aplican a tarjetas de crédito.")
        cambios[campo] = convertir(valor)
    return libro.guardar_cuenta(replace(cuenta, **cambios))


def cambiar_tipo(libro: Libro, cuenta_id: str, tipo: TipoCuenta) -> Cuenta:
    """Cambia el tipo de cuenta si sus movimientos siguen siendo válidos."""
    cuenta = libro.cuenta(cuenta_id)
    nueva = replace(cuenta, tipo=TipoCuenta(tipo))
    if nueva.tipo is not TipoCuenta.CREDITO:
        nueva = replace(nueva, limite_credito=None, dia_corte=None, dia_pago=None)
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
