"""Reglas contables: qué forma puede tener cada tipo de operación.

Es el único lugar donde se decide si una operación es válida. El ``Libro``
llama a :func:`validar_operacion` antes de guardar cualquier operación.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from motor.errores import ErrorValidacion
from motor.modelo import (
    CATEGORIA_AJUSTE,
    CATEGORIA_SALDO_INICIAL,
    ClaseCategoria,
    Operacion,
    TipoCuenta,
    TipoOperacion,
)

if TYPE_CHECKING:
    from motor.libro import Libro


def validar_operacion(libro: Libro, op: Operacion, original: Operacion | None = None) -> None:
    """Lanza ``ErrorValidacion`` si la operación no cumple las reglas.

    ``original`` es la versión anterior cuando se trata de una edición: se
    permite seguir usando cuentas o categorías archivadas que ya estaban en
    ella.
    """
    if len(op.partidas) < 2:
        raise ErrorValidacion("Una operación necesita al menos dos partidas.")
    if any(p.importe == 0 for p in op.partidas):
        raise ErrorValidacion("El importe no puede ser cero.")
    if sum(p.importe for p in op.partidas) != 0:
        raise ErrorValidacion("Las partidas de la operación no cuadran (no suman cero).")

    _validar_referencias(libro, op, original)
    _validar_msi(libro, op)

    cuentas = op.partidas_de_cuenta()
    categorias = op.partidas_de_categoria()
    clases = {libro.categoria(p.categoria_id).clase for p in categorias}

    match op.tipo:
        case TipoOperacion.GASTO:
            _una_cuenta(cuentas, signo=-1)
            _categorias(categorias, clases, ClaseCategoria.GASTO, signo=+1)
        case TipoOperacion.INGRESO:
            _una_cuenta(cuentas, signo=+1)
            _categorias(categorias, clases, ClaseCategoria.INGRESO, signo=-1)
        case TipoOperacion.REEMBOLSO:
            _una_cuenta(cuentas, signo=+1)
            _categorias(categorias, clases, ClaseCategoria.GASTO, signo=-1)
        case TipoOperacion.TRANSFERENCIA | TipoOperacion.PAGO_TARJETA:
            if categorias or len(cuentas) != 2:
                raise ErrorValidacion("Una transferencia mueve dinero entre exactamente dos cuentas.")
            origen, destino = sorted(cuentas, key=lambda p: p.importe)
            if origen.cuenta_id == destino.cuenta_id:
                raise ErrorValidacion("La cuenta de origen y la de destino deben ser distintas.")
            if op.tipo is TipoOperacion.PAGO_TARJETA and libro.cuenta(destino.cuenta_id).tipo is not TipoCuenta.CREDITO:
                raise ErrorValidacion("El pago de tarjeta debe ir a una cuenta de crédito.")
        case TipoOperacion.RENDIMIENTO:
            _una_cuenta(cuentas)
            if len(categorias) != 1 or clases != {ClaseCategoria.INGRESO}:
                raise ErrorValidacion("Un rendimiento se registra en una categoría de ingreso.")
        case TipoOperacion.AJUSTE:
            _una_cuenta(cuentas)
            if len(categorias) != 1 or categorias[0].categoria_id != CATEGORIA_AJUSTE:
                raise ErrorValidacion("Un ajuste usa la categoría «Ajuste de saldo».")
        case TipoOperacion.SALDO_INICIAL:
            _una_cuenta(cuentas)
            if len(categorias) != 1 or categorias[0].categoria_id != CATEGORIA_SALDO_INICIAL:
                raise ErrorValidacion("Un saldo inicial usa la categoría «Saldo inicial».")
            cuenta_id = cuentas[0].cuenta_id
            for otra in libro.operaciones():
                if (
                    otra.tipo is TipoOperacion.SALDO_INICIAL
                    and otra.id != op.id
                    and any(p.cuenta_id == cuenta_id for p in otra.partidas)
                ):
                    raise ErrorValidacion("Esta cuenta ya tiene un saldo inicial.")
        case _:
            raise ErrorValidacion(f"Tipo de operación desconocido: {op.tipo!r}.")


def _validar_referencias(libro: Libro, op: Operacion, original: Operacion | None) -> None:
    ya_usadas = set()
    if original is not None:
        ya_usadas = {p.cuenta_id or p.categoria_id for p in original.partidas}
    for p in op.partidas:
        if p.cuenta_id is not None:
            cuenta = libro.cuenta(p.cuenta_id)
            if not cuenta.activa and cuenta.id not in ya_usadas:
                raise ErrorValidacion(f"La cuenta «{cuenta.nombre}» está archivada.")
        else:
            categoria = libro.categoria(p.categoria_id)
            if not categoria.activa and categoria.id not in ya_usadas:
                raise ErrorValidacion(f"La categoría «{categoria.nombre}» está archivada.")


MSI_MINIMO, MSI_MAXIMO = 2, 60


def _validar_msi(libro: Libro, op: Operacion) -> None:
    if not op.msi:
        return
    if isinstance(op.msi, bool) or not isinstance(op.msi, int) or not MSI_MINIMO <= op.msi <= MSI_MAXIMO:
        raise ErrorValidacion(f"Los meses sin intereses van de {MSI_MINIMO} a {MSI_MAXIMO}.")
    cuentas = op.partidas_de_cuenta()
    if op.tipo is not TipoOperacion.GASTO or len(cuentas) != 1 or \
            libro.cuenta(cuentas[0].cuenta_id).tipo is not TipoCuenta.CREDITO:
        raise ErrorValidacion("Los meses sin intereses solo aplican a compras con tarjeta de crédito.")


def _una_cuenta(cuentas, signo: int | None = None) -> None:
    if len(cuentas) != 1:
        raise ErrorValidacion("Esta operación afecta exactamente a una cuenta.")
    if signo is not None and (cuentas[0].importe > 0) != (signo > 0):
        raise ErrorValidacion("El importe de la operación debe ser positivo.")


def _categorias(categorias, clases, clase: ClaseCategoria, signo: int) -> None:
    if not categorias:
        raise ErrorValidacion("Elige una categoría.")
    if clases != {clase}:
        nombre = "gasto" if clase is ClaseCategoria.GASTO else "ingreso"
        raise ErrorValidacion(f"La categoría debe ser de {nombre}.")
    if any((p.importe > 0) != (signo > 0) for p in categorias):
        raise ErrorValidacion("El importe de la operación debe ser positivo.")
