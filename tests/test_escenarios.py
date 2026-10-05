"""Escenarios completos con datos ficticios y propiedades que siempre deben cumplirse."""

import random
from datetime import date, timedelta

from conftest import D, JULIO
from motor import cuentas, movimientos, reportes, tarjetas
from motor.modelo import ClaseCategoria, TipoCuenta
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia


def test_consola_pagada_con_efectivo_tras_traspaso_cuenta_un_solo_gasto(libro, ctas, cat):
    """En Excel este caso se registraba como gasto dos veces (en el ahorro y como retiro).

    Flujo real: ahorro → débito (traspaso), y retiro en efectivo para pagar.
    """
    movimientos.actualizar_saldo(libro, ctas.ahorro, 10_000, date(2026, 7, 1))
    registrar_transferencia(libro, date(2026, 7, 30), ctas.ahorro, ctas.debito, 2600, "Para la consola")
    movimientos.registrar_gasto(
        libro, date(2026, 7, 30), ctas.debito, cat("Hardware y entretenimiento"), 2450, "Consola usada (efectivo)"
    )
    r = reportes.resumen(libro, *JULIO)
    assert r.gastos == D(2450)
    assert r.apartado_a_ahorro == D(-2600)
    assert cuentas.saldo(libro, ctas.debito) == D(150)


def test_mes_tipico(libro, ctas, cat):
    """Un mes con nómina quincenal, TDC, ahorro, rendimientos, terceros y devoluciones."""
    por_cobrar = cuentas.crear(libro, "Por cobrar", TipoCuenta.POR_COBRAR).id
    c = cat
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, "87.00", date(2026, 7, 1))
    cuentas.cambiar_saldo_inicial(libro, ctas.ahorro, 7000, date(2026, 7, 1))

    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, c("Nómina"), "4210.10")
    registrar_transferencia(libro, date(2026, 7, 15), ctas.debito, ctas.ahorro, "2500.50")
    registrar_transferencia(libro, date(2026, 7, 15), ctas.debito, ctas.inversion, "1111.11")
    registrar_pago_tarjeta(libro, date(2026, 7, 15), ctas.debito, ctas.credito, 380)
    movimientos.registrar_gasto(libro, date(2026, 7, 15), ctas.debito, c("Alimentos"), 100, "Snacks")
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, c("Alimentos"), 65)
    movimientos.registrar_gasto(libro, date(2026, 7, 6), ctas.credito, c("Regalos"), "333.33")
    movimientos.registrar_gasto(libro, date(2026, 7, 10), ctas.ahorro, c("Insumos de trabajo"), 1500)
    registrar_transferencia(libro, date(2026, 7, 18), ctas.ahorro, por_cobrar, "275.25", "Encargo para amistad")
    registrar_transferencia(libro, date(2026, 7, 18), por_cobrar, ctas.ahorro, "275.25", "Me pagó")
    movimientos.registrar_gasto(libro, date(2026, 7, 26), ctas.ahorro, c("Hogar y mantenimiento"), 310)
    movimientos.registrar_reembolso(libro, date(2026, 7, 30), ctas.ahorro, c("Hogar y mantenimiento"), 310)
    movimientos.registrar_gasto(libro, date(2026, 7, 31), ctas.debito, c("Retiros de efectivo"), 500)
    movimientos.registrar_ingreso(libro, date(2026, 7, 31), ctas.debito, c("Nómina"), "4215.20")
    registrar_transferencia(libro, date(2026, 7, 31), ctas.debito, ctas.ahorro, 990)
    saldo_ahorro = cuentas.saldo(libro, ctas.ahorro, date(2026, 7, 31))
    movimientos.actualizar_saldo(
        libro, ctas.ahorro, saldo_ahorro + D("61.70"), date(2026, 7, 31), categoria_id=c("Intereses y rendimientos")
    )

    r = reportes.resumen(libro, *JULIO)
    assert r.ingresos == D("4210.10") + D("4215.20") + D("61.70")
    assert r.gastos == D(100) + D(65) + D("333.33") + D(1500) + D(500)
    assert r.ahorro_real == r.ingresos - r.gastos
    assert r.apartado_a_ahorro == D("2500.50") + D("1111.11") + D(990)
    assert r.ajustes == 0

    gastos_por_cat = {t.nombre: t.total for t in reportes.gastos_por_categoria(libro, *JULIO)}
    assert "Hogar y mantenimiento" not in gastos_por_cat or gastos_por_cat["Hogar y mantenimiento"] == 0
    assert reportes.indicadores(libro).te_deben == 0
    assert tarjetas.deuda(libro, ctas.credito) == D("18.33")  # 398.33 de cargos − 380 pagados

    sobrantes = reportes.sobrantes_de_quincena(libro, ctas.debito)
    assert [s.sobrante for s in sobrantes] == [D("87.00"), D("87.00") + D("4210.10") - D("2500.50")
                                               - D("1111.11") - D(380) - D(100) - D(500)]


