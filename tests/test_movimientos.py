from datetime import date

import pytest

from conftest import AHORA, D, JULIO
from motor import cuentas, movimientos, reportes
from motor.errores import ErrorNoEncontrado, ErrorValidacion
from motor.modelo import CATEGORIA_AJUSTE, Operacion, Partida, TipoOperacion
from motor.transferencias import construir_transferencia


def test_ingreso(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, cat("Nómina"), "10,000")
    assert cuentas.saldo(libro, ctas.debito) == D(10_000)
    r = reportes.resumen(libro, *JULIO)
    assert (r.ingresos, r.gastos, r.ahorro_real) == (D(10_000), 0, D(10_000))


def test_gasto_con_debito(libro, ctas, cat):
    op = movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 300, "Pizza")
    assert cuentas.saldo(libro, ctas.debito) == D(-300)
    assert reportes.resumen(libro, *JULIO).gastos == D(300)
    assert op.descripcion == "Pizza"
    assert op.creado_en == AHORA


def test_las_partidas_siempre_suman_cero(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 300)
    movimientos.registrar_ingreso(libro, date(2026, 7, 2), ctas.debito, cat("Nómina"), 900)
    for op in libro.operaciones():
        assert sum(p.importe for p in op.partidas) == 0


def test_gasto_repartido_en_varias_categorias(libro, ctas, cat):
    op = movimientos.registrar_gasto(
        libro, date(2026, 7, 2), ctas.debito,
        reparto=[(cat("Alimentos"), 250), (cat("Hogar y mantenimiento"), "99.50")],
    )
    assert cuentas.saldo(libro, ctas.debito) == D("-349.50")
    totales = {t.nombre: t.total for t in reportes.gastos_por_categoria(libro, *JULIO)}
    assert totales == {"Alimentos": D(250), "Hogar y mantenimiento": D("99.50")}
    detalle = movimientos.describir(op)
    assert detalle.categoria_id is None and len(detalle.reparto) == 2


def test_reembolso_resta_del_gasto_de_la_categoria(libro, ctas, cat):
    hogar = cat("Hogar y mantenimiento")
    movimientos.registrar_gasto(libro, date(2026, 7, 26), ctas.ahorro, hogar, 310)
    movimientos.registrar_gasto(libro, date(2026, 7, 26), ctas.ahorro, hogar, 205)
    movimientos.registrar_reembolso(libro, date(2026, 7, 30), ctas.ahorro, hogar, 310, "Devolución")
    r = reportes.resumen(libro, *JULIO)
    assert r.gastos == D(205)
    assert r.ingresos == 0
    assert cuentas.saldo(libro, ctas.ahorro) == D(-205)


def test_reembolso_en_otro_mes(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 6, 28), ctas.credito, cat("Compras en línea"), 500)
    movimientos.registrar_reembolso(libro, date(2026, 7, 3), ctas.credito, cat("Compras en línea"), 500)
    assert reportes.resumen(libro, date(2026, 6, 1), date(2026, 6, 30)).gastos == D(500)
    assert reportes.resumen(libro, *JULIO).gastos == D(-500)
    assert reportes.resumen(libro, date(2026, 6, 1), date(2026, 7, 31)).gastos == 0


@pytest.mark.parametrize("monto", [0, -50, "-1"])
def test_importes_no_positivos_se_rechazan(libro, ctas, cat, monto):
    with pytest.raises(ErrorValidacion):
        movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, cat("Alimentos"), monto)


def test_categoria_de_clase_equivocada(libro, ctas, cat):
    with pytest.raises(ErrorValidacion, match="gasto"):
        movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, cat("Nómina"), 10)
    with pytest.raises(ErrorValidacion, match="ingreso"):
        movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("Alimentos"), 10)
    with pytest.raises(ErrorValidacion):
        movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, CATEGORIA_AJUSTE, 10)


