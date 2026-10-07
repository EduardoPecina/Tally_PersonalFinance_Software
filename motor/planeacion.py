"""Planeación: cuánto ganas al mes, cuánto se va en deudas, cuánto puedes gastar y cómo vas a cerrar el mes.

- **Ingresos**: tu ingreso **principal** (la nómina: marca tus quincenas) y tus ingresos **secundarios fijos** (una
  renta que cobras, honorarios de cada mes…) son subcategorías de ingreso marcadas así. Su promedio de los últimos
  meses completos es tu **ingreso esperado**, salvo que escribas uno a mano.
- **Capacidad de pago**: qué parte de tu ingreso se va en pagar deudas (préstamos y mínimos de tarjetas). Lo sano
  es menos del 30 %; más del 40 % ya aprieta (te puedes quedar sin para comer).
- **Presupuestos sugeridos**: lo que sueles gastar en cada categoría; si no te alcanza para tus deudas y tu meta de
  ahorro, se ajusta en la misma proporción.
- **Proyección del mes**: cuánto vas a gastar al cerrar el mes en cada categoría: al menos lo que sueles gastar
  (si ya te pasaste, lo que llevas); en categorías sin historial, a este ritmo.

Todo son cálculos sobre tus movimientos; nada se guarda salvo lo que el usuario elija.
"""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from motor import prestamos, tarjetas
from motor.dinero import a_pesos
from motor.libro import Libro
from motor.modelo import ClaseCategoria, TipoCuenta, TipoOperacion

MESES_PROMEDIO = 3
REDONDEO = 50                  # los presupuestos sugeridos se redondean a múltiplos de $50
CERO = Decimal(0)


def meses_completos(hoy: date, n: int = MESES_PROMEDIO) -> list[tuple[date, date]]:
    """Los ``n`` meses completos antes del mes de ``hoy``, del más antiguo al más reciente."""
    meses, fin = [], hoy.replace(day=1) - timedelta(days=1)
    for _ in range(n):
        inicio = fin.replace(day=1)
        meses.append((inicio, fin))
        fin = inicio - timedelta(days=1)
    return list(reversed(meses))


