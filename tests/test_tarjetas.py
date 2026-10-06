from datetime import date

import pytest

from conftest import D
from motor import cuentas, movimientos, tarjetas
from motor.errores import ErrorValidacion
from motor.transferencias import registrar_pago_tarjeta


@pytest.mark.parametrize(
    ("fecha", "corte", "esperado"),
    [
        (date(2026, 7, 10), 3, (date(2026, 7, 4), date(2026, 8, 3))),
        (date(2026, 7, 3), 3, (date(2026, 6, 4), date(2026, 7, 3))),
        (date(2026, 7, 4), 3, (date(2026, 7, 4), date(2026, 8, 3))),
        (date(2026, 12, 20), 3, (date(2026, 12, 4), date(2027, 1, 3))),
        (date(2026, 1, 2), 3, (date(2025, 12, 4), date(2026, 1, 3))),
        # Corte el 31 en meses cortos: el último día del mes.
        (date(2026, 2, 15), 31, (date(2026, 2, 1), date(2026, 2, 28))),
        (date(2026, 3, 1), 31, (date(2026, 3, 1), date(2026, 3, 31))),
        (date(2028, 2, 29), 30, (date(2028, 1, 31), date(2028, 2, 29))),
    ],
)
def test_ciclo_de(fecha, corte, esperado):
    assert tarjetas.ciclo_de(fecha, corte) == esperado


def test_credito_disponible(libro, ctas, cat):
    assert tarjetas.credito_disponible(libro, ctas.credito) == D(1000)
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("Alimentos"), "640.20")
    assert tarjetas.credito_disponible(libro, ctas.credito) == D("359.80")
    sin_limite = cuentas.crear(libro, "Sin límite", "credito").id
    assert tarjetas.credito_disponible(libro, sin_limite) is None


def test_funciones_de_tarjeta_solo_para_credito(libro, ctas):
    with pytest.raises(ErrorValidacion):
        tarjetas.deuda(libro, ctas.debito)


def test_resumen_de_ciclo_con_parcializaciones_y_liquidacion(libro, ctas, cat):
    """Patrón real: pagos parciales durante el ciclo y liquidación tras el corte."""
    alimentos = cat("Alimentos")
    # Ciclo 4 jul – 3 ago (corte día 3, pago día 23).
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, alimentos, 65)
    movimientos.registrar_gasto(libro, date(2026, 7, 6), ctas.credito, cat("Regalos"), "333.33")
    registrar_pago_tarjeta(libro, date(2026, 7, 15), ctas.debito, ctas.credito, 500, "Parcialización")
    movimientos.registrar_gasto(libro, date(2026, 7, 27), ctas.credito, alimentos, 99)
    movimientos.registrar_gasto(libro, date(2026, 8, 1), ctas.credito, alimentos, 99)
    # Del ciclo siguiente: no debe contar.
    movimientos.registrar_gasto(libro, date(2026, 8, 4), ctas.credito, alimentos, 1)

    r = tarjetas.resumen_ciclo(libro, ctas.credito, date(2026, 7, 20), hasta=date(2026, 8, 3))
    # Día de pago 23: el 23 de agosto de 2026 es domingo, así que se recorre al lunes 24.
    assert (r.inicio, r.fin, r.fecha_limite_pago) == (date(2026, 7, 4), date(2026, 8, 3), date(2026, 8, 24))
    assert r.saldo_inicial == 0
    assert r.cargos == D("596.33")
    assert r.abonos == D(500)
    assert r.deuda_al_corte == D("96.33")
    assert r.por_liquidar == D("96.33")

    registrar_pago_tarjeta(libro, date(2026, 8, 4), ctas.debito, ctas.credito, "96.33", "Liquidación")
    r = tarjetas.resumen_ciclo(libro, ctas.credito, date(2026, 7, 20), hasta=date(2026, 8, 10))
    assert r.pagado_despues_del_corte == D("96.33")
    assert r.por_liquidar == 0
    assert tarjetas.deuda(libro, ctas.credito) == D(1)