def test_referencias_inexistentes(libro, ctas, cat):
    with pytest.raises(ErrorNoEncontrado):
        movimientos.registrar_gasto(libro, date(2026, 7, 1), "no-existe", cat("Alimentos"), 10)
    with pytest.raises(ErrorNoEncontrado):
        movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, "no-existe", 10)


def test_operaciones_descuadradas_o_mal_formadas_se_rechazan(libro, ctas, cat):
    descuadrada = Operacion(
        date(2026, 7, 1), TipoOperacion.GASTO,
        (Partida(-100, cuenta_id=ctas.debito), Partida(90, categoria_id=cat("Alimentos"))),
    )
    with pytest.raises(ErrorValidacion, match="no cuadran"):
        libro.agregar_operacion(descuadrada)

    gasto_con_dos_cuentas = Operacion(
        date(2026, 7, 1), TipoOperacion.GASTO,
        (
            Partida(-100, cuenta_id=ctas.debito),
            Partida(-100, cuenta_id=ctas.ahorro),
            Partida(200, categoria_id=cat("Alimentos")),
        ),
    )
    with pytest.raises(ErrorValidacion):
        libro.agregar_operacion(gasto_con_dos_cuentas)

    with pytest.raises(ValueError):
        Partida(100, cuenta_id=ctas.debito, categoria_id=cat("Alimentos"))
    with pytest.raises(ValueError):
        Partida(1.5, cuenta_id=ctas.debito)


def test_fecha_con_hora_se_guarda_como_fecha(libro, ctas, cat):
    op = movimientos.registrar_gasto(libro, AHORA, ctas.debito, cat("Alimentos"), 10)
    assert op.fecha == AHORA.date()


# ------------------------------------------------------------------ edición


def test_editar_importe_categoria_y_fecha(libro, ctas, cat):
    op = movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 300)
    editada = movimientos.editar(
        libro, op.id, monto=350, categoria_id=cat("Snacks y antojos"), fecha=date(2026, 7, 3), descripcion="Helado"
    )
    assert editada.id == op.id
    assert editada.secuencia == op.secuencia
    assert editada.creado_en == op.creado_en
    detalle = movimientos.describir(editada)
    assert (detalle.monto, detalle.categoria_id, detalle.fecha, detalle.descripcion) == (
        D(350), cat("Snacks y antojos"), date(2026, 7, 3), "Helado"
    )
    assert cuentas.saldo(libro, ctas.debito) == D(-350)
    assert len(libro.operaciones()) == 1


def test_editar_cuenta_de_un_gasto(libro, ctas, cat):
    op = movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 300)
    movimientos.editar(libro, op.id, cuenta_id=ctas.credito)
    assert cuentas.saldo(libro, ctas.debito) == 0
    assert cuentas.saldo(libro, ctas.credito) == D(-300)


def test_editar_solo_descripcion_de_un_gasto_repartido(libro, ctas, cat):
    op = movimientos.registrar_gasto(
        libro, date(2026, 7, 2), ctas.debito, reparto=[(cat("Alimentos"), 1), (cat("Regalos"), 2)]
    )
    movimientos.editar(libro, op.id, descripcion="Súper")
    assert libro.operacion(op.id).descripcion == "Súper"
    with pytest.raises(ErrorValidacion, match="repartido"):
        movimientos.editar(libro, op.id, monto=5)
    movimientos.editar(libro, op.id, cuenta_id=ctas.credito)
    assert cuentas.saldo(libro, ctas.credito) == D(-3)


def test_editar_rechaza_campos_que_no_aplican(libro, ctas, cat):
    op = movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 300)
    with pytest.raises(ErrorValidacion):
        movimientos.editar(libro, op.id, cuenta_destino_id=ctas.ahorro)


def test_edicion_invalida_no_modifica_nada(libro, ctas, cat):
    op = movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 300)
    with pytest.raises(ErrorValidacion):
        movimientos.editar(libro, op.id, categoria_id=cat("Nómina"))
    assert libro.operacion(op.id) == op


