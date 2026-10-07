"""Contabilidad técnica: estados financieros de una persona, derivados de sus movimientos.

TALLY ya guarda cada movimiento en partida doble (``Operacion.partidas`` siempre suma cero). Aquí no se captura ni
se guarda nada nuevo: los cuatro reportes son **vistas** de esos mismos movimientos, así que si corriges uno, todos
cambian a la vez y siempre cuadran entre sí.

Convención (la de cualquier contabilidad): una partida positiva va al **Debe** y una negativa al **Haber**.

- Cuentas de débito, ahorro y efectivo → **Activo** (efectivo y bancos). Inversión → Activo (inversiones). Por
  cobrar → Activo (por cobrar): cuando te pagan, la cuenta queda en ceros (se compensa). Tarjeta de crédito →
  **Pasivo** a corto plazo.
- Subcategorías de ingreso y de gasto → **Resultados** (cada subcategoría es una subcuenta de su categoría).
- «SALDO INICIAL» → **Patrimonio** con el que empezaste a usar TALLY. «AJUSTE DE SALDO» → resultado (diferencias).
- Patrimonio = patrimonio inicial + resultados acumulados. Por la partida doble, Activo = Pasivo + Patrimonio
  siempre (si no, hay un error y el reporte lo dice).

Los rendimientos de las cuentas de inversión (los ajustes al valor oficial) se muestran aparte en el Estado de
Resultados, como cambio de valor, para no mezclarlos con lo que ganas y gastas en tu día a día.

El flujo de efectivo usa el **método directo**: cuánto efectivo entró y salió, y por qué. Cuenta como efectivo el
dinero en cuentas de débito, ahorro y efectivo (y las de tipo «otra» marcadas como disponibles).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from motor import reportes
from motor.dinero import a_pesos
from motor.libro import Libro
from motor.modelo import (
    CATEGORIA_AJUSTE,
    CATEGORIA_SALDO_INICIAL,
    ClaseCategoria,
    Cuenta,
    Operacion,
    TipoCuenta,
    TipoOperacion,
)

ACTIVO, PASIVO, PATRIMONIO, INGRESO, GASTO = "Activo", "Pasivo", "Patrimonio", "Ingreso", "Gasto"
DEUDORAS = (ACTIVO, GASTO)                  # su saldo natural está en el Debe

EFECTIVO_Y_BANCOS = "Efectivo y bancos"
INVERSIONES = "Inversiones"
POR_COBRAR = "Por cobrar"
OTROS_ACTIVOS = "Otros activos"
TARJETAS = "Tarjetas de crédito (corto plazo)"

PATRIMONIO_INICIAL = "Patrimonio inicial (saldos con los que empezaste)"
RESULTADOS_ANTERIORES = "Resultados de años anteriores"
RESULTADO_DEL_ANIO = "Resultado del año"
RESULTADOS_PREVIOS = "Resultados de periodos anteriores"
AJUSTES = "Ajustes de saldo"
RENDIMIENTOS_INVERSION = "Rendimientos y cambios de valor de tus inversiones"

_TIPOS_EFECTIVO = frozenset({TipoCuenta.DEBITO, TipoCuenta.AHORRO, TipoCuenta.EFECTIVO})


# --------------------------------------------------------------- clasificar


def es_efectivo(cuenta: Cuenta) -> bool:
    """Dinero que puedes usar: débito, ahorro, efectivo (y «otra» si la marcaste como disponible)."""
    return cuenta.tipo in _TIPOS_EFECTIVO or (cuenta.tipo is TipoCuenta.OTRA and cuenta.en_disponible)


def clasificar_cuenta(cuenta: Cuenta) -> tuple[str, str]:
    """(naturaleza, grupo dentro del Estado de Situación Financiera)."""
    if cuenta.tipo is TipoCuenta.CREDITO:
        return PASIVO, TARJETAS
    if es_efectivo(cuenta):
        return ACTIVO, EFECTIVO_Y_BANCOS
    if cuenta.tipo is TipoCuenta.INVERSION:
        return ACTIVO, INVERSIONES
    if cuenta.tipo is TipoCuenta.POR_COBRAR:
        return ACTIVO, POR_COBRAR
    return ACTIVO, OTROS_ACTIVOS


def _es_rendimiento_de_inversion(libro: Libro, op: Operacion) -> bool:
    return op.tipo is TipoOperacion.RENDIMIENTO and any(
        libro.cuenta(p.cuenta_id).tipo is TipoCuenta.INVERSION for p in op.partidas_de_cuenta())


def _resultados(libro: Libro, hasta: date, desde: date | None = None) -> int:
    """Resultado acumulado (ingresos − gastos ± ajustes) en centavos, de ``desde`` a ``hasta``."""
    total = 0
    for op in libro.operaciones(desde, hasta):
        for p in op.partidas_de_categoria():
            if p.categoria_id != CATEGORIA_SALDO_INICIAL:
                total -= p.importe
    return total


# ---------------------------------------------------------------- periodos

PERIODOS = {"anio": "Este año", "anio_pasado": "Año pasado", "mes": "Este mes", "mes_pasado": "Mes pasado",
            "12m": "Últimos 12 meses", "rango": "Elegir fechas"}
COMPARAR = {"anio_anterior": "El mismo periodo del año anterior", "anterior": "El periodo inmediato anterior",
            "no": "No comparar"}


def periodo(clave: str, hoy: date, elegido: tuple[date, date] | None = None) -> tuple[date, date]:
    """Fechas (inclusivas) de un periodo de :data:`PERIODOS`."""
    if clave == "anio_pasado":
        return date(hoy.year - 1, 1, 1), date(hoy.year - 1, 12, 31)
    if clave == "mes":
        return hoy.replace(day=1), hoy
    if clave == "mes_pasado":
        fin = hoy.replace(day=1) - timedelta(days=1)
        return fin.replace(day=1), fin
    if clave == "12m":
        return _un_anio_antes(hoy) + timedelta(days=1), hoy
    if clave == "rango" and elegido:
        return min(elegido), max(elegido)
    return date(hoy.year, 1, 1), hoy


def comparativo(desde: date, hasta: date, modo: str) -> tuple[date, date] | None:
    """El periodo contra el que se compara, o ``None``."""
    if modo == "no":
        return None
    if modo == "anterior":
        return reportes.periodo_anterior(desde, hasta)
    return _un_anio_antes(desde), _un_anio_antes(hasta)


def _un_anio_antes(dia: date) -> date:
    try:
        return dia.replace(year=dia.year - 1)
    except ValueError:                       # 29 de febrero
        return dia.replace(year=dia.year - 1, day=28)


# ----------------------------------------------- estado de situación financiera


@dataclass(frozen=True, slots=True)
class Renglon:
    """Un renglón de un estado financiero: un importe por cada fecha o periodo del reporte."""

    naturaleza: str
    grupo: str
    nombre: str
    importes: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class Situacion:
    fechas: tuple[date, ...]
    renglones: list[Renglon]            # activo, pasivo y patrimonio, en ese orden

    def total(self, naturaleza: str, grupo: str | None = None) -> tuple[Decimal, ...]:
        return _sumar_renglones([r for r in self.renglones
                                 if r.naturaleza == naturaleza and (grupo is None or r.grupo == grupo)],
                                len(self.fechas))

    def grupos(self, naturaleza: str) -> list[str]:
        return list(dict.fromkeys(r.grupo for r in self.renglones if r.naturaleza == naturaleza))

    @property
    def cuadra(self) -> bool:
        pasivo, patrimonio = self.total(PASIVO), self.total(PATRIMONIO)
        return all(a == p + c for a, p, c in zip(self.total(ACTIVO), pasivo, patrimonio))


_ORDEN_GRUPOS = (EFECTIVO_Y_BANCOS, INVERSIONES, POR_COBRAR, OTROS_ACTIVOS, TARJETAS)


def situacion(libro: Libro, fechas: list[date]) -> Situacion:
    """Activo, pasivo y patrimonio al final de cada una de ``fechas``. Las cuentas en ceros en todas se omiten."""
    renglones = []
    cuentas = sorted(libro.cuentas(), key=lambda c: (_ORDEN_GRUPOS.index(clasificar_cuenta(c)[1]), c.orden,
                                                     c.nombre.casefold()))
    for cuenta in cuentas:
        naturaleza, grupo = clasificar_cuenta(cuenta)
        saldos = tuple(libro.saldo_centavos(cuenta.id, f) for f in fechas)
        if any(saldos):
            signo = -1 if naturaleza == PASIVO else 1
            renglones.append(Renglon(naturaleza, grupo, cuenta.nombre, tuple(a_pesos(signo * s) for s in saldos)))
    inicial = tuple(-_saldo_categoria(libro, CATEGORIA_SALDO_INICIAL, f) for f in fechas)
    anteriores = tuple(_resultados(libro, date(f.year - 1, 12, 31)) for f in fechas)
    del_anio = tuple(_resultados(libro, f, date(f.year, 1, 1)) for f in fechas)
    for nombre, valores in ((PATRIMONIO_INICIAL, inicial), (RESULTADOS_ANTERIORES, anteriores),
                            (RESULTADO_DEL_ANIO, del_anio)):
        if any(valores):
            renglones.append(Renglon(PATRIMONIO, PATRIMONIO, nombre, tuple(a_pesos(v) for v in valores)))
    return Situacion(tuple(fechas), renglones)


def _saldo_categoria(libro: Libro, categoria_id: str, hasta: date, desde: date | None = None) -> int:
    return sum(p.importe for op in libro.operaciones(desde, hasta) for p in op.partidas_de_categoria()
               if p.categoria_id == categoria_id)


# ------------------------------------------------------- estado de resultados


@dataclass(frozen=True, slots=True)
class Resultados:
    periodos: tuple[tuple[date, date], ...]
    ingresos: list[Renglon]             # grupo = categoría, nombre = subcategoría
    gastos: list[Renglon]
    rendimientos_inversion: tuple[Decimal, ...]
    ajustes: tuple[Decimal, ...]

    def total_ingresos(self) -> tuple[Decimal, ...]:
        return _sumar_renglones(self.ingresos, len(self.periodos))

    def total_gastos(self) -> tuple[Decimal, ...]:
        return _sumar_renglones(self.gastos, len(self.periodos))

    def dia_a_dia(self) -> tuple[Decimal, ...]:
        """Ingresos − gastos: lo que te quedó de tu trabajo y tu vida diaria."""
        return tuple(i - g for i, g in zip(self.total_ingresos(), self.total_gastos()))

    def resultado(self) -> tuple[Decimal, ...]:
        """Resultado del periodo: cuánto cambió tu patrimonio por lo que ganaste, gastaste y ganaron tus
        inversiones (sin contar los saldos iniciales de cuentas nuevas)."""
        return tuple(d + r + a for d, r, a in zip(self.dia_a_dia(), self.rendimientos_inversion, self.ajustes))


def resultados(libro: Libro, periodos: list[tuple[date, date]]) -> Resultados:
    """Ingresos y gastos por categoría y subcategoría (los reembolsos restan del gasto) en cada periodo."""
    ingresos: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * len(periodos))
    gastos: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * len(periodos))
    rendimientos, ajustes = [0] * len(periodos), [0] * len(periodos)
    for i, (desde, hasta) in enumerate(periodos):
        for op in libro.operaciones(desde, hasta):
            inversion = _es_rendimiento_de_inversion(libro, op)
            for p in op.partidas_de_categoria():
                categoria = libro.categoria(p.categoria_id)
                if p.categoria_id == CATEGORIA_AJUSTE:
                    ajustes[i] -= p.importe
                elif inversion and categoria.clase is ClaseCategoria.INGRESO:
                    rendimientos[i] -= p.importe
                elif categoria.clase is ClaseCategoria.INGRESO:
                    ingresos[(reportes._nombre_rubro(libro, categoria.id), categoria.nombre)][i] -= p.importe
                elif categoria.clase is ClaseCategoria.GASTO:
                    gastos[(reportes._nombre_rubro(libro, categoria.id), categoria.nombre)][i] += p.importe
    return Resultados(tuple(periodos), _renglones(INGRESO, ingresos), _renglones(GASTO, gastos),
                      tuple(a_pesos(v) for v in rendimientos), tuple(a_pesos(v) for v in ajustes))


def _renglones(naturaleza: str, valores: dict[tuple[str, str], list[int]]) -> list[Renglon]:
    """Ordenados por el total de su categoría y luego por el suyo, de mayor a menor."""
    por_grupo: dict[str, int] = defaultdict(int)
    for (grupo, _), v in valores.items():
        por_grupo[grupo] += v[0]
    orden = sorted((k for k, v in valores.items() if any(v)),
                   key=lambda k: (-por_grupo[k[0]], k[0], -valores[k][0], k[1]))
    return [Renglon(naturaleza, g, n, tuple(a_pesos(x) for x in valores[(g, n)])) for g, n in orden]


# ------------------------------------------------------- flujo de efectivo

DIA_A_DIA = "Tu día a día"
FLUJO_TARJETAS = "Tarjetas de crédito"
FLUJO_INVERSIONES = "Inversiones"
FLUJO_POR_COBRAR = "Préstamos y cobros"
FLUJO_AJUSTES = "Cuentas nuevas y ajustes"
FLUJO_OTROS = "Otros movimientos"
SECCIONES_FLUJO = (DIA_A_DIA, FLUJO_TARJETAS, FLUJO_INVERSIONES, FLUJO_POR_COBRAR, FLUJO_AJUSTES, FLUJO_OTROS)


@dataclass(frozen=True, slots=True)
class Flujo:
    periodos: tuple[tuple[date, date], ...]
    inicial: tuple[Decimal, ...]        # efectivo al inicio de cada periodo
    renglones: list[Renglon]            # naturaleza = sección; importes con signo (+ entró, − salió)
    final: tuple[Decimal, ...]
    cuentas: list[str]                  # qué cuentas cuentan como efectivo
    gasto_con_tarjeta: tuple[Decimal, ...]   # gastos que aún no fueron salida de efectivo

    def total(self, seccion: str | None = None) -> tuple[Decimal, ...]:
        return _sumar_renglones([r for r in self.renglones if seccion is None or r.naturaleza == seccion],
                                len(self.periodos))

    def secciones(self) -> list[str]:
        presentes = {r.naturaleza for r in self.renglones}
        return [s for s in SECCIONES_FLUJO if s in presentes]

    @property
    def cuadra(self) -> bool:
        return all(i + t == f for i, t, f in zip(self.inicial, self.total(), self.final))


def flujo(libro: Libro, periodos: list[tuple[date, date]]) -> Flujo:
    """Cuánto efectivo había, cuánto entró y salió (y por qué) y cuánto quedó, en cada periodo."""
    efectivo = {c.id for c in libro.cuentas() if es_efectivo(c)}
    lineas: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * len(periodos))
    tarjeta = [0] * len(periodos)
    for i, (desde, hasta) in enumerate(periodos):
        for op in libro.operaciones(desde, hasta):
            if not any(p.cuenta_id in efectivo for p in op.partidas_de_cuenta()):
                if any(libro.cuenta(p.cuenta_id).tipo is TipoCuenta.CREDITO for p in op.partidas_de_cuenta()):
                    tarjeta[i] += sum(p.importe for p in op.partidas_de_categoria()
                                      if libro.categoria(p.categoria_id).clase is ClaseCategoria.GASTO)
                continue
            for p in op.partidas:
                if p.cuenta_id in efectivo:
                    continue
                lineas[_concepto_de_flujo(libro, p)][i] -= p.importe      # lo que la contrapartida da o recibe
    renglones = [Renglon(s, s, n, tuple(a_pesos(x) for x in v)) for (s, n), v in
                 sorted(lineas.items(), key=lambda kv: (SECCIONES_FLUJO.index(kv[0][0]), -abs(kv[1][0]), kv[0][1]))
                 if any(v)]
    inicial = tuple(a_pesos(sum(libro.saldo_centavos(c, d - timedelta(days=1)) for c in efectivo))
                    for d, _ in periodos)
    final = tuple(a_pesos(sum(libro.saldo_centavos(c, h) for c in efectivo)) for _, h in periodos)
    nombres = [libro.cuenta(c).nombre for c in sorted(efectivo, key=lambda c: libro.cuenta(c).nombre.casefold())]
    return Flujo(tuple(periodos), inicial, renglones, final, nombres, tuple(a_pesos(t) for t in tarjeta))


def _concepto_de_flujo(libro: Libro, p) -> tuple[str, str]:
    if p.categoria_id is not None:
        if p.categoria_id == CATEGORIA_SALDO_INICIAL:
            return FLUJO_AJUSTES, "Saldo inicial de cuentas nuevas"
        if p.categoria_id == CATEGORIA_AJUSTE:
            return FLUJO_AJUSTES, AJUSTES
        categoria = libro.categoria(p.categoria_id)
        que = "Cobraste" if categoria.clase is ClaseCategoria.INGRESO else "Pagaste"
        return DIA_A_DIA, f"{que}: {reportes._nombre_rubro(libro, categoria.id)}"
    cuenta = libro.cuenta(p.cuenta_id)
    if cuenta.tipo is TipoCuenta.CREDITO:
        return FLUJO_TARJETAS, cuenta.nombre
    if cuenta.tipo is TipoCuenta.INVERSION:
        return FLUJO_INVERSIONES, cuenta.nombre
    if cuenta.tipo is TipoCuenta.POR_COBRAR:
        return FLUJO_POR_COBRAR, cuenta.nombre
    return FLUJO_OTROS, cuenta.nombre


# ------------------------------------------------------ balanza de comprobación


@dataclass(frozen=True, slots=True)
class CuentaBalanza:
    naturaleza: str
    nombre: str                 # cuenta, o «CATEGORÍA › SUBCATEGORÍA»
    categoria: str              # para agrupar subcuentas («» en cuentas de balance)
    inicial: Decimal            # con signo: + deudor, − acreedor
    debe: Decimal
    haber: Decimal

    @property
    def final(self) -> Decimal:
        return self.inicial + self.debe - self.haber

    @property
    def variacion(self) -> Decimal:
        """Cuánto cambió, en el sentido natural de la cuenta (un pasivo que crece da positivo)."""
        cambio = self.final - self.inicial
        return cambio if self.naturaleza in DEUDORAS else -cambio

    @property
    def origen_aplicacion(self) -> str:
        """Solo en cuentas de balance: «Origen» si de ahí salieron recursos (bajó un activo o creció una deuda o
        tu patrimonio); «Aplicación» si ahí se usaron (creció un activo o bajó una deuda)."""
        cambio = self.final - self.inicial
        if self.naturaleza not in (ACTIVO, PASIVO, PATRIMONIO) or not cambio:
            return ""
        return "Aplicación" if cambio > 0 else "Origen"

    @property
    def lectura(self) -> str:
        if not self.final and (self.inicial or self.debe or self.haber) and self.naturaleza in (ACTIVO, PASIVO):
            return "En ceros: compensada ✓"
        v = self.variacion
        if self.naturaleza == ACTIVO:
            return "Tienes más" if v > 0 else "Tienes menos" if v < 0 else "Sin cambio"
        if self.naturaleza == PASIVO:
            return "Debes más" if v > 0 else "Debes menos ✓" if v < 0 else "Sin cambio"
        if self.naturaleza == PATRIMONIO:
            return "Aumentó" if v > 0 else "Disminuyó" if v < 0 else "Sin cambio"
        if self.nombre == AJUSTES:
            return "Diferencias corregidas"
        return "Ingreso del periodo" if self.naturaleza == INGRESO else "Gasto del periodo"


@dataclass(frozen=True, slots=True)
class Balanza:
    desde: date
    hasta: date
    cuentas: list[CuentaBalanza]

    def sumas(self) -> dict[str, Decimal]:
        """Las «sumas iguales»: deudor = acreedor al inicio y al final, y Debe = Haber en los movimientos."""
        s = defaultdict(Decimal)
        for c in self.cuentas:
            s["inicial_deudor"] += max(c.inicial, Decimal(0))
            s["inicial_acreedor"] += max(-c.inicial, Decimal(0))
            s["debe"] += c.debe
            s["haber"] += c.haber
            s["final_deudor"] += max(c.final, Decimal(0))
            s["final_acreedor"] += max(-c.final, Decimal(0))
        return dict(s)

    @property
    def cuadra(self) -> bool:
        s = self.sumas()
        return (s.get("inicial_deudor", 0) == s.get("inicial_acreedor", 0) and s.get("debe", 0) == s.get("haber", 0)
                and s.get("final_deudor", 0) == s.get("final_acreedor", 0))

    def por_categoria(self) -> Balanza:
        """Las subcuentas (subcategorías) sumadas en su cuenta (categoría)."""
        juntas: dict[tuple[str, str], list] = {}
        for c in self.cuentas:
            clave = (c.naturaleza, c.categoria or c.nombre)
            previo = juntas.setdefault(clave, [Decimal(0), Decimal(0), Decimal(0)])
            previo[0] += c.inicial
            previo[1] += c.debe
            previo[2] += c.haber
        return Balanza(self.desde, self.hasta, [CuentaBalanza(n, nombre, "", *v) for (n, nombre), v in juntas.items()])


_ORDEN_NATURALEZA = (ACTIVO, PASIVO, PATRIMONIO, INGRESO, GASTO)


def balanza(libro: Libro, desde: date, hasta: date) -> Balanza:
    """Saldo al inicio, movimientos (Debe y Haber) y saldo al final de cada cuenta y subcuenta del periodo.

    Las cuentas de resultados (ingresos, gastos, ajustes) empiezan cada periodo en cero: lo acumulado antes está en
    «Resultados de periodos anteriores», dentro del patrimonio.
    """
    antes = desde - timedelta(days=1)
    inicial: dict[tuple, int] = defaultdict(int)
    debe: dict[tuple, int] = defaultdict(int)
    haber: dict[tuple, int] = defaultdict(int)
    previos = 0
    for op in libro.operaciones(hasta=hasta):
        for p in op.partidas:
            clave = _clave_balanza(libro, p)
            if op.fecha <= antes:
                if clave[0] in (INGRESO, GASTO):
                    previos += p.importe
                else:
                    inicial[clave] += p.importe
            elif p.importe > 0:
                debe[clave] += p.importe
            else:
                haber[clave] -= p.importe
    if previos:
        inicial[(PATRIMONIO, RESULTADOS_PREVIOS, "")] += previos
    claves = sorted(set(inicial) | set(debe) | set(haber),
                    key=lambda k: (_ORDEN_NATURALEZA.index(k[0]), k[2], k[1]))
    filas = [CuentaBalanza(k[0], k[1], k[2], a_pesos(inicial[k]), a_pesos(debe[k]), a_pesos(haber[k]))
             for k in claves if inicial[k] or debe[k] or haber[k]]
    orden_cuentas = {c.nombre: i for i, c in enumerate(libro.cuentas())}
    filas.sort(key=lambda c: (_ORDEN_NATURALEZA.index(c.naturaleza), orden_cuentas.get(c.nombre, 10**6),
                              c.categoria, c.nombre))
    return Balanza(desde, hasta, filas)


def _clave_balanza(libro: Libro, p) -> tuple[str, str, str]:
    """(naturaleza, nombre, categoría)."""
    if p.cuenta_id is not None:
        cuenta = libro.cuenta(p.cuenta_id)
        return clasificar_cuenta(cuenta)[0], cuenta.nombre, ""
    if p.categoria_id == CATEGORIA_SALDO_INICIAL:
        return PATRIMONIO, PATRIMONIO_INICIAL, ""
    if p.categoria_id == CATEGORIA_AJUSTE:
        return GASTO, AJUSTES, ""
    categoria = libro.categoria(p.categoria_id)
    rubro = reportes._nombre_rubro(libro, categoria.id)
    naturaleza = INGRESO if categoria.clase is ClaseCategoria.INGRESO else GASTO
    return naturaleza, f"{rubro} › {categoria.nombre}", rubro


# ---------------------------------------------------------------- internos


def _sumar_renglones(renglones: list[Renglon], largo: int) -> tuple[Decimal, ...]:
    return tuple(sum((r.importes[i] for r in renglones), Decimal(0)) for i in range(largo))
