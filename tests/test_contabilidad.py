"""Contabilidad técnica: estados financieros derivados de los movimientos. Solo datos ficticios."""

from datetime import date

import pytest

from conftest import D
from motor import contabilidad as cb
from motor import cuentas, movimientos, portafolio
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia

ANIO_PASADO = (date(2025, 1, 1), date(2025, 12, 31))
ESTE_ANIO = (date(2026, 1, 1), date(2026, 7, 20))


@pytest.fixture
def datos(libro, ctas, cat):
    """2025: nómina y súper con tarjeta (pagada). 2026: inversión, préstamo cobrado, súper con tarjeta sin pagar."""
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 10_000, date(2025, 6, 1))
    movimientos.registrar_ingreso(libro, date(2025, 7, 1), ctas.debito, cat("NOMINA"), 20_000, "Nómina ficticia")
    movimientos.registrar_gasto(libro, date(2025, 7, 2), ctas.credito, cat("ALIMENTOS"), 1_500, "Súper ficticio")
    registrar_pago_tarjeta(libro, date(2025, 7, 20), ctas.debito, ctas.credito, 1_500, "Pago ficticio")
    registrar_transferencia(libro, date(2026, 1, 5), ctas.debito, ctas.inversion, 5_000, "Aportación")
    por_cobrar = cuentas.crear(libro, "Préstamo a amigo ficticio", "por_cobrar", fecha_creacion=date(2026, 1, 1)).id
    registrar_transferencia(libro, date(2026, 2, 1), ctas.debito, por_cobrar, 800, "Le presté")
    registrar_transferencia(libro, date(2026, 3, 1), por_cobrar, ctas.debito, 800, "Me pagó")
    movimientos.registrar_gasto(libro, date(2026, 3, 2), ctas.credito, cat("ALIMENTOS"), 700, "Súper ficticio")
    movimientos.registrar_ingreso(libro, date(2026, 4, 1), ctas.debito, cat("NOMINA"), 20_000, "Nómina ficticia")
    portafolio.ajustar_a_valor_oficial(libro, ctas.inversion, 5_150, date(2026, 6, 30))
    return {"por_cobrar": por_cobrar}


def test_situacion_financiera_cuadra_y_compara(libro, datos):
    s = cb.situacion(libro, [ESTE_ANIO[1], ANIO_PASADO[1]])
    assert s.cuadra
    assert s.total(cb.ACTIVO) == (D(48_650), D(28_500))           # 43,500 en débito + 5,150 invertidos
    assert s.total(cb.PASIVO) == (D(700), D(0))                    # la tarjeta sin pagar es deuda
    assert s.total(cb.PATRIMONIO) == (D(47_950), D(28_500))
    patrimonio = {r.nombre: r.importes for r in s.renglones if r.naturaleza == cb.PATRIMONIO}
    assert patrimonio[cb.PATRIMONIO_INICIAL] == (D(10_000), D(10_000))
    assert patrimonio[cb.RESULTADOS_ANTERIORES] == (D(18_500), D(0))
    assert patrimonio[cb.RESULTADO_DEL_ANIO] == (D(19_450), D(18_500))
    assert "Préstamo a amigo ficticio" not in {r.nombre for r in s.renglones}    # en ceros: no aparece
    assert s.grupos(cb.ACTIVO) == [cb.EFECTIVO_Y_BANCOS, cb.INVERSIONES]


def test_estado_de_resultados_separa_el_dia_a_dia_de_las_inversiones(libro, datos):
    r = cb.resultados(libro, [ESTE_ANIO, ANIO_PASADO])
    assert r.total_ingresos() == (D(20_000), D(20_000)) and r.total_gastos() == (D(700), D(1_500))
    assert r.dia_a_dia() == (D(19_300), D(18_500))
    assert r.rendimientos_inversion == (D(150), D(0))              # el ajuste al valor oficial, aparte
    assert r.resultado() == (D(19_450), D(18_500))                 # igual al «Resultado del año» del balance
    assert [(x.grupo, x.nombre) for x in r.gastos] == [("ALIMENTACION", "ALIMENTOS")]


def test_flujo_de_efectivo_metodo_directo(libro, datos):
    f = cb.flujo(libro, [ESTE_ANIO, ANIO_PASADO])
    assert f.cuadra and f.inicial == (D(28_500), D(0)) and f.final == (D(43_500), D(28_500))
    lineas = {(r.naturaleza, r.nombre): r.importes for r in f.renglones}
    assert lineas[(cb.DIA_A_DIA, "Cobraste: SUELDO Y PRESTACIONES")] == (D(20_000), D(20_000))
    assert lineas[(cb.FLUJO_INVERSIONES, "Inversión Ficticia")] == (D(-5_000), D(0))
    assert lineas[(cb.FLUJO_TARJETAS, "Tarjeta Ficticia")] == (D(0), D(-1_500))   # el gasto salió al pagar
    assert lineas[(cb.FLUJO_AJUSTES, "Saldo inicial de cuentas nuevas")] == (D(0), D(10_000))
    assert (cb.FLUJO_POR_COBRAR, "Préstamo a amigo ficticio") not in lineas        # se prestó y se cobró
    assert f.gasto_con_tarjeta == (D(700), D(1_500))                 # gasto que aún no era salida de efectivo
    assert f.cuentas == ["Ahorro Ficticio", "Banco Ficticio Débito"]


