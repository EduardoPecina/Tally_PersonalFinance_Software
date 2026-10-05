"""Transferencias entre cuentas propias y pagos de tarjeta.

Una transferencia es **una sola operación** con dos partidas de cuenta y
ninguna de categoría: nunca puede contar como gasto ni como ingreso.
"""

from __future__ import annotations

from datetime import date

from motor.dinero import a_centavos
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


def registrar_transferencia(
    libro: Libro, fecha: date, origen_id: str, destino_id: str, monto, descripcion: str = "", notas: str = ""
) -> Operacion:
    """Mueve dinero entre dos cuentas propias (débito → ahorro, ahorro → débito…)."""
    return libro.agregar_operacion(construir_transferencia(fecha, origen_id, destino_id, monto, descripcion, notas))


def registrar_pago_tarjeta(
    libro: Libro, fecha: date, origen_id: str, tarjeta_id: str, monto, descripcion: str = "", notas: str = ""
) -> Operacion:
    """Paga (total o parcialmente) una tarjeta de crédito. No es un gasto."""
    return libro.agregar_operacion(construir_pago_tarjeta(fecha, origen_id, tarjeta_id, monto, descripcion, notas))


def origen_y_destino(op: Operacion) -> tuple[str, str]:
    """Cuenta de origen y de destino de una transferencia o pago de tarjeta."""
    if op.tipo not in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
        raise ErrorValidacion("El movimiento no es una transferencia.")
    origen, destino = sorted(op.partidas_de_cuenta(), key=lambda p: p.importe)
    return origen.cuenta_id, destino.cuenta_id
