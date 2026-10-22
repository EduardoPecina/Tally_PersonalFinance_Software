"""Transferencias entre cuentas propias y pagos de tarjeta.

Una transferencia es **una sola operación** con dos partidas de cuenta y
ninguna de categoría: nunca puede contar como gasto ni como ingreso.

El importe es lo que sale, en la moneda de la cuenta de origen. Entre cuentas de distinta moneda (pesos a dólares),
lo que llega se calcula con el tipo de cambio del día, o se indica con ``llega`` (motor/divisas.py).
"""

from __future__ import annotations

from datetime import date

from motor import divisas
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Operacion, Partida, TipoOperacion


def construir_transferencia(
    fecha: date,
    origen_id: str,
    destino_id: str,
    monto,
    descripcion: str = "",
    notas: str = "",
    *,
    tipo: TipoOperacion = TipoOperacion.TRANSFERENCIA,
) -> Operacion:
    centavos = a_centavos(monto)
    if centavos <= 0:
        raise ErrorValidacion("El importe debe ser mayor que cero.")
    return Operacion(
        fecha=fecha,
        tipo=tipo,
        partidas=(Partida(-centavos, cuenta_id=origen_id), Partida(centavos, cuenta_id=destino_id)),
        descripcion=descripcion,
        notas=notas,
    )


def construir_pago_tarjeta(
    fecha: date, origen_id: str, tarjeta_id: str, monto, descripcion: str = "", notas: str = ""
) -> Operacion:
    return construir_transferencia(
        fecha, origen_id, tarjeta_id, monto, descripcion, notas, tipo=TipoOperacion.PAGO_TARJETA
    )


def construir_con_llegada(
    libro: Libro, fecha: date, origen_id: str, destino_id: str, monto, descripcion: str = "", notas: str = "", *,
    llega=None, tipo: TipoOperacion = TipoOperacion.TRANSFERENCIA,
) -> Operacion:
    """Como :func:`construir_transferencia`; con ``llega`` (lo que llegó, en la moneda del destino) si las cuentas
    son de distinta moneda."""
    if llega is None or divisas.moneda_de(libro, origen_id) == divisas.moneda_de(libro, destino_id):
        return construir_transferencia(fecha, origen_id, destino_id, monto, descripcion, notas, tipo=tipo)
    return divisas.transferencia(libro, fecha, origen_id, destino_id, monto, llega, descripcion, notas,
                                 tipo_operacion=tipo)


def construir_por_valor(
    libro: Libro, fecha: date, origen_id: str, destino_id: str, valor, descripcion: str = "", notas: str = "", *,
    tipo: TipoOperacion = TipoOperacion.TRANSFERENCIA,
) -> Operacion:
    """Una transferencia de ``valor`` en tu moneda (el pago de un préstamo, la compra de un bien, el aporte a una
    meta): lo que sale y lo que llega, cada uno en la moneda de su cuenta, al tipo de cambio de ese día."""
    de, a = divisas.moneda_de(libro, origen_id), divisas.moneda_de(libro, destino_id)
    if not divisas.en_otra_moneda(libro, origen_id):
        return construir_transferencia(fecha, origen_id, destino_id, valor, descripcion, notas, tipo=tipo)
    centavos = a_centavos(valor)
    sale = divisas.desde_base(centavos, divisas.tipo_o_error(libro, de, fecha))
    if a == de:
        return construir_transferencia(fecha, origen_id, destino_id, a_pesos(sale), descripcion, notas, tipo=tipo)
    llega = centavos if not divisas.en_otra_moneda(libro, destino_id) else divisas.desde_base(
        centavos, divisas.tipo_o_error(libro, a, fecha))
    return divisas.transferencia(libro, fecha, origen_id, destino_id, a_pesos(sale), a_pesos(llega), descripcion,
                                 notas, tipo_operacion=tipo)


def construir_por_llegada(
    libro: Libro, fecha: date, origen_id: str, destino_id: str, llega, descripcion: str = "", notas: str = "", *,
    tipo: TipoOperacion = TipoOperacion.TRANSFERENCIA,
) -> Operacion:
    """Una transferencia de la que sabes lo que llegó (en la moneda del destino), como la ve un estado de cuenta de
    la cuenta que la recibe; lo que salió se calcula con el tipo de cambio de ese día."""
    de, a = divisas.moneda_de(libro, origen_id), divisas.moneda_de(libro, destino_id)
    if de == a:
        return construir_transferencia(fecha, origen_id, destino_id, llega, descripcion, notas, tipo=tipo)
    centavos = a_centavos(llega)
    valor = centavos if not divisas.en_otra_moneda(libro, destino_id) else divisas.a_base(
        centavos, divisas.tipo_o_error(libro, a, fecha))
    sale = valor if not divisas.en_otra_moneda(libro, origen_id) else divisas.desde_base(
        valor, divisas.tipo_o_error(libro, de, fecha))
    return divisas.transferencia(libro, fecha, origen_id, destino_id, a_pesos(sale), llega, descripcion, notas,
                                 tipo_operacion=tipo)


def registrar_por_valor(libro: Libro, fecha: date, origen_id: str, destino_id: str, valor, descripcion: str = "",
                        notas: str = "") -> Operacion:
    """:func:`construir_por_valor` y la guarda."""
    return libro.agregar_operacion(construir_por_valor(libro, fecha, origen_id, destino_id, valor, descripcion, notas))


def registrar_transferencia(
    libro: Libro, fecha: date, origen_id: str, destino_id: str, monto, descripcion: str = "", notas: str = "", *,
    llega=None,
) -> Operacion:
    """Mueve dinero entre dos cuentas propias (débito → ahorro, ahorro → débito…)."""
    return libro.agregar_operacion(construir_con_llegada(libro, fecha, origen_id, destino_id, monto, descripcion,
                                                         notas, llega=llega))


def registrar_pago_tarjeta(
    libro: Libro, fecha: date, origen_id: str, tarjeta_id: str, monto, descripcion: str = "", notas: str = "", *,
    llega=None,
) -> Operacion:
    """Paga (total o parcialmente) una tarjeta de crédito. No es un gasto."""
    return libro.agregar_operacion(construir_con_llegada(libro, fecha, origen_id, tarjeta_id, monto, descripcion,
                                                         notas, llega=llega, tipo=TipoOperacion.PAGO_TARJETA))


def origen_y_destino(op: Operacion) -> tuple[str, str]:
    """Cuenta de origen y de destino de una transferencia o pago de tarjeta."""
    if op.tipo not in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
        raise ErrorValidacion("El movimiento no es una transferencia.")
    origen, destino = sorted(op.partidas_de_cuenta(), key=lambda p: p.importe)
    return origen.cuenta_id, destino.cuenta_id
