"""Bienes: depreciación, mejoras, avalúos, venta y su efecto en la contabilidad. Solo datos ficticios."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from conftest import D
from motor import bienes, contabilidad, cuentas, movimientos, reportes
from motor.errores import ErrorValidacion
from motor.modelo import MetodoDepreciacion, TipoOperacion
from motor.serializacion import instantanea, libro_desde_instantanea

INICIO = date(2026, 1, 1)
CUATRO_ANIOS = INICIO + timedelta(days=1461)          # 4 × 365.25 días


@pytest.fixture
def debito(libro, ctas):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 500_000, date(2025, 12, 1))
    return ctas.debito


def _dep(base, rescate_pct, vida, dias) -> Decimal:
    depreciable = Decimal(base) * (100 - Decimal(rescate_pct)) / 100
    return min(depreciable * (Decimal(dias) / Decimal("365.25")) / Decimal(vida), depreciable).quantize(D("0.01"))


def test_laptop_en_linea_recta_y_comprarla_no_es_gasto(libro, debito):
    laptop = bienes.crear(libro, "Laptop ficticia", "computadora", INICIO, 25_000, cuenta_pago=debito).cuenta_id
    assert (libro.bien(laptop).metodo, libro.bien(laptop).vida_anios) == (MetodoDepreciacion.LINEA_RECTA, 4)
    assert reportes.resumen(libro, INICIO, INICIO).gastos == 0                   # cambiaste dinero por una cosa
    assert cuentas.saldo(libro, debito) == D(475_000)
    a_medias = bienes.valuar(libro, laptop, INICIO + timedelta(days=500))
    assert a_medias.depreciacion == _dep(25_000, 10, 4, 500) and a_medias.costo == D(25_000)
    assert bienes.valuar(libro, laptop, CUATRO_ANIOS).valor == D(2_500)          # su valor de rescate (10 %)
    assert bienes.valuar(libro, laptop, CUATRO_ANIOS + timedelta(days=900)).valor == D(2_500)   # no baja más
    # El patrimonio del Resumen también la deprecia.
    antes = reportes.indicadores(libro, INICIO).patrimonio_neto
    assert reportes.indicadores(libro, CUATRO_ANIOS).patrimonio_neto == antes - D(22_500)


def test_auto_decreciente_y_casa_que_no_se_deprecia(libro, debito):
    auto = bienes.crear(libro, "Auto ficticio", "auto", INICIO, 300_000).cuenta_id        # ya lo tenía
    esperado = D(300_000) - (D(300_000) - D(300_000) * D("0.85") ** 4).quantize(D("0.01"))
    assert bienes.valuar(libro, auto, CUATRO_ANIOS).valor == esperado                       # ~156,601.88
    assert bienes.valuar(libro, auto, INICIO + timedelta(days=365 * 40)).valor == D(30_000)  # rescate
    casa = bienes.crear(libro, "Casa ficticia", "casa", INICIO, 2_000_000).cuenta_id
    assert bienes.valuar(libro, casa, CUATRO_ANIOS).valor == D(2_000_000)


def test_mejora_y_avaluo_con_plusvalia(libro, debito):
    casa = bienes.crear(libro, "Casa ficticia", "casa", INICIO, 2_000_000).cuenta_id
    bienes.registrar_mejora(libro, casa, date(2026, 3, 1), 100_000, debito, "Remodelación ficticia")
    assert reportes.resumen(libro, INICIO, date(2026, 12, 31)).gastos == 0             # una mejora no es gasto
    bienes.registrar_avaluo(libro, casa, date(2026, 6, 1), 2_500_000)
    v = bienes.valuar(libro, casa, date(2026, 7, 1))
    assert (v.costo, v.revaluacion, v.valor) == (D(2_100_000), D(400_000), D(2_500_000))
    assert bienes.valuar(libro, casa, date(2026, 5, 31)).revaluacion == 0
    bienes.quitar_avaluo(libro, casa, date(2026, 6, 1))
    assert bienes.valuar(libro, casa, date(2026, 7, 1)).valor == D(2_100_000)
    with pytest.raises(ErrorValidacion, match="futura"):
        bienes.registrar_avaluo(libro, casa, date(2027, 1, 1), 1)


def test_un_avaluo_reinicia_la_depreciacion_con_la_vida_que_le_queda(libro, debito):
    laptop = bienes.crear(libro, "Laptop ficticia", "computadora", INICIO, 25_000).cuenta_id
    mitad = INICIO + timedelta(days=730)
    antes = bienes.valuar(libro, laptop, mitad).valor
    libro._reloj = lambda: __import__("datetime").datetime(2031, 1, 1)             # «hoy» después del avalúo
    bienes.registrar_avaluo(libro, laptop, mitad, 10_000)
    assert bienes.valuar(libro, laptop, mitad).revaluacion == D(10_000) - antes
    assert bienes.valuar(libro, laptop, mitad).valor == D(10_000)
    # Le quedan ~2 años: al final vale su rescate sobre el avalúo (10 % de 10,000).
    assert bienes.valuar(libro, laptop, CUATRO_ANIOS + timedelta(days=2)).valor == D(1_000)


def test_vender_deja_la_cuenta_en_ceros_y_cuadra(libro, debito):
    auto = bienes.crear(libro, "Auto ficticio", "auto", INICIO, 300_000).cuenta_id
    libro._reloj = lambda: __import__("datetime").datetime(2028, 6, 1)
    venta = date(2028, 1, 1)
    valor = bienes.valuar(libro, auto, venta).valor
    bienes.vender(libro, auto, venta, 250_000, debito)
    assert bienes.valuar(libro, auto, date(2028, 5, 1)).valor == 0
    assert cuentas.saldo(libro, debito) == D(750_000)
    r = contabilidad.resultados(libro, [(date(2028, 1, 1), date(2028, 5, 31))])
    venta_bienes = next(x for x in r.cambios_de_valor if x.nombre == contabilidad.VENTA_BIENES)
    assert venta_bienes.importes == (D(250_000) - valor,)                       # ganancia (o pérdida) contra su valor
    s = contabilidad.situacion(libro, [date(2028, 5, 31), date(2027, 12, 31)])
    al_cierre = bienes.valuar(libro, auto, date(2027, 12, 31)).valor               # un día antes de venderlo
    assert s.cuadra and s.total(contabilidad.ACTIVO, contabilidad.BIENES) == (D(0), al_cierre)
    assert contabilidad.balanza(libro, date(2028, 1, 1), date(2028, 5, 31)).cuadra
    with pytest.raises(ErrorValidacion, match="ya se vendió"):
        bienes.registrar_avaluo(libro, auto, date(2028, 2, 1), 1)
    bienes.deshacer_venta(libro, auto)
    assert cuentas.saldo(libro, debito) == D(500_000) and bienes.valuar(libro, auto, venta).valor == valor


def test_convertir_un_gasto_en_un_bien(libro, ctas, cat, debito):
    gasto = movimientos.registrar_gasto(libro, INICIO, ctas.credito, cat("ALIMENTOS"), 900, "Laptop ficticia")
    op = bienes.crear_desde_gasto(libro, gasto.id, "Laptop ficticia", "computadora")
    assert op.tipo is TipoOperacion.TRANSFERENCIA and op.id == gasto.id and op.fecha == INICIO
    bien = next(b for b in libro.bienes())
    assert bienes.valuar(libro, bien.cuenta_id, INICIO).costo == D(900)
    assert reportes.resumen(libro, INICIO, INICIO).gastos == 0
    assert cuentas.saldo(libro, ctas.credito) == D(-900)                          # sigue siendo deuda de la tarjeta
    msi = movimientos.registrar_gasto(libro, INICIO, ctas.credito, cat("ALIMENTOS"), 1200, "Tele", msi=3)
    with pytest.raises(ErrorValidacion, match="meses sin intereses"):
        bienes.convertir_gasto(libro, msi.id, bien.cuenta_id)
    with pytest.raises(ErrorValidacion, match="Solo un gasto"):
        bienes.convertir_gasto(libro, op.id, bien.cuenta_id)


def test_contabilidad_con_bienes_cuadra_y_separa_los_cambios_de_valor(libro, debito):
    laptop = bienes.crear(libro, "Laptop ficticia", "computadora", INICIO, 25_000, cuenta_pago=debito).cuenta_id
    casa = bienes.crear(libro, "Casa ficticia", "casa", INICIO, 2_000_000).cuenta_id
    libro._reloj = lambda: __import__("datetime").datetime(2027, 12, 31)
    bienes.registrar_avaluo(libro, casa, date(2027, 6, 1), 2_300_000)
    anio = (date(2027, 1, 1), date(2027, 12, 31))
    s = contabilidad.situacion(libro, [anio[1], date(2026, 12, 31)], anio[0])
    assert s.cuadra
    nombres = {r.nombre for r in s.renglones}
    assert {"Depreciación acumulada · Laptop ficticia", "Plusvalía por avalúos · Casa ficticia"} <= nombres
    r = contabilidad.resultados(libro, [anio])
    cambios = {x.nombre: x.importes[0] for x in r.cambios_de_valor}
    esperada = (bienes.valuar(libro, laptop, anio[1]).depreciacion
                - bienes.valuar(libro, laptop, date(2026, 12, 31)).depreciacion)
    assert cambios[contabilidad.DEPRECIACION] == -esperada
    assert cambios[contabilidad.PLUSVALIA] == D(300_000)
    assert r.dia_a_dia() == (D(0),)                                               # no es dinero que entró o salió
    b = contabilidad.balanza(libro, *anio)
    assert b.cuadra and b.por_categoria().cuadra
    f = contabilidad.flujo(libro, [(INICIO, anio[1])])
    assert f.cuadra and {r.naturaleza for r in f.renglones} >= {contabilidad.FLUJO_BIENES}
    # El detalle de la depreciación del año es un asiento calculado.
    dep = next(x for x in r.cambios_de_valor if x.nombre == contabilidad.DEPRECIACION)
    (detalle,) = contabilidad.movimientos(libro, dep.origen)
    assert detalle.importe == -esperada and "Laptop ficticia" in detalle.descripcion


def test_se_guardan_en_los_respaldos(libro, debito):
    casa = bienes.crear(libro, "Casa ficticia", "casa", INICIO, 2_000_000).cuenta_id
    bienes.registrar_avaluo(libro, casa, date(2026, 6, 1), 2_100_000)
    bienes.configurar(libro, casa, metodo="linea_recta", vida_anios=50, rescate=20)
    copia = libro_desde_instantanea(instantanea(libro), libro.secuencia, reloj=libro.reloj)
    assert copia.bienes() == libro.bienes()


def test_validaciones(libro, debito):
    with pytest.raises(ErrorValidacion, match="tipo de bien"):
        bienes.crear(libro, "X", "nave espacial", INICIO, 1)
    laptop = bienes.crear(libro, "Laptop ficticia", "computadora", INICIO, 25_000).cuenta_id
    with pytest.raises(ErrorValidacion, match="vida útil"):
        bienes.configurar(libro, laptop, vida_anios=0)
    with pytest.raises(ErrorValidacion, match="rescate"):
        bienes.configurar(libro, laptop, rescate=100)
    with pytest.raises(ErrorValidacion, match="no es un bien"):
        bienes.valuar(libro, debito, INICIO)


def test_drill_down_de_los_estados(libro, ctas, cat, debito):
    movimientos.registrar_gasto(libro, date(2026, 2, 1), debito, cat("ALIMENTOS"), 300, "Súper ficticio")
    movimientos.registrar_ingreso(libro, date(2026, 2, 2), debito, cat("NOMINA"), 1_000, "Nómina ficticia")
    periodo = (INICIO, date(2026, 7, 20))
    s = contabilidad.situacion(libro, [periodo[1]], periodo[0])
    banco = next(r for r in s.renglones if r.nombre == "Banco Ficticio Débito")
    assert [m.importe for m in contabilidad.movimientos(libro, banco.origen)] == [D(1_000), D(-300)]
    r = contabilidad.resultados(libro, [periodo])
    (gasto,) = contabilidad.movimientos(libro, r.gastos[0].origen)
    assert (gasto.importe, gasto.detalle) == (D(300), "Banco Ficticio Débito")
    (ingreso,) = contabilidad.movimientos(libro, r.ingresos[0].origen)
    assert ingreso.importe == D(1_000)
    f = contabilidad.flujo(libro, [periodo])
    assert sum(m.importe for m in contabilidad.movimientos(libro, f.origen())) == f.total()[0]
    b = contabilidad.balanza(libro, *periodo)
    fila = next(c for c in b.cuentas if c.nombre == "Banco Ficticio Débito")
    assert sum(m.debe for m in contabilidad.movimientos(libro, fila.origen)) == fila.debe
    total_activo = contabilidad.movimientos(libro, s.origen(contabilidad.ACTIVO))
    assert sum(m.importe for m in total_activo) == D(700)
