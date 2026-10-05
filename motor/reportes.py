"""Cifras derivadas: resúmenes del periodo, indicadores y quincenas.

Ingresos y gastos se calculan **solo** a partir de partidas de categoría; las
transferencias y pagos de tarjeta no tienen ninguna y por eso nunca cuentan.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from motor.dinero import a_pesos
from motor.libro import Libro
from motor.modelo import (
    TIPOS_AHORRO,
    TIPOS_EN_CUENTAS,
    ClaseCategoria,
    Operacion,
    TipoCuenta,
    TipoOperacion,
)

SIN_GRUPO = "Sin grupo"


def rango_mes(anio: int, mes: int) -> tuple[date, date]:
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


# ------------------------------------------------------------------ resumen


@dataclass(frozen=True, slots=True)
class Resumen:
    ingresos: Decimal
    gastos: Decimal
    ahorro_real: Decimal  # ingresos − gastos
    apartado_a_ahorro: Decimal  # transferencias netas hacia ahorro/inversión
    ajustes: Decimal  # ajustes de saldo, mostrados aparte


def resumen(libro: Libro, desde: date, hasta: date) -> Resumen:
    ingresos = gastos = apartado = ajustes = 0
    for op in libro.operaciones(desde, hasta):
        for p in op.partidas_de_categoria():
            clase = libro.categoria(p.categoria_id).clase
            if clase is ClaseCategoria.GASTO:
                gastos += p.importe
            elif clase is ClaseCategoria.INGRESO:
                ingresos -= p.importe
            elif op.tipo is TipoOperacion.AJUSTE:
                ajustes -= p.importe
        if op.tipo in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
            apartado += _hacia_ahorro(libro, op)
    return Resumen(
        ingresos=a_pesos(ingresos),
        gastos=a_pesos(gastos),
        ahorro_real=a_pesos(ingresos - gastos),
        apartado_a_ahorro=a_pesos(apartado),
        ajustes=a_pesos(ajustes),
    )


def _hacia_ahorro(libro: Libro, op: Operacion) -> int:
    """Centavos que entran (+) o salen (−) del ahorro desde otras cuentas."""
    partidas = op.partidas_de_cuenta()
    es_ahorro = [libro.cuenta(p.cuenta_id).tipo in TIPOS_AHORRO for p in partidas]
    if all(es_ahorro) or not any(es_ahorro):
        return 0
    return sum(p.importe for p, ahorro in zip(partidas, es_ahorro) if ahorro)


# ------------------------------------------------------------- por categoría


@dataclass(frozen=True, slots=True)
class TotalCategoria:
    categoria_id: str
    nombre: str
    grupo: str
    total: Decimal


def por_categoria(libro: Libro, desde: date, hasta: date, clase: ClaseCategoria) -> list[TotalCategoria]:
    """Totales por categoría, de mayor a menor. Los reembolsos restan."""
    signo = 1 if clase is ClaseCategoria.GASTO else -1
    totales: dict[str, int] = defaultdict(int)
    for op in libro.operaciones(desde, hasta):
        for p in op.partidas_de_categoria():
            if libro.categoria(p.categoria_id).clase is clase:
                totales[p.categoria_id] += signo * p.importe
    resultado = [
        TotalCategoria(cat_id, libro.categoria(cat_id).nombre, _nombre_grupo(libro, cat_id), a_pesos(total))
        for cat_id, total in totales.items()
    ]
    return sorted(resultado, key=lambda t: (-t.total, t.nombre.casefold()))


def gastos_por_categoria(libro: Libro, desde: date, hasta: date) -> list[TotalCategoria]:
    return por_categoria(libro, desde, hasta, ClaseCategoria.GASTO)


def ingresos_por_categoria(libro: Libro, desde: date, hasta: date) -> list[TotalCategoria]:
    return por_categoria(libro, desde, hasta, ClaseCategoria.INGRESO)


def gastos_por_grupo(libro: Libro, desde: date, hasta: date) -> dict[str, Decimal]:
    totales: dict[str, Decimal] = defaultdict(Decimal)
    for t in gastos_por_categoria(libro, desde, hasta):
        totales[t.grupo] += t.total
    return dict(sorted(totales.items(), key=lambda kv: -kv[1]))


def gastos_por_cuenta(libro: Libro, desde: date, hasta: date) -> dict[str, Decimal]:
    """Gasto atribuido a la cuenta con la que se pagó (id de cuenta → total)."""
    totales: dict[str, int] = defaultdict(int)
    for op in libro.operaciones(desde, hasta):
        gasto = sum(
            p.importe
            for p in op.partidas_de_categoria()
            if libro.categoria(p.categoria_id).clase is ClaseCategoria.GASTO
        )
        if gasto:
            (cuenta,) = op.partidas_de_cuenta()
            totales[cuenta.cuenta_id] += gasto
    return {cuenta_id: a_pesos(total) for cuenta_id, total in totales.items()}


def _nombre_grupo(libro: Libro, categoria_id: str) -> str:
    grupo_id = libro.categoria(categoria_id).grupo_id
    return libro.grupo(grupo_id).nombre if grupo_id else SIN_GRUPO


# --------------------------------------------------------------- indicadores


@dataclass(frozen=True, slots=True)
class Indicadores:
    dinero_disponible: Decimal
    total_en_cuentas: Decimal
    te_deben: Decimal
    deuda_tarjetas: Decimal
    patrimonio_neto: Decimal


def indicadores(libro: Libro, al: date | None = None) -> Indicadores:
    """Situación a una fecha. Las cuentas archivadas con saldo también cuentan."""
    disponible = en_cuentas = te_deben = deuda = patrimonio = 0
    for cuenta in libro.cuentas():
        saldo = libro.saldo_centavos(cuenta.id, al)
        patrimonio += saldo
        if cuenta.en_disponible:
            disponible += saldo
        if cuenta.tipo in TIPOS_EN_CUENTAS:
            en_cuentas += saldo
        elif cuenta.tipo is TipoCuenta.POR_COBRAR:
            te_deben += saldo
        elif cuenta.tipo is TipoCuenta.CREDITO and saldo < 0:
            deuda -= saldo
    return Indicadores(
        dinero_disponible=a_pesos(disponible),
        total_en_cuentas=a_pesos(en_cuentas),
        te_deben=a_pesos(te_deben),
        deuda_tarjetas=a_pesos(deuda),
        patrimonio_neto=a_pesos(patrimonio),
    )


# ------------------------------------------------------------------ hechos


def hechos(libro: Libro, desde: date | None = None, hasta: date | None = None) -> list[dict]:
    """Una fila por partida de categoría: la base de reportes y tablas dinámicas.

    ``monto`` va en sentido natural: los gastos y los ingresos son positivos y
    los reembolsos, negativos.
    """
    filas = []
    for op in libro.operaciones(desde, hasta):
        cuentas = op.partidas_de_cuenta()
        cuenta = libro.cuenta(cuentas[0].cuenta_id) if len(cuentas) == 1 else None
        for p in op.partidas_de_categoria():
            categoria = libro.categoria(p.categoria_id)
            monto = p.importe if categoria.clase is ClaseCategoria.GASTO else -p.importe
            filas.append(
                {
                    "operacion_id": op.id,
                    "fecha": op.fecha,
                    "anio": op.fecha.year,
                    "mes": op.fecha.month,
                    "tipo": op.tipo.value,
                    "cuenta": cuenta.nombre if cuenta else "",
                    "tipo_cuenta": cuenta.tipo.value if cuenta else "",
                    "categoria": categoria.nombre,
                    "clase": categoria.clase.value,
                    "grupo": _nombre_grupo(libro, categoria.id),
                    "monto": a_pesos(monto),
                    "descripcion": op.descripcion,
                }
            )
    return filas


# ---------------------------------------------------------------- quincenas


def _es_ingreso_principal(libro: Libro, op: Operacion) -> bool:
    return op.tipo is TipoOperacion.INGRESO and any(
        libro.categoria(p.categoria_id).principal for p in op.partidas_de_categoria()
    )


def fechas_de_ingreso_principal(libro: Libro) -> list[date]:
    return sorted({op.fecha for op in libro.operaciones() if _es_ingreso_principal(libro, op)})


def quincena_de(libro: Libro, fecha: date) -> tuple[date, date | None] | None:
    """Periodo de ingreso principal a ingreso principal que contiene ``fecha``.

    Devuelve ``(inicio, fin)``; ``fin`` es ``None`` si aún no llega el
    siguiente ingreso. ``None`` si ``fecha`` es anterior al primer ingreso.
    """
    fechas = fechas_de_ingreso_principal(libro)
    inicio = next((f for f in reversed(fechas) if f <= fecha), None)
    if inicio is None:
        return None
    siguiente = next((f for f in fechas if f > inicio), None)
    return inicio, (siguiente - timedelta(days=1) if siguiente else None)


@dataclass(frozen=True, slots=True)
class Sobrante:
    fecha: date  # día en que llegó el ingreso principal
    operacion_id: str
    sobrante: Decimal  # saldo de la cuenta justo antes de recibirlo


def sobrantes_de_quincena(libro: Libro, cuenta_id: str) -> list[Sobrante]:
    """Lo que quedaba en la cuenta antes de cada ingreso principal (nómina).

    Sustituye a las filas «HISTORICO» del Excel. Respeta el orden de captura
    dentro de un mismo día.
    """
    libro.cuenta(cuenta_id)
    resultado = []
    saldo = 0
    for op in libro.operaciones():
        cambio = sum(p.importe for p in op.partidas if p.cuenta_id == cuenta_id)
        if cambio and _es_ingreso_principal(libro, op):
            resultado.append(Sobrante(op.fecha, op.id, a_pesos(saldo)))
        saldo += cambio
    return resultado
