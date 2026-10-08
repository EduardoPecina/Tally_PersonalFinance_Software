"""Sacar efectivo (motor/efectivo.py): con cuenta de efectivo no es gasto, pasa a esa cuenta. Solo datos ficticios."""

from datetime import date

import pytest

from conftest import D
from motor import bancos, comprobantes, cuentas, efectivo, movimientos, reportes, salud
from motor.bancos import Movimiento
from motor.errores import ErrorValidacion
from motor.modelo import TipoOperacion

DIA = date(2026, 7, 15)


@pytest.fixture
def banco(libro, ctas):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 10_000, date(2026, 1, 1))
    return ctas.debito


@pytest.fixture
def cartera(libro):
    return cuentas.crear(libro, "Efectivo Ficticio", "efectivo", saldo_inicial=200,
                         fecha_creacion=date(2026, 7, 1)).id


def retiro_como_gasto(libro, origen, monto=500, fecha=DIA):
    return movimientos.registrar_gasto(libro, fecha, origen, efectivo.subcategoria(libro), monto, "Retiro cajero")


def test_registrar_un_retiro_pasa_el_dinero_a_tu_efectivo(libro, banco, cartera):
    op = efectivo.registrar(libro, DIA, banco, 500, "Cajero ficticio")
    assert op.tipo is TipoOperacion.TRANSFERENCIA
    assert cuentas.saldo(libro, banco) == D(9_500) and cuentas.saldo(libro, cartera) == D(700)
    assert reportes.resumen(libro, DIA, DIA).gastos == 0                     # no es gasto
    assert efectivo.destino_para(libro, banco, efectivo.subcategoria(libro)).id == cartera
    assert efectivo.destino_para(libro, cartera, efectivo.subcategoria(libro)) is None    # de efectivo a efectivo no


def test_sin_cuenta_de_efectivo_sigue_siendo_gasto(libro, banco):
    assert efectivo.destino_para(libro, banco, efectivo.subcategoria(libro)) is None
    with pytest.raises(ErrorValidacion, match="cuenta de efectivo"):
        efectivo.registrar(libro, DIA, banco, 500)
    retiro_como_gasto(libro, banco)
    assert efectivo.pendientes(libro) == []
    assert reportes.resumen(libro, DIA, DIA).gastos == D(500)


def test_pasar_a_efectivo_lo_que_ya_guardaste_como_gasto(libro, banco, cartera, ctas):
    viejo = retiro_como_gasto(libro, banco, fecha=date(2026, 6, 20))       # antes de llevar tu efectivo: se queda
    hoy = retiro_como_gasto(libro, banco)
    tarjeta = retiro_como_gasto(libro, ctas.credito, 300)                  # disposición con la tarjeta
    comprobantes.adjuntar(libro, hoy.id, "ticket.jpg", b"\xff\xd8\xff" + b"cajero ficticio")
    assert [op.id for op in efectivo.pendientes(libro)] == [hoy.id, tarjeta.id]
    assert efectivo.convertible(libro, viejo) is None

    (h,) = [h for h in salud.revisar(libro).hallazgos if h.clave.startswith("efectivo:")]
    assert h.nivel == salud.REVISAR and h.cuantos == 2 and "$800.00" in h.detalle

    nueva = efectivo.convertir(libro, hoy.id)
    assert nueva.id == hoy.id and nueva.tipo is TipoOperacion.TRANSFERENCIA
    assert (nueva.fecha, nueva.descripcion) == (hoy.fecha, "Retiro cajero")
    assert [c.operacion_id for c in libro.comprobantes()] == [hoy.id]     # el comprobante sigue con él
    assert efectivo.convertir_todos(libro) == 1
    assert cuentas.saldo(libro, cartera) == D(200 + 500 + 300)
    assert efectivo.pendientes(libro) == []
    assert not any(h.clave.startswith("efectivo:") for h in salud.revisar(libro).hallazgos)
    with pytest.raises(ErrorValidacion):
        efectivo.convertir(libro, viejo.id)


def test_al_importar_del_banco_el_cajero_va_a_tu_efectivo(libro, banco):
    lista = [Movimiento(1, DIA, "RETIRO CAJERO ATM 1234", -50_000)]
    (sin,) = bancos.revisar(libro, banco, lista)
    assert sin.destino == bancos.destino_subcategoria(efectivo.subcategoria(libro))   # sin cuenta: gasto
    cartera = cuentas.crear(libro, "Efectivo Ficticio", "efectivo", fecha_creacion=date(2026, 7, 1)).id
    (con,) = bancos.revisar(libro, banco, lista)
    assert con.destino == bancos.destino_cuenta(cartera) and "Retiro de efectivo" in con.motivo