def test_resumen_de_ciclo_requiere_dia_de_corte(libro, ctas):
    sin_corte = cuentas.crear(libro, "Sin corte", "credito").id
    with pytest.raises(ErrorValidacion, match="corte"):
        tarjetas.resumen_ciclo(libro, sin_corte)


def test_resumen_de_ciclo_usa_hoy_por_defecto(libro, ctas):
    r = tarjetas.resumen_ciclo(libro, ctas.credito)  # el reloj de prueba marca 20 jul 2026
    assert (r.inicio, r.fin) == (date(2026, 7, 4), date(2026, 8, 3))


def test_actualizar_deuda(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("Alimentos"), 500)
    op = tarjetas.actualizar_deuda(libro, ctas.credito, 520, date(2026, 7, 31))
    assert op is not None
    assert tarjetas.deuda(libro, ctas.credito) == D(520)


# --------------------------------------------------------- fecha límite de pago


def _tdc(libro, **regla):
    return libro.cuenta(cuentas.crear(libro, "TDC regla", "credito", dia_corte=3, **regla).id)


@pytest.mark.parametrize(
    ("regla", "corte", "esperada"),
    [
        # «Hasta 10 días naturales contados a partir de la fecha de corte»: 13 de octubre (martes).
        ({"dias_para_pagar": 10}, date(2026, 10, 3), date(2026, 10, 13)),
        # El 13 de junio de 2026 es sábado: se recorre al lunes 15.
        ({"dias_para_pagar": 10}, date(2026, 6, 3), date(2026, 6, 15)),
        # Sin recorrer: se queda el sábado.
        ({"dias_para_pagar": 10, "recorrer_inhabil": False}, date(2026, 6, 3), date(2026, 6, 13)),
        # 10 días hábiles desde el sábado 3 de octubre: del lunes 5 al viernes 16.
        ({"dias_para_pagar": 10, "dias_habiles": True}, date(2026, 10, 3), date(2026, 10, 16)),
        # 10 días hábiles desde el 3 de noviembre: se salta el lunes 16 (Revolución) → miércoles 18.
        ({"dias_para_pagar": 10, "dias_habiles": True}, date(2026, 11, 3), date(2026, 11, 18)),
        # Día fijo 23 del mes: el 23 de julio de 2026 es jueves.
        ({"dia_pago": 23}, date(2026, 7, 3), date(2026, 7, 23)),
        # Día fijo que ya pasó en el mes del corte: el del mes siguiente.
        ({"dia_pago": 2}, date(2026, 7, 3), date(2026, 8, 3)),
        # Cae en jueves santo (2 de abril de 2026): se recorre al lunes 6.
        ({"dia_pago": 2}, date(2026, 3, 3), date(2026, 4, 6)),
    ],
)
def test_fecha_limite_de_pago(libro, regla, corte, esperada):
    assert tarjetas.fecha_limite_pago(_tdc(libro, **regla), corte) == esperada


def test_sin_regla_de_pago_no_hay_fecha_limite(libro):
    assert tarjetas.fecha_limite_pago(_tdc(libro), date(2026, 7, 3)) is None


def test_regla_de_pago_valida(libro):
    with pytest.raises(ErrorValidacion, match="no ambos"):
        cuentas.crear(libro, "TDC doble", "credito", dia_pago=23, dias_para_pagar=10)
    with pytest.raises(ErrorValidacion, match="entre 1 y 60"):
        cuentas.crear(libro, "TDC rara", "credito", dias_para_pagar=0)
    with pytest.raises(ErrorValidacion):
        cuentas.crear(libro, "Débito", "debito", dias_para_pagar=10)


def test_cambiar_regla_de_pago(libro):
    tdc = _tdc(libro, dia_pago=23)
    with pytest.raises(ErrorValidacion, match="no ambos"):
        cuentas.editar(libro, tdc.id, dias_para_pagar=10)
    cuentas.editar(libro, tdc.id, dia_pago=None, dias_para_pagar=10, dias_habiles=True, recorrer_inhabil=False)
    nueva = libro.cuenta(tdc.id)
    assert (nueva.dia_pago, nueva.dias_para_pagar, nueva.dias_habiles, nueva.recorrer_inhabil) == (None, 10, True, False)


