"""Metas de ahorro y fondo de emergencia. Solo datos ficticios."""

from dataclasses import replace
from datetime import date

import pytest

from conftest import AHORA, D
from motor import cuentas, metas, movimientos
from motor.errores import ErrorValidacion
from motor.serializacion import instantanea, libro_desde_instantanea

HOY = AHORA.date()                     # 20/07/2026


def test_crear_editar_y_guardar(libro, ctas):
    m = metas.crear(libro, "  Viaje a la playa  ", 12_000, cuenta_id=ctas.ahorro, fecha_limite=date(2026, 12, 20),
                    ya_tengo=2_000)
    assert (m.nombre, m.objetivo, metas.ahorrado(m), m.creada) == ("Viaje a la playa", 1_200_000, 200_000, HOY)
    assert libro.saldo_centavos(ctas.ahorro) == 0                    # «ya tengo» no mueve dinero
    m = metas.editar(libro, m.id, objetivo="15,000")
    assert m.objetivo == 1_500_000
    assert libro_desde_instantanea(instantanea(libro)).meta(m.id) == m
    metas.eliminar(libro, m.id)
    assert libro.metas() == []


def test_validaciones(libro, ctas):
    with pytest.raises(ErrorValidacion, match="mayor que cero"):
        metas.crear(libro, "Nada", 0)
    with pytest.raises(ErrorValidacion, match="débito, ahorro"):
        metas.crear(libro, "En la tarjeta", 100, cuenta_id=ctas.credito)
    metas.crear(libro, "Fondo", 100, emergencia=True)
    with pytest.raises(ErrorValidacion, match="solo puede haber uno"):
        metas.crear(libro, "Otro fondo", 100, emergencia=True)
    with pytest.raises(ErrorValidacion, match="Ya tienes una meta llamada"):
        metas.crear(libro, "FONDO", 100)


def test_aportar_y_retirar_mueven_el_dinero_a_la_cuenta_de_la_meta(libro, ctas):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 10_000, date(2026, 1, 1))
    m = metas.crear(libro, "Computadora", 20_000, cuenta_id=ctas.ahorro)
    m = metas.aportar(libro, m.id, 3_000, date(2026, 7, 1), desde=ctas.debito)
    assert libro.saldo_centavos(ctas.ahorro) == 300_000 and libro.saldo_centavos(ctas.debito) == 700_000
    assert m.aportes[-1].operacion_id
    m = metas.aportar(libro, m.id, 500, date(2026, 7, 2))                  # ya estaba en la cuenta
    assert libro.saldo_centavos(ctas.ahorro) == 300_000 and metas.ahorrado(m) == 350_000
    with pytest.raises(ErrorValidacion, match="solo tienes"):
        metas.retirar(libro, m.id, 4_000)
    m = metas.retirar(libro, m.id, 1_000, date(2026, 7, 3), hacia=ctas.debito)
    assert metas.ahorrado(m) == 250_000 and libro.saldo_centavos(ctas.debito) == 800_000


def test_como_vas_con_fecha_limite_y_ritmo(libro, ctas):
    m = metas.crear(libro, "Auto", 60_000, fecha_limite=date(2027, 1, 31))
    libro.guardar_meta(replace(libro.meta(m.id), creada=date(2026, 4, 20)))        # creada hace 3 meses
    for mes in (5, 6, 7):
        metas.aportar(libro, m.id, 5_000, date(2026, mes, 15))
    e = metas.estado(libro.meta(m.id), HOY)
    assert (e.ahorrado, e.falta, e.porcentaje, e.lograda) == (D(15_000), D(45_000), 25, False)
    assert e.meses_restantes == 6 and e.por_mes == D(7_500)
    assert e.ritmo == D(5_000) and e.fecha_estimada == date(2027, 4, 16)        # 9 meses al ritmo actual
    assert e.a_tiempo is False
    metas.aportar(libro, m.id, 45_000, HOY)
    e = metas.estado(libro.meta(m.id), HOY)
    assert e.lograda and e.porcentaje == 100 and e.por_mes is None and e.fecha_estimada is None


def test_lo_apartado_por_cuenta_avisa_si_no_alcanza(libro, ctas):
    metas.crear(libro, "Uno", 1_000, cuenta_id=ctas.ahorro, ya_tengo=600)
    metas.crear(libro, "Dos", 1_000, cuenta_id=ctas.ahorro, ya_tengo=300)
    (c,) = metas.por_cuenta(libro)
    assert (c.apartado, c.saldo, c.libre) == (D(900), D(0), D(-900))
    assert metas.totales(libro) == (D(900), D(2_000))


def test_fondo_de_emergencia_con_gastos_esenciales(libro, ctas, cat):
    for mes in (4, 5, 6):                                                     # 3 meses completos antes de julio
        movimientos.registrar_gasto(libro, date(2026, mes, 3), ctas.debito, cat("RENTA"), 6_000)       # Necesidad
        movimientos.registrar_gasto(libro, date(2026, mes, 5), ctas.debito, cat("DESPENSA"), 3_000)    # Necesidad
        movimientos.registrar_gasto(libro, date(2026, mes, 7), ctas.debito, cat("CINE"), 900)          # Disfrute
        movimientos.registrar_gasto(libro, date(2026, mes, 9), ctas.debito, cat("IMPUESTOS"), 300)     # Compromisos
    f = metas.fondo(libro, HOY)
    assert f.esencial_al_mes == D(9_300) and f.recomendado_minimo == D(27_900) and f.recomendado_ideal == D(55_800)
    assert f.meta is None and f.meses_cubiertos is None
    metas.crear(libro, "Fondo de emergencia", f.recomendado_minimo, emergencia=True, ya_tengo=13_950)
    assert metas.fondo(libro, HOY).meses_cubiertos == D("1.5")
    assert metas.estado(metas.fondo(libro, HOY).meta, HOY).ritmo == 0    # lo que ya tenías no es «tu ritmo»


def test_borrar_la_cuenta_deja_la_meta_sin_cuenta(libro):
    sin_movimientos = cuentas.crear(libro, "Alcancía Ficticia", "efectivo", fecha_creacion=date(2026, 1, 1)).id
    m = metas.crear(libro, "Regalo", 500, cuenta_id=sin_movimientos)
    libro.quitar_cuenta(sin_movimientos)
    assert libro.meta(m.id).cuenta_id is None