def test_cuadratura_global_con_operaciones_aleatorias(libro, cat):
    """Propiedades que se cumplen siempre, con cientos de operaciones al azar.

    1. Toda operación suma cero.
    2. Patrimonio = saldos iniciales + ajustes + ingresos − gastos.
    3. Quitar todas las transferencias no cambia ingresos ni gastos.
    """
    rnd = random.Random(20260705)
    ctas = [
        cuentas.crear(libro, f"Cuenta {i}", tipo).id
        for i, tipo in enumerate(
            [TipoCuenta.DEBITO, TipoCuenta.DEBITO, TipoCuenta.CREDITO, TipoCuenta.CREDITO,
             TipoCuenta.AHORRO, TipoCuenta.INVERSION, TipoCuenta.POR_COBRAR]
        )
    ]
    for cuenta_id in ctas:
        cuentas.cambiar_saldo_inicial(libro, cuenta_id, rnd.randint(-5000, 20000), date(2026, 1, 1))
    tarjetas_ids = [c for c in ctas if libro.cuenta(c).tipo is TipoCuenta.CREDITO]
    de_gasto = [c.id for c in libro.categorias() if c.clase is ClaseCategoria.GASTO]
    de_ingreso = [c.id for c in libro.categorias() if c.clase is ClaseCategoria.INGRESO]

    inicio = date(2026, 1, 1)
    for _ in range(400):
        fecha = inicio + timedelta(days=rnd.randint(0, 364))
        monto = D(rnd.randint(1, 500_000)) / 100
        cuenta = rnd.choice(ctas)
        accion = rnd.random()
        if accion < 0.4:
            movimientos.registrar_gasto(libro, fecha, cuenta, rnd.choice(de_gasto), monto)
        elif accion < 0.55:
            movimientos.registrar_ingreso(libro, fecha, cuenta, rnd.choice(de_ingreso), monto)
        elif accion < 0.6:
            movimientos.registrar_reembolso(libro, fecha, cuenta, rnd.choice(de_gasto), monto)
        elif accion < 0.8:
            destino = rnd.choice([c for c in ctas if c != cuenta])
            registrar_transferencia(libro, fecha, cuenta, destino, monto)
        elif accion < 0.9:
            tarjeta = rnd.choice([t for t in tarjetas_ids if t != cuenta])
            registrar_pago_tarjeta(libro, fecha, cuenta, tarjeta, monto)
        else:
            movimientos.actualizar_saldo(libro, cuenta, D(rnd.randint(-100_000, 100_000)) / 100, fecha)

    for op in libro.operaciones():
        assert sum(p.importe for p in op.partidas) == 0

    anio = (date(2026, 1, 1), date(2026, 12, 31))
    r = reportes.resumen(libro, *anio)
    iniciales = sum(
        -p.importe for op in libro.operaciones() if op.tipo.value == "saldo_inicial"
        for p in op.partidas_de_categoria()
    )
    assert reportes.indicadores(libro).patrimonio_neto == (
        D(iniciales) / 100 + r.ajustes + r.ingresos - r.gastos
    )

    for op in libro.operaciones():
        if op.tipo.value in ("transferencia", "pago_tarjeta"):
            libro.eliminar_operacion(op.id)
    sin_transferencias = reportes.resumen(libro, *anio)
    assert (sin_transferencias.ingresos, sin_transferencias.gastos) == (r.ingresos, r.gastos)
    assert sin_transferencias.apartado_a_ahorro == 0
