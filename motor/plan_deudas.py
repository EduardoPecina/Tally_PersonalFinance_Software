"""Plan para salir de deudas: cuánto pagar a cada tarjeta y préstamo, en qué orden y cuándo terminas.

Pones cuánto puedes pagar al mes entre **todas** tus deudas. Cada mes se paga el mínimo de cada una (lo que pide
la tarjeta, la mensualidad del préstamo y las mensualidades a meses sin intereses) y **todo lo que sobra va a una
sola deuda**, la primera de la lista. Cuando la terminas, lo que pagabas por ella se suma a la siguiente (por eso
el pago «crece» como bola de nieve). Dos formas de ordenar la lista:

- **Avalancha**: la de tasa más alta primero. Es la que menos intereses te cobra.
- **Bola de nieve**: la que debes menos primero. Terminas una pronto y eso motiva a seguir.

Es una estimación: supone que no compras más con las tarjetas y que las tasas no cambian. Las deudas sin tasa
registrada se calculan sin intereses (regístrala en Deudas para que el plan sea exacto).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import ROUND_CEILING, Decimal

from motor import prestamos, tarjetas
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import TipoCuenta

AVALANCHA, BOLA_DE_NIEVE = "avalancha", "bola_de_nieve"
ESTRATEGIAS = {AVALANCHA: "Avalancha: la de tasa más alta primero",
               BOLA_DE_NIEVE: "Bola de nieve: la que debes menos primero"}
MAXIMO_MESES = 600                      # 50 años: si no terminas en ese tiempo, con ese pago no terminas
CERO, CENTAVO = Decimal(0), Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Deuda:
    """Una tarjeta o préstamo con saldo, como entra al plan."""

    cuenta_id: str
    nombre: str
    tipo: TipoCuenta
    saldo: Decimal                       # lo que generará intereses (en tarjetas, sin lo que va a meses sin intereses)
    tasa_anual: Decimal | None           # la registrada (None = sin registrar: se calcula sin intereses)
    tasa_mes: Decimal                    # con el IVA de los intereses
    pago_fijo: Decimal = CERO            # préstamos: la mensualidad
    linea: Decimal = CERO                # tarjetas: la línea de crédito (para el mínimo)
    msi: tuple[tuple[Decimal, int], ...] = ()   # tarjetas: (mensualidad, cuántas faltan) de cada compra a MSI

    @property
    def total(self) -> Decimal:
        """Todo lo que debes en ella hoy (con lo que falta de meses sin intereses)."""
        return self.saldo + sum((m * n for m, n in self.msi), CERO)

    @property
    def sin_tasa(self) -> bool:
        return self.tasa_anual is None


@dataclass(frozen=True, slots=True)
class Liquidada:
    cuenta_id: str
    nombre: str
    mes: int                             # en qué mes del plan la terminas (1 = el próximo pago)
    fecha: date
    intereses: Decimal


@dataclass(frozen=True, slots=True)
class MesPlan:
    numero: int
    fecha: date
    pagos: dict[str, Decimal]            # cuenta → lo que le pagas ese mes
    saldo: Decimal                       # lo que debes en total después de pagar


@dataclass(frozen=True, slots=True)
class Resultado:
    """Cómo te va con una forma de pagar."""

    estrategia: str                      # avalancha, bola_de_nieve o "minimos"
    orden: tuple[str, ...]               # a qué deuda va lo que sobra, en orden
    meses: int | None                    # None = con ese pago no terminas
    intereses: Decimal
    pagado: Decimal
    liquidadas: list[Liquidada]
    tabla: list[MesPlan] = field(repr=False)

    @property
    def termina(self) -> bool:
        return self.meses is not None

    @property
    def fin(self) -> date | None:
        return self.tabla[-1].fecha if self.termina and self.tabla else None


@dataclass(frozen=True, slots=True)
class Plan:
    deudas: list[Deuda]
    presupuesto: Decimal                 # lo que pagas al mes entre todas
    minimo: Decimal                      # lo que piden todas este mes (sin eso no hay plan)
    avalancha: Resultado | None
    bola_de_nieve: Resultado | None
    solo_minimos: Resultado

    @property
    def alcanza(self) -> bool:
        return self.avalancha is not None

    def de(self, estrategia: str) -> Resultado | None:
        return self.avalancha if estrategia == AVALANCHA else self.bola_de_nieve

    @property
    def recomendada(self) -> str:
        """Avalancha si te ahorra intereses de verdad (más del 1 % o de un mes de diferencia); si casi da lo mismo,
        bola de nieve, que motiva más."""
        a, b = self.avalancha, self.bola_de_nieve
        if a is None or b is None or not b.termina:
            return AVALANCHA
        if not a.termina:
            return BOLA_DE_NIEVE
        diferencia = b.intereses - a.intereses
        return AVALANCHA if diferencia > max(b.intereses / 100, CENTAVO) or a.meses < b.meses else BOLA_DE_NIEVE

    @property
    def sin_tasa(self) -> list[Deuda]:
        return [d for d in self.deudas if d.sin_tasa and d.saldo]


# ------------------------------------------------------------------ tus deudas


def deudas(libro: Libro, hoy: date | None = None) -> list[Deuda]:
    """Tus tarjetas y préstamos activos con saldo, como entran al plan."""
    hoy = hoy or libro.hoy()
    resultado = []
    datos_prestamo = {p.cuenta_id: p for p in libro.prestamos()}
    for cuenta in libro.cuentas():
        if not cuenta.activa:
            continue
        if cuenta.tipo is TipoCuenta.CREDITO:
            debe = tarjetas.deuda(libro, cuenta.id, hoy)
            if debe <= 0:
                continue
            compras = tarjetas.compras_a_msi(libro, cuenta.id, hoy)
            msi = tuple((c.mensualidad, c.meses - c.cobradas) for c in compras if c.meses > c.cobradas)
            en_msi = sum((c.restante for c in compras), CERO)
            iva = tarjetas.iva_de_tarjeta(libro, cuenta) / 100
            tasa = cuenta.tasa_anual
            resultado.append(Deuda(
                cuenta.id, cuenta.nombre, cuenta.tipo, max(debe - en_msi, CERO), tasa,
                (tasa or CERO) / 100 / 12 * (1 + iva),
                linea=a_pesos(cuenta.limite_credito) if cuenta.limite_credito else CERO, msi=msi))
        elif cuenta.tipo is TipoCuenta.PRESTAMO and cuenta.id in datos_prestamo:
            debe = prestamos.deuda_al(libro, cuenta.id, hoy)
            if debe <= 0:
                continue
            p = datos_prestamo[cuenta.id]
            resultado.append(Deuda(cuenta.id, cuenta.nombre, cuenta.tipo, debe, p.tasa_anual,
                                   prestamos.tasa_mensual(libro, p), pago_fijo=prestamos.pago_mensual(libro, p)))
    return resultado


def ordenar(lista: list[Deuda], estrategia: str) -> tuple[str, ...]:
    """A qué deuda va lo que sobra, en orden."""
    if estrategia == AVALANCHA:
        clave = lambda d: (-d.tasa_mes, d.total, d.nombre)          # noqa: E731
    elif estrategia == BOLA_DE_NIEVE:
        clave = lambda d: (d.total, -d.tasa_mes, d.nombre)          # noqa: E731
    else:
        raise ErrorValidacion("Elige avalancha o bola de nieve.")
    return tuple(d.cuenta_id for d in sorted(lista, key=clave))


# ------------------------------------------------------------------ simulación


def _minimo(d: Deuda, saldo: Decimal, interes: Decimal) -> Decimal:
    """Lo que pide la deuda este mes sobre lo que genera intereses (sin las mensualidades a MSI)."""
    if saldo + interes <= 0:
        return CERO
    if d.tipo is TipoCuenta.CREDITO:
        pedido = max(saldo * tarjetas.PORCENTAJE_SALDO + interes, d.linea * tarjetas.PORCENTAJE_LINEA)
    else:
        pedido = d.pago_fijo
    return min(pedido, saldo + interes).quantize(CENTAVO, ROUND_CEILING)


def minimo_del_mes(lista: list[Deuda]) -> Decimal:
    """Lo que piden todas tus deudas el próximo mes: lo menos que puedes poner en el plan."""
    total = CERO
    for d in lista:
        interes = (d.saldo * d.tasa_mes).quantize(CENTAVO)
        total += _minimo(d, d.saldo, interes) + sum((m for m, n in d.msi if n > 0), CERO)
    return total


def simular(lista: list[Deuda], presupuesto: Decimal | None, estrategia: str, hoy: date) -> Resultado:
    """Mes por mes. ``presupuesto`` None = pagar solo los mínimos (lo que liberas no se reaprovecha)."""
    orden = ordenar(lista, estrategia) if presupuesto is not None else tuple(d.cuenta_id for d in lista)
    por_id = {d.cuenta_id: d for d in lista}
    saldos = {d.cuenta_id: d.saldo for d in lista}
    msi = {d.cuenta_id: [list(x) for x in d.msi] for d in lista}
    intereses = {d.cuenta_id: CERO for d in lista}
    liquidadas: list[Liquidada] = []
    tabla: list[MesPlan] = []
    pagado = CERO
    pendientes = {i for i in orden if saldos[i] > 0 or msi[i]}
    for numero in range(1, MAXIMO_MESES + 1):
        if not pendientes:
            break
        fecha = _sumar_meses(hoy, numero)
        disponible = presupuesto if presupuesto is not None else None
        pagos: dict[str, Decimal] = {}
        for i in orden:                                      # intereses y lo que pide cada una
            d = por_id[i]
            interes = (saldos[i] * d.tasa_mes).quantize(CENTAVO)
            intereses[i] += interes
            pago = _minimo(d, saldos[i], interes)
            saldos[i] = saldos[i] + interes - pago
            for compra in msi[i]:                            # las mensualidades a meses sin intereses
                if compra[1] > 0:
                    pago += compra[0]
                    compra[1] -= 1
            msi[i] = [c for c in msi[i] if c[1] > 0]
            pagos[i] = pago
            if disponible is not None:
                disponible -= pago
        if disponible is not None and disponible > 0:        # lo que sobra, a la primera de la lista
            for i in orden:
                if disponible <= 0:
                    break
                extra = min(disponible, saldos[i])
                if extra > 0:
                    saldos[i] -= extra
                    pagos[i] += extra
                    disponible -= extra
        pagado += sum(pagos.values(), CERO)
        for i in [i for i in orden if i in pendientes]:          # las que terminan el mismo mes, en su orden
            if saldos[i] <= CENTAVO and not msi[i]:
                pendientes.discard(i)
                saldos[i] = CERO
                liquidadas.append(Liquidada(i, por_id[i].nombre, numero, fecha, intereses[i]))
        tabla.append(MesPlan(numero, fecha, {i: p for i, p in pagos.items() if p}, sum(saldos.values(), CERO)
                             + sum((c[0] * c[1] for v in msi.values() for c in v), CERO)))
    termina = not pendientes
    return Resultado(estrategia if presupuesto is not None else "minimos", orden,
                     len(tabla) if termina else None, sum(intereses.values(), CERO), pagado, liquidadas, tabla)


def calcular(libro: Libro, presupuesto=None, hoy: date | None = None) -> Plan:
    """El plan con ``presupuesto`` al mes (por omisión, el guardado; si no hay, lo mínimo)."""
    hoy = hoy or libro.hoy()
    lista = deudas(libro, hoy)
    minimo = minimo_del_mes(lista)
    if presupuesto in (None, ""):
        guardado = guardado_de(libro)
        presupuesto = guardado[0] if guardado else minimo
    presupuesto = Decimal(str(presupuesto)).quantize(CENTAVO)
    solo_minimos = simular(lista, None, AVALANCHA, hoy)
    if not lista or presupuesto < minimo:
        return Plan(lista, presupuesto, minimo, None, None, solo_minimos)
    return Plan(lista, presupuesto, minimo, simular(lista, presupuesto, AVALANCHA, hoy),
                simular(lista, presupuesto, BOLA_DE_NIEVE, hoy), solo_minimos)


def sugerido(plan: Plan) -> Decimal:
    """Un monto redondo para empezar: lo mínimo + 10 %, a la centena."""
    return (plan.minimo * Decimal("1.1") / 100).quantize(Decimal(1), ROUND_CEILING) * 100


# ------------------------------------------------------------------ guardar tu plan


def guardar(libro: Libro, presupuesto, estrategia: str) -> None:
    """Guarda tu plan (se ve en el Resumen: a qué deuda va lo extra este mes)."""
    if libro.perfil is None:
        raise ErrorValidacion("Primero escribe tu nombre en la bienvenida.")
    if estrategia not in ESTRATEGIAS:
        raise ErrorValidacion("Elige avalancha o bola de nieve.")
    centavos = a_centavos(presupuesto)
    if centavos <= 0:
        raise ErrorValidacion("Escribe cuánto puedes pagar al mes.")
    libro.perfil = replace(libro.perfil, plan_deudas=centavos, estrategia_deudas=estrategia)


def quitar(libro: Libro) -> None:
    if libro.perfil is not None:
        libro.perfil = replace(libro.perfil, plan_deudas=None, estrategia_deudas="")


def guardado_de(libro: Libro) -> tuple[Decimal, str] | None:
    p = libro.perfil
    if p is None or not p.plan_deudas or p.estrategia_deudas not in ESTRATEGIAS:
        return None
    return a_pesos(p.plan_deudas), p.estrategia_deudas


@dataclass(frozen=True, slots=True)
class Avance:
    """Tu plan guardado, hoy: para el Resumen."""

    presupuesto: Decimal
    estrategia: str
    objetivo: Deuda | None               # a la que va lo extra este mes
    pagos: dict[str, Decimal]            # lo que toca pagar a cada una este mes
    fin: date | None
    alcanza: bool


def avance(libro: Libro, hoy: date | None = None) -> Avance | None:
    """``None`` si no guardaste un plan o ya no debes nada."""
    guardado = guardado_de(libro)
    if guardado is None:
        return None
    presupuesto, estrategia = guardado
    plan = calcular(libro, presupuesto, hoy)
    if not plan.deudas:
        return None
    resultado = plan.de(estrategia)
    if resultado is None:
        return Avance(presupuesto, estrategia, None, {}, None, False)
    por_id = {d.cuenta_id: d for d in plan.deudas}
    objetivo = next((por_id[i] for i in resultado.orden if por_id[i].saldo > 0), None)
    pagos = resultado.tabla[0].pagos if resultado.tabla else {}
    return Avance(presupuesto, estrategia, objetivo, pagos, resultado.fin, True)


def _sumar_meses(dia: date, meses: int) -> date:
    total = dia.year * 12 + dia.month - 1 + meses
    anio, mes = divmod(total, 12)
    return date(anio, mes + 1, min(dia.day, calendar.monthrange(anio, mes + 1)[1]))
