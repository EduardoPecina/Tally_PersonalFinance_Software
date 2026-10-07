"""Pagos que se repiten (renta, luz, suscripciones, la nómina) y el calendario de los próximos días.

- **Recurrentes**: un recordatorio con su importe estimado y cada cuánto se repite. No mueve dinero: cuando pagas,
  lo registras (con un clic desde el calendario) y TALLY lo da por pagado.
- **¿Ya se pagó?**: un movimiento de la misma cuenta y subcategoría (o la misma transferencia), a pocos días de la
  fecha y por un importe parecido (la luz cambia cada mes). Cada movimiento cubre una sola fecha.
- **Calendario**: los recurrentes, el pago de cada tarjeta (fecha límite y lo que falta para no generar intereses)
  y el de cada préstamo.
- **Flujo**: con tu dinero disponible de hoy, cómo quedaría día con día; avisa si llegarías a negativo.
- **Detectar**: en tu historial, lo que se repite cada mes (o cada quincena) casi igual, para agregarlo con un clic.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from motor import prestamos, tarjetas
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import ClaseCategoria, Operacion, Recurrente, TipoCuenta, TipoOperacion
from motor.movimientos import registrar_gasto, registrar_ingreso
from motor.textos import normalizar_nombre
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia

FRECUENCIAS = {
    "mensual": "Cada mes",
    "quincenal": "Cada quincena (el 15 y el último día del mes)",
    "semanal": "Cada semana",
    "catorcenal": "Cada 14 días",
    "bimestral": "Cada 2 meses",
    "trimestral": "Cada 3 meses",
    "semestral": "Cada 6 meses",
    "anual": "Cada año",
}
_MESES = {"mensual": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12}
_DIAS = {"semanal": 7, "catorcenal": 14}
_VECES_AL_MES = {"semanal": Decimal(52) / 12, "catorcenal": Decimal(26) / 12, "quincenal": Decimal(2),
                 "mensual": Decimal(1), "bimestral": Decimal(1) / 2, "trimestral": Decimal(1) / 3,
                 "semestral": Decimal(1) / 6, "anual": Decimal(1) / 12}
TIPOS = (TipoOperacion.GASTO, TipoOperacion.INGRESO, TipoOperacion.TRANSFERENCIA)
DIAS_DE_GRACIA = 7          # un pago hasta 7 días antes o después cuenta para esa fecha
DIAS_ATRAS = 14             # en el calendario se ven los pagos de las últimas 2 semanas (pagados o vencidos)
PAGADO, PENDIENTE, VENCIDO = "pagado", "pendiente", "vencido"
RECURRENTE, TARJETA, PRESTAMO = "recurrente", "tarjeta", "prestamo"


# ===================================================================== crear, editar, borrar


def crear(libro: Libro, nombre: str, tipo, monto, cuenta_id: str, frecuencia: str, inicio: date, *,
          categoria_id: str | None = None, destino_id: str | None = None, fin: date | None = None,
          suscripcion: bool = False, notas: str = "") -> Recurrente:
    r = Recurrente(id=libro.nuevo_id(), nombre=nombre, tipo=TipoOperacion(tipo), monto=_centavos(monto),
                   cuenta_id=cuenta_id, frecuencia=frecuencia, inicio=inicio, categoria_id=categoria_id,
                   destino_id=destino_id, fin=fin, suscripcion=suscripcion, notas=notas)
    return libro.guardar_recurrente(_validar(libro, r))


def editar(libro: Libro, recurrente_id: str, **cambios) -> Recurrente:
    if "monto" in cambios:
        cambios["monto"] = _centavos(cambios["monto"])
    if "tipo" in cambios:
        cambios["tipo"] = TipoOperacion(cambios["tipo"])
    return libro.guardar_recurrente(_validar(libro, replace(libro.recurrente(recurrente_id), **cambios)))


def eliminar(libro: Libro, recurrente_id: str) -> None:
    libro.quitar_recurrente(recurrente_id)


def _centavos(monto) -> int:
    centavos = a_centavos(monto)
    if centavos <= 0:
        raise ErrorValidacion("El importe debe ser mayor que cero.")
    return centavos


def _validar(libro: Libro, r: Recurrente) -> Recurrente:
    r = replace(r, nombre=normalizar_nombre(r.nombre), notas=r.notas.strip())
    if r.tipo not in TIPOS:
        raise ErrorValidacion("Un pago recurrente es un gasto, un ingreso o una transferencia a otra de tus cuentas.")
    if r.frecuencia not in FRECUENCIAS:
        raise ErrorValidacion("Elige cada cuánto se repite.")
    if r.fin is not None and r.fin < r.inicio:
        raise ErrorValidacion("La fecha en que termina no puede ser antes de la primera vez.")
    cuenta = libro.cuenta(r.cuenta_id)
    if not cuenta.activa:
        raise ErrorValidacion(f"La cuenta «{cuenta.nombre}» está archivada.")
    if r.tipo is TipoOperacion.TRANSFERENCIA:
        if not r.destino_id:
            raise ErrorValidacion("Elige a qué cuenta va el dinero.")
        if r.destino_id == r.cuenta_id:
            raise ErrorValidacion("La cuenta de origen y la de destino deben ser distintas.")
        if not libro.cuenta(r.destino_id).activa:
            raise ErrorValidacion(f"La cuenta «{libro.cuenta(r.destino_id).nombre}» está archivada.")
        return replace(r, categoria_id=None)
    if not r.categoria_id:
        raise ErrorValidacion("Elige la subcategoría.")
    categoria = libro.categoria(r.categoria_id)
    clase = ClaseCategoria.GASTO if r.tipo is TipoOperacion.GASTO else ClaseCategoria.INGRESO
    if categoria.clase is not clase or not categoria.rubro_id:
        raise ErrorValidacion(f"«{categoria.nombre}» no es una subcategoría de {'gasto' if clase is ClaseCategoria.GASTO else 'ingreso'}.")
    return replace(r, destino_id=None)


# ===================================================================== fechas


def fechas(r: Recurrente, desde: date, hasta: date) -> list[date]:
    """Las veces que toca entre ``desde`` y ``hasta`` (incluidas), desde su primera vez hasta su fin."""
    desde = max(desde, r.inicio)
    if r.fin is not None:
        hasta = min(hasta, r.fin)
    if desde > hasta:
        return []
    if r.frecuencia in _DIAS:
        paso = _DIAS[r.frecuencia]
        n = max(0, -(-(desde - r.inicio).days // paso))
        resultado, dia = [], r.inicio + timedelta(days=n * paso)
        while dia <= hasta:
            resultado.append(dia)
            dia += timedelta(days=paso)
        return resultado
    if r.frecuencia == "quincenal":
        resultado = []
        anio, mes = desde.year, desde.month
        while date(anio, mes, 1) <= hasta:
            for dia in (date(anio, mes, 15), date(anio, mes, calendar.monthrange(anio, mes)[1])):
                if desde <= dia <= hasta:
                    resultado.append(dia)
            anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
        return resultado
    paso = _MESES[r.frecuencia]
    meses = (desde.year - r.inicio.year) * 12 + desde.month - r.inicio.month
    n = max(0, meses // paso - 1)
    resultado = []
    while (dia := _sumar_meses(r.inicio, n * paso)) <= hasta:
        if dia >= desde:
            resultado.append(dia)
        n += 1
    return resultado


def siguiente(r: Recurrente, hoy: date) -> date | None:
    """La próxima vez que toca, desde hoy."""
    proximas = fechas(r, hoy, hoy + timedelta(days=400))
    return proximas[0] if proximas else None


def _sumar_meses(dia: date, meses: int) -> date:
    total = dia.year * 12 + dia.month - 1 + meses
    anio, mes = divmod(total, 12)
    return date(anio, mes + 1, min(dia.day, calendar.monthrange(anio, mes + 1)[1]))


# ===================================================================== costos


def al_mes(r: Recurrente) -> Decimal:
    """Lo que equivale al mes (una suscripción anual de $1,200 son $100 al mes)."""
    return a_pesos(int((Decimal(r.monto) * _VECES_AL_MES[r.frecuencia]).to_integral_value()))


def al_anio(r: Recurrente) -> Decimal:
    return a_pesos(int((Decimal(r.monto) * _VECES_AL_MES[r.frecuencia] * 12).to_integral_value()))


@dataclass(frozen=True, slots=True)
class Totales:
    gastos_al_mes: Decimal          # pagos fijos y suscripciones (sin transferencias)
    suscripciones_al_mes: Decimal
    suscripciones_al_anio: Decimal
    ingresos_al_mes: Decimal
    suscripciones: int


def totales(libro: Libro) -> Totales:
    activos = [r for r in libro.recurrentes() if r.activa]
    gastos = [r for r in activos if r.tipo is TipoOperacion.GASTO]
    suscripciones = [r for r in gastos if r.suscripcion]
    return Totales(sum((al_mes(r) for r in gastos), Decimal("0.00")),
                   sum((al_mes(r) for r in suscripciones), Decimal("0.00")),
                   sum((al_anio(r) for r in suscripciones), Decimal("0.00")),
                   sum((al_mes(r) for r in activos if r.tipo is TipoOperacion.INGRESO), Decimal("0.00")),
                   len(suscripciones))


# ===================================================================== ¿ya se pagó? y registrar


def _cubre(libro: Libro, r: Recurrente, op: Operacion) -> bool:
    """¿Este movimiento es un pago de este recurrente? (sin ver la fecha)."""
    if r.tipo is TipoOperacion.TRANSFERENCIA:
        if op.tipo not in (TipoOperacion.TRANSFERENCIA, TipoOperacion.PAGO_TARJETA):
            return False
        sale = sum(p.importe for p in op.partidas if p.cuenta_id == r.cuenta_id)
        entra = sum(p.importe for p in op.partidas if p.cuenta_id == r.destino_id)
        monto = entra if sale < 0 < entra else 0
    else:
        if op.tipo is not r.tipo or not any(p.categoria_id == r.categoria_id for p in op.partidas):
            return False
        monto = abs(sum(p.importe for p in op.partidas if p.cuenta_id == r.cuenta_id))
    return r.monto / 2 <= monto <= r.monto * 2


def pagos(libro: Libro, r: Recurrente, fechas_: list[date]) -> dict[date, Operacion]:
    """Fecha → el movimiento que la cubre (a ``DIAS_DE_GRACIA`` días o menos). Cada movimiento, una sola fecha."""
    if not fechas_:
        return {}
    gracia = timedelta(days=DIAS_DE_GRACIA)
    candidatos = [op for op in libro.operaciones(min(fechas_) - gracia, max(fechas_) + gracia) if _cubre(libro, r, op)]
    usados: set[str] = set()
    resultado = {}
    for dia in sorted(fechas_):
        libres = [op for op in candidatos if op.id not in usados and abs((op.fecha - dia).days) <= DIAS_DE_GRACIA]
        if libres:
            op = min(libres, key=lambda o: (abs((o.fecha - dia).days), o.fecha))
            usados.add(op.id)
            resultado[dia] = op
    return resultado


def registrar(libro: Libro, recurrente_id: str, fecha: date, monto=None, *, cuenta_id: str | None = None) -> Operacion:
    """Registra el pago (o el ingreso) con su importe estimado, u otro si este mes fue distinto."""
    r = libro.recurrente(recurrente_id)
    importe = a_pesos(r.monto) if monto is None else monto
    cuenta = cuenta_id or r.cuenta_id
    if r.tipo is TipoOperacion.GASTO:
        return registrar_gasto(libro, fecha, cuenta, r.categoria_id, importe, r.nombre)
    if r.tipo is TipoOperacion.INGRESO:
        return registrar_ingreso(libro, fecha, cuenta, r.categoria_id, importe, r.nombre)
    destino = libro.cuenta(r.destino_id)
    if destino.tipo is TipoCuenta.CREDITO and libro.cuenta(cuenta).tipo is not TipoCuenta.CREDITO:
        return registrar_pago_tarjeta(libro, fecha, cuenta, destino.id, importe, r.nombre)
    return registrar_transferencia(libro, fecha, cuenta, destino.id, importe, r.nombre)


# ===================================================================== calendario


@dataclass(frozen=True, slots=True)
class Evento:
    fecha: date
    nombre: str
    clase: str                    # RECURRENTE, TARJETA o PRESTAMO
    centavos: int                 # + entra, − sale (en la cuenta del evento)
    cuenta_id: str
    estado: str                   # PAGADO, PENDIENTE o VENCIDO
    recurrente_id: str = ""
    operacion_id: str = ""        # el movimiento que lo pagó
    destino_id: str | None = None
    detalle: str = ""
    suscripcion: bool = False


def calendario(libro: Libro, hoy: date | None = None, dias: int = 30) -> list[Evento]:
    """Lo que toca pagar (y cobrar) de ``DIAS_ATRAS`` días atrás a ``dias`` días adelante, en orden."""
    hoy = hoy or libro.hoy()
    desde, hasta = hoy - timedelta(days=DIAS_ATRAS), hoy + timedelta(days=dias)
    eventos: list[Evento] = []
    for r in libro.recurrentes():
        if not r.activa:
            continue
        dias_ = fechas(r, desde, hasta)
        hechos = pagos(libro, r, dias_)
        for dia in dias_:
            op = hechos.get(dia)
            estado = PAGADO if op else (VENCIDO if dia < hoy else PENDIENTE)
            signo = 1 if r.tipo is TipoOperacion.INGRESO else -1
            eventos.append(Evento(dia, r.nombre, RECURRENTE, signo * (op_monto(op, r) if op else r.monto),
                                  r.cuenta_id, estado, r.id, op.id if op else "", r.destino_id,
                                  FRECUENCIAS[r.frecuencia], r.suscripcion))
    eventos += _tarjetas(libro, hoy, desde, hasta)
    eventos += _prestamos(libro, hoy, hasta)
    orden = {VENCIDO: 0, PENDIENTE: 1, PAGADO: 2}
    return sorted(eventos, key=lambda e: (e.fecha, orden[e.estado], e.nombre.casefold()))


def op_monto(op: Operacion, r: Recurrente) -> int:
    cuenta = r.destino_id if r.tipo is TipoOperacion.TRANSFERENCIA else r.cuenta_id
    return abs(sum(p.importe for p in op.partidas if p.cuenta_id == cuenta))


def _tarjetas(libro: Libro, hoy: date, desde: date, hasta: date) -> list[Evento]:
    eventos = []
    for tarjeta in libro.cuentas():
        if tarjeta.tipo is not TipoCuenta.CREDITO or not tarjeta.activa:
            continue
        estado = tarjetas.estado(libro, tarjeta.id, hoy)
        corte = estado.corte
        if corte is not None and corte.fecha_limite_pago and desde <= corte.fecha_limite_pago <= hasta:
            falta = a_centavos(corte.por_liquidar)
            if falta:
                situacion = VENCIDO if corte.fecha_limite_pago < hoy else PENDIENTE
                detalle = f"Para no generar intereses (corte del {corte.fin:%d/%m})"
            else:
                situacion, detalle = PAGADO, f"Corte del {corte.fin:%d/%m}: ya está pagada"
                falta = a_centavos(corte.deuda_al_corte)
            if falta or situacion != PAGADO:
                eventos.append(Evento(corte.fecha_limite_pago, f"Pago de {tarjeta.nombre}", TARJETA, -falta,
                                      tarjeta.id, situacion, detalle=detalle))
        actual = estado.actual
        if (actual is not None and actual.fecha_limite_pago and hoy <= actual.fecha_limite_pago <= hasta
                and (corte is None or actual.fecha_limite_pago != corte.fecha_limite_pago)):
            gastado = a_centavos(actual.cargos) - a_centavos(actual.abonos)
            if gastado > 0:
                eventos.append(Evento(actual.fecha_limite_pago, f"Pago de {tarjeta.nombre}", TARJETA, -gastado,
                                      tarjeta.id, PENDIENTE,
                                      detalle=f"Estimado: lo que llevas del ciclo que corta el {actual.fin:%d/%m}"))
    return eventos


def _prestamos(libro: Libro, hoy: date, hasta: date) -> list[Evento]:
    eventos = []
    for p in libro.prestamos():
        cuenta = libro.cuenta(p.cuenta_id)
        if not cuenta.activa:
            continue
        estado = prestamos.estado(libro, p.cuenta_id, hoy)
        dias_ = []
        while estado.proximo_pago is not None and len(dias_) < 12:
            dia = _sumar_meses(estado.proximo_pago, len(dias_))
            if dia > hasta:
                break
            dias_.append(dia)
        gracia = timedelta(days=DIAS_DE_GRACIA)
        abonos = [op for op in libro.operaciones(hoy - gracia, hasta + gracia)
                  if op.tipo is TipoOperacion.TRANSFERENCIA
                  and any(pa.cuenta_id == cuenta.id and pa.importe > 0 for pa in op.partidas)]
        for dia in dias_:
            op = next((o for o in abonos if abs((o.fecha - dia).days) <= DIAS_DE_GRACIA), None)
            if op is not None:
                abonos.remove(op)
            eventos.append(Evento(dia, f"Pago de {cuenta.nombre}", PRESTAMO, -a_centavos(estado.pago_mensual),
                                  cuenta.id, PAGADO if op else PENDIENTE, operacion_id=op.id if op else "",
                                  detalle="Pago mensual del préstamo"))
    return eventos


# ===================================================================== flujo


@dataclass(frozen=True, slots=True)
class Flujo:
    hoy: date
    disponible: int                       # tu dinero disponible hoy (centavos)
    eventos: list[Evento]
    dias: list[tuple[date, int]]          # cómo quedaría al final de cada día
    entra: int                            # lo pendiente que entra al disponible
    sale: int                             # lo pendiente que sale del disponible (positivo)

    @property
    def minimo(self) -> tuple[date, int]:
        return min(self.dias, key=lambda d: (d[1], d[0]))

    @property
    def final(self) -> int:
        return self.dias[-1][1]

    @property
    def negativo(self) -> bool:
        return self.minimo[1] < 0


def efecto(libro: Libro, e: Evento) -> int:
    """Cuánto cambia tu dinero disponible si pasa (0 si ya se pagó). Una compra con tarjeta no lo cambia hoy: se
    paga en el pago de la tarjeta, que sí cuenta."""
    if e.estado == PAGADO:
        return 0
    if e.clase in (TARJETA, PRESTAMO):
        return e.centavos
    disponible = libro.cuenta(e.cuenta_id).en_disponible
    if e.destino_id:
        destino = libro.cuenta(e.destino_id).en_disponible
        return e.centavos if disponible and not destino else (-e.centavos if destino and not disponible else 0)
    return e.centavos if disponible else 0


def flujo(libro: Libro, hoy: date | None = None, dias: int = 30) -> Flujo:
    """Tu dinero disponible día con día, con lo pendiente. Lo vencido (no pagado) cuenta hoy. Lo que ya
    registraste con fecha futura (un pago programado) cuenta en su día."""
    from motor import reportes

    hoy = hoy or libro.hoy()
    eventos = calendario(libro, hoy, dias)
    disponible = a_centavos(reportes.indicadores(libro, hoy).dinero_disponible)
    por_dia: dict[date, int] = defaultdict(int)
    entra = sale = 0
    for e in eventos:
        cambio = efecto(libro, e)
        por_dia[max(e.fecha, hoy)] += cambio
        entra += max(cambio, 0)
        sale += max(-cambio, 0)
    disponibles = {c.id for c in libro.cuentas() if c.en_disponible}
    for op in libro.operaciones(hoy + timedelta(days=1), hoy + timedelta(days=dias)):
        cambio = sum(p.importe for p in op.partidas if p.cuenta_id in disponibles)
        por_dia[op.fecha] += cambio
        entra += max(cambio, 0)
        sale += max(-cambio, 0)
    saldo, puntos = disponible, []
    for n in range(dias + 1):
        dia = hoy + timedelta(days=n)
        saldo += por_dia.get(dia, 0)
        puntos.append((dia, saldo))
    return Flujo(hoy, disponible, eventos, puntos, entra, sale)


# ===================================================================== detectar en el historial


@dataclass(frozen=True, slots=True)
class Sugerencia:
    nombre: str
    tipo: TipoOperacion
    monto: Decimal
    cuenta_id: str
    categoria_id: str
    frecuencia: str
    siguiente: date
    veces: int
    suscripcion: bool


def detectar(libro: Libro, hoy: date | None = None) -> list[Sugerencia]:
    """Gastos (o ingresos) de los últimos 6 meses que se repiten cada mes o cada quincena casi igual: misma cuenta,
    subcategoría y descripción, al menos 3 veces, importe parecido (±20 %). Sin los que ya son un recurrente."""
    from motor.bancos import nucleo

    hoy = hoy or libro.hoy()
    grupos: dict[tuple, list[Operacion]] = defaultdict(list)
    for op in libro.operaciones(hoy - timedelta(days=190), hoy):
        if op.tipo not in (TipoOperacion.GASTO, TipoOperacion.INGRESO):
            continue
        categorias_ = {p.categoria_id for p in op.partidas_de_categoria()}
        cuentas_ = {p.cuenta_id for p in op.partidas_de_cuenta()}
        if len(categorias_) != 1 or len(cuentas_) != 1:
            continue
        grupos[(op.tipo, *cuentas_, *categorias_, nucleo(op.descripcion))].append(op)
    sugerencias = []
    for (tipo, cuenta_id, categoria_id, _), ops in grupos.items():
        if len(ops) < 3 or not libro.cuenta(cuenta_id).activa:
            continue
        ops.sort(key=lambda o: o.fecha)
        montos = [abs(sum(p.importe for p in o.partidas_de_cuenta())) for o in ops]
        if max(montos) > min(montos) * Decimal("1.2"):
            continue
        huecos = [(b.fecha - a.fecha).days for a, b in zip(ops, ops[1:])]
        if all(25 <= h <= 35 for h in huecos):
            frecuencia = "mensual"
        elif all(12 <= h <= 18 for h in huecos):
            frecuencia = "quincenal"
        else:
            continue
        if (hoy - ops[-1].fecha).days > 45:
            continue                                            # ya no se repite
        if any(r.cuenta_id == cuenta_id and r.categoria_id == categoria_id and r.tipo is tipo
               and abs(r.monto - montos[-1]) <= montos[-1] * Decimal("0.2") for r in libro.recurrentes()):
            continue
        categoria = libro.categoria(categoria_id)
        if not categoria.activa:
            continue
        base = Recurrente("", "x", tipo, montos[-1], cuenta_id, frecuencia, ops[-1].fecha)
        rubro = libro.rubro(categoria.rubro_id).nombre if categoria.rubro_id else ""
        sugerencias.append(Sugerencia(
            ops[-1].descripcion or categoria.nombre, tipo, a_pesos(montos[-1]), cuenta_id, categoria_id, frecuencia,
            siguiente(base, hoy + timedelta(days=1)) or hoy, len(ops),
            tipo is TipoOperacion.GASTO and (rubro == "SUSCRIPCIONES" or len(set(montos)) == 1)))
    return sorted(sugerencias, key=lambda s: (-s.veces, s.nombre.casefold()))


def agregar_sugerencia(libro: Libro, s: Sugerencia) -> Recurrente:
    return crear(libro, s.nombre, s.tipo, s.monto, s.cuenta_id, s.frecuencia, s.siguiente,
                 categoria_id=s.categoria_id, suscripcion=s.suscripcion)
