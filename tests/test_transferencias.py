"""Las reglas más importantes: nada de doble conteo."""

from datetime import date

import pytest

from conftest import D, JULIO
from motor import cuentas, movimientos, reportes, tarjetas
from motor.errores import ErrorValidacion
from motor.modelo import TipoOperacion
from motor.transferencias import origen_y_destino, registrar_pago_tarjeta, registrar_transferencia


def test_transferencia_a_ahorro_no_es_gasto(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, cat("Nómina"), 5000)
    op = registrar_transferencia(libro, date(2026, 7, 15), ctas.debito, ctas.ahorro, 3000, "Al ahorro")

    assert cuentas.saldo(libro, ctas.debito) == D(2000)
    assert cuentas.saldo(libro, ctas.ahorro) == D(3000)
    assert len(libro.operaciones()) == 2  # una sola operación para la transferencia
    assert op.partidas_de_categoria() == ()

    r = reportes.resumen(libro, *JULIO)
    assert r.gastos == 0
    assert r.ingresos == D(5000)
    assert r.ahorro_real == D(5000)
    assert r.apartado_a_ahorro == D(3000)
    assert reportes.gastos_por_categoria(libro, *JULIO) == []
    assert reportes.hechos(libro, *JULIO)[0]["categoria"] == "Nómina"
    assert len(reportes.hechos(libro, *JULIO)) == 1


def test_compra_con_tdc_y_pago_cuentan_un_solo_gasto(libro, ctas, cat):
    """Ejemplo fundamental del modelo: Gastos = 500, no 1,000."""
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("Nómina"), 2000)
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("Alimentos"), 500, "Restaurante")

    assert reportes.resumen(libro, *JULIO).gastos == D(500)
    assert tarjetas.deuda(libro, ctas.credito) == D(500)
    assert reportes.indicadores(libro).deuda_tarjetas == D(500)

    registrar_pago_tarjeta(libro, date(2026, 7, 20), ctas.debito, ctas.credito, 500)

    assert reportes.resumen(libro, *JULIO).gastos == D(500)
    assert tarjetas.deuda(libro, ctas.credito) == 0
    assert cuentas.saldo(libro, ctas.debito) == D(1500)
    assert reportes.indicadores(libro).patrimonio_neto == D(1500)


def test_pago_de_tarjeta_en_otro_mes_no_genera_gasto_en_ese_mes(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 6, 28), ctas.credito, cat("Alimentos"), 800)
    registrar_pago_tarjeta(libro, date(2026, 7, 4), ctas.debito, ctas.credito, 800)
    assert reportes.resumen(libro, date(2026, 6, 1), date(2026, 6, 30)).gastos == D(800)
    assert reportes.resumen(libro, *JULIO).gastos == 0


def test_pagos_parciales_desde_varias_cuentas(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("Alimentos"), 900)
    registrar_pago_tarjeta(libro, date(2026, 7, 10), ctas.debito, ctas.credito, 400)
    registrar_pago_tarjeta(libro, date(2026, 7, 12), ctas.ahorro, ctas.credito, 100)
    assert tarjetas.deuda(libro, ctas.credito) == D(400)
    assert reportes.resumen(libro, *JULIO).gastos == D(900)
    # Pagar la TDC desde el ahorro reduce el ahorro apartado.
    assert reportes.resumen(libro, *JULIO).apartado_a_ahorro == D(-100)


def test_pago_mayor_a_la_deuda_deja_saldo_a_favor(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("Alimentos"), 500)
    registrar_pago_tarjeta(libro, date(2026, 7, 6), ctas.debito, ctas.credito, 600)
    assert cuentas.saldo(libro, ctas.credito) == D(100)
    assert tarjetas.deuda(libro, ctas.credito) == 0
    assert reportes.indicadores(libro).deuda_tarjetas == 0


def test_pago_de_tarjeta_debe_ir_a_credito(libro, ctas):
    with pytest.raises(ErrorValidacion, match="crédito"):
        registrar_pago_tarjeta(libro, date(2026, 7, 1), ctas.debito, ctas.ahorro, 100)


def test_transferencia_a_la_misma_cuenta(libro, ctas):
    with pytest.raises(ErrorValidacion, match="distintas"):
        registrar_transferencia(libro, date(2026, 7, 1), ctas.debito, ctas.debito, 100)


