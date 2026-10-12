"""Impuestos para cualquier país: deducibles y cálculo/revisión de recibos. Solo datos ficticios."""

from datetime import date
from decimal import Decimal

import pytest

from conftest import D
from motor import cuentas, impuestos, movimientos
from motor.errores import ErrorValidacion
from motor.modelo import Impuesto, PerfilImpuestos
from motor.serializacion import instantanea, libro_desde_instantanea


DOS_TERCIOS = Decimal(2) / Decimal(3) * 100
HONORARIOS = "Honorarios ficticios (régimen general)"
RESICO = "Honorarios ficticios en RESICO"
PERFILES = {          # los ejemplos de la página, armados a mano como lo haría el usuario
    HONORARIOS: (Impuesto("IVA", D(16)), Impuesto("Retención ISR", D(10), retenido=True),
                 Impuesto("Retención IVA", DOS_TERCIOS, "IVA", retenido=True)),
    RESICO: (Impuesto("IVA", D(16)), Impuesto("Retención ISR", D("1.25"), retenido=True),
             Impuesto("Retención IVA", DOS_TERCIOS, "IVA", retenido=True)),
    "Venta con IVA": (Impuesto("IVA", D(16)),),
    "Autónomo (IVA 21 % e IRPF 15 %)": (Impuesto("IVA", D(21)), Impuesto("IRPF", D(15), retenido=True)),
    "IVA 19 %": (Impuesto("IVA", D(19)),),
    "Servicios con ReteIVA": (Impuesto("IVA", D(19)), Impuesto("Retención en la fuente", D(11), retenido=True),
                              Impuesto("ReteIVA", D(15), "IVA", retenido=True)),
}


def perfil(nombre):
    return PerfilImpuestos("x", nombre, PERFILES[nombre])


# ------------------------------------------------------------------ calcular y revisar


def test_calcular_honorarios_mexico():
    d = impuestos.calcular(perfil(HONORARIOS), 10_000)
    assert [(i.nombre, v) for i, v in d.lineas] == [
        ("IVA", D("1600.00")), ("Retención ISR", D("1000.00")), ("Retención IVA", D("1066.67"))]
    assert (d.trasladados, d.retenidos, d.total) == (D(1600), D("2066.67"), D("9533.33"))
    assert impuestos.calcular(perfil(RESICO), 10_000).total == D("10408.33")    # ISR 1.25 %


@pytest.mark.parametrize("nombre", list(PERFILES))
@pytest.mark.parametrize("subtotal", ["10000", "1234.56", "99.99", "87654.32", "0.50"])
def test_desde_lo_que_recibes_vuelve_al_mismo_subtotal(nombre, subtotal):
    p = perfil(nombre)
    d = impuestos.calcular(p, Decimal(subtotal))
    de_vuelta = impuestos.desde_total(p, d.total)
    assert de_vuelta.total == d.total and abs(de_vuelta.subtotal - d.subtotal) <= D("0.01")


def test_espana_y_otro_pais():
    d = impuestos.calcular(perfil("Autónomo (IVA 21 % e IRPF 15 %)"), 1_000)
    assert d.total == D(1060)
    assert impuestos.calcular(perfil("IVA 19 %"), 1_000).total == D(1190)
    assert impuestos.calcular(perfil("Servicios con ReteIVA"), 1_000).total == D("1051.50")    # 1000+190−110−28.50


def test_revisar_un_recibo():
    p = perfil(HONORARIOS)
    assert impuestos.revisar(p, 10_000, {"IVA": 1600, "Retención ISR": 1000, "Retención IVA": "1066.66"}) == []
    problemas = impuestos.revisar(p, 10_000, {"IVA": 0, "Retención ISR": 1000, "Retención IVA": 1600})
    assert problemas[0] == "No cuadra (diferencia total $2,133.33)"
    assert "IVA: dice $0.00, debería ser $1,600.00 (16 % del subtotal)" in problemas
    assert "Retención IVA: dice $1,600.00, debería ser $1,066.67 (2/3 (66.67 %) de IVA)" in problemas
    assert any("trae Retención IVA pero no IVA" in x for x in problemas)
    # Con RESICO, una retención de ISR del 10 % no cuadra.
    assert impuestos.revisar(perfil(RESICO), 10_000, {"IVA": 1600, "Retención ISR": 1000,
                                                      "Retención IVA": "1066.67"})[1].startswith("Retención ISR")