def _meses_con_datos(libro: Libro, meses: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Solo los meses que registraste completos (para no promediar con meses vacíos o a medias): desde el 1.º de
    mes en adelante de tu primer movimiento. Los saldos iniciales no cuentan: suelen llevar una fecha anterior."""
    primera = min((op.fecha for op in libro.operaciones() if op.tipo is not TipoOperacion.SALDO_INICIAL),
                  default=None)
    if primera is None:
        return []
    return [m for m in meses if m[0] >= primera]


# ------------------------------------------------------------------ ingresos


@dataclass(frozen=True, slots=True)
class Ingreso:
    categoria_id: str
    nombre: str
    tipo: str                  # "principal" o "secundario"
    promedio: Decimal          # al mes, de los últimos meses completos


def ingresos(libro: Libro, hoy: date | None = None) -> list[Ingreso]:
    hoy = hoy or libro.hoy()
    meses = _meses_con_datos(libro, meses_completos(hoy))
    elegidas = [c for c in libro.categorias()
                if c.clase is ClaseCategoria.INGRESO and c.activa and (c.principal or c.secundario)]
    totales: dict[str, int] = defaultdict(int)
    if meses:
        for op in libro.operaciones(meses[0][0], meses[-1][1]):
            for p in op.partidas_de_categoria():
                totales[p.categoria_id] -= p.importe
    return [Ingreso(c.id, c.nombre, "principal" if c.principal else "secundario",
                    (a_pesos(totales[c.id]) / len(meses)).quantize(Decimal("0.01")) if meses else CERO)
            for c in sorted(elegidas, key=lambda c: (not c.principal, c.nombre))]


@dataclass(frozen=True, slots=True)
class IngresoEsperado:
    monto: Decimal
    fuente: str                # "manual", "promedio", "configurado" (tus ingresos que se repiten) o "sin_datos"
    meses: int                 # cuántos meses se promediaron


def ingreso_esperado(libro: Libro, hoy: date | None = None) -> IngresoEsperado:
    hoy = hoy or libro.hoy()
    if libro.perfil and libro.perfil.ingreso_esperado:
        return IngresoEsperado(a_pesos(libro.perfil.ingreso_esperado), "manual", 0)
    meses = len(_meses_con_datos(libro, meses_completos(hoy)))
    total = sum((i.promedio for i in ingresos(libro, hoy)), CERO)
    if total:
        return IngresoEsperado(total, "promedio", meses)
    # Sin meses completos todavía: lo que configuraste en tus ingresos que se repiten.
    from motor import recurrentes

    elegidas = {c.id for c in libro.categorias() if c.principal or c.secundario}
    configurado = sum((recurrentes.al_mes(r) for r in libro.recurrentes()
                       if r.activa and r.tipo is TipoOperacion.INGRESO and r.categoria_id in elegidas), CERO)
    return IngresoEsperado(configurado, "configurado" if configurado else "sin_datos", meses)


# ---------------------------------------------------------- capacidad de pago


@dataclass(frozen=True, slots=True)
class Capacidad:
    ingreso: Decimal
    prestamos: Decimal         # pagos mensuales de tus préstamos
    minimos_tarjetas: Decimal  # pagos mínimos estimados de tus tarjetas
    para_no_generar_intereses: Decimal   # lo que deberías pagar de tus tarjetas para no pagar intereses

    @property
    def compromisos(self) -> Decimal:
        return self.prestamos + self.minimos_tarjetas

    @property
    def porcentaje(self) -> Decimal | None:
        return (self.compromisos / self.ingreso * 100).quantize(Decimal("0.1")) if self.ingreso else None

    @property
    def nivel(self) -> str:
        """sana (< 30 %), alta (30–40 %), riesgo (> 40 %) o sin_ingreso."""
        if self.porcentaje is None:
            return "sin_ingreso"
        if self.porcentaje < prestamos.CAPACIDAD_SANA:
            return "sana"
        return "alta" if self.porcentaje <= prestamos.CAPACIDAD_LIMITE else "riesgo"

    @property
    def libre(self) -> Decimal:
        """Lo que te queda para vivir después de pagar tus deudas."""
        return self.ingreso - self.compromisos

    @property
    def maximo_sano(self) -> Decimal:
        """Hasta cuánto podrías pagar de deudas al mes sin pasar del 30 % de tu ingreso."""
        return (self.ingreso * prestamos.CAPACIDAD_SANA / 100).quantize(Decimal("0.01"))


def capacidad(libro: Libro, hoy: date | None = None) -> Capacidad:
    hoy = hoy or libro.hoy()
    minimos = no_intereses = CERO
    for cuenta in libro.cuentas():
        if cuenta.tipo is TipoCuenta.CREDITO and cuenta.activa:
            pago = tarjetas.pago_minimo_estimado(libro, cuenta.id, hoy)
            if pago is not None:
                minimos += pago.minimo
                no_intereses += pago.para_no_generar_intereses
    return Capacidad(ingreso_esperado(libro, hoy).monto, prestamos.pagos_mensuales(libro, hoy), minimos, no_intereses)


# ------------------------------------------------------ presupuestos sugeridos


@dataclass(frozen=True, slots=True)
class Sugerencia:
    rubro_id: str
    nombre: str
    promedio: Decimal          # lo que sueles gastar al mes
    sugerido: Decimal
    actual: Decimal | None     # el presupuesto que ya tiene


@dataclass(frozen=True, slots=True)
class Plan:
    ingreso: Decimal
    deudas: Decimal            # pagos de préstamos al mes
    ahorro: Decimal            # tu meta de ahorro al mes
    para_gastar: Decimal       # ingreso − deudas − ahorro
    sugerencias: list[Sugerencia]
    factor: Decimal            # 1 = te alcanza; < 1 = se ajustó para que te alcance

    @property
    def total_sugerido(self) -> Decimal:
        return sum((s.sugerido for s in self.sugerencias), CERO)

    @property
    def total_promedio(self) -> Decimal:
        return sum((s.promedio for s in self.sugerencias), CERO)


def gasto_promedio(libro: Libro, hoy: date | None = None) -> dict[str, Decimal]:
    """Gasto promedio al mes de cada categoría de gasto (``rubro_id``), sin los intereses de préstamos (ya van en
    sus pagos)."""
    hoy = hoy or libro.hoy()
    meses = _meses_con_datos(libro, meses_completos(hoy))
    if not meses:
        return {}
    excluir = {c.id for c in libro.categorias() if c.nombre == prestamos.SUBCATEGORIA_INTERESES}
    totales: dict[str, int] = defaultdict(int)
    for op in libro.operaciones(meses[0][0], meses[-1][1]):
        for p in op.partidas_de_categoria():
            categoria = libro.categoria(p.categoria_id)
            if categoria.clase is ClaseCategoria.GASTO and categoria.rubro_id and p.categoria_id not in excluir:
                totales[categoria.rubro_id] += p.importe
    return {r: (a_pesos(v) / len(meses)).quantize(Decimal("0.01")) for r, v in totales.items() if v > 0}


def sugerir(libro: Libro, hoy: date | None = None) -> Plan:
    hoy = hoy or libro.hoy()
    ingreso = ingreso_esperado(libro, hoy).monto
    deudas = prestamos.pagos_mensuales(libro, hoy)
    meta = libro.perfil.meta_ahorro if libro.perfil else 10
    ahorro = (ingreso * meta / 100).quantize(Decimal("0.01"))
    para_gastar = max(ingreso - deudas - ahorro, CERO)
    promedios = gasto_promedio(libro, hoy)
    total = sum(promedios.values(), CERO)
    factor = Decimal(1) if not ingreso or total <= para_gastar else (para_gastar / total)
    sugerencias = []
    for rubro in libro.rubros():
        if rubro.clase is not ClaseCategoria.GASTO or rubro.id not in promedios:
            continue
        base = promedios[rubro.id] * factor
        redondeado = Decimal(math.ceil(base / REDONDEO) * REDONDEO) if factor == 1 else Decimal(
            math.floor(base / REDONDEO) * REDONDEO)
        sugerencias.append(Sugerencia(rubro.id, rubro.nombre, promedios[rubro.id], redondeado,
                                      a_pesos(rubro.presupuesto) if rubro.presupuesto else None))
    sugerencias.sort(key=lambda s: -s.promedio)
    return Plan(ingreso, deudas, ahorro, para_gastar, sugerencias, factor.quantize(Decimal("0.0001")))


# ------------------------------------------------------- proyección del mes


@dataclass(frozen=True, slots=True)
class ProyeccionRubro:
    nombre: str
    gastado: Decimal
    proyectado: Decimal        # a este ritmo, al cerrar el mes
    presupuesto: Decimal | None

    @property
    def se_pasa(self) -> bool:
        return self.presupuesto is not None and self.proyectado > self.presupuesto


@dataclass(frozen=True, slots=True)
class ProyeccionMes:
    desde: date
    hasta: date
    dias_transcurridos: int
    dias_del_mes: int
    ingreso_esperado: Decimal
    ingreso_recibido: Decimal
    gastado: Decimal
    gasto_proyectado: Decimal
    rubros: list[ProyeccionRubro]

    @property
    def ahorro_proyectado(self) -> Decimal:
        """Lo que te quedaría al cierre: tu ingreso del mes (el esperado, o el recibido si fue mayor) menos el gasto
        proyectado."""
        return max(self.ingreso_esperado, self.ingreso_recibido) - self.gasto_proyectado


def proyeccion_mes(libro: Libro, hoy: date | None = None) -> ProyeccionMes:
    from motor import reportes

    hoy = hoy or libro.hoy()
    desde = hoy.replace(day=1)
    dias_mes = calendar.monthrange(hoy.year, hoy.month)[1]
    transcurridos = hoy.day
    resumen = reportes.resumen(libro, desde, hoy)
    gastos = reportes.gastos_por_rubro(libro, desde, hoy)
    escala = Decimal(dias_mes) / Decimal(transcurridos)
    promedios = gasto_promedio(libro, hoy)
    rubros = []
    for rubro in libro.rubros():
        if rubro.clase is not ClaseCategoria.GASTO:
            continue
        gastado = gastos.get(rubro.nombre, CERO)
        promedio = promedios.get(rubro.id)
        if not gastado and not rubro.presupuesto and not promedio:
            continue
        # Con historial: al menos lo que sueles gastar (la renta ya pagada no se multiplica). Sin él: a este ritmo.
        proyectado = max(gastado, promedio) if promedio else (gastado * escala).quantize(Decimal("0.01"))
        rubros.append(ProyeccionRubro(rubro.nombre, gastado, proyectado,
                                      a_pesos(rubro.presupuesto) if rubro.presupuesto else None))
    rubros.sort(key=lambda r: -r.proyectado)
    return ProyeccionMes(desde, date(hoy.year, hoy.month, dias_mes), transcurridos, dias_mes,
                         ingreso_esperado(libro, hoy).monto, resumen.ingresos, resumen.gastos,
                         sum((r.proyectado for r in rubros), CERO), rubros)
