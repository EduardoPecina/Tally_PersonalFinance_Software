"""Ingresos: quincenas distintas, pagos que se adelantan por el fin de semana y cuánto tiene que durarte cada pago.
Solo datos ficticios."""

from datetime import date

import pytest

from conftest import D
from motor import cuentas, ingresos, movimientos, planeacion, recurrentes
from motor.errores import ErrorValidacion
from motor.serializacion import instantanea, libro_desde_instantanea


def nomina(libro, ctas, cat, **extra):
    datos = dict(monto_2="5,000.56", fin_de_semana="antes", inicio=date(2026, 1, 1), es_principal=True)
    datos.update(extra)
    return ingresos.guardar(libro, "Nómina Ficticia", cat("NOMINA"), "5,000.73", ctas.debito, "quincenal", **datos)


def test_quincenas_distintas_y_fin_de_semana(libro, ctas, cat):
    r = nomina(libro, ctas, cat)
    assert (r.monto, r.monto_2, r.fin_de_semana) == (500_073, 500_056, "antes")
    # El 15 de marzo de 2026 es domingo: te pagan el viernes 13. El 31 es martes.
    assert recurrentes.fechas(r, date(2026, 3, 1), date(2026, 3, 31)) == [date(2026, 3, 13), date(2026, 3, 31)]
    assert recurrentes.fechas(r, date(2026, 2, 1), date(2026, 2, 28)) == [date(2026, 2, 13), date(2026, 2, 27)]
    assert [recurrentes.quincena(r, d) for d in (date(2026, 3, 13), date(2026, 3, 31), date(2026, 2, 27))] == [1, 2, 2]
    assert recurrentes.monto_en(r, date(2026, 3, 13)) == 500_073
    assert recurrentes.monto_en(r, date(2026, 3, 31)) == 500_056
    assert recurrentes.al_mes(r) == D("10001.29")
    despues = recurrentes.editar(libro, r.id, fin_de_semana="despues")
    # La del sábado 28 de febrero se pasa al lunes 2 de marzo.
    assert recurrentes.fechas(despues, date(2026, 3, 1), date(2026, 3, 31)) == [
        date(2026, 3, 2), date(2026, 3, 16), date(2026, 3, 31)]
    assert recurrentes.quincena(despues, date(2026, 3, 2)) == 2
    igual = recurrentes.editar(libro, r.id, fin_de_semana="")
    assert recurrentes.fechas(igual, date(2026, 3, 1), date(2026, 3, 31)) == [date(2026, 3, 15), date(2026, 3, 31)]
    assert libro_desde_instantanea(instantanea(libro)).recurrente(r.id) == igual


def test_cuanto_tiene_que_durar_cada_quincena(libro, ctas, cat):
    r = nomina(libro, ctas, cat)
    lista = ingresos.periodos(r, date(2026, 3, 5), n=4)
    assert [(p.pago, p.hasta, p.dias, p.quincena) for p in lista] == [
        (date(2026, 2, 27), date(2026, 3, 12), 14, 2),
        (date(2026, 3, 13), date(2026, 3, 30), 18, 1),      # 1 semana hábil más que la anterior
        (date(2026, 3, 31), date(2026, 4, 14), 15, 2),
        (date(2026, 4, 15), date(2026, 4, 29), 15, 1),
    ]
    largo = lista[1]
    assert largo.largo and largo.dias_de_mas == 3 and largo.por_dia == D("277.82")
    assert lista[0].monto == D("5000.56") and not lista[0].largo and not lista[2].largo


def test_hasta_tu_proximo_pago(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 10_000, date(2026, 1, 1))
    nomina(libro, ctas, cat)
    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, cat("NOMINA"), "5000.73", "Nómina")
    recurrentes.crear(libro, "Renta Ficticia", "gasto", 3_000, ctas.debito, "mensual", date(2026, 1, 25),
                      categoria_id=cat("RENTA"))
    h = ingresos.hasta_el_proximo_pago(libro)                       # hoy: lunes 20/07/2026
    assert (h.proximo, h.dias, h.monto) == (date(2026, 7, 31), 11, D("5000.56"))
    assert (h.disponible, h.queda, h.compromisos, h.por_dia) == (D("15000.73"), D("12000.73"), D(3000), D("1090.98"))


