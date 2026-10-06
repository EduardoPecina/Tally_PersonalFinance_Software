"""Títulos (acciones, ETF, cripto) e inversiones a plazo (CETES, pagarés) de una cuenta de inversión.

Es un **detalle** de la cuenta, no un movimiento:

- El dinero entra y sale de la cuenta con transferencias, como siempre.
- Comprar o vender títulos con el dinero que ya está en la cuenta no cambia su saldo.
- La ganancia (o pérdida) solo entra a la contabilidad cuando el usuario lo pide con
  :func:`registrar_rendimiento`. Se registra como rendimiento, y la cuenta recuerda cuánto ya se registró
  (``Cuenta.plusvalia_registrada``), así que la siguiente vez solo se agrega lo nuevo: nada se cuenta dos veces.

El costo de cada título es el **costo promedio** (lo que pagaste, comisiones incluidas, entre los títulos que
tienes), en pesos al tipo de cambio del día de cada compra. Las inversiones a plazo se valúan sin internet, con
interés simple sobre año de 360 días (como se pagan los CETES), antes de impuestos.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from motor import categorias
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import (
    ClaseCategoria,
    Cuenta,
    InversionPlazo,
    Operacion,
    OperacionValor,
    TipoCuenta,
    TipoOperacion,
    TipoOperacionValor,
)
from motor.movimientos import construir_con_signo
from motor.textos import normalizar_nombre

CERO = Decimal(0)
BASE_DIAS = 360
CENTAVO = Decimal("0.01")
SUBCATEGORIA_RENDIMIENTO = "INTERESES Y RENDIMIENTOS"
_SIMBOLO = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$")
_MONEDA = re.compile(r"^[A-Z]{3}$")


# ----------------------------------------------------------------- registrar


def normalizar_simbolo(texto: str) -> str:
    """El símbolo como lo cotiza Yahoo Finance, en mayúsculas: IVVPESO.MX, AAPL, VOO, BTC-USD…"""
    simbolo = (texto or "").strip().upper().replace(" ", "")
    if not _SIMBOLO.match(simbolo):
        raise ErrorValidacion("Escribe el símbolo como lo muestra Yahoo Finance: por ejemplo IVVPESO.MX (BMV), "
                              "AAPL o VOO (EE. UU.), BTC-USD (cripto).")
    return simbolo


def registrar_compra(libro: Libro, cuenta_id: str, fecha: date, simbolo: str, titulos, precio, *, moneda: str = "MXN",
                     tipo_cambio=None, comision=0, notas: str = "") -> OperacionValor:
    """Compraste ``titulos`` de ``simbolo`` a ``precio`` cada uno (en ``moneda``)."""
    return _registrar(libro, cuenta_id, fecha, TipoOperacionValor.COMPRA, simbolo, titulos, precio, moneda,
                      tipo_cambio, comision, notas)


def registrar_venta(libro: Libro, cuenta_id: str, fecha: date, simbolo: str, titulos, precio, *, moneda: str = "MXN",
                    tipo_cambio=None, comision=0, notas: str = "") -> OperacionValor:
    """Vendiste ``titulos`` de ``simbolo`` a ``precio`` cada uno. No puedes vender más de los que tenías."""
    return _registrar(libro, cuenta_id, fecha, TipoOperacionValor.VENTA, simbolo, titulos, precio, moneda,
                      tipo_cambio, comision, notas)


def eliminar_valor(libro: Libro, valor_id: str) -> None:
    """Borra una compra o venta (si al quitarla no queda una venta de títulos que no tenías)."""
    valor = libro.valor(valor_id)
    _validar_historial([v for v in libro.valores(valor.cuenta_id) if v.id != valor_id])
    libro.quitar_valor(valor_id)


def registrar_plazo(libro: Libro, cuenta_id: str, nombre: str, fecha_inicio: date, monto, tasa_anual, plazo_dias: int,
                    notas: str = "") -> InversionPlazo:
    """CETES, pagaré o certificado de depósito: ``monto`` a ``tasa_anual`` % durante ``plazo_dias`` días."""
    cuenta = _cuenta_de_inversion(libro, cuenta_id)
    centavos = a_centavos(monto)
    if centavos <= 0:
        raise ErrorValidacion("El monto invertido debe ser mayor que cero.")
    tasa = _decimal(tasa_anual, "La tasa anual")
    if tasa > 100:
        raise ErrorValidacion("La tasa es anual, en %: por ejemplo 10.5 para 10.5 %.")
    if isinstance(plazo_dias, bool) or not 1 <= int(plazo_dias) <= 3650:
        raise ErrorValidacion("El plazo va de 1 a 3,650 días.")
    nombre = normalizar_nombre(nombre)
    plazo = InversionPlazo(libro.nuevo_id(), cuenta.id, nombre, fecha_inicio, centavos, tasa, int(plazo_dias),
                           notas.strip())
    return libro.guardar_plazo(plazo)


def eliminar_plazo(libro: Libro, plazo_id: str) -> None:
    libro.quitar_plazo(plazo_id)


# ----------------------------------------------------------------- consultar


@dataclass(frozen=True, slots=True)
class Posicion:
    """Lo que tienes (o tuviste) de un símbolo. Importes en pesos."""

    simbolo: str
    titulos: Decimal          # los que tienes hoy (0 si ya vendiste todo)
    costo: Decimal            # lo que te costaron los que tienes (costo promedio × títulos)
    realizada: Decimal        # ganancia o pérdida de lo que ya vendiste
    moneda: str               # en la que lo compraste

    @property
    def costo_promedio(self) -> Decimal:
        return (self.costo / self.titulos).quantize(Decimal("0.0001")) if self.titulos else CERO


def posiciones(libro: Libro, cuenta_id: str, al: date | None = None) -> list[Posicion]:
    """Una por símbolo, con costo promedio. ``al`` toma en cuenta solo hasta esa fecha."""
    return list(_acumular(v for v in libro.valores(cuenta_id) if al is None or v.fecha <= al).values())


@dataclass(frozen=True, slots=True)
class ValorPlazo:
    plazo: InversionPlazo
    vence: date
    valor_hoy: Decimal        # monto + interés ganado a la fecha
    interes_hoy: Decimal
    valor_al_vencer: Decimal
    vencido: bool


def valor_plazo(plazo: InversionPlazo, hoy: date) -> ValorPlazo:
    """Valor estimado: interés simple, año de 360 días, antes de impuestos. Después de vencer ya no crece."""
    monto = a_pesos(plazo.monto)
    dias = min(max((hoy - plazo.fecha_inicio).days, 0), plazo.plazo_dias)

    def interes(d: int) -> Decimal:
        return (monto * plazo.tasa_anual / 100 * d / BASE_DIAS).quantize(CENTAVO)

    return ValorPlazo(plazo, plazo.fecha_inicio + timedelta(days=plazo.plazo_dias), monto + interes(dias),
                      interes(dias), monto + interes(plazo.plazo_dias), dias >= plazo.plazo_dias)


@dataclass(frozen=True, slots=True)
class FilaValuacion:
    posicion: Posicion
    precio: Decimal | None    # precio actual de un título, en ``moneda_precio``
    moneda_precio: str
    valor: Decimal | None     # en pesos
    ganancia: Decimal | None  # no realizada, en pesos

    @property
    def porcentaje(self) -> Decimal | None:
        if self.ganancia is None or not self.posicion.costo:
            return None
        return self.ganancia / self.posicion.costo * 100


@dataclass(frozen=True, slots=True)
class Valuacion:
    filas: list[FilaValuacion]            # solo lo que tienes hoy
    plazos: list[ValorPlazo]
    costo: Decimal                        # de los títulos que tienes
    valor_titulos: Decimal | None         # None si falta el precio de alguno
    ganancia_no_realizada: Decimal | None
    ganancia_realizada: Decimal           # de lo que ya vendiste
    interes_plazos: Decimal
    faltan: list[str]                     # símbolos sin precio (o sin tipo de cambio)
    registrada: Decimal                   # ganancia que ya está en el saldo de la cuenta

    @property
    def valor_plazos(self) -> Decimal:
        return sum((p.valor_hoy for p in self.plazos), CERO)

    @property
    def valor_total(self) -> Decimal | None:
        return None if self.valor_titulos is None else self.valor_titulos + self.valor_plazos

    @property
    def ganancia_total(self) -> Decimal | None:
        if self.ganancia_no_realizada is None:
            return None
        return self.ganancia_no_realizada + self.ganancia_realizada + self.interes_plazos

    @property
    def por_registrar(self) -> Decimal | None:
        """Lo que falta pasar al saldo de la cuenta (negativo si bajó desde la última vez)."""
        return None if self.ganancia_total is None else self.ganancia_total - self.registrada


def valuar(libro: Libro, cuenta_id: str, precios: dict[str, tuple[Decimal, str]], tipos_cambio: dict[str, Decimal],
           hoy: date | None = None) -> Valuacion:
    """Valor aproximado con los ``precios`` dados (símbolo → (precio, moneda)) y ``tipos_cambio`` (moneda → pesos).

    Es pura aritmética: no sale a internet. Los precios vienen de :mod:`motor.cotizaciones` o los escribe el
    usuario.
    """
    hoy = hoy or libro.hoy()
    tipos = {"MXN": Decimal(1), **tipos_cambio}
    todas = posiciones(libro, cuenta_id)
    filas, faltan = [], []
    for posicion in (p for p in todas if p.titulos):
        precio, moneda = precios.get(posicion.simbolo, (None, posicion.moneda))
        tipo = tipos.get(moneda)
        if precio is None or tipo is None:
            faltan.append(posicion.simbolo)
            filas.append(FilaValuacion(posicion, precio, moneda, None, None))
            continue
        valor = (posicion.titulos * Decimal(precio) * tipo).quantize(CENTAVO)
        filas.append(FilaValuacion(posicion, Decimal(precio), moneda, valor, valor - posicion.costo))
    plazos = [valor_plazo(p, hoy) for p in libro.plazos(cuenta_id)]
    costo = sum((f.posicion.costo for f in filas), CERO)
    valor_titulos = None if faltan else sum((f.valor for f in filas), CERO)
    return Valuacion(
        filas=filas, plazos=plazos, costo=costo, valor_titulos=valor_titulos,
        ganancia_no_realizada=None if valor_titulos is None else valor_titulos - costo,
        ganancia_realizada=sum((p.realizada for p in todas), CERO),
        interes_plazos=sum((p.interes_hoy for p in plazos), CERO),
        faltan=faltan, registrada=a_pesos(libro.cuenta(cuenta_id).plusvalia_registrada),
    )


def registrar_rendimiento(libro: Libro, cuenta_id: str, valuacion: Valuacion, fecha: date | None = None
                          ) -> Operacion | None:
    """Pasa al saldo de la cuenta la ganancia (o pérdida) que aún no estaba registrada, como rendimiento.

    Devuelve ``None`` si no hay nada nuevo que registrar.
    """
    cuenta = _cuenta_de_inversion(libro, cuenta_id)
    if valuacion.por_registrar is None:
        raise ErrorValidacion("Falta el precio de: " + ", ".join(valuacion.faltan) + ". Consulta el valor o "
                              "escríbelo a mano.")
    centavos = a_centavos(valuacion.por_registrar)
    if centavos == 0:
        return None
    subcategoria = categorias.buscar(libro, SUBCATEGORIA_RENDIMIENTO, ClaseCategoria.INGRESO)
    if subcategoria is None:
        raise ErrorValidacion(f"No encuentro la subcategoría de ingreso «{SUBCATEGORIA_RENDIMIENTO}». Créala de "
                              "nuevo en Categorías → Ingresos.")
    op = construir_con_signo(TipoOperacion.RENDIMIENTO, fecha or libro.hoy(), cuenta.id, subcategoria.id,
                             a_pesos(centavos), "Valuación de tus títulos")
    op = libro.agregar_operacion(op)
    libro.guardar_cuenta(replace(cuenta, plusvalia_registrada=a_centavos(valuacion.ganancia_total)))
    return op


# ----------------------------------------------------------------- internos


def _registrar(libro, cuenta_id, fecha, tipo, simbolo, titulos, precio, moneda, tipo_cambio, comision, notas):
    cuenta = _cuenta_de_inversion(libro, cuenta_id)
    moneda = (moneda or "MXN").strip().upper()
    if not _MONEDA.match(moneda):
        raise ErrorValidacion("La moneda va en tres letras: MXN, USD, EUR…")
    if moneda == "MXN":
        tipo_cambio = Decimal(1)
    elif tipo_cambio in (None, ""):
        raise ErrorValidacion(f"Escribe el tipo de cambio de ese día (pesos por 1 {moneda}).")
    valor = OperacionValor(
        id=libro.nuevo_id(), cuenta_id=cuenta.id, fecha=fecha, tipo=TipoOperacionValor(tipo),
        simbolo=normalizar_simbolo(simbolo), titulos=_decimal(titulos, "Los títulos"),
        precio=_decimal(precio, "El precio"), moneda=moneda, tipo_cambio=_decimal(tipo_cambio, "El tipo de cambio"),
        comision=_decimal(comision or 0, "La comisión", cero=True), notas=notas.strip(),
    )
    _validar_historial([*libro.valores(cuenta.id), valor])
    return libro.guardar_valor(valor)


def _cuenta_de_inversion(libro: Libro, cuenta_id: str) -> Cuenta:
    cuenta = libro.cuenta(cuenta_id)
    if cuenta.tipo is not TipoCuenta.INVERSION:
        raise ErrorValidacion("Los títulos y las inversiones a plazo van en una cuenta de tipo Inversión.")
    if not cuenta.activa:
        raise ErrorValidacion(f"La cuenta «{cuenta.nombre}» está eliminada; restáurala para cambiarla.")
    return cuenta


def _decimal(valor, que: str, *, cero: bool = False) -> Decimal:
    try:
        numero = Decimal(str(valor).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        raise ErrorValidacion(f"{que}: «{valor}» no es un número.") from None
    if not numero.is_finite() or numero < 0 or (numero == 0 and not cero):
        raise ErrorValidacion(f"{que} debe ser mayor que cero.")
    return numero


def _validar_historial(valores: Iterable[OperacionValor]) -> None:
    """Nunca se venden títulos que no se tenían (en orden de fecha; el mismo día, primero las compras)."""
    _acumular(sorted(valores, key=lambda v: (v.fecha, v.tipo is TipoOperacionValor.VENTA)))


def _acumular(valores: Iterable[OperacionValor]) -> dict[str, Posicion]:
    estado: dict[str, list] = {}           # símbolo → [títulos, costo, realizada, moneda]
    for v in valores:
        titulos, costo, realizada, _ = estado.setdefault(v.simbolo, [CERO, CERO, CERO, v.moneda])
        bruto = v.titulos * v.precio * v.tipo_cambio
        comision = v.comision * v.tipo_cambio
        if v.tipo is TipoOperacionValor.COMPRA:
            titulos, costo = titulos + v.titulos, costo + bruto + comision
        else:
            if v.titulos > titulos:
                raise ErrorValidacion(f"El {v.fecha:%d/%m/%Y} vendes {_texto(v.titulos)} de {v.simbolo}, pero en "
                                      f"esa fecha solo tenías {_texto(titulos)}.")
            costo_vendido = costo * v.titulos / titulos
            realizada += bruto - comision - costo_vendido
            titulos, costo = titulos - v.titulos, costo - costo_vendido
        estado[v.simbolo] = [titulos, costo, realizada, v.moneda]
    return {s: Posicion(s, t, c.quantize(CENTAVO), r.quantize(CENTAVO), m) for s, (t, c, r, m) in estado.items()}


def _texto(numero: Decimal) -> str:
    return f"{numero.normalize():f}"
