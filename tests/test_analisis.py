"""Tablas dinámicas, presupuestos, estado de cuenta con saldo corrido y repetir movimientos. Datos ficticios."""

from datetime import date

import pytest

from conftest import D
from motor import analisis, categorias, consultas, movimientos, reportes
from motor.errores import ErrorValidacion
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia


@pytest.fixture
def datos(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 1, 15), ctas.debito, cat("Nómina"), 10000, "Quincena")
    movimientos.registrar_gasto(libro, date(2026, 1, 20), ctas.debito, cat("Despensa"), 800, "Súper")
    movimientos.registrar_gasto(libro, date(2026, 1, 21), ctas.credito, cat("Restaurantes"), 300, "Cena")
    movimientos.registrar_gasto(libro, date(2026, 2, 3), ctas.credito, cat("Despensa"), 500, "Súper")
    movimientos.registrar_reembolso(libro, date(2026, 2, 4), ctas.credito, cat("Despensa"), 100, "Devolución")
    movimientos.registrar_gasto(libro, date(2026, 2, 10), ctas.debito, cat("Gimnasio"), 650, "Gym")
    registrar_transferencia(libro, date(2026, 2, 15), ctas.debito, ctas.ahorro, 2000, "Al ahorro")
    registrar_pago_tarjeta(libro, date(2026, 2, 20), ctas.debito, ctas.credito, 300, "Pago TDC")
    return libro


def test_pivot_categoria_por_mes(datos):
    tabla = analisis.pivot(datos, filas="rubro", columnas="mes", medida="gastos")
    assert tabla.columnas == ["Ene 2026", "Feb 2026"]
    assert tabla.filas == ["ALIMENTACION", "DEPORTE Y BIENESTAR"]
    assert tabla.valor("ALIMENTACION", "Ene 2026") == D(1100)
    assert tabla.valor("ALIMENTACION", "Feb 2026") == D(400)                  # la devolución resta
    assert tabla.valor("DEPORTE Y BIENESTAR", "Ene 2026") is None
    assert tabla.total_fila == {"ALIMENTACION": D(1500), "DEPORTE Y BIENESTAR": D(650)}
    assert tabla.total_columna == {"Ene 2026": D(1100), "Feb 2026": D(1050)}
    assert tabla.total == D(2150)                                          # el pago de la tarjeta no es gasto


def test_pivot_con_apartado_a_ahorro_como_en_el_excel(datos):
    tabla = analisis.pivot(datos, filas="rubro", columnas="ninguna", incluir_apartado=True)
    assert tabla.filas[-1] == analisis.APARTADO
    assert tabla.valor(analisis.APARTADO, analisis.TOTAL) == D(2000)
    assert tabla.total == D(4150)


def test_pivot_otras_vistas(datos, ctas):
    por_sub = analisis.pivot(datos, filas="categoria", columnas="ninguna")
    assert por_sub.total_fila == {"DESPENSA": D(1200), "GIMNASIO": D(650), "RESTAURANTES": D(300)}
    solo_tdc = analisis.pivot(datos, filas="categoria", columnas="ninguna", cuentas={ctas.credito})
    assert solo_tdc.total_fila == {"DESPENSA": D(400), "RESTAURANTES": D(300)}
    rango = analisis.pivot(datos, filas="grupo", columnas="anio", desde=date(2026, 2, 1), hasta=date(2026, 2, 28))
    assert rango.columnas == ["2026"] and rango.total_fila == {"Crecimiento": D(650), "Necesidad": D(400)}
    todo = analisis.pivot(datos, filas="clase", columnas="mes", medida="todo")
    assert todo.valor("INGRESOS", "Ene 2026") == D(10000) and todo.valor("GASTOS", "Ene 2026") == D(1100)
    balance = analisis.pivot(datos, filas="cuenta", columnas="trimestre", medida="balance")
    assert balance.columnas == ["T1 2026"] and balance.total == D(10000 - 2150)
    with pytest.raises(ValueError):
        analisis.pivot(datos, filas="nada")


def test_pivot_vacio(libro):
    assert analisis.pivot(libro).vacia and analisis.meses_con_datos(libro) is None


def test_presupuestos(datos):
    alimentacion = categorias.buscar_rubro(datos, "Alimentación").id
    categorias.fijar_presupuesto(datos, alimentacion, 1000)
    (avance,) = reportes.presupuestos(datos, date(2026, 1, 1), date(2026, 1, 31))
    assert (avance.nombre, avance.presupuesto, avance.gastado, avance.restante, avance.avance) == (
        "ALIMENTACION", D(1000), D(1100), D(-100), D("1.1"))
    with pytest.raises(ErrorValidacion):
        categorias.fijar_presupuesto(datos, categorias.buscar_rubro(datos, "Ingresos varios").id, 100)
    categorias.fijar_presupuesto(datos, alimentacion, 0)
    assert reportes.presupuestos(datos, date(2026, 1, 1), date(2026, 1, 31)) == []


def test_estado_de_cuenta_con_saldo_corrido(datos, ctas):
    filas = consultas.movimientos_de_cuenta(datos, ctas.debito)
    assert [f.descripcion for f in filas] == ["Pago TDC", "Al ahorro", "Gym", "Súper", "Quincena"]
    assert [f.saldo for f in filas] == [D(6250), D(6550), D(8550), D(9200), D(10000)]
    assert (filas[0].cargo, filas[0].abono, filas[0].detalle) == (D(300), D(0), "→ Tarjeta Ficticia")
    assert filas[-1].detalle == "SUELDO Y PRESTACIONES › NOMINA" and filas[-1].abono == D(10000)
    # Con rango, el saldo sigue siendo el real.
    febrero = consultas.movimientos_de_cuenta(datos, ctas.debito, desde=date(2026, 2, 1))
    assert [f.saldo for f in febrero] == [D(6250), D(6550), D(8550)]
    tdc = consultas.movimientos_de_cuenta(datos, ctas.credito)
    assert tdc[0].detalle == "← Banco Ficticio Débito" and tdc[0].saldo == D(-400)


def test_repetir_un_movimiento(datos, ctas):
    gym = next(op for op in datos.operaciones() if op.descripcion == "Gym")
    otra = movimientos.duplicar(datos, gym.id, date(2026, 3, 10))
    assert otra.id != gym.id and otra.fecha == date(2026, 3, 10) and otra.partidas == gym.partidas
    from motor import cuentas

    nueva = cuentas.crear(datos, "Con saldo", "debito", saldo_inicial=50, fecha_creacion=date(2026, 1, 1))
    (inicial,) = [op for op in datos.operaciones() if any(p.cuenta_id == nueva.id for p in op.partidas)]
    with pytest.raises(ErrorValidacion):
        movimientos.duplicar(datos, inicial.id, date(2026, 3, 10))
