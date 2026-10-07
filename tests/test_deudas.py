"""Préstamos, pago mínimo de tarjetas y planeación (ingresos, capacidad, presupuestos). Solo datos ficticios."""

from datetime import date
from decimal import Decimal

import pytest

from conftest import D
from motor import (
    bienes,
    contabilidad,
    cuentas,
    movimientos,
    perfil,
    planeacion,
    prestamos,
    reportes,
    tarjetas,
)
from motor.errores import ErrorValidacion
from motor.modelo import TipoOperacion
from motor.serializacion import instantanea, libro_desde_instantanea

INICIO = date(2026, 1, 15)


@pytest.fixture
def debito(libro, ctas):
    perfil.configurar(libro, "Usuario Ficticio")
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 50_000, date(2025, 12, 1))
    return ctas.debito


def _personal(libro, debito, **extra):
    return prestamos.crear(libro, "Préstamo Ficticio", "personal", 100_000, 24, 24, INICIO, destino=debito, **extra)


# ------------------------------------------------------------------ préstamos


def test_contratar_un_prestamo_y_su_tabla(libro, debito):
    p = _personal(libro, debito, comision_apertura=2_000)
    assert cuentas.saldo(libro, debito) == D(148_000)                       # recibiste el monto menos la comisión
    assert cuentas.saldo(libro, p.cuenta_id) == D(-100_000)                 # debes el monto completo
    assert reportes.resumen(libro, INICIO, INICIO).gastos == D(2_000)       # la comisión es gasto
    assert prestamos.pago_mensual(libro, p) == D("5480.70")                 # 24 % anual + IVA 16 %, 24 meses
    tabla = prestamos.amortizacion(libro, p)
    assert len(tabla) == 24 and tabla[-1].saldo == 0
    assert (tabla[0].interes, tabla[0].iva) == (D(2_000), D(320))
    assert tabla[0].fecha == date(2026, 2, 15)


def test_un_pago_separa_capital_de_intereses_iva_y_cargos(libro, debito):
    p = _personal(libro, debito)
    ops = prestamos.registrar_pago(libro, p.cuenta_id, date(2026, 2, 15), 6_000, debito, interes=2_000, iva=320,
                                   cargos=150)
    assert [op.tipo for op in ops] == [TipoOperacion.GASTO, TipoOperacion.TRANSFERENCIA]
    assert cuentas.saldo(libro, p.cuenta_id) == D(-100_000 + 6_000 - 2_470)   # capital = 3,530
    assert cuentas.saldo(libro, debito) == D(144_000)
    gastos = {g.nombre: g.total for g in reportes.gastos_por_categoria(libro, INICIO, date(2026, 2, 28))}
    assert gastos == {prestamos.SUBCATEGORIA_INTERESES: D(2_320), prestamos.SUBCATEGORIA_CARGOS: D(150)}
    # Un abono extra a capital: sin intereses.
    (abono,) = prestamos.registrar_pago(libro, p.cuenta_id, date(2026, 2, 20), 1_000, debito, interes=0, iva=0)
    assert abono.tipo is TipoOperacion.TRANSFERENCIA
    with pytest.raises(ErrorValidacion, match="mayor que cero"):
        prestamos.registrar_pago(libro, p.cuenta_id, date(2026, 2, 20), 0, debito)


def test_si_pagas_menos_que_los_intereses_la_deuda_sube(libro, debito):
    p = _personal(libro, debito)
    prestamos.registrar_pago(libro, p.cuenta_id, date(2026, 2, 15), 1_000, debito)     # intereses estimados: 2,320
    assert cuentas.saldo(libro, p.cuenta_id) == D(-101_320)
    prestamos.registrar_cargo(libro, p.cuenta_id, date(2026, 3, 20), 350, descripcion="Mora ficticia")
    assert cuentas.saldo(libro, p.cuenta_id) == D(-101_670)
    e = prestamos.estado(libro, p.cuenta_id, date(2026, 3, 31))
    assert e.intereses_pagados == D(2_670) and e.pagado == D(1_000)


