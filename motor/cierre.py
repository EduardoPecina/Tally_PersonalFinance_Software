"""Cierre de mes: la «boleta» de un mes que terminó. Junta lo de todas las páginas y dice qué pasó, qué estuvo bien,
qué no y qué hacer el mes siguiente.

- **Veredicto**: cuánto entró, cuánto salió y cuánto ahorraste, contra tu meta de ahorro, el mes anterior y tu
  promedio de los 3 meses previos.
- **A dónde se fue**: cada categoría contra su promedio, los gastos hormiga (muchos gastos chicos) y las
  suscripciones que te cobraron.
- **Presupuestos, ingresos fijos, deudas, metas y patrimonio** de ese mes.
- **Para cerrar bien**: lo que falta registrar (pagos del calendario, cargos que no te han devuelto, el pago de una
  tarjeta).
- **Recomendaciones**: hasta 3, calculadas con tus números (nada sale de tu computadora).

**Cerrar un mes no lo bloquea** (no es la contabilidad de una empresa): guarda cómo estaban sus números. Si después
registras o corriges algo de ese mes, el cierre lo muestra como «cambios después de cerrar», y puedes volver a
cerrarlo para aceptarlos.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from motor import categorias, metas, planeacion, recurrentes, reportes, tarjetas, temporales
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import CierreMes, ClaseCategoria, Operacion, TipoCuenta, TipoOperacion

CERO = Decimal("0.00")
UMBRAL_HORMIGA = Decimal(100)          # un gasto «hormiga»: menos de esto
SUBE_PORCENTAJE = Decimal(20)          # una categoría «subió» si gastaste 20 % más que tu promedio…
SUBE_MINIMO = Decimal(200)             # …y al menos 200 más
INTERESES = ("INTERESES DE TARJETAS", "INTERESES DE PRESTAMOS", "COMISIONES BANCARIAS", "ANUALIDADES")
DIAS_AVISO = 10                        # los primeros días del mes, el Resumen te recuerda cerrar el anterior


def clave(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


def rango(anio: int, mes: int) -> tuple[date, date]:
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def meses(libro: Libro, hoy: date | None = None) -> list[tuple[int, int]]:
    """Los meses con movimientos, del más reciente al más antiguo (el mes en curso incluido)."""
    hoy = hoy or libro.hoy()
    fechas = [op.fecha for op in libro.operaciones() if op.tipo is not TipoOperacion.SALDO_INICIAL
              and op.fecha <= hoy]
    if not fechas:
        return []
    resultado, dia = [], hoy.replace(day=1)
    primero = min(fechas).replace(day=1)
    while dia >= primero:
        resultado.append((dia.year, dia.month))
        dia = (dia - timedelta(days=1)).replace(day=1)
    return resultado


def anterior(hoy: date) -> tuple[int, int]:
    dia = hoy.replace(day=1) - timedelta(days=1)
    return dia.year, dia.month


# ===================================================================== el reporte


@dataclass(frozen=True, slots=True)
class Numeros:
    ingresos: Decimal
    gastos: Decimal

    @property
    def ahorro(self) -> Decimal:
        return self.ingresos - self.gastos

    @property
    def tasa(self) -> Decimal | None:
        """Qué parte de lo que entró ahorraste (%)."""
        return (self.ahorro / self.ingresos * 100).quantize(Decimal("0.1")) if self.ingresos else None


@dataclass(frozen=True, slots=True)
class Rubro:
    nombre: str
    gastado: Decimal
    promedio: Decimal | None           # en los meses previos (None si no hay historial)

    @property
    def diferencia(self) -> Decimal | None:
        return None if self.promedio is None else self.gastado - self.promedio

    @property
    def subio(self) -> bool:
        d = self.diferencia
        return d is not None and d >= SUBE_MINIMO and (not self.promedio or d * 100 >= self.promedio * SUBE_PORCENTAJE)


@dataclass(frozen=True, slots=True)
class Hormiga:
    veces: int
    total: Decimal
    ejemplos: list[tuple[str, int, Decimal]]     # (descripción, veces, total), los que más suman


@dataclass(frozen=True, slots=True)
class IngresoFijo:
    nombre: str
    esperado: Decimal
    recibido: Decimal
    faltan: list[date]                 # pagos que no llegaron (o no registraste)


@dataclass(frozen=True, slots=True)
class Deuda:
    nombre: str
    al_inicio: Decimal                 # lo que debías al empezar el mes
    al_final: Decimal

    @property
    def cambio(self) -> Decimal:
        """Negativo: bajó."""
        return self.al_final - self.al_inicio


@dataclass(frozen=True, slots=True)
class MetaDelMes:
    nombre: str
    aportado: Decimal                  # neto, en el mes
    ahorrado: Decimal                  # al final del mes
    objetivo: Decimal
    a_tiempo: bool | None
    emergencia: bool


@dataclass(frozen=True, slots=True)
class Pendiente:
    clase: str                         # "calendario", "temporal" o "tarjeta"
    texto: str
    fecha: date


@dataclass(frozen=True, slots=True)
class Cambios:
    """Lo que cambió en el mes después de cerrarlo."""

    ingresos: Decimal                  # actual − al cerrar
    gastos: Decimal
    patrimonio: Decimal
    nuevos: list[Operacion]            # registrados después de cerrar
    editados: list[Operacion]
    borrados: int

    @property
    def hay(self) -> bool:
        return bool(self.ingresos or self.gastos or self.patrimonio or self.nuevos or self.editados or self.borrados)


@dataclass(frozen=True, slots=True)
class Reporte:
    anio: int
    mes: int
    desde: date
    hasta: date
    en_curso: bool                     # el mes aún no termina
    numeros: Numeros
    anterior: Numeros | None           # el mes anterior (si tiene datos)
    promedio: Numeros | None           # promedio de hasta 3 meses previos con datos
    meta_ahorro: int                   # tu meta de ahorro (% del ingreso)
    rubros: list[Rubro]
    hormiga: Hormiga
    suscripciones: list[tuple[str, Decimal]]
    presupuestos: list[reportes.AvancePresupuesto]
    ingresos_fijos: list[IngresoFijo]
    deudas: list[Deuda]
    intereses: Decimal                 # intereses y comisiones que pagaste en el mes
    metas: list[MetaDelMes]
    fondo_meses: Decimal | None        # cuántos meses de gastos esenciales cubre tu fondo de emergencia
    patrimonio_inicio: Decimal
    patrimonio_fin: Decimal
    pendientes: list[Pendiente]
    recomendaciones: list[str]
    movimientos: int
    cierre: CierreMes | None = None
    cambios: Cambios | None = None
    subieron: list[Rubro] = field(default_factory=list)

    @property
    def cerrado(self) -> bool:
        return self.cierre is not None


def reporte(libro: Libro, anio: int, mes: int, hoy: date | None = None) -> Reporte:
    hoy = hoy or libro.hoy()
    desde, hasta = rango(anio, mes)
    numeros = resultado(libro, desde, hasta)
    previos = planeacion._meses_con_datos(libro, planeacion.meses_completos(desde))
    anterior_ = resultado(libro, *previos[-1]) if previos and previos[-1][0] == _mes_anterior(desde) else None
    promedio = None
    if previos:
        sumas = [resultado(libro, a, b) for a, b in previos]
        n = len(sumas)
        promedio = Numeros((sum((s.ingresos for s in sumas), CERO) / n).quantize(Decimal("0.01")),
                           (sum((s.gastos for s in sumas), CERO) / n).quantize(Decimal("0.01")))
    rubros = _rubros(libro, desde, hasta, previos)
    patrimonio_inicio = reportes.indicadores(libro, desde - timedelta(days=1)).patrimonio_neto
    patrimonio_fin = reportes.indicadores(libro, min(hasta, hoy)).patrimonio_neto
    fondo = metas.fondo(libro, hasta + timedelta(days=1))
    datos = dict(
        anio=anio, mes=mes, desde=desde, hasta=hasta, en_curso=hasta >= hoy, numeros=numeros, anterior=anterior_,
        promedio=promedio, meta_ahorro=libro.perfil.meta_ahorro if libro.perfil else 10, rubros=rubros,
        hormiga=_hormiga(libro, desde, hasta), suscripciones=_suscripciones(libro, desde, hasta),
        presupuestos=reportes.presupuestos(libro, desde, hasta), ingresos_fijos=_ingresos_fijos(libro, desde, hasta, hoy),
        deudas=_deudas(libro, desde, hasta), intereses=_intereses(libro, desde, hasta),
        metas=_metas(libro, desde, hasta), fondo_meses=fondo.meses_cubiertos,
        patrimonio_inicio=patrimonio_inicio, patrimonio_fin=patrimonio_fin,
        pendientes=_pendientes(libro, desde, hasta, hoy),
        movimientos=len(libro.operaciones(desde, hasta)),
        subieron=sorted((r for r in rubros if r.subio), key=lambda r: -(r.diferencia or 0)),
    )
    cierre_ = libro.cierre(clave(anio, mes))
    datos["cierre"] = cierre_
    datos["cambios"] = cambios(libro, cierre_) if cierre_ else None
    r = Reporte(**datos, recomendaciones=[])
    return replace(r, recomendaciones=recomendaciones(r))


def _mes_anterior(desde: date) -> date:
    return (desde - timedelta(days=1)).replace(day=1)


def resultado(libro: Libro, desde: date, hasta: date) -> Numeros:
    """Cuánto entró y cuánto salió entre dos fechas."""
    r = reportes.resumen(libro, desde, hasta)
    return Numeros(r.ingresos, r.gastos)


def _rubros(libro: Libro, desde: date, hasta: date, previos: list[tuple[date, date]]) -> list[Rubro]:
    actual = reportes.gastos_por_rubro(libro, desde, hasta)
    promedios: dict[str, Decimal] = defaultdict(Decimal)
    for a, b in previos:
        for nombre, total in reportes.gastos_por_rubro(libro, a, b).items():
            promedios[nombre] += total
    n = len(previos)
    nombres = [k for k, v in actual.items() if v > 0] + sorted(k for k in promedios if k not in actual and promedios[k] > 0)
    return [Rubro(nombre, actual.get(nombre, CERO),
                  (promedios[nombre] / n).quantize(Decimal("0.01")) if n else None) for nombre in nombres]


def _hormiga(libro: Libro, desde: date, hasta: date) -> Hormiga:
    montos: dict[str, list[Decimal]] = defaultdict(list)
    nombres: dict[str, str] = {}                      # cómo se escribió (se agrupa sin mayúsculas)
    for op in libro.operaciones(desde, hasta):
        if op.tipo is not TipoOperacion.GASTO:
            continue
        partidas = [p for p in op.partidas_de_categoria() if libro.categoria(p.categoria_id).clase is ClaseCategoria.GASTO]
        monto = a_pesos(sum(p.importe for p in partidas))
        if partidas and 0 < monto < UMBRAL_HORMIGA:
            nombre = " ".join(op.descripcion.split()) or libro.categoria(partidas[0].categoria_id).nombre
            montos[nombre.casefold()].append(monto)
            nombres.setdefault(nombre.casefold(), nombre)
    ejemplos = sorted(((nombres[k], len(v), sum(v, CERO)) for k, v in montos.items()),
                      key=lambda e: (-e[2], -e[1], e[0].casefold()))
    return Hormiga(sum(e[1] for e in ejemplos), sum((e[2] for e in ejemplos), CERO), ejemplos[:5])


def _suscripciones(libro: Libro, desde: date, hasta: date) -> list[tuple[str, Decimal]]:
    resultado = []
    for r in libro.recurrentes():
        if r.tipo is not TipoOperacion.GASTO or not r.suscripcion:
            continue
        hechos = recurrentes.pagos(libro, r, recurrentes.fechas(r, desde, hasta))
        total = sum((recurrentes.op_monto(op, r) for op in hechos.values()), 0)
        if total:
            resultado.append((r.nombre, a_pesos(total)))
    return sorted(resultado, key=lambda s: -s[1])


def _ingresos_fijos(libro: Libro, desde: date, hasta: date, hoy: date) -> list[IngresoFijo]:
    resultado = []
    for r in libro.recurrentes():
        if r.tipo is not TipoOperacion.INGRESO or not r.activa:
            continue
        dias = [d for d in recurrentes.fechas(r, desde, hasta) if d <= hoy]
        if not dias:
            continue
        hechos = recurrentes.pagos(libro, r, dias)
        resultado.append(IngresoFijo(
            r.nombre, a_pesos(sum(recurrentes.monto_en(r, d) for d in dias)),
            a_pesos(sum(recurrentes.op_monto(op, r) for op in hechos.values())),
            [d for d in dias if d not in hechos]))
    return resultado


def _deudas(libro: Libro, desde: date, hasta: date) -> list[Deuda]:
    resultado = []
    for c in libro.cuentas():
        if c.tipo not in (TipoCuenta.CREDITO, TipoCuenta.PRESTAMO):
            continue
        inicio = max(0, -libro.saldo_centavos(c.id, desde - timedelta(days=1)))
        final = max(0, -libro.saldo_centavos(c.id, hasta))
        if inicio or final:
            resultado.append(Deuda(c.nombre, a_pesos(inicio), a_pesos(final)))
    return resultado


def _intereses(libro: Libro, desde: date, hasta: date) -> Decimal:
    ids = {c.id for nombre in INTERESES if (c := categorias.buscar(libro, nombre)) is not None}
    total = 0
    for op in libro.operaciones(desde, hasta):
        total += sum(p.importe for p in op.partidas_de_categoria() if p.categoria_id in ids)
    return a_pesos(total)


def _metas(libro: Libro, desde: date, hasta: date) -> list[MetaDelMes]:
    resultado = []
    for m in libro.metas():
        aportado = sum(a.centavos for a in m.aportes if desde <= a.fecha <= hasta and a.operacion_id != metas.INICIAL)
        if not m.activa and not aportado:
            continue
        ahorrado = sum(a.centavos for a in m.aportes if a.fecha <= hasta)
        resultado.append(MetaDelMes(m.nombre, a_pesos(aportado), a_pesos(ahorrado), a_pesos(m.objetivo),
                                    metas.estado(m, min(hasta, libro.hoy())).a_tiempo, m.emergencia))
    return resultado


def _pendientes(libro: Libro, desde: date, hasta: date, hoy: date) -> list[Pendiente]:
    resultado = []
    for r in libro.recurrentes():
        if not r.activa:
            continue
        dias = [d for d in recurrentes.fechas(r, desde, hasta) if d < hoy]
        hechos = recurrentes.pagos(libro, r, dias)
        for d in dias:
            if d not in hechos:
                resultado.append(Pendiente("calendario", f"{r.nombre}: no está registrado el del {d:%d/%m}", d))
    for c in temporales.pendientes(libro, hoy):
        if c.fecha <= hasta:
            resultado.append(Pendiente("temporal", f"{c.descripcion or 'Cargo temporal'} ({c.cuenta}): aún no te "
                                                   f"lo devuelven", c.fecha))
    for t in libro.cuentas():
        if t.tipo is not TipoCuenta.CREDITO or not t.activa:
            continue
        corte = tarjetas.ciclo_por_pagar(libro, t.id, hoy)
        if (corte is not None and corte.por_liquidar and corte.fin <= hasta and corte.fecha_limite_pago
                and corte.fecha_limite_pago < hoy):
            resultado.append(Pendiente("tarjeta", f"{t.nombre}: falta registrar el pago del corte del "
                                                  f"{corte.fin:%d/%m}", corte.fecha_limite_pago))
    return sorted(resultado, key=lambda p: p.fecha)


# ===================================================================== recomendaciones


def _dinero(valor: Decimal) -> str:
    return f"${valor:,.2f}"


def recomendaciones(r: Reporte) -> list[str]:
    """Hasta 3 recomendaciones, de la más importante a la menos."""
    lista: list[str] = []
    n = r.numeros
    if n.ingresos and n.ahorro < 0:
        lista.append(f"Gastaste {_dinero(-n.ahorro)} más de lo que entró. Antes de cualquier otra cosa, revisa en "
                     "qué categorías te pasaste y pon un presupuesto ahí.")
    elif n.tasa is not None and n.tasa < r.meta_ahorro:
        falta = (n.ingresos * r.meta_ahorro / 100 - n.ahorro).quantize(Decimal("0.01"))
        lista.append(f"Ahorraste el {n.tasa} % y tu meta es el {r.meta_ahorro} %: te faltaron {_dinero(falta)}. "
                     "Apártalo apenas te paguen, no al final del mes.")
    if r.subieron:
        s = r.subieron[0]
        lista.append(f"En {s.nombre} gastaste {_dinero(s.diferencia)} más que tu promedio. Si vuelves a tu promedio, "
                     f"son {_dinero(s.diferencia)} más de ahorro al mes.")
    pasados = sorted((p for p in r.presupuestos if p.restante < 0), key=lambda p: p.restante)
    if pasados:
        p = pasados[0]
        otros = f" (y en {len(pasados) - 1} más)" if len(pasados) > 1 else ""
        lista.append(f"Te pasaste del presupuesto de {p.nombre} por {_dinero(-p.restante)}{otros}. Ajusta el "
                     "presupuesto a algo realista o recorta ese gasto.")
    if r.intereses > 0:
        lista.append(f"Pagaste {_dinero(r.intereses)} de intereses y comisiones. Pagar tus tarjetas completas "
                     "(para no generar intereses) te ahorra ese dinero.")
    if r.hormiga.veces >= 15 or (n.gastos and r.hormiga.total * 10 >= n.gastos):
        lista.append(f"Tuviste {r.hormiga.veces} gastos chicos (menos de {_dinero(UMBRAL_HORMIGA)}) que sumaron "
                     f"{_dinero(r.hormiga.total)}. Uno por uno no se nota; juntos, sí.")
    if r.fondo_meses is not None and r.fondo_meses < metas.MESES_FONDO[0]:
        lista.append(f"Tu fondo de emergencia cubre {r.fondo_meses} meses de tus gastos esenciales; lo recomendable "
                     f"son al menos {metas.MESES_FONDO[0]}.")
    faltan = [i for i in r.ingresos_fijos if i.faltan]
    if faltan:
        lista.append(f"No aparece «{faltan[0].nombre}» del {faltan[0].faltan[0]:%d/%m}. Si ya te llegó, regístralo "
                     "para que tus números cuadren.")
    if not lista and n.ingresos:
        lista.append(f"¡Buen mes! Ahorraste el {n.tasa} % de lo que entró. Si te sobra, súmalo a una meta o a tu "
                     "fondo de emergencia.")
    return lista[:3]


# ===================================================================== cerrar y lo que cambió después


def cerrar(libro: Libro, anio: int, mes: int, notas: str = "") -> CierreMes:
    """Marca el mes como cerrado (o lo vuelve a cerrar, aceptando los cambios): guarda sus números de hoy."""
    desde, hasta = rango(anio, mes)
    if hasta >= libro.hoy():
        raise ErrorValidacion("Ese mes aún no termina: ciérralo cuando acabe.")
    r = reportes.resumen(libro, desde, hasta)
    return libro.guardar_cierre(CierreMes(
        clave(anio, mes), libro.ahora(), a_centavos(r.ingresos), a_centavos(r.gastos),
        a_centavos(reportes.indicadores(libro, hasta).patrimonio_neto), len(libro.operaciones(desde, hasta)),
        notas.strip()))


def reabrir(libro: Libro, anio: int, mes: int) -> None:
    """Quita el cierre (tus movimientos no se tocan)."""
    libro.quitar_cierre(clave(anio, mes))


def cambios(libro: Libro, cierre_: CierreMes) -> Cambios:
    anio, mes = (int(x) for x in cierre_.id.split("-"))
    desde, hasta = rango(anio, mes)
    ops = libro.operaciones(desde, hasta)
    nuevos = [op for op in ops if op.creado_en and op.creado_en > cierre_.cerrado_en]
    ids_nuevos = {op.id for op in nuevos}
    editados = [op for op in ops if op.id not in ids_nuevos and op.modificado_en
                and op.modificado_en > cierre_.cerrado_en]
    r = reportes.resumen(libro, desde, hasta)
    return Cambios(
        r.ingresos - a_pesos(cierre_.ingresos), r.gastos - a_pesos(cierre_.gastos),
        reportes.indicadores(libro, hasta).patrimonio_neto - a_pesos(cierre_.patrimonio),
        nuevos, editados, max(0, cierre_.movimientos - (len(ops) - len(nuevos))))


def cerrado(libro: Libro, fecha: date) -> CierreMes | None:
    """El cierre del mes de ``fecha`` (o ``None`` si ese mes no está cerrado)."""
    return libro.cierre(clave(fecha.year, fecha.month))


def huella(libro: Libro) -> dict[str, tuple[date, datetime | None]]:
    """Para saber qué movimientos cambió una acción: id → (fecha, última modificación)."""
    return {op.id: (op.fecha, op.modificado_en) for op in libro.operaciones()}


def meses_tocados(libro: Libro, antes: dict[str, tuple[date, datetime | None]]) -> list[str]:
    """Los meses cerrados donde una acción agregó, cambió o borró movimientos (comparando con ``antes``)."""
    despues = huella(libro)
    fechas = [antes[i][0] for i in antes.keys() - despues.keys()]               # borrados
    fechas += [despues[i][0] for i in despues.keys() - antes.keys()]            # nuevos
    for i in antes.keys() & despues.keys():
        if antes[i] != despues[i]:
            fechas += [antes[i][0], despues[i][0]]                              # cambió (quizá de fecha)
    return sorted({clave(f.year, f.month) for f in fechas if cerrado(libro, f)})


def recordar(libro: Libro, hoy: date | None = None) -> tuple[int, int] | None:
    """Los primeros días del mes: el mes anterior, si tiene movimientos y no lo has cerrado."""
    hoy = hoy or libro.hoy()
    if hoy.day > DIAS_AVISO:
        return None
    anio, mes = anterior(hoy)
    if libro.cierre(clave(anio, mes)) is not None:
        return None
    desde, hasta = rango(anio, mes)
    if not any(op.tipo is not TipoOperacion.SALDO_INICIAL for op in libro.operaciones(desde, hasta)):
        return None
    return anio, mes