@pytest.mark.parametrize("monto", [0, -10])
def test_transferencia_con_importe_no_positivo(libro, ctas, monto):
    with pytest.raises(ErrorValidacion):
        registrar_transferencia(libro, date(2026, 7, 1), ctas.debito, ctas.ahorro, monto)


def test_editar_transferencia_cambia_ambos_lados(libro, ctas):
    op = registrar_transferencia(libro, date(2026, 7, 15), ctas.debito, ctas.ahorro, 3000)
    movimientos.editar(libro, op.id, monto=2500)
    assert cuentas.saldo(libro, ctas.debito) == D(-2500)
    assert cuentas.saldo(libro, ctas.ahorro) == D(2500)

    movimientos.editar(libro, op.id, cuenta_destino_id=ctas.inversion)
    assert cuentas.saldo(libro, ctas.ahorro) == 0
    assert cuentas.saldo(libro, ctas.inversion) == D(2500)
    assert origen_y_destino(libro.operacion(op.id)) == (ctas.debito, ctas.inversion)
    with pytest.raises(ErrorValidacion):
        movimientos.editar(libro, op.id, categoria_id="x")


def test_eliminar_transferencia_borra_ambos_lados(libro, ctas):
    op = registrar_transferencia(libro, date(2026, 7, 15), ctas.debito, ctas.ahorro, 3000)
    movimientos.eliminar(libro, op.id)
    assert cuentas.saldo(libro, ctas.debito) == 0
    assert cuentas.saldo(libro, ctas.ahorro) == 0


def test_retiro_de_efectivo_es_gasto(libro, ctas, cat):
    """Decisión del usuario: el efectivo retirado se da por gastado."""
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Retiros de efectivo"), 600)
    assert reportes.resumen(libro, *JULIO).gastos == D(600)


def test_retiro_con_cuenta_de_efectivo_es_transferencia(libro, ctas, cat):
    """Quien sí quiera rastrear su efectivo puede tener una cuenta de efectivo."""
    efectivo = cuentas.crear(libro, "Cartera", "efectivo").id
    registrar_transferencia(libro, date(2026, 7, 2), ctas.debito, efectivo, 600)
    movimientos.registrar_gasto(libro, date(2026, 7, 3), efectivo, cat("Alimentos"), 150)
    assert reportes.resumen(libro, *JULIO).gastos == D(150)
    assert reportes.indicadores(libro).dinero_disponible == D(-150)


def test_terceros_por_cobrar(libro, ctas, cat):
    """Pagar algo de alguien más no es gasto; que te lo devuelvan no es ingreso."""
    por_cobrar = cuentas.crear(libro, "Por cobrar: Amigo Ficticio", "por_cobrar").id
    registrar_transferencia(libro, date(2026, 7, 18), ctas.debito, por_cobrar, 400, "Encargo")
    assert reportes.indicadores(libro).te_deben == D(400)

    registrar_transferencia(libro, date(2026, 7, 20), por_cobrar, ctas.debito, 400, "Me pagó")
    r = reportes.resumen(libro, *JULIO)
    assert (r.ingresos, r.gastos) == (0, 0)
    assert reportes.indicadores(libro).te_deben == 0


def test_tercero_paga_de_mas(libro, ctas, cat):
    por_cobrar = cuentas.crear(libro, "Por cobrar", "por_cobrar").id
    registrar_transferencia(libro, date(2026, 7, 1), ctas.debito, por_cobrar, "412.40")
    registrar_transferencia(libro, date(2026, 7, 2), por_cobrar, ctas.debito, "412.40")
    movimientos.registrar_ingreso(libro, date(2026, 7, 2), ctas.debito, cat("Otros ingresos"), "37.60")
    assert reportes.resumen(libro, *JULIO).ingresos == D("37.60")
    assert cuentas.saldo(libro, ctas.debito) == D("37.60")


def test_tipo_de_operacion_se_conserva(libro, ctas):
    op = registrar_pago_tarjeta(libro, date(2026, 7, 1), ctas.debito, ctas.credito, 10)
    assert op.tipo is TipoOperacion.PAGO_TARJETA
    movimientos.editar(libro, op.id, monto=20)
    assert libro.operacion(op.id).tipo is TipoOperacion.PAGO_TARJETA