def test_simulador_y_recomendaciones(libro, debito):
    p = _personal(libro, debito)
    hoy = date(2026, 1, 20)
    base = prestamos.proyectar(libro, p.cuenta_id, hoy=hoy)
    assert base.meses == 24 and base.fin == date(2028, 1, 15)
    mas = prestamos.proyectar(libro, p.cuenta_id, extra_mensual=1_000, abono_unico=10_000, hoy=hoy)
    assert mas.meses < base.meses and mas.intereses < base.intereses
    nunca = prestamos.proyectar(libro, p.cuenta_id, pago=2_000, hoy=hoy)      # no cubre 2,320 de intereses
    assert not nunca.alcanza and nunca.meses is None
    assert prestamos.pago_para_terminar_en(libro, p.cuenta_id, 24, hoy) == prestamos.pago_mensual(libro, p)
    e = prestamos.estado(libro, p.cuenta_id, hoy)
    assert e.meses_contrato_restantes == 24 and e.proximo_pago == date(2026, 2, 15)
    assert [n for n, _ in e.sugerencias] == ["+10 % al mes", "+25 % al mes"]
    assert all(s.meses < base.meses for _, s in e.sugerencias)


def test_hipoteca_sin_iva_ya_existente_y_pago_pactado(libro, debito):
    h = prestamos.crear(libro, "Hipoteca Ficticia", "hipoteca", 1_000_000, 10, 240, date(2020, 1, 1),
                        deuda_actual=800_000, pago_pactado=10_500, dia_pago=5)
    assert prestamos.iva_de(libro, h) == 0
    assert cuentas.saldo(libro, h.cuenta_id) == D(-800_000)
    assert prestamos.pago_mensual(libro, h) == D(10_500)
    assert prestamos.estimar_interes(libro, h.cuenta_id) == (D("6666.67"), D(0))
    familiar = prestamos.crear(libro, "Préstamo de mi tía", "familiar", 12_000, 0, 12, date(2026, 6, 1),
                               destino=debito)
    assert prestamos.pago_mensual(libro, familiar) == D(1_000)


def test_credito_de_auto_directo_a_un_bien(libro, debito):
    # Enganche de 50,000 con tu débito y el crédito de 250,000 va directo a la agencia (al auto).
    auto = bienes.crear(libro, "Auto Ficticio", "auto", INICIO, 50_000, cuenta_pago=debito)
    p = prestamos.crear(libro, "Crédito Auto Ficticio", "auto", 250_000, 13, 48, INICIO, destino=auto.cuenta_id)
    assert bienes.valuar(libro, auto.cuenta_id, INICIO).costo == D(300_000)
    assert cuentas.saldo(libro, debito) == D(0)
    s = contabilidad.situacion(libro, [date(2026, 7, 20)])
    assert s.cuadra
    assert contabilidad.PRESTAMOS_LARGO in s.grupos(contabilidad.PASIVO)
    f = contabilidad.flujo(libro, [(INICIO, date(2026, 7, 20))])
    assert f.cuadra
    assert prestamos.estado(libro, p.cuenta_id).deuda == D(250_000)


def test_validaciones_y_respaldos(libro, debito):
    with pytest.raises(ErrorValidacion, match="tipo de préstamo"):
        prestamos.crear(libro, "X", "tarjeta", 1, 1, 1, INICIO)
    with pytest.raises(ErrorValidacion, match="plazo"):
        prestamos.crear(libro, "X", "personal", 1_000, 10, 0, INICIO)
    with pytest.raises(ErrorValidacion, match="comisión"):
        prestamos.crear(libro, "X", "personal", 1_000, 10, 12, INICIO, destino=debito, comision_apertura=1_000)
    p = _personal(libro, debito)
    prestamos.configurar(libro, p.cuenta_id, tasa_anual=18, pago_pactado=5_000, cat=30)
    copia = libro_desde_instantanea(instantanea(libro), libro.secuencia, reloj=libro.reloj)
    assert copia.prestamos() == libro.prestamos()
    assert copia.prestamo(p.cuenta_id).tasa_anual == 18


# ------------------------------------------------------------- tarjetas