def test_balanza_sumas_iguales_y_cuenta_por_cobrar_compensada(libro, datos):
    b = cb.balanza(libro, *ESTE_ANIO)
    assert b.cuadra and b.por_categoria().cuadra
    s = b.sumas()
    assert s["inicial_deudor"] == s["inicial_acreedor"] == D(28_500)
    assert s["debe"] == s["haber"] == D(27_450)
    filas = {c.nombre: c for c in b.cuentas}
    prestamo = filas["Préstamo a amigo ficticio"]
    assert (prestamo.debe, prestamo.haber, prestamo.final) == (D(800), D(800), D(0))
    assert prestamo.lectura == "En ceros: compensada ✓" and prestamo.origen_aplicacion == ""
    debito = filas["Banco Ficticio Débito"]
    assert (debito.inicial, debito.final, debito.variacion) == (D(28_500), D(43_500), D(15_000))
    assert debito.origen_aplicacion == "Aplicación" and debito.lectura == "Tienes más"
    tarjeta = filas["Tarjeta Ficticia"]
    assert (tarjeta.final, tarjeta.variacion, tarjeta.origen_aplicacion) == (D(-700), D(700), "Origen")
    assert tarjeta.lectura == "Debes más"
    assert filas[cb.RESULTADOS_PREVIOS].inicial == D(-18_500)       # lo ganado antes, en el patrimonio
    assert filas["SUELDO Y PRESTACIONES › NOMINA"].inicial == 0      # resultados empiezan en ceros
    assert {c.nombre for c in b.por_categoria().cuentas} >= {"SUELDO Y PRESTACIONES", "ALIMENTACION"}


def test_balanza_comparada_con_otro_periodo(libro, datos):
    actual = cb.balanza(libro, *ESTE_ANIO)
    anterior = cb.balanza(libro, date(2025, 1, 1), date(2025, 12, 31))
    comparadas = cb.comparar_balanzas(actual, anterior)
    filas = {x.cuenta.nombre: x for x in comparadas}
    debito = filas["Banco Ficticio Débito"]
    assert debito.anterior == D(28_500) and debito.diferencia == D(15_000)   # saldo final 2025 → hoy
    tarjeta = filas["Tarjeta Ficticia"]
    assert tarjeta.cuenta.natural == D(700) and tarjeta.diferencia == tarjeta.cuenta.natural - tarjeta.anterior
    # Una cuenta que solo tuvo movimientos en el otro periodo aparece en ceros, con su saldo de allá.
    solo_alla = [x for x in comparadas if not (x.cuenta.inicial or x.cuenta.debe or x.cuenta.haber)]
    assert all(x.cuenta.lectura == "Sin movimientos en este periodo" for x in solo_alla)
    assert {x.cuenta.nombre for x in comparadas} >= {c.nombre for c in actual.cuentas}
    assert {x.cuenta.nombre for x in comparadas} >= {c.nombre for c in anterior.cuentas}
    naturalezas = [x.cuenta.naturaleza for x in comparadas]
    assert naturalezas == sorted(naturalezas, key=[cb.ACTIVO, cb.PASIVO, cb.PATRIMONIO, cb.INGRESO, cb.GASTO].index)


def test_un_movimiento_corregido_cambia_todos_los_reportes(libro, datos, ctas, cat):
    op = movimientos.registrar_gasto(libro, date(2026, 5, 1), ctas.debito, cat("ALIMENTOS"), 300, "Ficticio")
    assert cb.resultados(libro, [ESTE_ANIO]).total_gastos() == (D(1_000),)
    libro.eliminar_operacion(op.id)
    assert cb.resultados(libro, [ESTE_ANIO]).total_gastos() == (D(700),)
    assert cb.situacion(libro, [ESTE_ANIO[1]]).cuadra and cb.balanza(libro, *ESTE_ANIO).cuadra


def test_libro_vacio(libro):
    assert cb.situacion(libro, [date(2026, 7, 20)]).cuadra
    assert cb.balanza(libro, *ESTE_ANIO).cuadra and cb.flujo(libro, [ESTE_ANIO]).cuadra


def test_periodos_y_comparativos():
    hoy = date(2026, 7, 20)
    assert cb.periodo("anio", hoy) == (date(2026, 1, 1), hoy)
    assert cb.periodo("anio_pasado", hoy) == ANIO_PASADO
    assert cb.periodo("mes_pasado", hoy) == (date(2026, 6, 1), date(2026, 6, 30))
    assert cb.periodo("12m", hoy) == (date(2025, 7, 21), hoy)
    assert cb.periodo("rango", hoy, (date(2026, 3, 1), date(2026, 2, 1))) == (date(2026, 2, 1), date(2026, 3, 1))
    assert cb.comparativo(*ANIO_PASADO, "anio_anterior") == (date(2024, 1, 1), date(2024, 12, 31))
    assert cb.comparativo(date(2026, 6, 1), date(2026, 6, 30), "anterior") == (date(2026, 5, 1), date(2026, 5, 31))
    assert cb.comparativo(*ANIO_PASADO, "no") is None
    assert cb.comparativo(date(2028, 2, 29), date(2028, 2, 29), "anio_anterior") == (date(2027, 2, 28),) * 2
