from datetime import date

import pytest

from conftest import D
from motor import cuentas, movimientos, reportes
from motor.errores import ErrorNoEncontrado, ErrorValidacion
from motor.modelo import CATEGORIA_SALDO_INICIAL, TipoCuenta, TipoOperacion


def test_crear_cuenta_con_saldo_inicial(libro):
    cuenta = cuentas.crear(libro, "Débito", TipoCuenta.DEBITO, saldo_inicial="1,500.50", fecha_creacion=date(2026, 1, 1))
    assert cuentas.saldo(libro, cuenta.id) == D("1500.50")
    assert cuenta.en_disponible
    assert cuenta.moneda == "MXN"
    (op,) = libro.operaciones()
    assert op.tipo is TipoOperacion.SALDO_INICIAL


def test_saldo_inicial_no_es_ingreso(libro):
    cuentas.crear(libro, "Débito", TipoCuenta.DEBITO, saldo_inicial=10_000, fecha_creacion=date(2026, 7, 1))
    r = reportes.resumen(libro, date(2026, 7, 1), date(2026, 7, 31))
    assert r.ingresos == 0
    assert r.gastos == 0
    assert r.ajustes == 0


def test_tarjeta_con_deuda_inicial(libro):
    tdc = cuentas.crear(libro, "TDC", TipoCuenta.CREDITO, deuda_inicial=800, limite_credito=5000)
    assert cuentas.saldo(libro, tdc.id) == D(-800)
    assert not tdc.en_disponible


def test_varias_cuentas_del_mismo_tipo(libro):
    for i in range(12):
        cuentas.crear(libro, f"Tarjeta {i}", TipoCuenta.CREDITO)
    assert len(cuentas.listar(libro, tipo=TipoCuenta.CREDITO)) == 12


def test_nombre_unico_sin_importar_mayusculas_ni_espacios(libro):
    cuentas.crear(libro, "Mercado Pago", TipoCuenta.AHORRO)
    with pytest.raises(ErrorValidacion):
        cuentas.crear(libro, "  mercado   pago ", TipoCuenta.AHORRO)


def test_datos_de_credito_solo_en_tarjetas(libro):
    with pytest.raises(ErrorValidacion):
        cuentas.crear(libro, "Débito", TipoCuenta.DEBITO, dia_corte=3)
    with pytest.raises(ErrorValidacion):
        cuentas.crear(libro, "TDC", TipoCuenta.CREDITO, dia_corte=32)
    with pytest.raises(ErrorValidacion):
        cuentas.crear(libro, "TDC", TipoCuenta.CREDITO, saldo_inicial=-5, deuda_inicial=5)


def test_editar_cuenta(libro, ctas):
    cuentas.editar(libro, ctas.credito, nombre="Nueva TDC", limite_credito=2000, dia_corte=None)
    tdc = libro.cuenta(ctas.credito)
    assert tdc.nombre == "Nueva TDC"
    assert tdc.limite_credito == 200000
    assert tdc.dia_corte is None
    assert tdc.dia_pago == 23
    with pytest.raises(ErrorValidacion):
        cuentas.editar(libro, ctas.debito, limite_credito=100)


def test_archivar_impide_movimientos_nuevos_pero_conserva_historial(libro, ctas, cat):
    op = movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, cat("Alimentos"), 100)
    cuentas.archivar(libro, ctas.debito)
    with pytest.raises(ErrorValidacion, match="archivada"):
        movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 100)
    # Editar un movimiento existente sí se permite.
    movimientos.editar(libro, op.id, monto=150)
    assert cuentas.saldo(libro, ctas.debito) == D(-150)
    assert ctas.debito not in [c.id for c in cuentas.listar(libro)]
    assert ctas.debito in [c.id for c in cuentas.listar(libro, incluir_archivadas=True)]
    cuentas.reactivar(libro, ctas.debito)
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 100)


def test_cuenta_archivada_con_saldo_sigue_en_patrimonio(libro):
    cuenta = cuentas.crear(libro, "Vieja", TipoCuenta.AHORRO, saldo_inicial=300)
    cuentas.archivar(libro, cuenta.id)
    assert reportes.indicadores(libro).patrimonio_neto == D(300)


def test_eliminar_cuenta(libro, ctas, cat):
    vacia = cuentas.crear(libro, "Vacía", TipoCuenta.EFECTIVO, saldo_inicial=50)
    cuentas.eliminar(libro, vacia.id)
    with pytest.raises(ErrorNoEncontrado):
        libro.cuenta(vacia.id)
    assert libro.operaciones() == []

    movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, cat("Alimentos"), 10)
    with pytest.raises(ErrorValidacion, match="archívala"):
        cuentas.eliminar(libro, ctas.debito)


def test_cambiar_saldo_inicial(libro):
    cuenta = cuentas.crear(libro, "Débito", TipoCuenta.DEBITO, fecha_creacion=date(2026, 1, 1))
    cuentas.cambiar_saldo_inicial(libro, cuenta.id, 500)
    assert cuentas.saldo(libro, cuenta.id) == D(500)
    cuentas.cambiar_saldo_inicial(libro, cuenta.id, 700)
    assert cuentas.saldo(libro, cuenta.id) == D(700)
    assert len(libro.operaciones()) == 1
    cuentas.cambiar_saldo_inicial(libro, cuenta.id, 0)
    assert libro.operaciones() == []


def test_solo_un_saldo_inicial_por_cuenta(libro):
    cuenta = cuentas.crear(libro, "Débito", TipoCuenta.DEBITO, saldo_inicial=100)
    segundo = movimientos.construir_con_signo(
        TipoOperacion.SALDO_INICIAL, date(2026, 1, 1), cuenta.id, CATEGORIA_SALDO_INICIAL, 100
    )
    with pytest.raises(ErrorValidacion, match="ya tiene un saldo inicial"):
        libro.agregar_operacion(segundo)


def test_cambiar_tipo(libro, ctas):
    cuentas.cambiar_tipo(libro, ctas.ahorro, TipoCuenta.INVERSION)
    assert libro.cuenta(ctas.ahorro).tipo is TipoCuenta.INVERSION


def test_no_deja_de_ser_credito_si_recibio_pagos(libro, ctas):
    from motor.transferencias import registrar_pago_tarjeta

    registrar_pago_tarjeta(libro, date(2026, 7, 1), ctas.debito, ctas.credito, 100)
    with pytest.raises(ErrorValidacion):
        cuentas.cambiar_tipo(libro, ctas.credito, TipoCuenta.DEBITO)


def test_saldo_a_una_fecha(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("Nómina"), 1000)
    movimientos.registrar_gasto(libro, date(2026, 7, 10), ctas.debito, cat("Alimentos"), 300)
    assert cuentas.saldo(libro, ctas.debito, date(2026, 6, 30)) == 0
    assert cuentas.saldo(libro, ctas.debito, date(2026, 7, 9)) == D(1000)
    assert cuentas.saldo(libro, ctas.debito, date(2026, 7, 10)) == D(700)