@pytest.mark.parametrize("texto, tasa", [("16", D(16)), ("16 %", D(16)), ("1,25", D("1.25")),
                                         ("2/3", D("66.6666666667"))])
def test_tasas(texto, tasa):
    assert impuestos.leer_tasa(texto) == tasa


def test_tasas_invalidas():
    for texto in ("abc", "150", "-1", "1/0"):
        with pytest.raises(ErrorValidacion):
            impuestos.leer_tasa(texto)


# ------------------------------------------------------------------ perfiles


def test_perfiles_personalizados_y_guardados(libro):
    p = impuestos.guardar_perfil(libro, "Mi país ficticio", [
        {"nombre": "Impuesto al consumo", "tasa": "12"},
        {"nombre": "Retención sobre el impuesto", "tasa": "1/3", "sobre": "Impuesto al consumo", "retenido": True},
    ])
    assert impuestos.calcular(p, 100).total == D(108)
    with pytest.raises(ErrorValidacion, match="debe ir antes"):
        impuestos.guardar_perfil(libro, "Mal orden", [
            Impuesto("B", D(1), "A"), Impuesto("A", D(10))])
    with pytest.raises(ErrorValidacion, match="dos veces"):
        impuestos.guardar_perfil(libro, "Repetido", [Impuesto("A", D(1)), Impuesto("a", D(2))])
    with pytest.raises(ErrorValidacion, match="al menos un impuesto"):
        impuestos.guardar_perfil(libro, "Vacío", [{"nombre": " ", "tasa": 1}])
    copia = impuestos.guardar_perfil(libro, "Copia", PERFILES[HONORARIOS])
    with pytest.raises(ErrorValidacion, match="Ya tienes un perfil"):
        impuestos.guardar_perfil(libro, "COPIA", PERFILES[RESICO])
    editado = impuestos.guardar_perfil(libro, "Copia editada", PERFILES[RESICO], perfil_id=copia.id)
    assert [x.nombre for x in libro.fiscal.perfiles] == ["Mi país ficticio", "Copia editada"]
    assert editado.impuestos[1].tasa == D("1.25")
    assert libro_desde_instantanea(instantanea(libro)).fiscal == libro.fiscal
    impuestos.eliminar_perfil(libro, copia.id)
    assert [x.nombre for x in libro.fiscal.perfiles] == ["Mi país ficticio"]


# ------------------------------------------------------------------ deducibles


def test_deducibles_con_porcentaje_topes_y_efectivo(libro, ctas, cat):
    efectivo = cuentas.crear(libro, "Cartera Ficticia", "efectivo", fecha_creacion=date(2026, 1, 1)).id
    movimientos.registrar_ingreso(libro, date(2026, 1, 15), ctas.debito, cat("NOMINA"), 100_000)
    movimientos.registrar_gasto(libro, date(2026, 2, 3), ctas.debito, cat("DENTISTA"), 4_000, "Consultorio")
    movimientos.registrar_gasto(libro, date(2026, 3, 3), efectivo, cat("CONSULTAS MEDICAS"), 1_000, "En efectivo")
    movimientos.registrar_reembolso(libro, date(2026, 3, 9), ctas.debito, cat("DENTISTA"), 500, "Devolución")
    movimientos.registrar_gasto(libro, date(2026, 4, 3), ctas.credito, cat("LENTES Y OPTICA"), 3_100, "Lentes")
    movimientos.registrar_gasto(libro, date(2025, 12, 3), ctas.debito, cat("DENTISTA"), 9_999, "Otro año")
    medicos = impuestos.guardar_concepto(libro, "Médicos", [cat("DENTISTA"), cat("CONSULTAS MEDICAS")],
                                         sin_efectivo=True)
    impuestos.guardar_concepto(libro, "Lentes", [cat("LENTES Y OPTICA")], tope=2_500, sin_efectivo=True)
    impuestos.guardar_concepto(libro, "Médicos al 40 %", [cat("DENTISTA")], porcentaje=40)
    r = impuestos.deducibles(libro, 2026)
    resumen = {x.concepto.nombre: (x.pagado, x.en_efectivo, x.considerado, x.deducible) for x in r.renglones}
    assert resumen == {"Médicos": (D(4_500), D(1_000), D(3_500), D(3_500)),
                       "Lentes": (D(3_100), D(0), D(3_100), D(2_500)),
                       "Médicos al 40 %": (D(3_500), D(0), D(1_400), D(1_400))}
    assert r.suma == D(7_400) and r.ingreso == D(100_000) and r.tope is None and r.total == D(7_400)
    assert [p.importe for p in r.renglones[0].pagos] == [D(4_000), D(1_000), D(-500)]
    impuestos.ajustar_topes(libro, tope_porcentaje=5)
    assert impuestos.deducibles(libro, 2026).total == D(5_000)
    impuestos.ajustar_topes(libro, tope_total=4_000, tope_porcentaje=5)
    assert impuestos.deducibles(libro, 2026).tope == D(4_000)
    impuestos.ajustar_topes(libro)
    assert impuestos.deducibles(libro, 2026, ingreso=D(1)).tope is None
    # Editar sin perder el lugar en la lista.
    impuestos.guardar_concepto(libro, "Médicos y dentistas", [cat("DENTISTA")], concepto_id=medicos.id)
    assert libro.fiscal.conceptos[0].nombre == "Médicos y dentistas"
    impuestos.eliminar_concepto(libro, medicos.id)
    assert len(libro.fiscal.conceptos) == 2


