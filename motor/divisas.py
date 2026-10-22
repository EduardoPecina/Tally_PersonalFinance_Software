"""Cuentas en otra moneda (dólares, euros…) y sus tipos de cambio.

TALLY suma todo en tu moneda (la de tu perfil, motor/monedas.py). Una cuenta de débito, ahorro, efectivo, inversión
u «otra» puede estar en otra moneda: sus movimientos guardan dos cifras,

- el importe en la moneda de la cuenta (``Partida.original``), para que su saldo cuadre con tu banco al centavo, y
- lo que eso valía en tu moneda al tipo de cambio de ese día (``Partida.importe``): con eso se calculan el Resumen,
  los presupuestos, la contabilidad y los cierres. Así lo que gastaste el mes pasado no cambia cuando se mueve el
  dólar.

Lo que sí cambia con el dólar es lo que valen hoy tus dólares: el saldo de la cuenta por el tipo de cambio del día
(:func:`valor`). La diferencia contra lo que valían al entrar es la ganancia (o pérdida) **por tipo de cambio**
(:func:`ajuste`): se suma a tu patrimonio, como la depreciación de los bienes, sin ser un movimiento.

Al registrar en una cuenta así escribes el importe en su moneda y nada más: el Libro lo pasa a la tuya al guardar
(:func:`en_tu_moneda`). Solo al mover dinero entre cuentas de distinta moneda puedes decir también cuánto llegó
(:func:`transferencia`), como lo ves en tu banco.

Tipos de cambio: cuánto de tu moneda vale una unidad de la otra, por día. Los escribes tú o TALLY los trae de
internet (:func:`consultar`, solo el par de monedas: ``USDMXN=X``). Para un día sin tipo de cambio se usa el último
anterior; antes del primero, el primero.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING

from motor import monedas
from motor.dinero import a_centavos
from motor.errores import ErrorValidacion
from motor.modelo import TIPOS_EN_OTRA_MONEDA, Cuenta, Operacion, Partida, TipoCambio, TipoOperacion

if TYPE_CHECKING:
    from motor.libro import Libro

DECIMALES = Decimal("0.00000001")   # los tipos de cambio se guardan con hasta 8 decimales (1 COP = 0.00022 EUR)
MAXIMO_HISTORIAL = 3653             # días hacia atrás que se piden a internet, a lo más (10 años)


# ------------------------------------------------------------------ monedas


def moneda_de(libro: Libro, cuenta: Cuenta | str) -> str:
    """La moneda de la cuenta (la tuya si no tiene otra)."""
    cuenta = libro.cuenta(cuenta) if isinstance(cuenta, str) else cuenta
    return cuenta.moneda or monedas.de(libro)


def en_otra_moneda(libro: Libro, cuenta: Cuenta | str) -> bool:
    cuenta = libro.cuenta(cuenta) if isinstance(cuenta, str) else cuenta
    return bool(cuenta.moneda) and cuenta.moneda != monedas.de(libro)


def cuentas_en_otra_moneda(libro: Libro) -> list[Cuenta]:
    """Las cuentas en otra moneda (también las eliminadas: su saldo sigue contando)."""
    return [c for c in libro.cuentas() if en_otra_moneda(libro, c)]


def monedas_en_uso(libro: Libro) -> list[str]:
    """Las otras monedas de tus cuentas."""
    return sorted({c.moneda for c in cuentas_en_otra_moneda(libro)})


def moneda_para_cuenta(libro: Libro, tipo, moneda: str | None) -> str:
    """Lo que se guarda en ``Cuenta.moneda``: "" si es la tuya. Solo algunos tipos de cuenta pueden tener otra."""
    if not moneda:
        return ""
    codigo = monedas.moneda(moneda).codigo
    if codigo == monedas.de(libro):
        return ""
    if libro.perfil is None:
        raise ErrorValidacion("Primero elige tu moneda (en la bienvenida); después agrega las cuentas en otra.")
    if tipo not in TIPOS_EN_OTRA_MONEDA:
        raise ErrorValidacion("Las tarjetas de crédito, los préstamos, los bienes y lo que te deben van en tu moneda. "
                              "En otra moneda puede ir una cuenta de débito, ahorro, efectivo, inversión u «otra».")
    return codigo


# ---------------------------------------------------------- tipos de cambio


def tipo(libro: Libro, moneda: str, dia: date | None = None) -> Decimal | None:
    """Cuánto de tu moneda vale 1 ``moneda`` en ``dia`` (hoy, si no se dice): el último tipo de cambio guardado hasta
    ese día (antes del primero, el primero). ``None`` si no hay ninguno."""
    if moneda == monedas.de(libro):
        return Decimal(1)
    fechas, tipos = libro.serie_cambio(moneda)
    if not fechas:
        return None
    i = bisect_right(fechas, dia or libro.hoy())
    return tipos[i - 1] if i else tipos[0]


def tipo_o_error(libro: Libro, moneda: str, dia: date) -> Decimal:
    valor = tipo(libro, moneda, dia)
    if valor is None:
        base = monedas.de(libro)
        raise ErrorValidacion(f"Falta el tipo de cambio: cuántos {base} vale 1 {moneda}. Escríbelo en Configuración → "
                              "Tipos de cambio (o deja que TALLY lo traiga de internet).")
    return valor


def leer_tipo(valor) -> Decimal:
    """Un tipo de cambio escrito por el usuario (mayor que cero), con hasta 8 decimales."""
    try:
        numero = Decimal(repr(valor) if isinstance(valor, float) else str(valor).strip())
    except (InvalidOperation, ValueError):
        raise ErrorValidacion(f"El tipo de cambio «{valor}» no es un número.") from None
    if not numero.is_finite() or numero <= 0:
        raise ErrorValidacion("El tipo de cambio debe ser mayor que cero.")
    numero = numero.quantize(DECIMALES, rounding=ROUND_HALF_UP)
    if numero <= 0:
        raise ErrorValidacion("El tipo de cambio es demasiado chico.")
    return numero.normalize()


def guardar_tipo(libro: Libro, moneda: str, fecha: date, valor, *, manual: bool = True) -> TipoCambio:
    """El tipo de cambio de ``moneda`` en ``fecha`` (lo que escribiste tú manda sobre lo que traiga internet)."""
    codigo = monedas.moneda(moneda).codigo
    if codigo == monedas.de(libro):
        raise ErrorValidacion("Esa ya es tu moneda: su tipo de cambio siempre es 1.")
    if fecha > libro.hoy():
        raise ErrorValidacion("El tipo de cambio no puede ser de una fecha futura.")
    return libro.guardar_tipo_cambio(TipoCambio(codigo, fecha, leer_tipo(valor), manual))


def quitar_tipo(libro: Libro, moneda: str, fecha: date) -> None:
    libro.quitar_tipo_cambio(TipoCambio(moneda, fecha, Decimal(1)).id)


def de_internet(libro: Libro, series: dict[str, dict[date, Decimal]]) -> int:
    """Guarda los tipos de cambio traídos de internet (moneda → {día: tipo}) sin pisar los que escribiste tú.
    Devuelve cuántos agregó o cambió."""
    base, hoy, cambiados = monedas.de(libro), libro.hoy(), 0
    for moneda, cierres in series.items():
        if moneda == base or moneda not in monedas.MONEDAS:
            continue
        for dia, valor in cierres.items():
            try:
                numero = leer_tipo(valor)
            except ErrorValidacion:
                continue
            previo = libro.tipo_cambio(TipoCambio(moneda, dia, numero).id)
            if dia > hoy or (previo is not None and (previo.manual or previo.tipo == numero)):
                continue
            libro.guardar_tipo_cambio(TipoCambio(moneda, dia, numero))
            cambiados += 1
    return cambiados


# -------------------------------------------------------------- conversión


def a_base(centavos: int, tipo_cambio: Decimal) -> int:
    """Centavos de otra moneda → centavos de la tuya."""
    return int((Decimal(centavos) * tipo_cambio).to_integral_value(ROUND_HALF_UP))


def desde_base(centavos: int, tipo_cambio: Decimal) -> int:
    """Centavos de tu moneda → centavos de otra."""
    return int((Decimal(centavos) / tipo_cambio).to_integral_value(ROUND_HALF_UP))


def repartir(total: int, partes: list[int]) -> list[int]:
    """Reparte ``total`` en proporción a ``partes`` (del mismo signo entre sí), sin perder ni sobrar un centavo."""
    if len(partes) <= 1:
        return [total] * len(partes)
    suma = sum(abs(p) for p in partes)
    signo, resto = (1 if total >= 0 else -1), abs(total)
    exactos = [Decimal(resto) * abs(p) / suma for p in partes]
    enteros = [int(e.to_integral_value(ROUND_DOWN)) for e in exactos]
    faltan = resto - sum(enteros)
    for i in sorted(range(len(partes)), key=lambda i: enteros[i] - exactos[i])[:faltan]:
        enteros[i] += 1
    return [signo * e for e in enteros]


def en_tu_moneda(libro: Libro, op: Operacion) -> Operacion:
    """Pasa a tu moneda un movimiento que toca cuentas en otra moneda. Lo llama el Libro al guardar.

    Los importes de esas cuentas llegan en su moneda (sin ``original``):

    - En un movimiento de una cuenta (gasto, ingreso, rendimiento…), el importe es el de la cuenta; sus categorías se
      convierten en la misma proporción.
    - En una transferencia, el importe es lo que salió, en la moneda de la cuenta de origen; lo que llega se calcula
      con el tipo de cambio. Si sabes lo que llegó, usa :func:`transferencia`.

    Lo que ya trae su ``original`` (ya convertido) se queda como está.
    """
    cuentas = op.partidas_de_cuenta()
    otras = [p for p in cuentas if en_otra_moneda(libro, p.cuenta_id)]
    pendientes = [p for p in otras if p.original is None]
    if not pendientes:
        return op
    if len(pendientes) != len(otras):
        raise ErrorValidacion("El movimiento mezcla importes ya convertidos y sin convertir.")
    if len(cuentas) == 1:
        (cuenta,) = cuentas
        importe = _sin_cero(a_base(cuenta.importe, tipo_o_error(libro, moneda_de(libro, cuenta.cuenta_id), op.fecha)))
        de_categoria = op.partidas_de_categoria()
        nuevas = dict(zip(map(id, de_categoria), repartir(-importe, [p.importe for p in de_categoria])))
        partidas = tuple(replace(p, importe=importe, original=p.importe) if p is cuenta
                         else replace(p, importe=_sin_cero(nuevas[id(p)])) for p in op.partidas)
        return replace(op, partidas=partidas)
    if len(cuentas) != 2 or op.partidas_de_categoria():
        raise ErrorValidacion("Este movimiento no se puede registrar con cuentas en otra moneda.")
    origen, destino = sorted(cuentas, key=lambda p: p.importe)
    base = monedas.de(libro)
    de, a = moneda_de(libro, origen.cuenta_id), moneda_de(libro, destino.cuenta_id)
    sale = -origen.importe
    valor = sale if de == base else a_base(sale, tipo_o_error(libro, de, op.fecha))
    llega = sale if a == de else valor if a == base else desde_base(valor, tipo_o_error(libro, a, op.fecha))
    return replace(op, partidas=_de_transferencia(origen.cuenta_id, destino.cuenta_id, _sin_cero(valor),
                                                 sale if de != base else None, _sin_cero(llega) if a != base else None))


def sin_convertir(op: Operacion) -> Operacion:
    """El movimiento con los importes de sus cuentas en otra moneda otra vez solo en su moneda (como se capturaron),
    para que el Libro los vuelva a convertir, p. ej. con el tipo de cambio de otra fecha. En una transferencia queda
    lo que salió; lo que llega se vuelve a calcular."""
    cuentas = op.partidas_de_cuenta()
    if all(p.original is None for p in cuentas):
        return op
    if len(cuentas) == 1:
        (cuenta,) = cuentas
        de_categoria = op.partidas_de_categoria()
        nuevas = dict(zip(map(id, de_categoria), repartir(-cuenta.original, [p.importe for p in de_categoria])))
        return replace(op, partidas=tuple(Partida(cuenta.original, cuenta_id=cuenta.cuenta_id) if p is cuenta
                                          else replace(p, importe=nuevas[id(p)]) for p in op.partidas))
    origen, destino = sorted(cuentas, key=lambda p: p.importe)
    sale = -origen.en_su_moneda
    return replace(op, partidas=(Partida(-sale, cuenta_id=origen.cuenta_id), Partida(sale, cuenta_id=destino.cuenta_id)))


def transferencia(libro: Libro, fecha: date, origen_id: str, destino_id: str, sale, llega, descripcion: str = "",
                  notas: str = "", *, tipo_operacion: TipoOperacion = TipoOperacion.TRANSFERENCIA) -> Operacion:
    """Transferencia entre cuentas de distinta moneda cuando sabes lo que salió (en la moneda de origen) y lo que
    llegó (en la de destino), como lo ves en tu banco: el tipo de cambio real, con su comisión, queda implícito.
    Sin guardarla."""
    de, a, base = moneda_de(libro, origen_id), moneda_de(libro, destino_id), monedas.de(libro)
    sale, llega = a_centavos(sale), a_centavos(llega)
    if sale <= 0 or llega <= 0:
        raise ErrorValidacion("Lo que sale y lo que llega deben ser mayores que cero.")
    if de == a:
        if sale != llega:
            raise ErrorValidacion("Las dos cuentas están en la misma moneda: lo que sale es lo que llega.")
        valor = sale if de == base else a_base(sale, tipo_o_error(libro, de, fecha))
    else:
        valor = sale if de == base else llega if a == base else a_base(sale, tipo_o_error(libro, de, fecha))
    partidas = _de_transferencia(origen_id, destino_id, _sin_cero(valor), sale if de != base else None,
                                 llega if a != base else None)
    return Operacion(fecha=fecha, tipo=tipo_operacion, partidas=partidas, descripcion=descripcion, notas=notas)


def _de_transferencia(origen_id: str, destino_id: str, valor: int, sale: int | None, llega: int | None
                      ) -> tuple[Partida, Partida]:
    return (Partida(-valor, cuenta_id=origen_id, original=None if sale is None else -sale),
            Partida(valor, cuenta_id=destino_id, original=llega))


def _sin_cero(centavos: int) -> int:
    if centavos == 0:
        raise ErrorValidacion("El importe es tan chico que al cambiarlo de moneda da cero.")
    return centavos


# --------------------------------------------------------------- valuación


def valor(libro: Libro, cuenta_id: str, al: date | None = None) -> int:
    """Lo que vale la cuenta en tu moneda al final de ``al`` (hoy, si no se dice): su saldo por el tipo de cambio de
    ese día. En una cuenta en tu moneda, su saldo."""
    cuenta = libro.cuenta(cuenta_id)
    if not en_otra_moneda(libro, cuenta):
        return libro.saldo_centavos(cuenta_id, al)
    tipo_cambio = tipo(libro, cuenta.moneda, al)
    if tipo_cambio is None:
        return libro.saldo_en_base(cuenta_id, al)
    return a_base(libro.saldo_centavos(cuenta_id, al), tipo_cambio)


def valores(libro: Libro, al: date | None = None) -> dict[str, int]:
    """:func:`valor` de todas las cuentas."""
    return {c.id: valor(libro, c.id, al) for c in libro.cuentas()}


def ajuste(libro: Libro, al: date | None = None) -> int:
    """Ganancia (+) o pérdida (−) por tipo de cambio a ``al``: lo que valen tus cuentas en otra moneda menos lo que
    valían sus movimientos el día que entraron. Ya está incluida en :func:`valor`; aparte, para mostrarla."""
    return sum(valor(libro, c.id, al) - libro.saldo_en_base(c.id, al) for c in cuentas_en_otra_moneda(libro))


@dataclass(frozen=True, slots=True)
class Cuadro:
    """Una cuenta en otra moneda, para mostrarla: su saldo, lo que vale en tu moneda y con qué tipo de cambio."""

    cuenta: Cuenta
    saldo: int              # centavos de la moneda de la cuenta
    valor: int              # centavos de tu moneda
    tipo: Decimal | None    # el tipo de cambio usado (None: no hay, se usó lo que valían al entrar)
    por_tipo_de_cambio: int  # ganancia (+) o pérdida (−) por tipo de cambio de esta cuenta


def cuadro(libro: Libro, cuenta_id: str, al: date | None = None) -> Cuadro:
    cuenta = libro.cuenta(cuenta_id)
    tipo_cambio = tipo(libro, moneda_de(libro, cuenta), al)
    valor_ = valor(libro, cuenta_id, al)
    return Cuadro(cuenta, libro.saldo_centavos(cuenta_id, al), valor_, tipo_cambio,
                  valor_ - libro.saldo_en_base(cuenta_id, al))


# ------------------------------------------------------------- de internet


@dataclass(frozen=True, slots=True)
class Consulta:
    series: dict[str, dict[date, Decimal]]     # moneda → {día: tipo}
    aviso: str = ""
    sin_conexion: bool = False


def pendientes(libro: Libro, hoy: date | None = None) -> dict[str, date]:
    """Qué pedir a internet: moneda → desde qué día. Desde el primer movimiento de esa moneda (o desde el último tipo
    guardado, si ya está todo lo de antes); nada si ya hay uno de hoy."""
    hoy = hoy or libro.hoy()
    pedidos = {}
    for moneda in monedas_en_uso(libro):
        primera = min((op.fecha for c in cuentas_en_otra_moneda(libro) if c.moneda == moneda
                       for op in libro.operaciones(cuenta_id=c.id)[:1]), default=hoy)
        primera = max(primera, hoy - timedelta(days=MAXIMO_HISTORIAL))
        fechas, _ = libro.serie_cambio(moneda)
        completo = bool(fechas) and fechas[0] <= primera + timedelta(days=7)   # fines de semana y días festivos
        if completo and fechas[-1] >= hoy:
            continue
        pedidos[moneda] = fechas[-1] if completo else primera
    return pedidos


def consultar(pedidos: dict[str, date], base: str, hoy: date, enviar: Callable | None = None) -> Consulta:
    """Trae de internet los cierres diarios de cada tipo de cambio desde su fecha. Solo viaja el par de monedas
    (``USDMXN=X``) y el periodo (motor/cotizaciones.py). Si un par no existe, lo calcula con el dólar
    (cuántos de tu moneda vale 1 USD ÷ cuántos de la otra vale 1 USD)."""
    from motor import cotizaciones

    if not pedidos:
        return Consulta({})
    directos = {cotizaciones.simbolo_tipo_de_cambio(m, base): d for m, d in pedidos.items()}
    consulta = cotizaciones.consultar_historial(directos, hoy, enviar, base=base)
    if consulta.sin_conexion:
        return Consulta({}, consulta.aviso, sin_conexion=True)
    series = {m: dict(consulta.series[s].cierres) for m, s in zip(pedidos, directos)
              if s in consulta.series and consulta.series[s].ok}
    faltan = {m: d for m, d in pedidos.items() if m not in series}
    if faltan:
        cruces = {f"USD{m}=X": d for m, d in faltan.items() if m != "USD"}
        if cruces and base != "USD":
            cruces[f"USD{base}=X"] = min(faltan.values())
        respaldo = cotizaciones.consultar_historial(cruces, hoy, enviar, base=base) if cruces else None
        dolar = respaldo.series.get(f"USD{base}=X") if respaldo else None
        for m in faltan:
            otra = respaldo.series.get(f"USD{m}=X") if respaldo else None
            if base == "USD" and otra and otra.ok:
                series[m] = {d: 1 / v for d, v in otra.cierres.items()}
            elif dolar and dolar.ok and otra and otra.ok:
                series[m] = {d: dolar.cierres[d] / v for d, v in otra.cierres.items() if d in dolar.cierres}
    sin = sorted(m for m in pedidos if not series.get(m))
    aviso = f"No se encontró en internet el tipo de cambio de {', '.join(sin)}: escríbelo a mano." if sin else ""
    return Consulta({m: s for m, s in series.items() if s}, aviso)