def test_cambiar_tipo_de_gasto_a_transferencia(libro, ctas, cat):
    """Caso típico: se registró como gasto algo que era un traspaso al ahorro."""
    op = movimientos.registrar_gasto(libro, date(2026, 7, 15), ctas.debito, cat("Otros gastos"), 4000)
    nueva = construir_transferencia(date(2026, 7, 15), ctas.debito, ctas.ahorro, 4000)
    movimientos.reemplazar(libro, op.id, nueva)
    r = reportes.resumen(libro, *JULIO)
    assert r.gastos == 0
    assert r.apartado_a_ahorro == D(4000)
    assert libro.operacion(op.id).tipo is TipoOperacion.TRANSFERENCIA


def test_eliminar(libro, ctas, cat):
    op = movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, cat("Alimentos"), 300)
    borrada = movimientos.eliminar(libro, op.id)
    assert borrada == op
    assert cuentas.saldo(libro, ctas.debito) == 0
    with pytest.raises(ErrorNoEncontrado):
        movimientos.eliminar(libro, op.id)


def test_saldo_inicial_no_se_borra_ni_reemplaza_como_movimiento(libro):
    cuenta = cuentas.crear(libro, "Débito", "debito", saldo_inicial=100)
    (op,) = libro.operaciones()
    with pytest.raises(ErrorValidacion):
        movimientos.eliminar(libro, op.id)
    with pytest.raises(ErrorValidacion):
        movimientos.reemplazar(libro, op.id, construir_transferencia(date(2026, 7, 1), cuenta.id, cuenta.id, 1))


# ----------------------------------------------------- actualizar saldo


def test_actualizar_saldo_con_ajuste(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("Nómina"), 1000)
    op = movimientos.actualizar_saldo(libro, ctas.debito, "975.50", date(2026, 7, 20))
    assert op.tipo is TipoOperacion.AJUSTE
    assert cuentas.saldo(libro, ctas.debito) == D("975.50")
    r = reportes.resumen(libro, *JULIO)
    assert (r.ingresos, r.gastos, r.ajustes) == (D(1000), 0, D("-24.50"))
    assert movimientos.actualizar_saldo(libro, ctas.debito, "975.50", date(2026, 7, 20)) is None


def test_actualizar_saldo_como_rendimiento(libro, ctas, cat):
    """Sustituye las filas de «Interés diario»: una captura por semana o mes."""
    intereses = cat("Intereses y rendimientos")
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.ahorro, cat("Otros ingresos"), 18_000)
    op = movimientos.actualizar_saldo(libro, ctas.ahorro, "18,042.50", date(2026, 7, 31), categoria_id=intereses)
    assert op.tipo is TipoOperacion.RENDIMIENTO
    totales = {t.nombre: t.total for t in reportes.ingresos_por_categoria(libro, *JULIO)}
    assert totales["Intereses y rendimientos"] == D("42.50")


def test_rendimiento_negativo_en_inversion(libro, ctas, cat):
    rend = cat("Intereses y rendimientos")
    movimientos.actualizar_saldo(libro, ctas.inversion, 1000, date(2026, 7, 1))
    movimientos.actualizar_saldo(libro, ctas.inversion, 950, date(2026, 7, 31), categoria_id=rend)
    assert reportes.resumen(libro, *JULIO).ingresos == D(-50)
    assert cuentas.saldo(libro, ctas.inversion) == D(950)


def test_actualizar_saldo_solo_acepta_categorias_de_ingreso(libro, ctas, cat):
    with pytest.raises(ErrorValidacion):
        movimientos.actualizar_saldo(libro, ctas.ahorro, 10, date(2026, 7, 1), categoria_id=cat("Alimentos"))


def test_editar_ajuste_conserva_signo(libro, ctas):
    op = movimientos.actualizar_saldo(libro, ctas.debito, -20, date(2026, 7, 1))
    assert movimientos.describir(op).monto == D(-20)
    movimientos.editar(libro, op.id, monto=-30)
    assert cuentas.saldo(libro, ctas.debito) == D(-30)
    assert libro.operacion(op.id).partidas[1].categoria_id == CATEGORIA_AJUSTE