def test_validaciones_de_conceptos(libro, cat):
    with pytest.raises(ErrorValidacion, match="al menos una"):
        impuestos.guardar_concepto(libro, "Nada", [])
    with pytest.raises(ErrorValidacion, match="no es una subcategoría de gasto"):
        impuestos.guardar_concepto(libro, "Sueldo", [cat("NOMINA")])
    with pytest.raises(ErrorValidacion, match="mayor que cero"):
        impuestos.guardar_concepto(libro, "Cero", [cat("DENTISTA")], porcentaje=0)
    impuestos.guardar_concepto(libro, "Médicos", [cat("DENTISTA")])
    with pytest.raises(ErrorValidacion, match="Ya tienes un concepto"):
        impuestos.guardar_concepto(libro, "MÉDICOS", [cat("DENTISTA")])


def test_borrar_todos_los_deducibles_y_notas(libro, cat):
    impuestos.guardar_concepto(libro, "Médicos", [cat("DENTISTA")])
    impuestos.ajustar_topes(libro, tope_porcentaje=15)
    impuestos.ajustar_notas(libro, "  Revisar topes del año  ")
    assert libro.fiscal.notas == "Revisar topes del año"
    impuestos.quitar_deducibles(libro)
    assert (libro.fiscal.conceptos, libro.fiscal.tope_porcentaje, libro.fiscal.notas) == ((), None, "")


def test_conceptos_fuera_del_tope_total(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 1, 15), ctas.debito, cat("NOMINA"), 10_000)
    movimientos.registrar_gasto(libro, date(2026, 2, 3), ctas.debito, cat("DENTISTA"), 4_000)
    movimientos.registrar_gasto(libro, date(2026, 2, 5), ctas.debito, cat("COLEGIATURAS"), 3_000)
    impuestos.guardar_concepto(libro, "Médicos", [cat("DENTISTA")], sin_efectivo=True)
    impuestos.guardar_concepto(libro, "Colegiaturas", [cat("COLEGIATURAS")], fuera_del_tope=True)
    impuestos.ajustar_topes(libro, tope_porcentaje=15)
    r = impuestos.deducibles(libro, 2026)
    assert r.tope == D(1_500) and r.fuera_del_tope == D(3_000)
    assert r.total == D(1_500) + D(3_000)              # el 15 % topa a los médicos, no a la colegiatura
    assert libro_desde_instantanea(instantanea(libro)).fiscal == libro.fiscal


# ===================================================================== lo que pagas tú y los pagos al fisco

RESICO_A_PERSONAS = (Impuesto("ISR", D("1.25"), a_cargo=True), Impuesto("IVA", D(16)))
RESICO_A_EMPRESAS = (Impuesto("IVA", D(16)), Impuesto("ISR", D("1.25"), a_cargo=True),
                     Impuesto("Retención ISR", D("1.25"), retenido=True),
                     Impuesto("Retención IVA", DOS_TERCIOS, "IVA", retenido=True))


def test_lo_que_pagas_tu_no_cambia_el_recibo():
    perfil = PerfilImpuestos("p", "RESICO ficticio", RESICO_A_PERSONAS)
    d = impuestos.calcular(perfil, 6_000)
    assert (d.total, d.trasladados, d.a_cargo, d.retenidos) == (D("6960.00"), D("960.00"), D("75.00"), D(0))
    assert impuestos.desde_total(perfil, 6_960).subtotal == D("6000.00")
    assert impuestos.revisar(perfil, 6_000, {"IVA": D(960)}) == []          # el ISR no viene en el recibo


