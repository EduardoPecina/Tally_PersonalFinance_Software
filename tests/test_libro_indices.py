"""Los índices del libro (movimientos por cuenta, saldos, fechas tocadas) dan lo mismo que recorrer todo.

Cientos de acciones al azar (siempre las mismas: semilla fija) con datos ficticios; después de cada una se compara
contra la forma lenta y obvia de calcular lo mismo.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from motor import bienes, categorias, cierre, cuentas, movimientos
from motor.errores import ErrorTally
from motor.libro import Libro
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia

INICIO = date(2025, 1, 1)


class Reloj:
    """Cada acción en un instante distinto (como en la vida real)."""

    def __init__(self) -> None:
        self.momento = datetime(2026, 3, 1, 9, 0)

    def __call__(self) -> datetime:
        self.momento += timedelta(seconds=1)
        return self.momento


def _huella_lenta(libro: Libro) -> dict:
    return {op.id: (op.fecha, op.modificado_en) for op in libro.operaciones()}


def _meses_tocados_lento(libro: Libro, antes: dict) -> list[str]:
    despues = _huella_lenta(libro)
    fechas = [antes[i][0] for i in antes.keys() - despues.keys()]
    fechas += [despues[i][0] for i in despues.keys() - antes.keys()]
    for i in antes.keys() & despues.keys():
        if antes[i] != despues[i]:
            fechas += [antes[i][0], despues[i][0]]
    return sorted({cierre.clave(f.year, f.month) for f in fechas if cierre.cerrado(libro, f)})


def _valuar_lento(libro: Libro, cuenta_id: str, dia: date) -> bienes.Valuacion:
    """Como antes: revisando todos los movimientos, no solo los de la cuenta."""
    original = libro.operaciones
    libro.operaciones = lambda desde=None, hasta=None, cuenta_id=None: original(desde, hasta)
    try:
        return bienes.valuar(libro, cuenta_id, dia)
    finally:
        del libro.operaciones


@pytest.mark.parametrize("semilla", [1, 2])
def test_los_indices_dan_lo_mismo_que_recorrer_todo(semilla):
    rnd = random.Random(semilla)
    lib = Libro(reloj=Reloj())
    categorias.cargar_catalogo_inicial(lib)
    deb = cuentas.crear(lib, "Débito Ficticio", "debito", saldo_inicial=50_000, fecha_creacion=INICIO).id
    aho = cuentas.crear(lib, "Ahorro Ficticio", "ahorro", saldo_inicial=10_000, fecha_creacion=INICIO).id
    tdc = cuentas.crear(lib, "TDC Ficticia", "credito", limite_credito=80_000, dia_corte=3, dia_pago=23,
                        fecha_creacion=INICIO).id
    auto = bienes.crear(lib, "Auto Ficticio", "auto", date(2025, 2, 1), 200_000).cuenta_id
    gastos = [c.id for c in lib.categorias() if c.clase.value == "gasto"][:20]
    ingresos = [c.id for c in lib.categorias() if c.clase.value == "ingreso"][:3]

    def fecha() -> date:
        return INICIO + timedelta(days=rnd.randint(0, 540))

    for paso in range(250):
        ops = [op for op in lib.operaciones() if op.tipo.value != "saldo_inicial"]
        antes, marca = _huella_lenta(lib), cierre.huella(lib)
        x = rnd.random()
        try:
            if x < 0.35:
                movimientos.registrar_gasto(lib, fecha(), rnd.choice([deb, tdc]), rnd.choice(gastos),
                                            Decimal(rnd.randint(1, 300_000)) / 100, f"Gasto {paso}")
            elif x < 0.45:
                movimientos.registrar_ingreso(lib, fecha(), deb, rnd.choice(ingresos), rnd.randint(100, 20_000))
            elif x < 0.52:
                registrar_transferencia(lib, fecha(), deb, aho, rnd.randint(1, 3_000))
            elif x < 0.58:
                registrar_pago_tarjeta(lib, fecha(), deb, tdc, rnd.randint(1, 5_000))
            elif x < 0.72 and ops:
                cambio = rnd.choice([{"fecha": fecha()}, {"monto": rnd.randint(1, 900)}, {"descripcion": "Editado"}])
                movimientos.editar(lib, rnd.choice(ops).id, **cambio)
            elif x < 0.82 and ops:
                movimientos.eliminar(lib, rnd.choice(ops).id)
            elif x < 0.86:
                bienes.registrar_avaluo(lib, auto, fecha(), rnd.randint(100_000, 300_000))
            elif x < 0.89:
                bienes.registrar_mejora(lib, auto, fecha(), rnd.randint(100, 9_000), deb)
            else:
                anio, mes = 2025, rnd.randint(1, 12)
                if lib.cierre(cierre.clave(anio, mes)) is None:
                    cierre.cerrar(lib, anio, mes)
                else:
                    cierre.reabrir(lib, anio, mes)
        except ErrorTally:
            continue
        assert cierre.meses_tocados(lib, marca) == _meses_tocados_lento(lib, antes), paso

        if paso % 10 == 0:
            todas = lib.operaciones()
            for c in lib.cuentas():
                propias = [op for op in todas if any(p.cuenta_id == c.id for p in op.partidas)]
                assert lib.operaciones(cuenta_id=c.id) == propias
                desde, hasta = sorted((fecha(), fecha()))
                assert lib.operaciones(desde, hasta, cuenta_id=c.id) == [op for op in propias
                                                                         if desde <= op.fecha <= hasta]
                dia = fecha()
                assert lib.saldo_centavos(c.id, dia) == sum(p.importe for op in todas if op.fecha <= dia
                                                            for p in op.partidas if p.cuenta_id == c.id)
            dia = fecha()
            assert bienes.valuar(lib, auto, dia) == _valuar_lento(lib, auto, dia)
