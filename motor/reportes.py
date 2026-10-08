"""Cifras derivadas: resúmenes del periodo, indicadores y quincenas.

Ingresos y gastos se calculan **solo** a partir de partidas de categoría; las
transferencias y pagos de tarjeta no tienen ninguna y por eso nunca cuentan.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from motor.dinero import a_pesos
from motor.libro import Libro
from motor.modelo import (
    CATEGORIA_AJUSTE,
    TIPOS_AHORRO,
    TIPOS_EN_CUENTAS,
    ClaseCategoria,
    Operacion,
    TipoCuenta,
    TipoOperacion,
)

SIN_GRUPO = "Sin clasificación"
SIN_RUBRO = "SIN CATEGORIA"


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
            elif p.categoria_id == CATEGORIA_AJUSTE:
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


@dataclass(frozen=True, slots=True)
class Comparacion:
    actual: Resumen
    anterior: Resumen
    diferencia: Resumen  # actual − anterior, campo por campo (hasta ``al``, si el periodo va a la mitad)
    desde_anterior: date
    hasta_anterior: date
    al: date | None = None  # el periodo va a la mitad: se comparó hasta este día con los mismos días del anterior


def comparar(libro: Libro, desde: date, hasta: date, hoy: date | None = None) -> Comparacion:
    """Resumen del periodo frente al periodo anterior ("¿gasté más que el mes pasado?").

    Si ``hoy`` cae dentro del periodo (el mes va a la mitad), lo que llevas se compara con los mismos días del
    periodo anterior: el 7 de octubre, del 1 al 7 de octubre contra del 1 al 7 de septiembre. Así a principio de
    mes no parece que gastaste mucho menos solo porque el mes pasado ya terminó.
    """
    desde_ant, hasta_ant = periodo_anterior(desde, hasta)
    actual = base = resumen(libro, desde, hasta)
    al = hoy if hoy is not None and desde <= hoy < hasta else None
    if al is not None:
        hasta_ant = min(hasta_ant, _dia_equivalente(al, desde, desde_ant))
        base = resumen(libro, desde, al)
    anterior = resumen(libro, desde_ant, hasta_ant)
    diferencia = Resumen(*(getattr(base, f) - getattr(anterior, f) for f in Resumen.__dataclass_fields__))
    return Comparacion(actual, anterior, diferencia, desde_ant, hasta_ant, al)


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
    """Total de una subcategoría (``nombre``), con su categoría (``rubro``) y su clasificación (``grupo``)."""

    categoria_id: str
    nombre: str
    grupo: str
    total: Decimal
    rubro: str = SIN_RUBRO


def por_categoria(libro: Libro, desde: date, hasta: date, clase: ClaseCategoria) -> list[TotalCategoria]:
    """Totales por categoría, de mayor a menor. Los reembolsos restan."""
    signo = 1 if clase is ClaseCategoria.GASTO else -1
    totales: dict[str, int] = defaultdict(int)
    for op in libro.operaciones(desde, hasta):
        for p in op.partidas_de_categoria():
            if libro.categoria(p.categoria_id).clase is clase:
                totales[p.categoria_id] += signo * p.importe
    resultado = [
        TotalCategoria(cat_id, libro.categoria(cat_id).nombre, _nombre_grupo(libro, cat_id), a_pesos(total),
                       _nombre_rubro(libro, cat_id))
        for cat_id, total in totales.items()
    ]
    return sorted(resultado, key=lambda t: (-t.total, t.nombre.casefold()))


def gastos_por_categoria(libro: Libro, desde: date, hasta: date) -> list[TotalCategoria]:
    return por_categoria(libro, desde, hasta, ClaseCategoria.GASTO)


def ingresos_por_categoria(libro: Libro, desde: date, hasta: date) -> list[TotalCategoria]:
    return por_categoria(libro, desde, hasta, ClaseCategoria.INGRESO)


def gastos_por_rubro(libro: Libro, desde: date, hasta: date) -> dict[str, Decimal]:
    """Gastos por categoría que agrupa (SALUD, TECNOLOGIA…), de mayor a menor."""
    totales: dict[str, Decimal] = defaultdict(Decimal)
    for t in gastos_por_categoria(libro, desde, hasta):
        totales[t.rubro] += t.total
    return dict(sorted(totales.items(), key=lambda kv: -kv[1]))


@dataclass(frozen=True, slots=True)
class AvancePresupuesto:
    rubro_id: str
    nombre: str
    presupuesto: Decimal
    gastado: Decimal

    @property
    def restante(self) -> Decimal:
        return self.presupuesto - self.gastado

    @property
    def avance(self) -> Decimal:
        """Fracción usada (1 = todo el presupuesto; puede pasar de 1)."""
        return (self.gastado / self.presupuesto).quantize(Decimal("0.0001")) if self.presupuesto else Decimal(0)


def presupuestos(libro: Libro, desde: date, hasta: date) -> list[AvancePresupuesto]:
    """Cuánto se ha gastado de cada categoría con presupuesto, en el periodo (normalmente el mes)."""
    gastado = gastos_por_rubro(libro, desde, hasta)
    return [
        AvancePresupuesto(r.id, r.nombre, a_pesos(r.presupuesto), gastado.get(r.nombre, Decimal("0.00")))
        for r in libro.rubros() if r.presupuesto
    ]


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


def _nombre_rubro(libro: Libro, categoria_id: str) -> str:
    rubro_id = libro.categoria(categoria_id).rubro_id
    return libro.rubro(rubro_id).nombre if rubro_id else SIN_RUBRO


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
    from motor import bienes

    indicadores_ = _indicadores(libro, {c.id: libro.saldo_centavos(c.id, al) for c in libro.cuentas()})
    ajuste = bienes.ajuste_de_valor(libro, al or libro.hoy()) if libro.bienes() else 0
    return replace(indicadores_, patrimonio_neto=indicadores_.patrimonio_neto + a_pesos(ajuste))


def _indicadores(libro: Libro, saldos: dict[str, int]) -> Indicadores:
    disponible = en_cuentas = te_deben = deuda = patrimonio = 0
    for cuenta in libro.cuentas():
        saldo = saldos.get(cuenta.id, 0)
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


@dataclass(frozen=True, slots=True)
class PuntoEvolucion:
    fecha: date
    patrimonio_neto: Decimal
    dinero_disponible: Decimal
    deuda_tarjetas: Decimal


def evolucion(libro: Libro, desde: date, hasta: date) -> list[PuntoEvolucion]:
    """Patrimonio, disponible y deuda al cierre de cada día, semana o mes del rango.

    El paso se elige solo según la longitud del rango (diario hasta ~3 meses,
    semanal hasta ~1 año, mensual después). El último punto siempre es ``hasta``.
    """
    if hasta < desde:
        desde, hasta = hasta, desde
    dias = (hasta - desde).days
    if dias <= 93:
        puntos = [desde + timedelta(days=i) for i in range(dias + 1)]
    elif dias <= 400:
        puntos = [desde + timedelta(days=i) for i in range(6, dias + 1, 7)]
    else:
        puntos, actual = [], date(desde.year, desde.month, 1)
        while actual <= hasta:
            fin_mes = rango_mes(actual.year, actual.month)[1]
            if fin_mes >= desde:
                puntos.append(min(fin_mes, hasta))
            actual = fin_mes + timedelta(days=1)
    if not puntos or puntos[-1] != hasta:
        puntos.append(hasta)

    from motor import bienes

    con_bienes = bool(libro.bienes())     # la depreciación y los avalúos también cambian el patrimonio
    saldos: dict[str, int] = defaultdict(int)
    operaciones = libro.operaciones(hasta=hasta)
    resultado, i = [], 0
    for punto in puntos:
        while i < len(operaciones) and operaciones[i].fecha <= punto:
            for p in operaciones[i].partidas_de_cuenta():
                saldos[p.cuenta_id] += p.importe
            i += 1
        ind = _indicadores(libro, saldos)
        patrimonio = ind.patrimonio_neto + (a_pesos(bienes.ajuste_de_valor(libro, punto)) if con_bienes else 0)
        resultado.append(PuntoEvolucion(punto, patrimonio, ind.dinero_disponible, ind.deuda_tarjetas))
    return resultado


# ------------------------------------------------------------------ periodos

PERIODOS = {
    "mes_actual": "Este mes",
    "mes_anterior": "Mes pasado",
    "quincena": "Esta quincena",
    "anio": "Este año",
    "12_meses": "Últimos 12 meses",
}


def rango_periodo(libro: Libro, clave: str, hoy: date | None = None) -> tuple[date, date]:
    """Fechas (inclusivas) de un periodo con nombre. Por omisión, el mes actual."""
    hoy = hoy or libro.hoy()
    if clave == "mes_anterior":
        ultimo = date(hoy.year, hoy.month, 1) - timedelta(days=1)
        return rango_mes(ultimo.year, ultimo.month)
    if clave == "quincena":
        quincena = quincena_de(libro, hoy)
        if quincena is not None:
            return quincena[0], quincena[1] or hoy
        if hoy.day <= 15:
            return date(hoy.year, hoy.month, 1), date(hoy.year, hoy.month, 15)
        return date(hoy.year, hoy.month, 16), rango_mes(hoy.year, hoy.month)[1]
    if clave == "anio":
        return date(hoy.year, 1, 1), date(hoy.year, 12, 31)
    if clave == "12_meses":
        inicio = date(hoy.year - 1, hoy.month, 1) + timedelta(days=32)
        return date(inicio.year, inicio.month, 1), rango_mes(hoy.year, hoy.month)[1]
    return rango_mes(hoy.year, hoy.month)


def periodo_anterior(desde: date, hasta: date) -> tuple[date, date]:
    """El periodo inmediatamente anterior, para comparar ("¿gasté más que el mes pasado?"). Siempre termina el día
    antes de ``desde``:

    - meses completos (un mes, un año, los últimos 12 meses…): los mismos meses de antes. 2025 se compara con todo
      2024, aunque 2024 tenga 29 de febrero;
    - una quincena (del 1 al 15, o del 16 a fin de mes): la quincena anterior;
    - un año exacto (del 8 de octubre al 7 de octubre): el año anterior;
    - cualquier otro rango: uno de la misma duración.
    """
    fin = desde - timedelta(days=1)
    if desde.day == 1 and hasta == rango_mes(hasta.year, hasta.month)[1]:
        meses = (hasta.year - desde.year) * 12 + hasta.month - desde.month + 1
        return _sumar_meses(desde, -meses), fin
    if desde.day == 1 and hasta == desde.replace(day=15):                        # 1.ª quincena: la 2.ª de antes
        return fin.replace(day=16), fin
    if desde.day == 16 and hasta == rango_mes(desde.year, desde.month)[1]:       # 2.ª quincena: la 1.ª
        return fin.replace(day=1), fin
    if desde == _sumar_meses(hasta, -12) + timedelta(days=1):
        return _sumar_meses(desde, -12), fin
    return fin - (hasta - desde), fin


def _sumar_meses(dia: date, meses: int) -> date:
    """El mismo día, ``meses`` después (o antes); si ese mes es más corto, su último día (31 de marzo → 28 de
    febrero)."""
    total = dia.year * 12 + dia.month - 1 + meses
    anio, mes = divmod(total, 12)
    return date(anio, mes + 1, min(dia.day, calendar.monthrange(anio, mes + 1)[1]))


def _dia_equivalente(dia: date, desde: date, desde_anterior: date) -> date:
    """El día del periodo anterior que corresponde a ``dia``: el mismo día del mes si los periodos son de meses
    completos (el 7 de octubre → el 7 de septiembre), o los mismos días desde el inicio si no."""
    if desde.day == desde_anterior.day == 1:
        return _sumar_meses(dia, -((desde.year - desde_anterior.year) * 12 + desde.month - desde_anterior.month))
    return desde_anterior + (dia - desde)


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
                    "rubro": _nombre_rubro(libro, categoria.id),
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


def sobrantes_de_quincena(libro: Libro, cuenta_id: str, desde: date | None = None) -> list[Sobrante]:
    """Lo que quedaba en la cuenta antes de cada ingreso principal (nómina), desde ``desde`` (o de siempre).

    Sustituye a las filas «HISTORICO» del Excel. Respeta el orden de captura
    dentro de un mismo día.
    """
    libro.cuenta(cuenta_id)
    resultado = []
    saldo = libro.saldo_centavos(cuenta_id, desde - timedelta(days=1)) if desde is not None else 0
    for op in libro.operaciones(desde):
        cambio = sum(p.importe for p in op.partidas if p.cuenta_id == cuenta_id)
        if cambio and _es_ingreso_principal(libro, op):
            resultado.append(Sobrante(op.fecha, op.id, a_pesos(saldo)))
        saldo += cambio
    return resultado
