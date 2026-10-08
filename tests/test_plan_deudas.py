"""Plan para salir de deudas (motor/plan_deudas.py). Solo tarjetas, préstamos y montos ficticios."""

from datetime import date
from decimal import Decimal

import pytest

from conftest import D
from motor import categorias, cuentas, movimientos, perfil, plan_deudas as plan, prestamos
from motor.errores import ErrorValidacion
from motor.serializacion import instantanea, libro_desde_instantanea

HOY = date(2026, 7, 20)          # el reloj de las pruebas (conftest.AHORA)


@pytest.fixture
def deudas(libro):
    """Dos tarjetas y un préstamo ficticios."""
    perfil.configurar(libro, "Usuario Ficticio")
    grande = cuentas.crear(libro, "TDC Grande", "credito", deuda_inicial=30_000, limite_credito=50_000, dia_corte=3,
                           dia_pago=23, fecha_creacion=date(2026, 1, 1))
    cuentas.editar(libro, grande.id, tasa_anual=60)
    chica = cuentas.crear(libro, "TDC Chica", "credito", deuda_inicial=5_000, limite_credito=10_000, dia_corte=10,
                          dia_pago=30, fecha_creacion=date(2026, 1, 1))
    cuentas.editar(libro, chica.id, tasa_anual=36)
    auto = prestamos.crear(libro, "Préstamo Ficticio", "auto", 40_000, 18, 24, date(2026, 1, 1),
                           deuda_actual=20_000)
    return {"grande": grande.id, "chica": chica.id, "auto": auto.cuenta_id}


def test_tus_deudas_con_su_tasa_y_su_pago(libro, deudas):
    lista = {d.nombre: d for d in plan.deudas(libro)}
    assert set(lista) == {"TDC Grande", "TDC Chica", "Préstamo Ficticio"}
    grande = lista["TDC Grande"]
    assert (grande.saldo, grande.linea, grande.tasa_anual) == (D(30_000), D(50_000), D(60))
    assert grande.tasa_mes == D(60) / 100 / 12 * D("1.16")                       # con el IVA de los intereses
    auto = lista["Préstamo Ficticio"]
    assert auto.saldo == D(20_000) and auto.pago_fijo > 0
    # Una tarjeta que ya no debe nada no entra.
    cuentas.crear(libro, "TDC Pagada", "credito", deuda_inicial=0, fecha_creacion=date(2026, 1, 1))
    assert len(plan.deudas(libro)) == 3


def test_el_orden_de_cada_estrategia(libro, deudas):
    lista = plan.deudas(libro)
    assert plan.ordenar(lista, plan.AVALANCHA) == (deudas["grande"], deudas["chica"], deudas["auto"])
    assert plan.ordenar(lista, plan.BOLA_DE_NIEVE) == (deudas["chica"], deudas["auto"], deudas["grande"])
    with pytest.raises(ErrorValidacion):
        plan.ordenar(lista, "otra")


def test_sin_alcanzar_los_minimos_no_hay_plan(libro, deudas):
    p = plan.calcular(libro, 100)
    assert not p.alcanza and p.avalancha is None and p.minimo > 100
    assert plan.calcular(libro, p.minimo).alcanza                                  # justo lo mínimo, sí


def test_avalancha_paga_menos_intereses_y_ambas_ganan_a_los_minimos(libro, deudas):
    p = plan.calcular(libro, 6_000)
    a, b, m = p.avalancha, p.bola_de_nieve, p.solo_minimos
    assert a.termina and b.termina
    assert a.intereses < b.intereses < m.intereses
    assert a.meses <= b.meses and (not m.termina or m.meses > a.meses)
    assert p.recomendada == plan.AVALANCHA
    # Bola de nieve termina primero la chica; avalancha va por la de tasa más alta.
    assert b.liquidadas[0].nombre == "TDC Chica"
    assert [x.cuenta_id for x in a.liquidadas].index(deudas["grande"]) < [x.cuenta_id for x in b.liquidadas].index(
        deudas["grande"])
    # Cada mes pagas lo que dijiste (salvo el último, que es lo que faltaba).
    assert all(sum(mes.pagos.values()) == D(6_000) for mes in a.tabla[:-1])
    assert a.fin == a.tabla[-1].fecha and a.tabla[0].fecha == date(2026, 8, 20)