def test_sin_ingreso_principal_no_hay_proximo_pago(libro):
    assert ingresos.principal(libro) is None and ingresos.hasta_el_proximo_pago(libro) is None


def test_guardar_marca_principal_y_secundarios(libro, ctas, cat):
    r = nomina(libro, ctas, cat)
    assert ingresos.principal(libro) == r and libro.categoria(cat("NOMINA")).principal
    renta = ingresos.guardar(libro, "", cat("RENTAS COBRADAS"), 2_000, ctas.debito, "mensual",
                             inicio=date(2026, 7, 1), monto_2=999)
    assert renta.nombre == "RENTAS COBRADAS" and renta.monto_2 is None        # solo la quincena tiene 2.ª
    assert libro.categoria(cat("RENTAS COBRADAS")).secundario
    assert [x.id for x in ingresos.fijos(libro)] == [r.id, renta.id]
    # Sin meses completos registrados, el ingreso esperado es lo configurado.
    esperado = planeacion.ingreso_esperado(libro)
    assert (esperado.monto, esperado.fuente) == (D("12001.29"), "configurado")
    # Cambiar el principal a otra subcategoría desmarca la anterior.
    ingresos.guardar(libro, "Honorarios", cat("HONORARIOS"), 9_000, ctas.debito, "mensual", es_principal=True,
                     inicio=date(2026, 7, 1))
    assert not libro.categoria(cat("NOMINA")).principal and libro.categoria(cat("HONORARIOS")).principal


def test_validaciones(libro, ctas, cat):
    with pytest.raises(ErrorValidacion, match="fin de semana"):
        nomina(libro, ctas, cat, fin_de_semana="domingo")
    with pytest.raises(ErrorValidacion, match="subcategoría de ingreso"):
        ingresos.guardar(libro, "X", None, 100, ctas.debito, "quincenal")
    r = nomina(libro, ctas, cat, monto_2="5000.73")
    assert r.monto_2 is None                                       # igual a la 1.ª: no hace falta


def test_calendario_y_registrar_usan_el_importe_de_cada_quincena(libro, ctas, cat):
    r = nomina(libro, ctas, cat)
    eventos = [e for e in recurrentes.calendario(libro, date(2026, 7, 20)) if e.recurrente_id == r.id]
    assert [(e.fecha, e.centavos) for e in eventos] == [(date(2026, 7, 15), 500_073), (date(2026, 7, 31), 500_056),
                                                         (date(2026, 8, 14), 500_073)]     # 15/08 es sábado
    op = recurrentes.registrar(libro, r.id, date(2026, 7, 31))
    assert sum(p.importe for p in op.partidas if p.cuenta_id == ctas.debito) == 500_056


def test_el_primer_mes_a_medias_no_se_promedia(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 3_000, date(2026, 1, 1))
    nomina(libro, ctas, cat)
    movimientos.registrar_ingreso(libro, date(2026, 6, 30), ctas.debito, cat("NOMINA"), "5000.56", "Nómina")
    esperado = planeacion.ingreso_esperado(libro)              # junio está a medias: aún no hay meses completos
    assert (esperado.monto, esperado.fuente) == (D("10001.29"), "configurado")


def test_el_nombre_de_tu_ingreso_principal(libro, ctas, cat):
    assert ingresos.nombre_principal(libro) == "NOMINA"                  # la subcategoría marcada (catálogo)
    nomina(libro, ctas, cat)
    assert ingresos.nombre_principal(libro) == "Nómina Ficticia"         # el nombre que le pusiste en Ingresos
    ingresos.guardar(libro, "Honorarios Ficticios", cat("HONORARIOS"), 9_000, ctas.debito, "mensual",
                     inicio=date(2026, 1, 1), es_principal=True)
    assert ingresos.nombre_principal(libro) == "Honorarios Ficticios"   # una persona independiente
