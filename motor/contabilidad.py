"""Contabilidad técnica: estados financieros de una persona, derivados de sus movimientos.

TALLY ya guarda cada movimiento en partida doble (``Operacion.partidas`` siempre suma cero). Aquí no se captura ni
se guarda nada nuevo: los cuatro reportes son **vistas** de esos mismos movimientos, así que si corriges uno, todos
cambian a la vez y siempre cuadran entre sí.

Convención (la de cualquier contabilidad): una partida positiva va al **Debe** y una negativa al **Haber**.

- Cuentas de débito, ahorro y efectivo → **Activo** (efectivo y bancos). Inversión → Activo (inversiones). Por
  cobrar → Activo (por cobrar): cuando te pagan, la cuenta queda en ceros (se compensa). Bienes (casa, auto,
  laptop) → Activo (bienes), a su costo, menos su depreciación acumulada, más o menos su plusvalía por avalúos.
  Tarjeta de crédito → **Pasivo** a corto plazo.
- Subcategorías de ingreso y de gasto → **Resultados** (cada subcategoría es una subcuenta de su categoría).
- «SALDO INICIAL» → **Patrimonio** con el que empezaste a usar TALLY. «AJUSTE DE SALDO» → resultado (diferencias).
- Patrimonio = patrimonio inicial + resultados acumulados. Por la partida doble, Activo = Pasivo + Patrimonio
  siempre (si no, hay un error y el reporte lo dice).

La depreciación y los avalúos de los bienes no son movimientos: se calculan (motor/bienes.py) y aquí se suman como
asientos calculados, para que el balance y la balanza los reflejen y sigan cuadrando.

En el Estado de Resultados, los **cambios de valor** (rendimientos de tus inversiones, depreciación y plusvalía de
tus bienes, ganancia o pérdida al venderlos) van aparte de tu día a día: no son dinero que ganaste o gastaste.

El flujo de efectivo usa el **método directo**: cuánto efectivo entró y salió, y por qué. Cuenta como efectivo el
dinero en cuentas de débito, ahorro y efectivo (y las de tipo «otra» marcadas como disponibles).

Cada renglón trae su :class:`Origen`: de qué movimientos sale. :func:`movimientos` los lista (el detalle que se ve
al dar clic en un renglón).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal

from motor import bienes, prestamos, reportes
from motor.consultas import ETIQUETA_TIPO_OPERACION
from motor.dinero import a_centavos, a_pesos, formatear
from motor.libro import Libro
from motor.modelo import (
    CATEGORIA_AJUSTE,
    CATEGORIA_BIENES,
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
BIENES = "Bienes (casa, auto, equipo)"
OTROS_ACTIVOS = "Otros activos"
TARJETAS = "Tarjetas de crédito (corto plazo)"
PRESTAMOS_CORTO = "Préstamos a corto plazo (los terminas en un año o menos)"
PRESTAMOS_LARGO = "Préstamos a largo plazo (más de un año)"

PATRIMONIO_INICIAL = "Patrimonio inicial (saldos con los que empezaste)"
RESULTADOS_ANTERIORES = "Resultados de años anteriores"
RESULTADO_DEL_ANIO = "Resultado del año"
RESULTADOS_PREVIOS = "Resultados de periodos anteriores"
AJUSTES = "Ajustes de saldo"
RENDIMIENTOS_INVERSION = "Rendimientos y cambios de valor de tus inversiones"
DEPRECIACION = "Depreciación de tus bienes"
PLUSVALIA = "Plusvalía (o minusvalía) por avalúos"
VENTA_BIENES = "Ganancia o pérdida al vender bienes"

DEPRECIADO, AVALUADO = "depreciacion", "plusvalia"

_TIPOS_EFECTIVO = frozenset({TipoCuenta.DEBITO, TipoCuenta.AHORRO, TipoCuenta.EFECTIVO})


# ---------------------------------------------------------------- origen (detalle)


@dataclass(frozen=True, slots=True)
class Origen:
    """De qué movimientos sale un renglón, para listarlos (:func:`movimientos`).

    - ``cuentas``/``categorias``: las partidas de esas cuentas o subcategorías entre ``desde`` y ``hasta``.
    - ``inversion``: True = solo rendimientos de cuentas de inversión; False = sin ellos; None = todo.
    - ``flujo``: (sección, concepto) del flujo de efectivo (None = cualquiera).
    - ``calculado``: depreciación o plusvalía de los bienes en ``cuentas`` (no son movimientos guardados).
    - ``partes``: un renglón que junta varios orígenes (subtotales y totales).
    - ``signo``: −1 si el renglón se lee al revés de la partida (pasivo, patrimonio, ingresos).
    """

    desde: date | None = None
    hasta: date | None = None
    signo: int = 1
    cuentas: frozenset[str] = frozenset()
    categorias: frozenset[str] = frozenset()
    inversion: bool | None = None
    flujo: tuple[str | None, str | None] | None = None
    calculado: str = ""
    partes: tuple[Origen, ...] = ()


def unir(origenes) -> Origen | None:
    """Un origen con todos los de ``origenes`` (los de cuentas y subcategorías del mismo tipo se juntan, así una
    transferencia entre dos cuentas del mismo grupo no aparece dos veces)."""
    juntos: dict[tuple, Origen] = {}
    otros = []
    for o in origenes:
        for parte in (o.partes or (o,)) if o is not None else ():
            if parte.flujo is None and not parte.calculado:
                clave = (parte.desde, parte.hasta, parte.signo, parte.inversion)
                previo = juntos.get(clave)
                juntos[clave] = parte if previo is None else replace(
                    previo, cuentas=previo.cuentas | parte.cuentas, categorias=previo.categorias | parte.categorias)
            else:
                otros.append(parte)
    partes = (*juntos.values(), *otros)
    if not partes:
        return None
    return partes[0] if len(partes) == 1 else Origen(partes=partes)


@dataclass(frozen=True, slots=True)
class Movimiento:
    fecha: date
    descripcion: str
    tipo: str
    detalle: str                # la otra parte: cuenta o subcategoría
    importe: Decimal            # en el sentido del renglón (con ``Origen.signo``)
    debe: Decimal               # la partida tal cual, para la balanza
    haber: Decimal


def movimientos(libro: Libro, origen: Origen | None) -> list[Movimiento]:
    """Los movimientos (y los asientos calculados de los bienes) que forman un renglón, del más reciente al más
    antiguo."""
    if origen is None:
        return []
    if origen.partes:
        filas = [m for parte in origen.partes for m in movimientos(libro, parte)]
        return sorted(filas, key=lambda m: m.fecha, reverse=True)
    if origen.calculado:
        return _calculados(libro, origen)
    efectivo = {c.id for c in libro.cuentas() if es_efectivo(c)} if origen.flujo is not None else set()
    filas = []
    for op in libro.operaciones(origen.desde, origen.hasta):
        if origen.flujo is not None:
            if not any(p.cuenta_id in efectivo for p in op.partidas_de_cuenta()):
                continue
            seccion, nombre = origen.flujo
            propias = [p for p in op.partidas if p.cuenta_id not in efectivo
                       and (seccion is None or _concepto_de_flujo(libro, p)[0] == seccion)
                       and (nombre is None or _concepto_de_flujo(libro, p)[1] == nombre)]
            centavos = -sum(p.importe for p in propias)
            otras = [p for p in op.partidas if p.cuenta_id in efectivo]
        else:
            if origen.inversion is not None and _es_rendimiento_de_inversion(libro, op) != origen.inversion:
                continue
            propias = [p for p in op.partidas
                       if p.cuenta_id in origen.cuentas or p.categoria_id in origen.categorias]
            centavos = sum(p.importe for p in propias)
            otras = [p for p in op.partidas if p not in propias]
        if not propias or not centavos:
            continue
        importe = a_pesos(centavos * origen.signo)
        filas.append(Movimiento(op.fecha, op.descripcion, ETIQUETA_TIPO_OPERACION[op.tipo],
                                ", ".join(dict.fromkeys(_nombre_partida(libro, p) for p in otras)), importe,
                                a_pesos(max(centavos, 0)), a_pesos(max(-centavos, 0))))
    return list(reversed(filas))


def _calculados(libro: Libro, origen: Origen) -> list[Movimiento]:
    """Depreciación del periodo (un renglón por bien) o el efecto de cada avalúo del periodo."""
    filas = []
    antes = (origen.desde - timedelta(days=1)) if origen.desde else None
    for cuenta_id in origen.cuentas:
        nombre = libro.cuenta(cuenta_id).nombre
        if origen.calculado == DEPRECIADO:
            inicio = bienes.valuar(libro, cuenta_id, antes).depreciacion if antes else Decimal(0)
            cambio = bienes.valuar(libro, cuenta_id, origen.hasta).depreciacion - inicio
            if cambio:
                filas.append(_calculado(origen.hasta, f"Depreciación de {nombre}", "Calculada", cambio,
                                        origen.signo, debe=False))
            continue
        bien = libro.bien(cuenta_id)
        for avaluo in bien.avaluos:
            if (origen.desde and avaluo.fecha < origen.desde) or avaluo.fecha > origen.hasta:
                continue
            cambio = (bienes.valuar(libro, cuenta_id, avaluo.fecha).revaluacion
                      - bienes.valuar(libro, cuenta_id, avaluo.fecha - timedelta(days=1)).revaluacion)
            if cambio:
                filas.append(_calculado(avaluo.fecha, f"Avalúo de {nombre}: {formatear(a_pesos(avaluo.valor))}",
                                        "Avalúo", cambio, origen.signo, debe=True))
    return sorted(filas, key=lambda m: m.fecha, reverse=True)


def _calculado(fecha, descripcion, tipo, cambio: Decimal, signo: int, *, debe: bool) -> Movimiento:
    """Un asiento calculado sobre la cuenta del bien: la depreciación la baja (Haber), un avalúo la mueve."""
    partida = cambio if debe else -cambio
    return Movimiento(fecha, descripcion, tipo, "Calculado (no es un movimiento guardado)", cambio * signo,
                      max(partida, Decimal(0)), max(-partida, Decimal(0)))


def _nombre_partida(libro: Libro, p) -> str:
    if p.cuenta_id is not None:
        return libro.cuenta(p.cuenta_id).nombre
    return {CATEGORIA_SALDO_INICIAL: "Saldo inicial", CATEGORIA_AJUSTE: AJUSTES,
            CATEGORIA_BIENES: VENTA_BIENES}.get(p.categoria_id) or (
        f"{reportes._nombre_rubro(libro, p.categoria_id)} › {libro.categoria(p.categoria_id).nombre}")


# --------------------------------------------------------------- clasificar


def es_efectivo(cuenta: Cuenta) -> bool:
    """Dinero que puedes usar: débito, ahorro, efectivo (y «otra» si la marcaste como disponible)."""
    return cuenta.tipo in _TIPOS_EFECTIVO or (cuenta.tipo is TipoCuenta.OTRA and cuenta.en_disponible)


def clasificar_cuenta(cuenta: Cuenta, libro: Libro | None = None, dia: date | None = None) -> tuple[str, str]:
    """(naturaleza, grupo dentro del Estado de Situación Financiera). Con ``libro`` y ``dia``, un préstamo es de corto
    o largo plazo según cuántos meses te faltan con su pago mensual."""
    if cuenta.tipo is TipoCuenta.CREDITO:
        return PASIVO, TARJETAS
    if cuenta.tipo is TipoCuenta.PRESTAMO:
        if libro is not None and libro.prestamo(cuenta.id) is not None:
            meses = prestamos.meses_restantes(libro, cuenta.id, dia)
            if meses is not None and meses <= 12:
                return PASIVO, PRESTAMOS_CORTO
        return PASIVO, PRESTAMOS_LARGO
    if es_efectivo(cuenta):
        return ACTIVO, EFECTIVO_Y_BANCOS
    if cuenta.tipo is TipoCuenta.INVERSION:
        return ACTIVO, INVERSIONES
    if cuenta.tipo is TipoCuenta.POR_COBRAR:
        return ACTIVO, POR_COBRAR
    if cuenta.tipo is TipoCuenta.BIEN:
        return ACTIVO, BIENES
    return ACTIVO, OTROS_ACTIVOS


def _es_rendimiento_de_inversion(libro: Libro, op: Operacion) -> bool:
    return op.tipo is TipoOperacion.RENDIMIENTO and any(
        libro.cuenta(p.cuenta_id).tipo is TipoCuenta.INVERSION for p in op.partidas_de_cuenta())


def _categorias_de_resultados(libro: Libro) -> frozenset[str]:
    return frozenset(c.id for c in libro.categorias() if c.id != CATEGORIA_SALDO_INICIAL)


def _resultados(libro: Libro, hasta: date, desde: date | None = None) -> int:
    """Resultado acumulado (ingresos − gastos ± ajustes ± cambios de valor de los bienes) en centavos."""
    total = 0
    for op in libro.operaciones(desde, hasta):
        for p in op.partidas_de_categoria():
            if p.categoria_id != CATEGORIA_SALDO_INICIAL:
                total -= p.importe
    total += bienes.ajuste_de_valor(libro, hasta)
    if desde is not None:
        total -= bienes.ajuste_de_valor(libro, desde - timedelta(days=1))
    return total


def _origen_resultados(libro: Libro, desde: date | None, hasta: date) -> Origen | None:
    ids = frozenset(b.cuenta_id for b in libro.bienes())
    return unir([Origen(desde, hasta, -1, categorias=_categorias_de_resultados(libro)),
                 *([Origen(desde, hasta, -1, cuentas=ids, calculado=DEPRECIADO),
                    Origen(desde, hasta, 1, cuentas=ids, calculado=AVALUADO)] if ids else [])])


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
    origen: Origen | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class Situacion:
    fechas: tuple[date, ...]
    renglones: list[Renglon]            # activo, pasivo y patrimonio, en ese orden

    def total(self, naturaleza: str, grupo: str | None = None) -> tuple[Decimal, ...]:
        return _sumar_renglones(self._de(naturaleza, grupo), len(self.fechas))

    def origen(self, naturaleza: str, grupo: str | None = None) -> Origen | None:
        return unir(r.origen for r in self._de(naturaleza, grupo))

    def _de(self, naturaleza: str, grupo: str | None) -> list[Renglon]:
        return [r for r in self.renglones if r.naturaleza == naturaleza and (grupo is None or r.grupo == grupo)]

    def grupos(self, naturaleza: str) -> list[str]:
        return list(dict.fromkeys(r.grupo for r in self.renglones if r.naturaleza == naturaleza))

    @property
    def cuadra(self) -> bool:
        pasivo, patrimonio = self.total(PASIVO), self.total(PATRIMONIO)
        return all(a == p + c for a, p, c in zip(self.total(ACTIVO), pasivo, patrimonio))


_ORDEN_GRUPOS = (EFECTIVO_Y_BANCOS, INVERSIONES, POR_COBRAR, BIENES, OTROS_ACTIVOS, TARJETAS, PRESTAMOS_CORTO,
                 PRESTAMOS_LARGO)


def situacion(libro: Libro, fechas: list[date], desde: date | None = None) -> Situacion:
    """Activo, pasivo y patrimonio al final de cada una de ``fechas``. Las cuentas en ceros en todas se omiten.

    ``desde`` es el inicio del periodo: el detalle de cada cuenta muestra sus movimientos de ``desde`` a la fecha.
    """
    renglones = []
    corte = fechas[0]
    cuentas = sorted(libro.cuentas(), key=lambda c: (_ORDEN_GRUPOS.index(clasificar_cuenta(c, libro, corte)[1]),
                                                     c.orden, c.nombre.casefold()))
    for cuenta in cuentas:
        naturaleza, grupo = clasificar_cuenta(cuenta, libro, corte)
        signo = -1 if naturaleza == PASIVO else 1
        saldos = tuple(libro.saldo_centavos(cuenta.id, f) for f in fechas)
        propios = [Renglon(naturaleza, grupo, cuenta.nombre, tuple(a_pesos(signo * s) for s in saldos),
                           Origen(desde, corte, signo, cuentas=frozenset({cuenta.id})))]
        if libro.bien(cuenta.id) is not None:
            propios += _renglones_de_bien(libro, cuenta, fechas, desde)
        totales = [sum((r.importes[i] for r in propios), Decimal(0)) for i in range(len(fechas))]
        if any(r.importes[i] for r in propios for i in range(len(fechas))) and (
                libro.bien(cuenta.id) is None or any(totales) or len(propios) == 1):
            renglones += [r for r in propios if any(r.importes)]
    ids = frozenset({CATEGORIA_SALDO_INICIAL})
    inicial = tuple(-_saldo_categoria(libro, CATEGORIA_SALDO_INICIAL, f) for f in fechas)
    fin_anterior = date(corte.year - 1, 12, 31)
    anteriores = tuple(_resultados(libro, date(f.year - 1, 12, 31)) for f in fechas)
    del_anio = tuple(_resultados(libro, f, date(f.year, 1, 1)) for f in fechas)
    for nombre, valores, origen in (
            (PATRIMONIO_INICIAL, inicial, Origen(None, corte, -1, categorias=ids)),
            (RESULTADOS_ANTERIORES, anteriores, _origen_resultados(libro, None, fin_anterior)),
            (RESULTADO_DEL_ANIO, del_anio, _origen_resultados(libro, date(corte.year, 1, 1), corte))):
        if any(valores):
            renglones.append(Renglon(PATRIMONIO, PATRIMONIO, nombre, tuple(a_pesos(v) for v in valores), origen))
    return Situacion(tuple(fechas), renglones)


def _renglones_de_bien(libro: Libro, cuenta: Cuenta, fechas: list[date], desde: date | None) -> list[Renglon]:
    valuaciones = [bienes.valuar(libro, cuenta.id, f) for f in fechas]
    ids = frozenset({cuenta.id})
    return [Renglon(ACTIVO, BIENES, f"Depreciación acumulada · {cuenta.nombre}",
                    tuple(-v.depreciacion for v in valuaciones),
                    Origen(desde, fechas[0], -1, cuentas=ids, calculado=DEPRECIADO)),
            Renglon(ACTIVO, BIENES, f"Plusvalía por avalúos · {cuenta.nombre}",
                    tuple(v.revaluacion for v in valuaciones),
                    Origen(desde, fechas[0], 1, cuentas=ids, calculado=AVALUADO))]


def _saldo_categoria(libro: Libro, categoria_id: str, hasta: date, desde: date | None = None) -> int:
    return sum(p.importe for op in libro.operaciones(desde, hasta) for p in op.partidas_de_categoria()
               if p.categoria_id == categoria_id)


# ------------------------------------------------------- estado de resultados


@dataclass(frozen=True, slots=True)
class Resultados:
    periodos: tuple[tuple[date, date], ...]
    ingresos: list[Renglon]             # grupo = categoría, nombre = subcategoría
    gastos: list[Renglon]
    cambios_de_valor: list[Renglon]     # inversiones, depreciación, plusvalía y venta de bienes
    ajustes: Renglon

    def total_ingresos(self) -> tuple[Decimal, ...]:
        return _sumar_renglones(self.ingresos, len(self.periodos))

    def total_gastos(self) -> tuple[Decimal, ...]:
        return _sumar_renglones(self.gastos, len(self.periodos))

    def total_cambios_de_valor(self) -> tuple[Decimal, ...]:
        return _sumar_renglones(self.cambios_de_valor, len(self.periodos))

    def dia_a_dia(self) -> tuple[Decimal, ...]:
        """Ingresos − gastos: lo que te quedó de tu trabajo y tu vida diaria."""
        return tuple(i - g for i, g in zip(self.total_ingresos(), self.total_gastos()))

    def resultado(self) -> tuple[Decimal, ...]:
        """Resultado del periodo: cuánto cambió tu patrimonio por lo que ganaste, gastaste y cambió de valor (sin
        contar los saldos iniciales de cuentas nuevas)."""
        return tuple(d + c + a for d, c, a in zip(self.dia_a_dia(), self.total_cambios_de_valor(),
                                                   self.ajustes.importes))

    @property
    def rendimientos_inversion(self) -> tuple[Decimal, ...]:
        return next(r.importes for r in self.cambios_de_valor if r.nombre == RENDIMIENTOS_INVERSION)

    def origen(self, renglones: list[Renglon]) -> Origen | None:
        return unir(r.origen for r in renglones)


def resultados(libro: Libro, periodos: list[tuple[date, date]]) -> Resultados:
    """Ingresos y gastos por categoría y subcategoría (los reembolsos restan del gasto) en cada periodo."""
    n = len(periodos)
    ingresos: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * n)
    gastos: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * n)
    ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    rendimientos, ajustes, ventas = [0] * n, [0] * n, [0] * n
    depreciacion, plusvalia = [Decimal(0)] * n, [Decimal(0)] * n
    for i, (desde, hasta) in enumerate(periodos):
        for op in libro.operaciones(desde, hasta):
            inversion = _es_rendimiento_de_inversion(libro, op)
            for p in op.partidas_de_categoria():
                categoria = libro.categoria(p.categoria_id)
                clave = (reportes._nombre_rubro(libro, categoria.id), categoria.nombre)
                if p.categoria_id == CATEGORIA_AJUSTE:
                    ajustes[i] -= p.importe
                elif p.categoria_id == CATEGORIA_BIENES:
                    ventas[i] -= p.importe
                elif inversion and categoria.clase is ClaseCategoria.INGRESO:
                    rendimientos[i] -= p.importe
                elif categoria.clase is ClaseCategoria.INGRESO:
                    ingresos[clave][i] -= p.importe
                    ids[clave].add(categoria.id)
                elif categoria.clase is ClaseCategoria.GASTO:
                    gastos[clave][i] += p.importe
                    ids[clave].add(categoria.id)
        for bien in libro.bienes():
            inicio = bienes.valuar(libro, bien.cuenta_id, desde - timedelta(days=1))
            fin = bienes.valuar(libro, bien.cuenta_id, hasta)
            depreciacion[i] -= fin.depreciacion - inicio.depreciacion
            plusvalia[i] += fin.revaluacion - inicio.revaluacion
    desde, hasta = periodos[0]
    de_ingreso = frozenset(c.id for c in libro.categorias() if c.clase is ClaseCategoria.INGRESO)
    con_bienes = frozenset(b.cuenta_id for b in libro.bienes())
    cambios = [
        Renglon(INGRESO, "", RENDIMIENTOS_INVERSION, tuple(a_pesos(v) for v in rendimientos),
                Origen(desde, hasta, -1, categorias=de_ingreso, inversion=True)),
        Renglon(GASTO, "", DEPRECIACION, tuple(depreciacion),
                Origen(desde, hasta, -1, cuentas=con_bienes, calculado=DEPRECIADO)),
        Renglon(INGRESO, "", PLUSVALIA, tuple(plusvalia),
                Origen(desde, hasta, 1, cuentas=con_bienes, calculado=AVALUADO)),
        Renglon(INGRESO, "", VENTA_BIENES, tuple(a_pesos(v) for v in ventas),
                Origen(desde, hasta, -1, categorias=frozenset({CATEGORIA_BIENES}))),
    ]
    return Resultados(
        tuple(periodos),
        _renglones(INGRESO, ingresos, ids, Origen(desde, hasta, -1, inversion=False)),
        _renglones(GASTO, gastos, ids, Origen(desde, hasta, 1)),
        cambios,
        Renglon(GASTO, "", AJUSTES, tuple(a_pesos(v) for v in ajustes),
                Origen(desde, hasta, -1, categorias=frozenset({CATEGORIA_AJUSTE}))))


def _renglones(naturaleza: str, valores: dict[tuple[str, str], list[int]], ids: dict, base: Origen) -> list[Renglon]:
    """Ordenados por el total de su categoría y luego por el suyo, de mayor a menor."""
    por_grupo: dict[str, int] = defaultdict(int)
    for (grupo, _), v in valores.items():
        por_grupo[grupo] += v[0]
    orden = sorted((k for k, v in valores.items() if any(v)),
                   key=lambda k: (-por_grupo[k[0]], k[0], -valores[k][0], k[1]))
    return [Renglon(naturaleza, g, n, tuple(a_pesos(x) for x in valores[(g, n)]),
                    replace(base, categorias=frozenset(ids[(g, n)]))) for g, n in orden]


# ------------------------------------------------------- flujo de efectivo

DIA_A_DIA = "Tu día a día"
FLUJO_TARJETAS = "Tarjetas de crédito"
FLUJO_INVERSIONES = "Inversiones"
FLUJO_BIENES = "Bienes (compras, mejoras y ventas)"
FLUJO_PRESTAMOS = "Préstamos (lo que recibiste y lo que pagaste)"
FLUJO_POR_COBRAR = "Préstamos y cobros"
FLUJO_AJUSTES = "Cuentas nuevas y ajustes"
FLUJO_OTROS = "Otros movimientos"
SECCIONES_FLUJO = (DIA_A_DIA, FLUJO_TARJETAS, FLUJO_PRESTAMOS, FLUJO_INVERSIONES, FLUJO_BIENES, FLUJO_POR_COBRAR,
                   FLUJO_AJUSTES, FLUJO_OTROS)


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

    def origen(self, seccion: str | None = None) -> Origen:
        desde, hasta = self.periodos[0]
        return Origen(desde, hasta, flujo=(seccion, None))

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
    desde, hasta = periodos[0]
    renglones = [Renglon(s, s, n, tuple(a_pesos(x) for x in v), Origen(desde, hasta, flujo=(s, n)))
                 for (s, n), v in sorted(lineas.items(),
                                         key=lambda kv: (SECCIONES_FLUJO.index(kv[0][0]), -abs(kv[1][0]), kv[0][1]))
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
        if p.categoria_id in (CATEGORIA_AJUSTE, CATEGORIA_BIENES):
            return FLUJO_AJUSTES, AJUSTES
        categoria = libro.categoria(p.categoria_id)
        que = "Cobraste" if categoria.clase is ClaseCategoria.INGRESO else "Pagaste"
        return DIA_A_DIA, f"{que}: {reportes._nombre_rubro(libro, categoria.id)}"
    cuenta = libro.cuenta(p.cuenta_id)
    if cuenta.tipo is TipoCuenta.CREDITO:
        return FLUJO_TARJETAS, cuenta.nombre
    if cuenta.tipo is TipoCuenta.INVERSION:
        return FLUJO_INVERSIONES, cuenta.nombre
    if cuenta.tipo is TipoCuenta.BIEN:
        return FLUJO_BIENES, cuenta.nombre
    if cuenta.tipo is TipoCuenta.PRESTAMO:
        return FLUJO_PRESTAMOS, cuenta.nombre
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
    origen: Origen | None = field(default=None, compare=False)

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
    def natural(self) -> Decimal:
        """El saldo final en el sentido de la cuenta: lo que tienes, debes, ganaste o gastaste (positivo)."""
        return self.final if self.naturaleza in DEUDORAS else -self.final

    @property
    def lectura(self) -> str:
        if not (self.inicial or self.debe or self.haber):
            return "Sin movimientos en este periodo"
        if not self.final and (self.inicial or self.debe or self.haber) and self.naturaleza in (ACTIVO, PASIVO):
            return "En ceros: compensada ✓"
        v = self.variacion
        if self.nombre.startswith("Depreciación acumulada"):
            return "Perdió valor" if self.final < self.inicial else "Sin cambio"
        if self.naturaleza == ACTIVO:
            return "Tienes más" if v > 0 else "Tienes menos" if v < 0 else "Sin cambio"
        if self.naturaleza == PASIVO:
            return "Debes más" if v > 0 else "Debes menos ✓" if v < 0 else "Sin cambio"
        if self.naturaleza == PATRIMONIO:
            return "Aumentó" if v > 0 else "Disminuyó" if v < 0 else "Sin cambio"
        if self.nombre == AJUSTES:
            return "Diferencias corregidas"
        if self.nombre in (DEPRECIACION, PLUSVALIA, VENTA_BIENES):
            return "Cambio de valor del periodo"
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
            previo = juntas.setdefault(clave, [Decimal(0), Decimal(0), Decimal(0), []])
            previo[0] += c.inicial
            previo[1] += c.debe
            previo[2] += c.haber
            previo[3].append(c.origen)
        return Balanza(self.desde, self.hasta, [CuentaBalanza(n, nombre, "", i, d, h, unir(o))
                                                for (n, nombre), (i, d, h, o) in juntas.items()])


_ORDEN_NATURALEZA = (ACTIVO, PASIVO, PATRIMONIO, INGRESO, GASTO)


@dataclass(frozen=True, slots=True)
class Comparada:
    """Un renglón de la balanza junto con su saldo final en el periodo contra el que se compara."""

    cuenta: CuentaBalanza
    anterior: Decimal           # saldo final del otro periodo, en el sentido de la cuenta

    @property
    def diferencia(self) -> Decimal:
        return self.cuenta.natural - self.anterior


def comparar_balanzas(actual: Balanza, anterior: Balanza) -> list[Comparada]:
    """Los renglones de ``actual`` con el saldo final de cada cuenta en ``anterior``. Las cuentas que solo tuvieron
    saldo o movimientos en el otro periodo (un gasto que este año no hubo) se agregan en ceros, en su grupo."""
    previos = {(c.naturaleza, c.nombre): c for c in anterior.cuentas}
    vistos = {(c.naturaleza, c.nombre) for c in actual.cuentas}
    faltan = [CuentaBalanza(c.naturaleza, c.nombre, c.categoria, Decimal(0), Decimal(0), Decimal(0))
              for c in anterior.cuentas if (c.naturaleza, c.nombre) not in vistos]
    filas = []
    for naturaleza in _ORDEN_NATURALEZA:
        filas += [c for c in actual.cuentas if c.naturaleza == naturaleza]
        filas += [c for c in faltan if c.naturaleza == naturaleza]
    filas += [c for c in actual.cuentas if c.naturaleza not in _ORDEN_NATURALEZA]
    return [Comparada(c, previos[(c.naturaleza, c.nombre)].natural if (c.naturaleza, c.nombre) in previos
                      else Decimal(0)) for c in filas]


def balanza(libro: Libro, desde: date, hasta: date) -> Balanza:
    """Saldo al inicio, movimientos (Debe y Haber) y saldo al final de cada cuenta y subcuenta del periodo.

    Las cuentas de resultados (ingresos, gastos, ajustes) empiezan cada periodo en cero: lo acumulado antes está en
    «Resultados de periodos anteriores», dentro del patrimonio. La depreciación y los avalúos de los bienes entran
    como asientos calculados.
    """
    antes = desde - timedelta(days=1)
    inicial: dict[tuple, int] = defaultdict(int)
    debe: dict[tuple, int] = defaultdict(int)
    haber: dict[tuple, int] = defaultdict(int)
    origenes: dict[tuple, Origen] = {}
    previos = 0
    for op in libro.operaciones(hasta=hasta):
        for p in op.partidas:
            clave = _clave_balanza(libro, p)
            origenes.setdefault(clave, _origen_balanza(p, desde, hasta))
            if op.fecha <= antes:
                if clave[0] in (INGRESO, GASTO):
                    previos += p.importe
                else:
                    inicial[clave] += p.importe
            elif p.importe > 0:
                debe[clave] += p.importe
            else:
                haber[clave] -= p.importe

    def asentar(clave, importe_antes: int, importe_periodo: int, origen: Origen) -> None:
        nonlocal previos
        origenes[clave] = origen
        if clave[0] in (INGRESO, GASTO):
            previos += importe_antes
        else:
            inicial[clave] += importe_antes
        if importe_periodo > 0:
            debe[clave] += importe_periodo
        else:
            haber[clave] -= importe_periodo

    for bien in libro.bienes():
        nombre = libro.cuenta(bien.cuenta_id).nombre
        ids = frozenset({bien.cuenta_id})
        v0, v1 = bienes.valuar(libro, bien.cuenta_id, antes), bienes.valuar(libro, bien.cuenta_id, hasta)
        d0, d1 = a_centavos(v0.depreciacion), a_centavos(v1.depreciacion)
        r0, r1 = a_centavos(v0.revaluacion), a_centavos(v1.revaluacion)
        if d0 or d1:
            asentar((ACTIVO, f"Depreciación acumulada · {nombre}", ""), -d0, -(d1 - d0),
                    Origen(desde, hasta, 1, cuentas=ids, calculado=DEPRECIADO))
            asentar((GASTO, DEPRECIACION, ""), d0, d1 - d0, Origen(desde, hasta, 1, cuentas=ids, calculado=DEPRECIADO))
        if r0 or r1:
            asentar((ACTIVO, f"Plusvalía por avalúos · {nombre}", ""), r0, r1 - r0,
                    Origen(desde, hasta, 1, cuentas=ids, calculado=AVALUADO))
            asentar((INGRESO, PLUSVALIA, ""), -r0, -(r1 - r0),
                    Origen(desde, hasta, 1, cuentas=ids, calculado=AVALUADO))
    if previos:
        inicial[(PATRIMONIO, RESULTADOS_PREVIOS, "")] += previos
        origenes[(PATRIMONIO, RESULTADOS_PREVIOS, "")] = _origen_resultados(libro, None, antes)
    claves = set(inicial) | set(debe) | set(haber)
    orden_cuentas = {c.nombre: i for i, c in enumerate(libro.cuentas())}
    filas = [CuentaBalanza(k[0], k[1], k[2], a_pesos(inicial[k]), a_pesos(debe[k]), a_pesos(haber[k]),
                           origenes.get(k)) for k in claves if inicial[k] or debe[k] or haber[k]]
    filas.sort(key=lambda c: (_ORDEN_NATURALEZA.index(c.naturaleza),
                              orden_cuentas.get(c.nombre.split(" · ")[-1], 10**6), c.categoria, c.nombre))
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
    if p.categoria_id == CATEGORIA_BIENES:
        return GASTO, VENTA_BIENES, ""
    categoria = libro.categoria(p.categoria_id)
    rubro = reportes._nombre_rubro(libro, categoria.id)
    naturaleza = INGRESO if categoria.clase is ClaseCategoria.INGRESO else GASTO
    return naturaleza, f"{rubro} › {categoria.nombre}", rubro


def _origen_balanza(p, desde: date, hasta: date) -> Origen:
    if p.cuenta_id is not None:
        return Origen(desde, hasta, cuentas=frozenset({p.cuenta_id}))
    return Origen(desde, hasta, categorias=frozenset({p.categoria_id}))


# ---------------------------------------------------------------- internos


def _sumar_renglones(renglones: list[Renglon], largo: int) -> tuple[Decimal, ...]:
    return tuple(sum((r.importes[i] for r in renglones), Decimal(0)) for i in range(largo))
