"""Sacar efectivo (cajero, ventanilla o disposición con tarjeta de crédito).

Si tienes una cuenta de **Efectivo**, sacar dinero del banco no es un gasto: el dinero pasa de tu banco a tu cartera,
igual que una transferencia al ahorro. El gasto es lo que pagas después con ese efectivo. Por eso, en cuanto tienes una
cuenta de efectivo activa:

- al **registrar** un gasto en RETIROS DE EFECTIVO se guarda como transferencia a tu cuenta de efectivo;
- al **importar** del banco, los retiros en cajero se sugieren como paso a tu cuenta de efectivo;
- lo que ya registraste como gasto en RETIROS DE EFECTIVO (desde que llevas tu efectivo en TALLY) se puede pasar a
  tu cuenta de efectivo de un clic (Historial y Salud de tus datos).

Sin cuenta de efectivo, RETIROS DE EFECTIVO sigue siendo un gasto: es la forma sencilla de llevarlo para quien no
anota en qué gasta el efectivo.
"""

from __future__ import annotations

from datetime import date

from motor import categorias
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Cuenta, Operacion, TipoCuenta, TipoOperacion
from motor.transferencias import construir_transferencia

SUBCATEGORIA = "RETIROS DE EFECTIVO"


def subcategoria(libro: Libro) -> str | None:
    """El id de la subcategoría RETIROS DE EFECTIVO (si existe)."""
    categoria = categorias.buscar(libro, SUBCATEGORIA)
    return categoria.id if categoria is not None else None


def es_retiro(libro: Libro, categoria_id: str | None) -> bool:
    return categoria_id is not None and categoria_id == subcategoria(libro)


def cuenta(libro: Libro, excepto: str | None = None) -> Cuenta | None:
    """Tu cuenta de efectivo activa (la primera, si tienes varias), distinta de ``excepto``."""
    return next((c for c in libro.cuentas()
                 if c.activa and c.tipo is TipoCuenta.EFECTIVO and c.id != excepto), None)


def destino_para(libro: Libro, origen_id: str, categoria_id: str | None) -> Cuenta | None:
    """Si un gasto con esa subcategoría en realidad es sacar efectivo: la cuenta de efectivo a la que va."""
    return cuenta(libro, excepto=origen_id) if es_retiro(libro, categoria_id) else None


def registrar(libro: Libro, fecha: date, origen_id: str, monto, descripcion: str = "", notas: str = "", *,
              destino_id: str | None = None) -> Operacion:
    """Sacar efectivo: pasa ``monto`` de tu banco (o tarjeta) a tu cuenta de efectivo. No es gasto."""
    destino = libro.cuenta(destino_id) if destino_id else cuenta(libro, excepto=origen_id)
    if destino is None:
        raise ErrorValidacion("No tienes una cuenta de efectivo activa: agrégala en Cuentas.")
    if destino.tipo is not TipoCuenta.EFECTIVO:
        raise ErrorValidacion(f"«{destino.nombre}» no es una cuenta de efectivo.")
    return libro.agregar_operacion(construir_transferencia(fecha, origen_id, destino.id, monto,
                                                           descripcion or "Retiro de efectivo", notas))


# ------------------------------------------------------------------ lo que ya registraste como gasto


def desde(libro: Libro, efectivo: Cuenta) -> date:
    """Desde cuándo llevas tu efectivo en TALLY: la fecha de su saldo inicial (o de cuando la creaste). Los retiros
    de antes ya están dentro de ese saldo inicial: pasarlos inflaría tu efectivo."""
    from motor.cuentas import saldo_inicial

    registrado = saldo_inicial(libro, efectivo.id)
    return registrado[1] if registrado else efectivo.fecha_creacion


def convertible(libro: Libro, op: Operacion) -> Cuenta | None:
    """Si ese movimiento es un retiro de efectivo guardado como gasto que conviene pasar a tu cuenta de efectivo:
    la cuenta a la que iría."""
    if op.tipo is not TipoOperacion.GASTO or op.msi or op.liquida:
        return None
    de_categoria, de_cuenta = op.partidas_de_categoria(), op.partidas_de_cuenta()
    if len(de_categoria) != 1 or len(de_cuenta) != 1 or not es_retiro(libro, de_categoria[0].categoria_id):
        return None
    efectivo = cuenta(libro, excepto=de_cuenta[0].cuenta_id)
    if efectivo is None or op.fecha < desde(libro, efectivo):
        return None
    return efectivo


def pendientes(libro: Libro) -> list[Operacion]:
    """Los retiros de efectivo guardados como gasto desde que llevas tu efectivo en TALLY."""
    retiro = subcategoria(libro)
    if retiro is None or cuenta(libro) is None:
        return []
    return [op for op in libro.operaciones()
            if any(p.categoria_id == retiro for p in op.partidas_de_categoria()) and convertible(libro, op)]


def convertir(libro: Libro, operacion_id: str) -> Operacion:
    """Pasa ese gasto a tu cuenta de efectivo: el mismo movimiento (fecha, importe, descripción, notas y
    comprobantes), ahora como transferencia."""
    from motor.movimientos import a_transferencia

    efectivo = convertible(libro, libro.operacion(operacion_id))
    if efectivo is None:
        raise ErrorValidacion("Ese movimiento no es un retiro de efectivo que se pueda pasar a tu cuenta de efectivo.")
    return a_transferencia(libro, operacion_id, efectivo.id)


def convertir_todos(libro: Libro) -> int:
    hechos = 0
    for op in pendientes(libro):
        convertir(libro, op.id)
        hechos += 1
    return hechos
