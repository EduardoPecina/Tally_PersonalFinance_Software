"""Cargos temporales: lo que te cobran para verificar tu tarjeta y te devuelven después.

Amazon, Uber, un hotel o una gasolinera a veces cobran $1 (o retienen un depósito) y lo regresan días o
semanas después. **No es gasto**: es dinero que te deben. Por eso se registra como transferencia de tu
cuenta a la cuenta POR RECUPERAR (tipo «Por cobrar», suma en «Te deben»):

- al cobrarlo: tu cuenta → POR RECUPERAR (el saldo de la tarjeta sube, ningún gasto se mueve);
- al devolverlo: POR RECUPERAR → tu cuenta (el movimiento guarda en ``liquida`` qué cargo devuelve);
- si nunca lo devuelven: un gasto pagado desde POR RECUPERAR, con la subcategoría que elijas.

Lo que aún no vuelve es :func:`pendientes`. Las devoluciones que no dicen qué cargo liquidan (por ejemplo,
las de la plantilla de carga) se emparejan con el cargo pendiente más antiguo del mismo importe.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from motor import cuentas, movimientos
from motor.dinero import a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Cuenta, Operacion, TipoCuenta, TipoOperacion
from motor.textos import clave
from motor.transferencias import construir_transferencia

NOMBRE_CUENTA = "POR RECUPERAR"
DIAS_PARA_RECLAMAR = 45


@dataclass(frozen=True, slots=True)
class CargoTemporal:
    """Un cargo que todavía no te devuelven."""

    operacion_id: str
    fecha: date
    cuenta_id: str          # la cuenta o tarjeta donde te lo cobraron
    cuenta: str
    descripcion: str
    monto: Decimal
    dias: int               # días desde el cargo
    vencido: bool           # ya pasó el plazo para reclamar


def cuenta(libro: Libro) -> Cuenta | None:
    """La cuenta POR RECUPERAR, si ya existe (aunque esté archivada)."""
    return next((c for c in libro.cuentas() if clave(c.nombre) == clave(NOMBRE_CUENTA)), None)


def asegurar_cuenta(libro: Libro, fecha: date | None = None) -> Cuenta:
    """La cuenta POR RECUPERAR: la crea (o la reactiva) la primera vez que hace falta."""
    existente = cuenta(libro)
    if existente is None:
        return cuentas.crear(libro, NOMBRE_CUENTA, TipoCuenta.POR_COBRAR, fecha_creacion=fecha,
                             notas="Cargos temporales que te van a devolver (verificaciones de tarjeta, depósitos…).")
    if existente.tipo is not TipoCuenta.POR_COBRAR:
        raise ErrorValidacion(f"Ya tienes una cuenta llamada «{existente.nombre}» que no es de tipo Por cobrar. "
                              "Cámbiale el nombre o el tipo para usar los cargos temporales.")
    if not existente.activa:
        existente = cuentas.reactivar(libro, existente.id)
    return existente


def registrar(libro: Libro, fecha: date, cuenta_id: str, monto, descripcion: str = "", notas: str = "") -> Operacion:
    """Un cargo que te van a devolver, cobrado en ``cuenta_id`` (débito, tarjeta de crédito…). No es gasto."""
    destino = asegurar_cuenta(libro, fecha)
    if cuenta_id == destino.id:
        raise ErrorValidacion("Elige la cuenta o tarjeta donde te hicieron el cargo.")
    op = construir_transferencia(fecha, cuenta_id, destino.id, monto, descripcion.strip() or "Cargo temporal", notas)
    return libro.agregar_operacion(op)


def pendientes(libro: Libro, hoy: date | None = None, dias_para_reclamar: int | None = None) -> list[CargoTemporal]:
    """Los cargos temporales que aún no te devuelven, del más antiguo al más reciente."""
    por_recuperar = cuenta(libro)
    if por_recuperar is None:
        return []
    hoy = hoy or libro.hoy()
    if dias_para_reclamar is None:
        dias_para_reclamar = libro.perfil.dias_para_reclamar if libro.perfil else DIAS_PARA_RECLAMAR
    ops = sorted(libro.operaciones(), key=lambda o: o.orden)
    liquidados = {op.liquida for op in ops if op.liquida}
    abiertos: list[Operacion] = []
    for op in ops:
        importe = _importe_en(op, por_recuperar.id)
        if importe > 0 and op.tipo is TipoOperacion.TRANSFERENCIA and op.id not in liquidados:
            abiertos.append(op)
        elif importe < 0 and not op.liquida:
            pareja = next((c for c in abiertos if _importe_en(c, por_recuperar.id) == -importe), None)
            if pareja is not None:
                abiertos.remove(pareja)
    resultado = []
    for op in abiertos:
        origen = _origen(op, por_recuperar.id)
        dias = (hoy - op.fecha).days
        resultado.append(CargoTemporal(
            operacion_id=op.id, fecha=op.fecha, cuenta_id=origen, cuenta=libro.cuenta(origen).nombre,
            descripcion=op.descripcion, monto=a_pesos(_importe_en(op, por_recuperar.id)), dias=dias,
            vencido=dias > dias_para_reclamar,
        ))
    return resultado


def vencidos(libro: Libro, hoy: date | None = None) -> list[CargoTemporal]:
    """Los que ya pasaron del plazo: conviene reclamarlos (para avisar en el Resumen)."""
    return [c for c in pendientes(libro, hoy) if c.vencido]


def devolver(libro: Libro, cargo_id: str, fecha: date, *, cuenta_id: str | None = None) -> Operacion:
    """Ya te lo devolvieron: regresa el dinero de POR RECUPERAR a la cuenta del cargo (u otra que indiques)."""
    cargo = _pendiente(libro, cargo_id)
    if fecha < cargo.fecha:
        raise ErrorValidacion("La devolución no puede ser antes del cargo.")
    op = construir_transferencia(fecha, cuenta(libro).id, cuenta_id or cargo.cuenta_id, cargo.monto,
                                 f"Devolución: {cargo.descripcion}"[:120])
    return libro.agregar_operacion(replace(op, liquida=cargo.operacion_id))


def pasar_a_gasto(libro: Libro, cargo_id: str, fecha: date, categoria_id: str) -> Operacion:
    """No te lo van a devolver: se vuelve gasto (en ``fecha``, con la subcategoría elegida)."""
    cargo = _pendiente(libro, cargo_id)
    if fecha < cargo.fecha:
        raise ErrorValidacion("La fecha no puede ser antes del cargo.")
    op = movimientos.construir(TipoOperacion.GASTO, fecha, cuenta(libro).id, categoria_id, cargo.monto,
                               cargo.descripcion, "Cargo temporal que no se devolvió.")
    return libro.agregar_operacion(replace(op, liquida=cargo.operacion_id))


def _pendiente(libro: Libro, cargo_id: str) -> CargoTemporal:
    cargo = next((c for c in pendientes(libro) if c.operacion_id == cargo_id), None)
    if cargo is None:
        raise ErrorValidacion("Ese cargo temporal ya no está pendiente.")
    return cargo


def _importe_en(op: Operacion, cuenta_id: str) -> int:
    return sum(p.importe for p in op.partidas if p.cuenta_id == cuenta_id)


def _origen(op: Operacion, cuenta_id: str) -> str:
    return next(p.cuenta_id for p in op.partidas_de_cuenta() if p.cuenta_id != cuenta_id)
