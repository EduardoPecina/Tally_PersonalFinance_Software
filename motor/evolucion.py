"""Rendimiento de tus inversiones a lo largo del tiempo: cuánto valían, cuánto metiste y sacaste, y cuánto ganaste.

Dos formas de verlo, con el mismo resultado (:class:`Evolucion`) para que las gráficas y los totales sean iguales:

- **Por título** (:func:`por_titulo`): cada símbolo y cada inversión a plazo, día por día, con precios de mercado.
  Es una **estimación**: precio de cierre diario (de :mod:`motor.cotizaciones`, guardado en tu PC) por los títulos
  que tenías ese día, en pesos. Si un día no hay precio se usa el más reciente conocido (tu precio de compra o el
  último consultado). Las inversiones a plazo crecen con interés simple y, al vencer, su dinero sale (vuelve a la
  cuenta), así que reinvertirlo en otro CETE no se cuenta dos veces.
- **Oficial** (:func:`oficial`): el saldo de cada cuenta de inversión en TALLY. Lo que entra o sale con
  transferencias es dinero que metiste o sacaste; lo que cambia con rendimientos (los ajustes al valor oficial de
  tu app) es la ganancia. Es exacto: solo cambia cuando registras el valor oficial.

La ganancia de un periodo es ``valor final − valor inicial − (lo que metiste − lo que sacaste)``. El rendimiento
en % usa el método de Dietz modificado: divide la ganancia entre el valor inicial más lo que metiste, pesado por
el tiempo que estuvo invertido (meter dinero el último día no infla el %).

Todo es aritmética en tu PC; este módulo no sale a internet.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from motor import portafolio
from motor.dinero import a_pesos
from motor.libro import Libro
from motor.modelo import TipoCuenta, TipoOperacion, TipoOperacionValor

CERO = Decimal(0)
CENTAVO = Decimal("0.01")
TITULO, PLAZO, CUENTA = "titulo", "plazo", "cuenta"

Mercado = dict[str, tuple[str, dict[date, Decimal]]]     # símbolo → (moneda, {fecha: precio de cierre})


@dataclass(frozen=True, slots=True)
class Instrumento:
    """Lo que se puede elegir en las gráficas: un símbolo, un tipo de inversión a plazo o una cuenta."""

    nombre: str      # IVV, CETES 28 DÍAS, GBM…
    tipo: str        # TITULO, PLAZO o CUENTA

    @property
    def etiqueta(self) -> str:
        return f"{self.nombre} (a plazo)" if self.tipo == PLAZO else self.nombre


@dataclass(frozen=True, slots=True)
class Evolucion:
    """Valor de cada serie al cierre de cada día, y el dinero que le entró (+) o salió (−) ese día.

    ``fechas[0]`` es el día **anterior** a ``desde``: su valor es el valor inicial del periodo.
    """

    desde: date
    hasta: date
    fechas: list[date]
    valores: dict[str, list[Decimal]]
    flujos: dict[str, list[Decimal]]
    estimados: frozenset[str] = field(default_factory=frozenset)   # series sin historial de precios

    @property
    def nombres(self) -> list[str]:
        return list(self.valores)


@dataclass(frozen=True, slots=True)
class Resultado:
    valor_inicial: Decimal
    entradas: Decimal          # dinero que metiste (compras, inversiones a plazo, aportaciones)
    salidas: Decimal           # dinero que sacaste (ventas, vencimientos, retiros), en positivo
    valor_final: Decimal
    ganancia: Decimal
    rendimiento: Decimal | None    # en %, Dietz modificado; None si no hubo dinero invertido


# ------------------------------------------------------------------ elegir


def instrumentos(libro: Libro, cuenta_ids: list[str]) -> list[Instrumento]:
    """Los símbolos y tipos de inversión a plazo de esas cuentas (cada uno una vez aunque esté en varias; los
    plazos se juntan por nombre sin importar mayúsculas: «Cetes 28 días» y «CETES 28 DÍAS» son lo mismo)."""
    titulos = sorted({v.simbolo for c in cuenta_ids for v in libro.valores(c)})
    plazos: dict[str, str] = {}
    for p in sorted((p for c in cuenta_ids for p in libro.plazos(c)), key=lambda p: p.fecha_inicio):
        plazos.setdefault(p.nombre.casefold(), p.nombre)
    return [Instrumento(s, TITULO) for s in titulos] + [Instrumento(n, PLAZO) for n in sorted(plazos.values())]


def cuentas_de_inversion(libro: Libro) -> list[str]:
    """Las cuentas de inversión, también las eliminadas que conservan historial."""
    return [c.id for c in libro.cuentas() if c.tipo is TipoCuenta.INVERSION]


def primera_fecha(libro: Libro, cuenta_ids: list[str], *, oficial: bool = False) -> date | None:
    """El primer día con algo que mostrar: la primera compra o inversión a plazo (o el primer movimiento)."""
    if oficial:
        fechas = [op.fecha for op in libro.operaciones()
                  if any(p.cuenta_id in cuenta_ids for p in op.partidas)]
    else:
        fechas = [v.fecha for c in cuenta_ids for v in libro.valores(c)]
        fechas += [p.fecha_inicio for c in cuenta_ids for p in libro.plazos(c)]
    return min(fechas, default=None)


PERIODOS = {
    "mes": "Este mes", "mes_pasado": "Mes pasado", "3m": "Últimos 3 meses", "6m": "Últimos 6 meses",
    "anio": "Este año", "1a": "Último año", "2a": "Últimos 2 años", "5a": "Últimos 5 años",
    "10a": "Últimos 10 años", "todo": "Desde el inicio", "rango": "Elegir fechas",
}
_MESES_ATRAS = {"3m": 3, "6m": 6, "1a": 12, "2a": 24, "5a": 60, "10a": 120}


def rango(clave: str, hoy: date, inicio: date | None = None,
          elegido: tuple[date, date] | None = None) -> tuple[date, date]:
    """Fechas (inclusivas) de un periodo de :data:`PERIODOS`. Nunca empieza antes de ``inicio`` (si se da)."""
    if clave == "mes":
        desde, hasta = hoy.replace(day=1), hoy
    elif clave == "mes_pasado":
        hasta = hoy.replace(day=1) - timedelta(days=1)
        desde = hasta.replace(day=1)
    elif clave == "anio":
        desde, hasta = hoy.replace(month=1, day=1), hoy
    elif clave in _MESES_ATRAS:
        desde, hasta = _restar_meses(hoy, _MESES_ATRAS[clave]) + timedelta(days=1), hoy
    elif clave == "rango" and elegido:
        desde, hasta = min(elegido), min(max(elegido), hoy)
    else:
        desde, hasta = inicio or hoy, hoy
    if inicio is not None and desde < inicio <= hasta:
        desde = inicio
    return desde, hasta


def _restar_meses(dia: date, meses: int) -> date:
    total = dia.year * 12 + dia.month - 1 - meses
    anio, mes = divmod(total, 12)
    siguiente = date(anio + (mes + 1) // 12, (mes + 1) % 12 + 1, 1)
    return date(anio, mes + 1, min(dia.day, (siguiente - timedelta(days=1)).day))


# --------------------------------------------------------------- calcular


def por_titulo(libro: Libro, cuenta_ids: list[str], desde: date, hasta: date, mercado: Mercado,
               elegidos: set[Instrumento] | None = None) -> Evolucion:
    """Valor estimado de cada símbolo y tipo de inversión a plazo, día por día (ver el inicio del módulo)."""
    fechas = _dias(desde - timedelta(days=1), hasta)
    valores: dict[str, list[Decimal]] = {}
    flujos: dict[str, list[Decimal]] = {}
    estimados = set()
    tipos = _tipos_de_cambio(libro, cuenta_ids, mercado)
    for instrumento in instrumentos(libro, cuenta_ids):
        if elegidos is not None and instrumento not in elegidos:
            continue
        if instrumento.tipo == TITULO:
            operaciones = [v for c in cuenta_ids for v in libro.valores(c) if v.simbolo == instrumento.nombre]
            precio, real = _precios_en_pesos(instrumento.nombre, operaciones, mercado, tipos)
            valor, flujo = _serie_titulo(operaciones, fechas, precio)
            if not real:
                estimados.add(instrumento.etiqueta)
        else:
            plazos = [p for c in cuenta_ids for p in libro.plazos(c)
                      if p.nombre.casefold() == instrumento.nombre.casefold()]
            valor, flujo = _serie_plazos(plazos, fechas)
        valores[instrumento.etiqueta] = [v.quantize(CENTAVO) for v in valor]
        flujos[instrumento.etiqueta] = [f.quantize(CENTAVO) for f in flujo]
    return Evolucion(desde, hasta, fechas, valores, flujos, frozenset(estimados))


def oficial(libro: Libro, cuenta_ids: list[str], desde: date, hasta: date) -> Evolucion:
    """El saldo de cada cuenta en TALLY: transferencias = dinero que metiste o sacaste; rendimientos = ganancia."""
    fechas = _dias(desde - timedelta(days=1), hasta)
    indice = {d: i for i, d in enumerate(fechas)}
    valores: dict[str, list[Decimal]] = {}
    flujos: dict[str, list[Decimal]] = {}
    for cuenta_id in cuenta_ids:
        antes, cambios, aportes = 0, defaultdict(int), defaultdict(int)
        for op in libro.operaciones(hasta=hasta):
            importe = sum(p.importe for p in op.partidas if p.cuenta_id == cuenta_id)
            if not importe:
                continue
            if op.fecha <= fechas[0]:
                antes += importe
                continue
            cambios[indice[op.fecha]] += importe
            if op.tipo is not TipoOperacion.RENDIMIENTO:
                aportes[indice[op.fecha]] += importe
        saldo, serie = antes, []
        for i in range(len(fechas)):
            saldo += cambios.get(i, 0)
            serie.append(a_pesos(saldo))
        nombre = libro.cuenta(cuenta_id).nombre
        valores[nombre] = serie
        flujos[nombre] = [a_pesos(aportes.get(i, 0)) for i in range(len(fechas))]
    return Evolucion(desde, hasta, fechas, valores, flujos)


# ---------------------------------------------------------------- resumir


def resultado(evo: Evolucion, nombres: list[str] | None = None) -> Resultado:
    """Totales del periodo de las series ``nombres`` (todas si es None)."""
    nombres = evo.nombres if nombres is None else nombres
    valores = _sumar(evo.valores, nombres, len(evo.fechas))
    flujos = _sumar(evo.flujos, nombres, len(evo.fechas))
    return _resultado(valores, flujos, 1, len(evo.fechas) - 1)


def por_serie(evo: Evolucion) -> list[tuple[str, Resultado]]:
    return [(n, resultado(evo, [n])) for n in evo.nombres]


def ganancia_por_periodo(evo: Evolucion, nombres: list[str] | None = None, *, por_anio: bool = False
                         ) -> list[tuple[date, Decimal]]:
    """Ganancia de cada mes (o año) del rango: ``(primer día del periodo, ganancia)``."""
    nombres = evo.nombres if nombres is None else nombres
    valores = _sumar(evo.valores, nombres, len(evo.fechas))
    flujos = _sumar(evo.flujos, nombres, len(evo.fechas))
    salida, inicio = [], 1
    for i in range(1, len(evo.fechas)):
        ultimo = i == len(evo.fechas) - 1
        dia, siguiente = evo.fechas[i], evo.fechas[i] + timedelta(days=1)
        cambia = siguiente.year != dia.year if por_anio else siguiente.month != dia.month
        if cambia or ultimo:
            r = _resultado(valores, flujos, inicio, i)
            salida.append((evo.fechas[inicio].replace(month=1 if por_anio else evo.fechas[inicio].month, day=1),
                           r.ganancia))
            inicio = i + 1
    return salida


def serie_total(evo: Evolucion, nombres: list[str] | None = None) -> list[tuple[date, Decimal, Decimal]]:
    """``(fecha, valor, lo que metiste)``: el valor inicial más lo que entró menos lo que salió hasta ese día.

    La distancia entre las dos líneas es lo que llevas ganado (o perdido) en el periodo.
    """
    nombres = evo.nombres if nombres is None else nombres
    valores = _sumar(evo.valores, nombres, len(evo.fechas))
    flujos = _sumar(evo.flujos, nombres, len(evo.fechas))
    invertido, salida = valores[0], []
    for i, dia in enumerate(evo.fechas):
        if i:
            invertido += flujos[i]
        salida.append((dia, valores[i], invertido))
    return salida


# ---------------------------------------------------------------- internos


def _dias(desde: date, hasta: date) -> list[date]:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


def _sumar(series: dict[str, list[Decimal]], nombres: list[str], largo: int) -> list[Decimal]:
    total = [CERO] * largo
    for nombre in nombres:
        for i, v in enumerate(series.get(nombre, ())):
            total[i] += v
    return total


def _resultado(valores: list[Decimal], flujos: list[Decimal], inicio: int, fin: int) -> Resultado:
    """De ``inicio`` a ``fin`` (índices inclusivos); el valor inicial es el del día ``inicio − 1``."""
    v0, v1 = valores[inicio - 1], valores[fin]
    tramo = flujos[inicio:fin + 1]
    entradas = sum((f for f in tramo if f > 0), CERO)
    salidas = -sum((f for f in tramo if f < 0), CERO)
    ganancia = v1 - v0 - (entradas - salidas)
    dias = fin - inicio + 1
    base = v0 + sum((f * Decimal(dias - k) / dias for k, f in enumerate(tramo)), CERO)
    rendimiento = (ganancia / base * 100).quantize(Decimal("0.01")) if base > 0 else None
    return Resultado(v0, entradas, salidas, v1, ganancia, rendimiento)


def _tipos_de_cambio(libro: Libro, cuenta_ids: list[str], mercado: Mercado) -> dict[str, list[tuple[date, Decimal]]]:
    """Moneda → [(fecha, pesos por unidad)]: el historial guardado más el tipo de cambio de cada compra o venta."""
    puntos: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for c in cuenta_ids:
        for v in libro.valores(c):
            if v.moneda != "MXN":
                puntos[v.moneda][v.fecha] = v.tipo_cambio
    monedas = set(puntos) | {m for m, _ in mercado.values() if m != "MXN"}
    for moneda in monedas:
        _, cierres = mercado.get(f"{moneda}MXN=X", ("MXN", {}))
        puntos[moneda].update(cierres)
    return {m: sorted(p.items()) for m, p in puntos.items() if p}


def _en(puntos: list[tuple[date, Decimal]], dia: date) -> Decimal | None:
    """El valor más reciente a ``dia``; antes del primero, el primero."""
    if not puntos:
        return None
    i = bisect_right(puntos, (dia, Decimal("Infinity")))
    return puntos[max(i - 1, 0)][1]


def _precios_en_pesos(simbolo, operaciones, mercado: Mercado, tipos) -> tuple[list[tuple[date, Decimal]], bool]:
    """Precio de un título en pesos por fecha. Manda el historial de mercado; los precios de compra o venta
    rellenan los días sin él. ``real`` dice si hubo historial de mercado."""
    puntos = {v.fecha: v.precio * v.tipo_cambio for v in operaciones}
    moneda, cierres = mercado.get(simbolo, ("MXN", {}))
    tipo = tipos.get(moneda) if moneda != "MXN" else [(date.min, Decimal(1))]
    real = False
    if tipo:
        for dia, cierre in cierres.items():
            puntos[dia] = cierre * _en(tipo, dia)
            real = True
    return sorted(puntos.items()), real


def _serie_titulo(operaciones, fechas: list[date], precio: list[tuple[date, Decimal]]):
    por_dia: dict[date, list] = defaultdict(list)
    for v in operaciones:
        por_dia[v.fecha].append(v)
    titulos = sum((v.titulos if v.tipo is TipoOperacionValor.COMPRA else -v.titulos
                   for v in operaciones if v.fecha <= fechas[0]), CERO)
    valores, flujos = [], []
    for i, dia in enumerate(fechas):
        flujo = CERO
        if i:
            for v in por_dia.get(dia, ()):
                bruto, comision = v.titulos * v.precio * v.tipo_cambio, v.comision * v.tipo_cambio
                if v.tipo is TipoOperacionValor.COMPRA:
                    titulos += v.titulos
                    flujo += bruto + comision
                else:
                    titulos -= v.titulos
                    flujo -= bruto - comision
        valores.append(titulos * _en(precio, dia) if titulos else CERO)
        flujos.append(flujo)
    return valores, flujos


def _serie_plazos(plazos, fechas: list[date]):
    valores, flujos = [CERO] * len(fechas), [CERO] * len(fechas)
    for plazo in plazos:
        vence = plazo.fecha_inicio + timedelta(days=plazo.plazo_dias)
        for i, dia in enumerate(fechas):
            if plazo.fecha_inicio <= dia < vence:
                valores[i] += portafolio.valor_plazo(plazo, dia).valor_hoy
            if i and dia == plazo.fecha_inicio:
                flujos[i] += a_pesos(plazo.monto)
            if i and dia == vence:
                flujos[i] -= portafolio.valor_plazo(plazo, vence).valor_al_vencer
    return valores, flujos
