"""Registro, consulta, edición y borrado de movimientos.

El usuario captura un importe positivo y el motor decide los signos de cada
partida según el tipo de movimiento. En una cuenta en otra moneda, el importe va en
esa moneda: el Libro lo pasa a la tuya al guardar (motor/divisas.py).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from motor import divisas
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import CATEGORIA_AJUSTE, Operacion, Partida, TipoCuenta, TipoOperacion
from motor.transferencias import construir_con_llegada, construir_transferencia

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
    """Hace que el saldo de la cuenta en ``fecha`` sea ``saldo_real`` (en la moneda de la cuenta).

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
    """Vista simple de una operación, en los términos que captura el usuario: los importes, en la moneda de la
    cuenta (la de origen, en una transferencia)."""

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
    llega: Decimal | None = None  # transferencia entre cuentas de distinta moneda: lo que llegó, en la del destino


def describir(op: Operacion) -> Detalle:
    if op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
        origen, destino = op.partidas_de_cuenta()
        if origen.importe > 0:
            origen, destino = destino, origen
        sale, llega = -origen.en_su_moneda, destino.en_su_moneda
        return Detalle(op.id, op.fecha, op.tipo, a_pesos(sale), origen.cuenta_id, destino.cuenta_id, None, (),
                       op.descripcion, op.notas, a_pesos(llega) if llega != sale else None)

    (cuenta,) = op.partidas_de_cuenta()
    signo = _SIGNO_CUENTA.get(op.tipo)
    if cuenta.original is None:
        reparto = tuple((p.categoria_id, a_pesos(abs(p.importe))) for p in op.partidas_de_categoria())
        propio = cuenta.importe
    else:                                              # cuenta en otra moneda: el reparto, también en esa moneda
        de_categoria = op.partidas_de_categoria()
        partes = divisas.repartir(abs(cuenta.original), [abs(p.importe) for p in de_categoria])
        reparto = tuple((p.categoria_id, a_pesos(parte)) for p, parte in zip(de_categoria, partes))
        propio = cuenta.original
    monto = a_pesos(abs(propio) if signo else propio)
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
    llega: Monto | None | object = _SIN_CAMBIO,
) -> Operacion:
    """Edita un movimiento conservando su tipo (y sus meses sin intereses, salvo que se indique ``msi``).

    En una transferencia, cambiar el importe cambia ambos lados a la vez; entre cuentas de distinta moneda,
    ``llega`` es lo que llegó (``None``: calcularlo con el tipo de cambio). Los importes van en la moneda de la
    cuenta; si cambia la fecha de un movimiento en otra moneda, se convierte con el tipo de cambio del nuevo día.
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
    en_otra_moneda = any(p.original is not None for p in op.partidas)
    if all(v is _SIN_CAMBIO for v in estructura) and llega is _SIN_CAMBIO and not (
            en_otra_moneda and nueva_fecha != op.fecha):
        nueva = replace(op, fecha=nueva_fecha, descripcion=nueva_descripcion, notas=nuevas_notas, msi=nuevo_msi)
        return libro.reemplazar_operacion(operacion_id, nueva)

    nuevo_monto = valor(monto, actual.monto)
    nueva_cuenta = valor(cuenta_id, actual.cuenta_id)
    reparto = actual.reparto
    if monto is _SIN_CAMBIO and divisas.moneda_de(libro, nueva_cuenta) != divisas.moneda_de(libro, actual.cuenta_id):
        # Pasó a una cuenta de otra moneda sin cambiar el importe: vale lo mismo en tu moneda (no «$100 → US$100»).
        nuevo_monto, reparto = _en_la_moneda_de(libro, op, nueva_cuenta, nueva_fecha)

    if op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
        if categoria_id is not _SIN_CAMBIO:
            raise ErrorValidacion("Una transferencia no tiene categoría.")
        nuevo_destino = valor(cuenta_destino_id, actual.cuenta_destino_id)
        # Lo que llegó sigue valiendo si el destino sigue en la misma moneda (otra cuenta de dólares, p. ej.).
        misma_llegada = monto is _SIN_CAMBIO and (
            divisas.moneda_de(libro, nuevo_destino) == divisas.moneda_de(libro, actual.cuenta_destino_id))
        nueva = construir_con_llegada(
            libro, nueva_fecha, nueva_cuenta, nuevo_destino, nuevo_monto, nueva_descripcion, nuevas_notas,
            llega=valor(llega, actual.llega if misma_llegada else None), tipo=op.tipo,
        )
    else:
        if cuenta_destino_id is not _SIN_CAMBIO or llega not in (_SIN_CAMBIO, None):
            raise ErrorValidacion("Este movimiento no tiene cuenta de destino.")
        if op.tipo in _SIGNO_CUENTA:
            if actual.categoria_id is None and (monto is not _SIN_CAMBIO or categoria_id is not _SIN_CAMBIO):
                raise ErrorValidacion("El movimiento está repartido en varias categorías; edítalo completo.")
            if actual.categoria_id is None:
                nueva = construir(
                    op.tipo, nueva_fecha, nueva_cuenta, descripcion=nueva_descripcion, notas=nuevas_notas,
                    reparto=reparto,
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


def _en_la_moneda_de(libro: Libro, op: Operacion, cuenta_id: str, fecha: date
                     ) -> tuple[Decimal, tuple[tuple[str, Decimal], ...]]:
    """El importe del movimiento (y su reparto) en la moneda de ``cuenta_id``, con lo que valía en tu moneda."""
    def convertir(centavos: int) -> int:
        if not divisas.en_otra_moneda(libro, cuenta_id):
            return centavos
        return divisas.desde_base(centavos, divisas.tipo_o_error(libro, divisas.moneda_de(libro, cuenta_id), fecha))

    if op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
        return a_pesos(convertir(-min(p.importe for p in op.partidas_de_cuenta()))), ()
    (cuenta,) = op.partidas_de_cuenta()
    total = convertir(abs(cuenta.importe))
    de_categoria = op.partidas_de_categoria()
    partes = divisas.repartir(total, [abs(p.importe) for p in de_categoria])
    monto = total if op.tipo in _SIGNO_CUENTA or cuenta.importe > 0 else -total
    return a_pesos(monto), tuple((p.categoria_id, a_pesos(x)) for p, x in zip(de_categoria, partes))


def duplicar(libro: Libro, operacion_id: str, fecha: date) -> Operacion:
    """Registra otra vez el mismo movimiento en ``fecha`` (la renta, una suscripción…)."""
    op = libro.operacion(operacion_id)
    if op.tipo is TipoOperacion.SALDO_INICIAL:
        raise ErrorValidacion("El saldo inicial no se puede repetir.")
    nueva = op if fecha == op.fecha else divisas.sin_convertir(op)      # en otra moneda: al tipo de cambio de ese día
    return libro.agregar_operacion(replace(nueva, id="", fecha=fecha, secuencia=0, creado_en=None, modificado_en=None,
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
    importe = a_pesos(abs(cuenta.en_su_moneda))
    if origen == cuenta.cuenta_id or divisas.moneda_de(libro, origen) == divisas.moneda_de(libro, destino):
        nueva = construir_transferencia(op.fecha, origen, destino, importe, op.descripcion, op.notas, tipo=tipo)
    else:       # llegó a esta cuenta desde una de otra moneda: lo que salió de aquella, con lo que valía ese día
        sale = abs(cuenta.importe)
        if divisas.en_otra_moneda(libro, origen):
            sale = divisas.desde_base(sale, divisas.tipo_o_error(libro, divisas.moneda_de(libro, origen), op.fecha))
        nueva = divisas.transferencia(libro, op.fecha, origen, destino, a_pesos(sale), importe, op.descripcion,
                                      op.notas, tipo_operacion=tipo)
    return libro.reemplazar_operacion(op.id, nueva)


def eliminar(libro: Libro, operacion_id: str) -> Operacion:
    """Borra el movimiento (las dos partes, si es una transferencia)."""
    if libro.operacion(operacion_id).tipo is TipoOperacion.SALDO_INICIAL:
        raise ErrorValidacion("El saldo inicial se cambia desde la cuenta.")
    return libro.eliminar_operacion(operacion_id)