def test_describir_regla_pago(libro):
    assert tarjetas.describir_regla_pago(_tdc(libro, dias_para_pagar=10)) == \
        "10 días naturales después del corte (si es inhábil, el siguiente día hábil)"
    libro2 = libro
    assert tarjetas.describir_regla_pago(
        libro2.cuenta(cuentas.crear(libro2, "Otra", "credito", dias_para_pagar=5, dias_habiles=True,
                                    recorrer_inhabil=False).id)) == "5 días hábiles después del corte"
    assert tarjetas.describir_regla_pago(
        libro2.cuenta(cuentas.crear(libro2, "Fija", "credito", dia_pago=23).id)).startswith("el día 23 de cada mes")
    assert tarjetas.describir_regla_pago(libro2.cuenta(cuentas.crear(libro2, "Sin", "credito").id)) == ""


def test_estado_de_la_tarjeta(libro, ctas, cat):
    """Línea de 1,000, corte el 3 y pago el 23 (si es inhábil, el siguiente hábil)."""
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("Alimentos"), "640.20")

    hoy = tarjetas.estado(libro, ctas.credito, date(2026, 7, 20))
    assert (hoy.limite, hoy.deuda, hoy.disponible, hoy.uso) == (D(1000), D("640.20"), D("359.80"), D("0.6402"))
    assert hoy.situacion == tarjetas.AL_CORRIENTE                   # el corte del 3 de julio no debía nada
    assert hoy.actual.cargos == D("640.20") and hoy.actual.fin == date(2026, 8, 3)
    assert not hoy.excedida

    # Después del corte del 3 de agosto: hay que pagar antes del lunes 24 (el 23 es domingo).
    agosto = tarjetas.estado(libro, ctas.credito, date(2026, 8, 10))
    assert agosto.situacion == tarjetas.POR_PAGAR and agosto.corte.por_liquidar == D("640.20")
    assert agosto.corte.fecha_limite_pago == date(2026, 8, 24) and agosto.dias_para_pagar == 14
    registrar_pago_tarjeta(libro, date(2026, 8, 12), ctas.debito, ctas.credito, 400)
    assert tarjetas.estado(libro, ctas.credito, date(2026, 8, 20)).corte.por_liquidar == D("240.20")

    vencida = tarjetas.estado(libro, ctas.credito, date(2026, 8, 25))
    assert vencida.situacion == tarjetas.VENCIDA and vencida.dias_para_pagar == -1
    registrar_pago_tarjeta(libro, date(2026, 8, 25), ctas.debito, ctas.credito, "240.20")
    assert tarjetas.estado(libro, ctas.credito, date(2026, 8, 25)).situacion == tarjetas.AL_CORRIENTE


def test_estado_excedida_saldo_a_favor_y_sin_datos(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("Alimentos"), 1200)
    excedida = tarjetas.estado(libro, ctas.credito, date(2026, 7, 20))
    assert excedida.excedida and excedida.uso == D("1.2") and excedida.disponible == D(-200)

    registrar_pago_tarjeta(libro, date(2026, 7, 6), ctas.debito, ctas.credito, 1300)
    a_favor = tarjetas.estado(libro, ctas.credito, date(2026, 7, 20))
    assert (a_favor.deuda, a_favor.saldo_a_favor, a_favor.disponible, a_favor.uso) == (0, D(100), D(1100), 0)

    sencilla = tarjetas.estado(libro, cuentas.crear(libro, "Sin datos", "credito").id)
    assert (sencilla.limite, sencilla.disponible, sencilla.uso, sencilla.situacion) == (
        None, None, None, tarjetas.SIN_CORTE)


def test_estado_sin_regla_de_pago(libro, cat):
    tdc = cuentas.crear(libro, "Solo corte", "credito", dia_corte=3, fecha_creacion=date(2026, 6, 1)).id
    movimientos.registrar_gasto(libro, date(2026, 6, 20), tdc, cat("Alimentos"), 50)
    estado = tarjetas.estado(libro, tdc, date(2026, 7, 10))
    assert estado.situacion == tarjetas.SIN_FECHA and estado.dias_para_pagar is None