@pytest.mark.parametrize("estrategia", [plan.AVALANCHA, plan.BOLA_DE_NIEVE])
def test_lo_pagado_es_lo_que_debias_mas_los_intereses(libro, deudas, estrategia):
    p = plan.calcular(libro, 5_321)
    r = p.de(estrategia)
    debias = sum(d.total for d in p.deudas)
    assert r.pagado == debias + r.intereses
    assert r.tabla[-1].saldo == 0
    assert sum(x.intereses for x in r.liquidadas) == r.intereses


def test_meses_sin_intereses_se_pagan_aparte_y_sin_intereses(libro, deudas):
    ropa = categorias.buscar(libro, "ROPA").id
    movimientos.registrar_gasto(libro, date(2026, 7, 1), deudas["chica"], ropa, 1_200, "Compra ficticia a MSI", msi=6)
    chica = next(d for d in plan.deudas(libro) if d.cuenta_id == deudas["chica"])
    # La primera mensualidad ya entró en el corte del 10 de julio: ya es parte de lo que generará intereses.
    assert chica.saldo == D(5_200) and chica.msi == ((D(200), 5),)
    assert chica.total == D(6_200)
    r = plan.calcular(libro, 6_000).avalancha
    assert r.pagado == sum(d.total for d in plan.deudas(libro)) + r.intereses


def test_una_deuda_sin_tasa_se_avisa(libro, deudas):
    cuentas.editar(libro, deudas["chica"], tasa_anual=None)
    p = plan.calcular(libro, 6_000)
    assert [d.nombre for d in p.sin_tasa] == ["TDC Chica"]
    assert next(d for d in p.deudas if d.cuenta_id == deudas["chica"]).tasa_mes == 0


def test_con_un_pago_muy_bajo_solo_minimos_no_termina(libro):
    perfil.configurar(libro, "Usuario Ficticio")
    tdc = cuentas.crear(libro, "TDC Ficticia", "credito", deuda_inicial=10_000, dia_corte=3, dia_pago=23,
                        fecha_creacion=date(2026, 1, 1))
    cuentas.editar(libro, tdc.id, tasa_anual=200)                                  # el mínimo no cubre el interés
    p = plan.calcular(libro, 3_000)
    assert not p.solo_minimos.termina and p.avalancha.termina


def test_sin_deudas_no_hay_nada_que_planear(libro, ctas):
    p = plan.calcular(libro, 1_000)
    assert p.deudas == [] and not p.alcanza and p.minimo == 0


def test_guardar_el_plan_y_ver_el_avance(libro, deudas):
    assert plan.avance(libro) is None
    with pytest.raises(ErrorValidacion):
        plan.guardar(libro, 0, plan.AVALANCHA)
    with pytest.raises(ErrorValidacion):
        plan.guardar(libro, 5_000, "otra")
    plan.guardar(libro, 6_000, plan.BOLA_DE_NIEVE)
    assert plan.guardado_de(libro) == (D(6_000), plan.BOLA_DE_NIEVE)
    av = plan.avance(libro)
    assert av.alcanza and av.objetivo.cuenta_id == deudas["chica"]
    assert sum(av.pagos.values()) == D(6_000)
    assert av.pagos[deudas["grande"]] == D(2_190)          # solo su mínimo: 1.5 % de 30,000 + 1,740 de intereses
    assert av.pagos[deudas["chica"]] > D(1_500)            # lo que sobra va a la chica
    assert plan.calcular(libro).presupuesto == D(6_000)                            # el guardado, por omisión

    otro = libro_desde_instantanea(instantanea(libro), libro.secuencia)            # se guarda con tu perfil
    assert plan.guardado_de(otro) == (D(6_000), plan.BOLA_DE_NIEVE)
    plan.quitar(libro)
    assert plan.avance(libro) is None


def test_el_avance_sin_alcanzar_avisa(libro, deudas):
    plan.guardar(libro, 100, plan.AVALANCHA)
    av = plan.avance(libro)
    assert not av.alcanza and av.objetivo is None


def test_monto_sugerido_redondo(libro, deudas):
    p = plan.calcular(libro)
    assert plan.sugerido(p) % 100 == 0 and plan.sugerido(p) >= p.minimo * Decimal("1.1")