def test_pago_minimo_estimado_de_una_tarjeta(libro, ctas, cat, debito):
    # Corte el día 3, línea de 1,000 (conftest). Debes 965 del corte del 3 de julio.
    movimientos.registrar_gasto(libro, date(2026, 6, 10), ctas.credito, cat("ALIMENTOS"), 965, "Compra ficticia")
    sin_tasa = tarjetas.pago_minimo_estimado(libro, ctas.credito)
    assert sin_tasa.minimo == D("14.48") and not sin_tasa.con_tasa             # 1.5 % de 965 (> 1.25 % de 1,000)
    assert sin_tasa.para_no_generar_intereses == D(965)
    cuentas.editar(libro, ctas.credito, limite_credito=5_000, tasa_anual=70, cat=95)
    con_tasa = tarjetas.pago_minimo_estimado(libro, ctas.credito)
    assert con_tasa.minimo == D("62.50")                                       # 1.25 % de 5,000
    assert con_tasa.meses_solo_minimo > 24 and con_tasa.intereses_solo_minimo > D(965)
    cuentas.editar(libro, ctas.credito, tasa_incluye_iva=True)
    assert tarjetas.iva_de_tarjeta(libro, libro.cuenta(ctas.credito)) == 0
    perfil.ajustar(libro, iva=21)                                              # España
    cuentas.editar(libro, ctas.credito, tasa_incluye_iva=False)
    assert tarjetas.iva_de_tarjeta(libro, libro.cuenta(ctas.credito)) == 21
    with pytest.raises(ErrorValidacion):
        cuentas.editar(libro, debito, tasa_anual=10)


# ------------------------------------------------------------- planeación


@pytest.fixture
def con_historial(libro, ctas, cat, debito):
    for mes in range(3, 8):
        movimientos.registrar_ingreso(libro, date(2026, mes, 1), debito, cat("NOMINA"), 20_000, "Nómina")
        movimientos.registrar_ingreso(libro, date(2026, mes, 2), debito, cat("HONORARIOS"), 3_000, "Honorarios")
        movimientos.registrar_gasto(libro, date(2026, mes, 3), debito, cat("RENTA"), 8_000, "Renta")
        movimientos.registrar_gasto(libro, date(2026, mes, 5), debito, cat("ALIMENTOS"), 5_000, "Súper")
    from motor import categorias

    categorias.editar(libro, cat("NOMINA"), principal=True)
    categorias.editar(libro, cat("HONORARIOS"), secundario=True)
    return debito


def test_ingresos_principal_y_secundario(libro, con_historial):
    ingresos = planeacion.ingresos(libro)
    assert [(i.nombre, i.tipo, i.promedio) for i in ingresos] == [
        ("NOMINA", "principal", D(20_000)), ("HONORARIOS", "secundario", D(3_000))]
    esperado = planeacion.ingreso_esperado(libro)
    assert (esperado.monto, esperado.fuente, esperado.meses) == (D(23_000), "promedio", 3)
    perfil.ajustar(libro, ingreso_esperado=25_000)
    assert planeacion.ingreso_esperado(libro).monto == D(25_000)
    perfil.ajustar(libro, ingreso_esperado=None)
    assert planeacion.ingreso_esperado(libro).fuente == "promedio"


def test_capacidad_de_pago(libro, con_historial):
    assert planeacion.capacidad(libro).nivel == "sana"
    prestamos.crear(libro, "Préstamo grande", "personal", 300_000, 24, 36, date(2026, 6, 1), destino=con_historial)
    cap = planeacion.capacidad(libro)
    assert cap.prestamos > 0 and cap.nivel in ("alta", "riesgo")
    assert cap.maximo_sano == D(6_900) and cap.libre == cap.ingreso - cap.compromisos


def test_presupuestos_sugeridos_y_proyeccion(libro, con_historial):
    plan = planeacion.sugerir(libro)
    assert plan.factor == 1 and plan.ahorro == D(2_300)
    assert {s.nombre: s.sugerido for s in plan.sugerencias} == {"HOGAR": D(8_000), "ALIMENTACION": D(5_000)}
    perfil.ajustar(libro, meta_ahorro=50)
    apretado = planeacion.sugerir(libro)                                       # 23,000 − 11,500 = 11,500 < 13,000
    assert apretado.factor < 1 and apretado.total_sugerido <= apretado.para_gastar
    proyeccion = planeacion.proyeccion_mes(libro)                              # 20 de julio
    assert proyeccion.gastado == D(13_000) and proyeccion.gasto_proyectado == D(13_000)   # ya pagaste lo usual
    assert proyeccion.ahorro_proyectado == D(10_000)


def test_meses_completos():
    assert planeacion.meses_completos(date(2026, 3, 10)) == [
        (date(2025, 12, 1), date(2025, 12, 31)), (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28))]


def test_iva_del_perfil(libro):
    perfil.configurar(libro, "Usuario Ficticio")
    assert libro.perfil.iva == 16
    with pytest.raises(ErrorValidacion):
        perfil.ajustar(libro, iva=80)
    with pytest.raises(ErrorValidacion):
        perfil.ajustar(libro, meta_ahorro=95)
    assert Decimal(perfil.ajustar(libro, iva="19").iva) == 19
