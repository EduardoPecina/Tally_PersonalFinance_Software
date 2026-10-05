"""Tarjetas de crédito: deuda, crédito disponible y ciclos de corte.

Una TDC es una cuenta más. Una compra con ella es un gasto en la fecha de la
compra; pagarla es una transferencia (ver ``motor.transferencias``).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Cuenta, Operacion, TipoCuenta
from motor.movimientos import actualizar_saldo


def deuda(libro: Libro, tarjeta_id: str, al: date | None = None) -> Decimal:
    """Lo que se debe en la tarjeta (0 si tiene saldo a favor)."""
    _tarjeta(libro, tarjeta_id)
    return a_pesos(max(0, -libro.saldo_centavos(tarjeta_id, al)))


def credito_disponible(libro: Libro, tarjeta_id: str, al: date | None = None) -> Decimal | None:
    """Límite + saldo. ``None`` si la tarjeta no tiene límite registrado."""
    tarjeta = _tarjeta(libro, tarjeta_id)
    if tarjeta.limite_credito is None:
        return None
    return a_pesos(tarjeta.limite_credito + libro.saldo_centavos(tarjeta_id, al))


def actualizar_deuda(libro: Libro, tarjeta_id: str, deuda_real, fecha: date) -> Operacion | None:
    """Ajusta la tarjeta para que su deuda en ``fecha`` sea ``deuda_real``."""
    _tarjeta(libro, tarjeta_id)
    return actualizar_saldo(libro, tarjeta_id, -a_pesos(a_centavos(deuda_real)), fecha)


# ------------------------------------------------------------------- ciclos


def _dia_en_mes(anio: int, mes: int, dia: int) -> date:
    """El día indicado del mes, o el último si el mes es más corto."""
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def _mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def _mes_anterior(anio: int, mes: int) -> tuple[int, int]:
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def ciclo_de(fecha: date, dia_corte: int) -> tuple[date, date]:
    """Primer y último día del ciclo que contiene ``fecha``.

    El ciclo termina el día de corte (incluido). Con corte el día 3, el 10 de
    julio pertenece al ciclo 4 jul – 3 ago.
    """
    corte = _dia_en_mes(fecha.year, fecha.month, dia_corte)
    if fecha > corte:
        corte = _dia_en_mes(*_mes_siguiente(fecha.year, fecha.month), dia_corte)
    corte_anterior = _dia_en_mes(*_mes_anterior(corte.year, corte.month), dia_corte)
    return corte_anterior + timedelta(days=1), corte


@dataclass(frozen=True, slots=True)
class ResumenCiclo:
    inicio: date
    fin: date  # día de corte
    fecha_limite_pago: date | None
    saldo_inicial: Decimal  # saldo al cerrar el ciclo anterior (negativo = deuda)
    cargos: Decimal  # compras, comisiones… (positivo)
    abonos: Decimal  # pagos y devoluciones dentro del ciclo (positivo)
    saldo_al_corte: Decimal
    deuda_al_corte: Decimal
    pagado_despues_del_corte: Decimal
    por_liquidar: Decimal  # lo que falta pagar de la deuda al corte


def resumen_ciclo(libro: Libro, tarjeta_id: str, fecha: date | None = None, *, hasta: date | None = None) -> ResumenCiclo:
    """Estado del ciclo de la tarjeta que contiene ``fecha`` (hoy por defecto).

    ``hasta`` limita los pagos posteriores al corte que se toman en cuenta
    para calcular lo que falta por liquidar (hoy por defecto).
    """
    tarjeta = _tarjeta(libro, tarjeta_id)
    if tarjeta.dia_corte is None:
        raise ErrorValidacion(f"La tarjeta «{tarjeta.nombre}» no tiene día de corte registrado.")
    hoy = libro.hoy()
    inicio, fin = ciclo_de(fecha or hoy, tarjeta.dia_corte)
    hasta = hasta or hoy

    cargos = abonos = pagos_posteriores = 0
    for op in libro.operaciones(desde=inicio):
        for p in op.partidas:
            if p.cuenta_id != tarjeta_id:
                continue
            if op.fecha <= fin:
                if p.importe < 0:
                    cargos -= p.importe
                else:
                    abonos += p.importe
            elif op.fecha <= hasta and p.importe > 0:
                pagos_posteriores += p.importe

    saldo_al_corte = libro.saldo_centavos(tarjeta_id, fin)
    deuda_al_corte = max(0, -saldo_al_corte)
    return ResumenCiclo(
        inicio=inicio,
        fin=fin,
        fecha_limite_pago=_fecha_limite(fin, tarjeta.dia_pago),
        saldo_inicial=a_pesos(libro.saldo_centavos(tarjeta_id, inicio - timedelta(days=1))),
        cargos=a_pesos(cargos),
        abonos=a_pesos(abonos),
        saldo_al_corte=a_pesos(saldo_al_corte),
        deuda_al_corte=a_pesos(deuda_al_corte),
        pagado_despues_del_corte=a_pesos(pagos_posteriores),
        por_liquidar=a_pesos(max(0, deuda_al_corte - pagos_posteriores)),
    )


def ciclo_por_pagar(libro: Libro, tarjeta_id: str, hoy: date | None = None) -> ResumenCiclo | None:
    """El último ciclo ya cortado: el que hay que liquidar. ``None`` si la tarjeta no tiene día de corte."""
    tarjeta = _tarjeta(libro, tarjeta_id)
    if tarjeta.dia_corte is None:
        return None
    hoy = hoy or libro.hoy()
    inicio, fin = ciclo_de(hoy, tarjeta.dia_corte)
    return resumen_ciclo(libro, tarjeta_id, hoy if fin == hoy else inicio - timedelta(days=1), hasta=hoy)


def ciclo_actual(libro: Libro, tarjeta_id: str, hoy: date | None = None) -> ResumenCiclo | None:
    """El ciclo en curso (aún sin cortar). ``None`` si la tarjeta no tiene día de corte."""
    if _tarjeta(libro, tarjeta_id).dia_corte is None:
        return None
    hoy = hoy or libro.hoy()
    return resumen_ciclo(libro, tarjeta_id, hoy, hasta=hoy)


def _fecha_limite(corte: date, dia_pago: int | None) -> date | None:
    if dia_pago is None:
        return None
    candidata = _dia_en_mes(corte.year, corte.month, dia_pago)
    if candidata <= corte:
        candidata = _dia_en_mes(*_mes_siguiente(corte.year, corte.month), dia_pago)
    return candidata


def _tarjeta(libro: Libro, tarjeta_id: str) -> Cuenta:
    cuenta = libro.cuenta(tarjeta_id)
    if cuenta.tipo is not TipoCuenta.CREDITO:
        raise ErrorValidacion(f"«{cuenta.nombre}» no es una tarjeta de crédito.")
    return cuenta