def test_un_impuesto_no_es_retenido_y_a_tu_cargo(libro):
    with pytest.raises(ErrorValidacion, match="a la vez"):
        impuestos.guardar_perfil(libro, "Raro", [{"nombre": "ISR", "tasa": "1", "retenido": True, "a_cargo": True}])


@pytest.mark.parametrize("frecuencia, dia, meses_despues, dia_limite, esperado", [
    ("mensual", date(2026, 10, 12), 1, 17, (date(2026, 10, 1), date(2026, 10, 31), date(2026, 11, 17))),
    ("bimestral", date(2026, 10, 12), 1, 17, (date(2026, 9, 1), date(2026, 10, 31), date(2026, 11, 17))),
    ("trimestral", date(2026, 2, 3), 1, 20, (date(2026, 1, 1), date(2026, 3, 31), date(2026, 4, 20))),
    ("anual", date(2026, 10, 12), 4, 30, (date(2026, 1, 1), date(2026, 12, 31), date(2027, 4, 30))),
    ("mensual", date(2026, 1, 20), 1, 31, (date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 28))),
])
def test_periodo_y_fecha_limite(frecuencia, dia, meses_despues, dia_limite, esperado):
    perfil = PerfilImpuestos("p", "Ficticio", (), frecuencia=frecuencia, dia_limite=dia_limite,
                             meses_despues=meses_despues)
    desde, hasta = impuestos.periodo(perfil, dia)
    assert (desde, hasta, impuestos.limite(perfil, hasta)) == esperado


@pytest.fixture
def honorarios(libro, ctas, cat):
    """Dos cobros ficticios de octubre, registrados con lo que llega a la cuenta (subtotal + IVA)."""
    for dia in (10, 25):
        movimientos.registrar_ingreso(libro, date(2026, 10, dia), ctas.debito, cat("HONORARIOS"), 6_960,
                                      "Cliente ficticio")
    return impuestos.guardar_perfil(libro, "RESICO ficticio", RESICO_A_PERSONAS, frecuencia="mensual",
                                    subcategorias=[cat("HONORARIOS")], registro="recibido")


def test_cuanto_pagar_al_fisco_por_lo_que_cobraste(libro, honorarios):
    pago = impuestos.pago_del_periodo(libro, honorarios, date(2026, 10, 1), date(2026, 10, 31))
    assert (pago.cobrado, pago.base, pago.limite, pago.estimado) == (D(13_920), D(12_000), date(2026, 11, 17), False)
    assert [(i.nombre, i.a_pagar) for i in pago.impuestos] == [("ISR", D(150)), ("IVA", D(1_920))]
    assert pago.total == D(2_070)
    vacio = impuestos.pago_del_periodo(libro, honorarios, date(2026, 9, 1), date(2026, 9, 30))
    assert vacio.total == 0 and not vacio.estimado


def test_las_retenciones_se_restan_de_su_mismo_impuesto(libro, cat):
    a_empresas = impuestos.guardar_perfil(libro, "RESICO a empresas", RESICO_A_EMPRESAS, frecuencia="mensual",
                                          subcategorias=[cat("HONORARIOS")], registro="subtotal")
    movimientos.registrar_ingreso(libro, date(2026, 10, 5), cuentas.crear(libro, "Banco 2", "debito").id,
                                  cat("HONORARIOS"), 10_000, "Factura ficticia")
    pago = impuestos.pago_del_periodo(libro, a_empresas, date(2026, 10, 1), date(2026, 10, 31))
    assert {i.nombre: (i.causado, i.retenido, i.a_pagar) for i in pago.impuestos} == {
        "IVA": (D(1_600), D("1066.67"), D("533.33")), "ISR": (D(125), D(125), D(0))}
    assert pago.total == D("533.33") and pago.otras_retenciones == 0
    # Sin el renglón de ISR a tu cargo, la retención de ISR no se resta del IVA: ya se pagó por ti.
    sin_isr = impuestos.guardar_perfil(libro, "Sin ISR", PERFILES[RESICO], frecuencia="mensual",
                                       subcategorias=[cat("HONORARIOS")], registro="subtotal")
    pago = impuestos.pago_del_periodo(libro, sin_isr, date(2026, 10, 1), date(2026, 10, 31))
    assert pago.total == D("533.33") and pago.otras_retenciones == D(125)


