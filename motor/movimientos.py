"""Registro, consulta, edición y borrado de movimientos.

El usuario captura un importe positivo y el motor decide los signos de cada
partida según el tipo de movimiento.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import CATEGORIA_AJUSTE, Operacion, Partida, TipoCuenta, TipoOperacion
from motor.transferencias import construir_pago_tarjeta, construir_transferencia, origen_y_destino

Monto = Decimal | int | float | str
Reparto = Iterable[tuple[str, Monto]]

# Signo de la partida de cuenta en cada tipo con categorías.
_SIGNO_CUENTA = {
    TipoOperacion.GASTO: -1,
    TipoOperacion.INGRESO: +1,
    TipoOperacion.REEMBOLSO: +1,
}
CON_CUENTA_Y_CATEGORIA = tuple(_SIGNO_CUENTA)      # gasto, ingreso y devolución: los que se pueden pasar a transferencia


# ------------------------------------------------------------- construcción


def construir(
    tipo: TipoOperacion,
    fecha: date,
    cuenta_id: str,
    categoria_id: str | None = None,
    monto: Monto | None = None,
    descripcion: str = "",
    notas: str = "",
    *,
    reparto: Reparto | None = None,
) -> Operacion:
    """Construye un gasto, ingreso o reembolso (sin guardarlo).

    Para repartir un mismo movimiento entre varias categorías se usa
    ``reparto=[(categoria_id, monto), ...]`` en lugar de ``categoria_id`` y
    ``monto``.
    """
    tipo = TipoOperacion(tipo)
    if tipo not in _SIGNO_CUENTA:
        raise ErrorValidacion("Usa la función específica para este tipo de movimiento.")
    if reparto is None:
        if categoria_id is None or monto is None:
            raise ErrorValidacion("Indica la categoría y el importe.")
        reparto = [(categoria_id, monto)]
    elif categoria_id is not None or monto is not None:
        raise ErrorValidacion("Indica una categoría con importe o un reparto, no ambos.")

    signo = _SIGNO_CUENTA[tipo]
    partidas_categoria = []
    for cat_id, parte in reparto:
        centavos = a_centavos(parte)
        if centavos <= 0:
            raise ErrorValidacion("El importe debe ser mayor que cero.")
        partidas_categoria.append(Partida(-signo * centavos, categoria_id=cat_id))
    if not partidas_categoria:
        raise ErrorValidacion("Elige una categoría.")
    total = sum(-p.importe for p in partidas_categoria)
    return Operacion(
        fecha=fecha,
        tipo=tipo,
        partidas=(Partida(total, cuenta_id=cuenta_id), *partidas_categoria),
        descripcion=descripcion,
        notas=notas,
    )


def construir_con_signo(
    tipo: TipoOperacion, fecha: date, cuenta_id: str, categoria_id: str, monto: Monto, descripcion: str = "", notas: str = ""
) -> Operacion:
    """Rendimiento, ajuste o saldo inicial: ``monto`` es el cambio en la cuenta, con signo."""
    tipo = TipoOperacion(tipo)
    if tipo not in (TipoOperacion.RENDIMIENTO, TipoOperacion.AJUSTE, TipoOperacion.SALDO_INICIAL):
        raise ErrorValidacion("Usa la función específica para este tipo de movimiento.")
    centavos = a_centavos(monto)
    return Operacion(
        fecha=fecha,
        tipo=tipo,
        partidas=(Partida(centavos, cuenta_id=cuenta_id), Partida(-centavos, categoria_id=categoria_id)),
        descripcion=descripcion,
        notas=notas,
    )


# ----------------------------------------------------------------- registro


def registrar_gasto(
    libro: Libro,
    fecha: date,
    cuenta_id: str,
    categoria_id: str | None = None,
    monto: Monto | None = None,
    descripcion: str = "",
    notas: str = "",
    *,
    reparto: Reparto | None = None,
    msi: int = 0,
) -> Operacion:
    """Gasto pagado con cualquier cuenta (débito, TDC, efectivo, ahorro…).

    ``msi``: compra con tarjeta de crédito a meses sin intereses (el gasto cuenta completo hoy).
    """
    op = construir(TipoOperacion.GASTO, fecha, cuenta_id, categoria_id, monto, descripcion, notas, reparto=reparto)
    return libro.agregar_operacion(replace(op, msi=int(msi or 0)))


def registrar_ingreso(
    libro: Libro,
    fecha: date,
    cuenta_id: str,
    categoria_id: str | None = None,
    monto: Monto | None = None,
    descripcion: str = "",
    notas: str = "",
    *,
    reparto: Reparto | None = None,
) -> Operacion:
    op = construir(TipoOperacion.INGRESO, fecha, cuenta_id, categoria_id, monto, descripcion, notas, reparto=reparto)
    return libro.agregar_operacion(op)


def registrar_reembolso(
    libro: Libro,
    fecha: date,
    cuenta_id: str,
    categoria_id: str | None = None,
    monto: Monto | None = None,
    descripcion: str = "",
    notas: str = "",
    *,
    reparto: Reparto | None = None,
) -> Operacion:
    """Devolución de una compra: resta del gasto de la categoría, no es ingreso."""
    op = construir(TipoOperacion.REEMBOLSO, fecha, cuenta_id, categoria_id, monto, descripcion, notas, reparto=reparto)
    return libro.agregar_operacion(op)


def actualizar_saldo(
    libro: Libro,
    cuenta_id: str,
    saldo_real: Monto,
    fecha: date,
    *,
    categoria_id: str | None = None,
    descripcion: str = "",
) -> Operacion | None:
    """Hace que el saldo de la cuenta en ``fecha`` sea ``saldo_real``.

    - Sin categoría: registra un **ajuste** (no cuenta como ingreso ni gasto).
    - Con una categoría de ingreso (p. ej. «Intereses y rendimientos»):
      registra un **rendimiento**, ideal para intereses diarios o para la
      valuación de una inversión.

    Devuelve ``None`` si el saldo ya coincide.
    """
    diferencia = a_centavos(saldo_real) - libro.saldo_centavos(cuenta_id, fecha)
    if diferencia == 0:
        return None
    if categoria_id is None:
        tipo, categoria_id = TipoOperacion.AJUSTE, CATEGORIA_AJUSTE
        descripcion = descripcion or "Ajuste de saldo"
    else:
        tipo = TipoOperacion.RENDIMIENTO
        descripcion = descripcion or "Rendimiento"
    op = construir_con_signo(tipo, fecha, cuenta_id, categoria_id, a_pesos(diferencia), descripcion)
    return libro.agregar_operacion(op)


# ----------------------------------------------------------------- consulta


@dataclass(frozen=True, slots=True)
class Detalle:
    """Vista simple de una operación, en los términos que captura el usuario."""

    id: str
    fecha: date
    tipo: TipoOperacion
    monto: Decimal  # positivo; con signo solo en rendimientos, ajustes y saldo inicial
    cuenta_id: str
    cuenta_destino_id: str | None
    categoria_id: str | None  # None si el movimiento está repartido
    reparto: tuple[tuple[str, Decimal], ...]
    descripcion: str
    notas: str


def describir(op: Operacion) -> Detalle:
    if op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
        origen, destino = origen_y_destino(op)
        monto = a_pesos(max(p.importe for p in op.partidas))
        return Detalle(op.id, op.fecha, op.tipo, monto, origen, destino, None, (), op.descripcion, op.notas)

    (cuenta,) = op.partidas_de_cuenta()
    signo = _SIGNO_CUENTA.get(op.tipo)
    reparto = tuple((p.categoria_id, a_pesos(abs(p.importe))) for p in op.partidas_de_categoria())
    monto = a_pesos(abs(cuenta.importe) if signo else cuenta.importe)
    categoria_id = reparto[0][0] if len(reparto) == 1 else None
    return Detalle(op.id, op.fecha, op.tipo, monto, cuenta.cuenta_id, None, categoria_id, reparto, op.descripcion, op.notas)


def detalle(libro: Libro, operacion_id: str) -> Detalle:
    return describir(libro.operacion(operacion_id))


# ------------------------------------------------------------ edición/borrado

_SIN_CAMBIO = object()


def editar(
    libro: Libro,
    operacion_id: str,
    *,
    fecha: date | object = _SIN_CAMBIO,
    monto: Monto | object = _SIN_CAMBIO,
    cuenta_id: str | object = _SIN_CAMBIO,
    cuenta_destino_id: str | object = _SIN_CAMBIO,
    categoria_id: str | object = _SIN_CAMBIO,
    descripcion: str | object = _SIN_CAMBIO,
    notas: str | object = _SIN_CAMBIO,
    msi: int | object = _SIN_CAMBIO,
) -> Operacion:
    """Edita un movimiento conservando su tipo (y sus meses sin intereses, salvo que se indique ``msi``).

    En una transferencia, cambiar el importe cambia ambos lados a la vez.
    Para cambiar el tipo (p. ej. de gasto a transferencia) usa :func:`reemplazar`.
    """
    op = libro.operacion(operacion_id)
    actual = describir(op)

    def valor(nuevo, anterior):
        return anterior if nuevo is _SIN_CAMBIO else nuevo

    nueva_fecha = valor(fecha, op.fecha)
    nueva_descripcion = valor(descripcion, op.descripcion)
    nuevas_notas = valor(notas, op.notas)
    estructura = (monto, cuenta_id, cuenta_destino_id, categoria_id)

    nuevo_msi = int(valor(msi, op.msi) or 0)
    if all(v is _SIN_CAMBIO for v in estructura):
        nueva = replace(op, fecha=nueva_fecha, descripcion=nueva_descripcion, notas=nuevas_notas, msi=nuevo_msi)
        return libro.reemplazar_operacion(operacion_id, nueva)

    nuevo_monto = valor(monto, actual.monto)
    nueva_cuenta = valor(cuenta_id, actual.cuenta_id)

    if op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
        if categoria_id is not _SIN_CAMBIO:
            raise ErrorValidacion("Una transferencia no tiene categoría.")
        constructor = construir_pago_tarjeta if op.tipo is TipoOperacion.PAGO_TARJETA else construir_transferencia
        nueva = constructor(
            nueva_fecha, nueva_cuenta, valor(cuenta_destino_id, actual.cuenta_destino_id),
            nuevo_monto, nueva_descripcion, nuevas_notas,
        )
    else:
        if cuenta_destino_id is not _SIN_CAMBIO:
            raise ErrorValidacion("Este movimiento no tiene cuenta de destino.")
        if op.tipo in _SIGNO_CUENTA:
            if actual.categoria_id is None and (monto is not _SIN_CAMBIO or categoria_id is not _SIN_CAMBIO):
                raise ErrorValidacion("El movimiento está repartido en varias categorías; edítalo completo.")
            if actual.categoria_id is None:
                nueva = construir(
                    op.tipo, nueva_fecha, nueva_cuenta, descripcion=nueva_descripcion, notas=nuevas_notas,
                    reparto=actual.reparto,
                )
            else:
                nueva = construir(
                    op.tipo, nueva_fecha, nueva_cuenta, valor(categoria_id, actual.categoria_id),
                    nuevo_monto, nueva_descripcion, nuevas_notas,
                )
        else:
            nueva = construir_con_signo(
                op.tipo, nueva_fecha, nueva_cuenta, valor(categoria_id, actual.categoria_id),
                nuevo_monto, nueva_descripcion, nuevas_notas,
            )
    if op.tipo is TipoOperacion.GASTO:
        nueva = replace(nueva, msi=nuevo_msi)
    return libro.reemplazar_operacion(operacion_id, replace(nueva, liquida=op.liquida))


def duplicar(libro: Libro, operacion_id: str, fecha: date) -> Operacion:
    """Registra otra vez el mismo movimiento en ``fecha`` (la renta, una suscripción…)."""
    op = libro.operacion(operacion_id)
    if op.tipo is TipoOperacion.SALDO_INICIAL:
        raise ErrorValidacion("El saldo inicial no se puede repetir.")
    return libro.agregar_operacion(replace(op, id="", fecha=fecha, secuencia=0, creado_en=None, modificado_en=None,
                                              liquida=""))


def reemplazar(libro: Libro, operacion_id: str, nueva: Operacion) -> Operacion:
    """Sustituye un movimiento por otro (puede cambiar de tipo)."""
    if nueva.tipo is TipoOperacion.SALDO_INICIAL or libro.operacion(operacion_id).tipo is TipoOperacion.SALDO_INICIAL:
        raise ErrorValidacion("El saldo inicial se cambia desde la cuenta.")
    return libro.reemplazar_operacion(operacion_id, nueva)


def a_transferencia(libro: Libro, operacion_id: str, otra_cuenta_id: str) -> Operacion:
    """Un gasto o ingreso que en realidad fue mover dinero entre tus cuentas (al ahorro, a tu efectivo, a pagar tu
    tarjeta…): el mismo movimiento —fecha, importe, descripción, notas y comprobantes—, ahora como transferencia, o
    como pago de tarjeta si fue a una de crédito. En un gasto, el dinero fue a ``otra_cuenta_id``; en un ingreso,
    vino de ella. Deja de contar como gasto o ingreso y aparece en la otra cuenta."""
    op = libro.operacion(operacion_id)
    if op.tipo not in _SIGNO_CUENTA:
        raise ErrorValidacion("Solo un gasto, un ingreso o una devolución se pueden pasar a transferencia.")
    if op.msi:
        raise ErrorValidacion("Es una compra a meses sin intereses: esa sí es un gasto.")
    if op.liquida:
        raise ErrorValidacion("Es parte de un cargo temporal: arréglalo desde «Te deben» en el Resumen.")
    (cuenta,) = op.partidas_de_cuenta()
    otra = libro.cuenta(otra_cuenta_id)
    if otra.id == cuenta.cuenta_id:
        raise ErrorValidacion("Elige otra de tus cuentas, no la misma.")
    origen, destino = (cuenta.cuenta_id, otra.id) if cuenta.importe < 0 else (otra.id, cuenta.cuenta_id)
    tipo = (TipoOperacion.PAGO_TARJETA if libro.cuenta(destino).tipo is TipoCuenta.CREDITO
            and libro.cuenta(origen).tipo is not TipoCuenta.CREDITO else TipoOperacion.TRANSFERENCIA)
    nueva = construir_transferencia(op.fecha, origen, destino, a_pesos(abs(cuenta.importe)), op.descripcion, op.notas,
                                    tipo=tipo)
    return libro.reemplazar_operacion(op.id, nueva)


def eliminar(libro: Libro, operacion_id: str) -> Operacion:
    """Borra el movimiento (las dos partes, si es una transferencia)."""
    if libro.operacion(operacion_id).tipo is TipoOperacion.SALDO_INICIAL:
        raise ErrorValidacion("El saldo inicial se cambia desde la cuenta.")
    return libro.eliminar_operacion(operacion_id)