def test_sin_ingresos_registrados_usa_tu_calendario(libro, ctas, cat):
    from motor import recurrentes

    recurrentes.crear(libro, "Honorarios ficticios", "ingreso", 6_000, ctas.debito, "quincenal", date(2026, 1, 15),
                      categoria_id=cat("HONORARIOS"))
    perfil = impuestos.guardar_perfil(libro, "Estimado", RESICO_A_PERSONAS, frecuencia="mensual",
                                      subcategorias=[cat("HONORARIOS")], registro="subtotal")
    pago = impuestos.pago_del_periodo(libro, perfil, date(2026, 10, 1), date(2026, 10, 31))
    assert pago.estimado and pago.base == D(12_000) and pago.total == D(150 + 1_920)


def test_el_recordatorio_va_desde_que_termina_el_periodo_hasta_que_lo_pagas(libro, honorarios):
    assert impuestos.por_pagar(libro, date(2026, 10, 20)) == []                # octubre va en curso
    (pago,) = impuestos.por_pagar(libro, date(2026, 11, 5))
    assert (pago.total, pago.estado(date(2026, 11, 5))) == (D(2_070), impuestos.PENDIENTE)
    assert pago.estado(date(2026, 11, 18)) == impuestos.VENCIDO
    assert impuestos.por_pagar(libro, date(2026, 12, 18)) == []                # 30 días después de la fecha límite
    impuestos.marcar_pagado(libro, pago.clave)
    assert impuestos.por_pagar(libro, date(2026, 11, 5)) == []
    assert impuestos.pagos_al_fisco(libro, honorarios, date(2026, 11, 5))[1].estado(date(2026, 11, 5)) == \
        impuestos.PAGADO
    impuestos.marcar_pagado(libro, pago.clave, False)
    assert len(impuestos.por_pagar(libro, date(2026, 11, 5))) == 1
    assert len(libro.operaciones()) == 2                                       # no registró nada solo
    septiembre = impuestos.pagos_al_fisco(libro, honorarios, date(2026, 11, 5))[2]
    assert (septiembre.total, septiembre.estado(date(2026, 11, 5))) == (0, impuestos.SIN_PAGO)   # no cobró nada


def test_no_recuerda_pagos_que_vencieron_antes_de_configurarlo(libro, honorarios, cat):
    from dataclasses import replace

    tarde = replace(honorarios, recordatorio_desde=date(2026, 11, 20))         # lo configuraste después del 17
    libro.fiscal = replace(libro.fiscal, perfiles=(tarde,))
    assert impuestos.por_pagar(libro, date(2026, 11, 25)) == []
    editado = impuestos.guardar_perfil(libro, "RESICO ficticio", RESICO_A_PERSONAS, frecuencia="mensual",
                                       subcategorias=[cat("HONORARIOS")], perfil_id=tarde.id)
    assert editado.recordatorio_desde == date(2026, 11, 20)                    # editarlo no lo reinicia


def test_validaciones_del_recordatorio(libro, cat):
    with pytest.raises(ErrorValidacion, match="sobre qué ingresos"):
        impuestos.guardar_perfil(libro, "Sin ingresos", RESICO_A_PERSONAS, frecuencia="mensual")
    with pytest.raises(ErrorValidacion, match="subcategorías de ingreso"):
        impuestos.guardar_perfil(libro, "Con un gasto", RESICO_A_PERSONAS, frecuencia="mensual",
                                 subcategorias=[cat("ALIMENTOS")])
    with pytest.raises(ErrorValidacion, match="del 1 al 31"):
        impuestos.guardar_perfil(libro, "Día raro", RESICO_A_PERSONAS, frecuencia="mensual",
                                 subcategorias=[cat("HONORARIOS")], dia_limite=40)
    sin = impuestos.guardar_perfil(libro, "Sin recordatorio", RESICO_A_PERSONAS)
    assert sin.recordatorio_desde is None and impuestos.pagos_al_fisco(libro, sin, date(2026, 11, 5)) == []


def test_el_recordatorio_se_guarda_y_sigue_a_su_subcategoria(libro, honorarios, cat):
    from motor import categorias

    impuestos.marcar_pagado(libro, f"{honorarios.id}:2026-10")
    copia = libro_desde_instantanea(instantanea(libro))
    assert copia.fiscal == libro.fiscal
    categorias.eliminar(libro, cat("HONORARIOS"), reasignar_a=cat("FREELANCE"))
    assert libro.fiscal.perfiles[0].subcategorias == (cat("FREELANCE"),)
