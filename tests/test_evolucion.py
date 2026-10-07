"""Rendimiento de las inversiones en el tiempo. Datos y precios ficticios; nunca se sale a internet."""

from datetime import date

import pytest

from conftest import D
from motor import cuentas, evolucion, portafolio
from motor.evolucion import PLAZO, TITULO, Instrumento
from motor.transferencias import registrar_transferencia

JUNIO, JULIO_20 = date(2026, 6, 1), date(2026, 7, 20)


@pytest.fixture
def inversion(libro, ctas):
    """3,000 pesos a la cuenta de inversión; compra títulos en pesos y en dólares, y un CETE."""
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 10_000, date(2026, 1, 1))
    registrar_transferencia(libro, JUNIO, ctas.debito, ctas.inversion, 3000, "Aportación")
    portafolio.registrar_compra(libro, ctas.inversion, date(2026, 6, 2), "FICT", 10, 100)
    portafolio.registrar_compra(libro, ctas.inversion, date(2026, 6, 2), "FUSD", 1, 10, moneda="USD", tipo_cambio=20)
    portafolio.registrar_plazo(libro, ctas.inversion, "Cetes ficticios", JUNIO, 1000, 10, 28)
    return ctas.inversion


MERCADO = {"FICT": ("MXN", {date(2026, 6, 30): D(110), date(2026, 7, 15): D(120)}),
           "FUSD": ("USD", {date(2026, 6, 30): D(11)}),
           "USDMXN=X": ("MXN", {date(2026, 6, 30): D(19)})}


def test_valor_por_titulo_con_precios_de_cierre_y_tipo_de_cambio(libro, inversion):
    evo = evolucion.por_titulo(libro, [inversion], JUNIO, JULIO_20, MERCADO)
    assert evo.nombres == ["FICT", "FUSD", "Cetes ficticios (a plazo)"] and not evo.estimados
    fict, fusd, cetes = (r for _, r in evolucion.por_serie(evo))
    assert (fict.entradas, fict.valor_final, fict.ganancia) == (D(1000), D(1200), D(200))   # 10 × 120
    assert fict.rendimiento == D("20.41")              # 200 / (1000 × 49/50): invertido desde el 2.º día
    assert (fusd.valor_final, fusd.ganancia) == (D(209), D(9))                              # 11 USD × 19
    assert evo.valores["FICT"][evo.fechas.index(date(2026, 6, 20))] == D(1000)  # sin cierre aún: precio de compra


def test_el_cete_al_vencer_sale_y_su_ganancia_es_el_interes(libro, inversion):
    evo = evolucion.por_titulo(libro, [inversion], JUNIO, JULIO_20, MERCADO,
                               {Instrumento("Cetes ficticios", PLAZO)})
    total = evolucion.resultado(evo)
    assert evo.nombres == ["Cetes ficticios (a plazo)"]
    assert (total.entradas, total.salidas, total.valor_final, total.ganancia) == (
        D(1000), D("1007.78"), D(0), D("7.78"))                                  # 1000 × 10 % × 28 / 360
    a_medias = evo.valores["Cetes ficticios (a plazo)"][evo.fechas.index(date(2026, 6, 15))]
    assert a_medias == D("1003.89")
    # Reinvertir lo que venció en otro CETE no cuenta el dinero dos veces.
    portafolio.registrar_plazo(libro, inversion, "CETES FICTICIOS", date(2026, 6, 29), "1007.78", 10, 28)
    otra = evolucion.resultado(evolucion.por_titulo(libro, [inversion], JUNIO, JULIO_20, MERCADO,
                                                    {Instrumento("Cetes ficticios", PLAZO)}))
    # 1007.78 × 10 % × 21 / 360 = 5.88 más los 7.78 del primero; reinvertir el mismo día no es dinero nuevo.
    assert (otra.entradas, otra.valor_final, otra.ganancia) == (D(1000), D("1013.66"), D("13.66"))


def test_ganancia_por_mes_y_lo_que_metiste(libro, inversion):
    evo = evolucion.por_titulo(libro, [inversion], JUNIO, JULIO_20, MERCADO)
    assert evolucion.ganancia_por_periodo(evo) == [(date(2026, 6, 1), D("116.78")), (date(2026, 7, 1), D(100))]
    assert evolucion.ganancia_por_periodo(evo, por_anio=True) == [(date(2026, 1, 1), D("216.78"))]
    dia, valor, metiste = evolucion.serie_total(evo)[-1]
    assert (dia, valor, valor - metiste) == (JULIO_20, D(1409), D("216.78"))   # la distancia es la ganancia
    solo_fict = evolucion.resultado(evo, ["FICT"])
    assert solo_fict.ganancia == D(200)


def test_filtrar_un_titulo_y_un_periodo_que_empieza_con_valor(libro, inversion):
    elegidos = {Instrumento("FICT", TITULO)}
    evo = evolucion.por_titulo(libro, [inversion], date(2026, 7, 1), JULIO_20, MERCADO, elegidos)
    r = evolucion.resultado(evo)
    assert evo.nombres == ["FICT"]
    assert (r.valor_inicial, r.entradas, r.valor_final, r.ganancia, r.rendimiento) == (
        D(1100), D(0), D(1200), D(100), D("9.09"))


def test_ventas_y_titulos_sin_historial(libro, inversion):
    portafolio.registrar_venta(libro, inversion, date(2026, 7, 16), "FICT", 4, 121, comision=1)
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 1), "SINDATOS", 2, 50)
    evo = evolucion.por_titulo(libro, [inversion], JUNIO, JULIO_20, MERCADO)
    fict = dict(evolucion.por_serie(evo))["FICT"]
    # Después de vender, el precio más reciente es el de la venta (121): 6 × 121; 483 − 1000 + 726.
    assert (fict.salidas, fict.valor_final, fict.ganancia) == (D(483), D(726), D(209))
    assert evo.estimados == {"SINDATOS"} and dict(evolucion.por_serie(evo))["SINDATOS"].ganancia == 0


def test_titulo_comprado_en_pesos_con_historial_en_dolares(libro, ctas):
    portafolio.registrar_compra(libro, ctas.inversion, date(2026, 7, 1), "FUSD", 2, 200)     # por el SIC, en MXN
    mercado = {"FUSD": ("USD", {date(2026, 7, 10): D(11)}), "USDMXN=X": ("MXN", {date(2026, 7, 10): D(20)})}
    evo = evolucion.por_titulo(libro, [ctas.inversion], date(2026, 7, 1), JULIO_20, mercado)
    assert evolucion.resultado(evo).valor_final == D(440)                                   # 2 × 11 × 20


def test_vista_oficial_transferencias_son_aportaciones_y_rendimientos_ganancia(libro, inversion, ctas):
    portafolio.ajustar_a_valor_oficial(libro, inversion, "3100.50", date(2026, 6, 30))
    registrar_transferencia(libro, date(2026, 7, 5), inversion, ctas.debito, 100, "Retiro")
    portafolio.ajustar_a_valor_oficial(libro, inversion, 3050, JULIO_20)
    evo = evolucion.oficial(libro, [inversion], JUNIO, JULIO_20)
    r = evolucion.resultado(evo)
    assert (r.valor_inicial, r.entradas, r.salidas, r.valor_final, r.ganancia) == (
        D(0), D(3000), D(100), D(3050), D(150))
    assert evolucion.ganancia_por_periodo(evo) == [(date(2026, 6, 1), D("100.50")), (date(2026, 7, 1), D("49.50"))]
    assert evo.nombres == ["Inversión Ficticia"]


def test_instrumentos_y_primera_fecha(libro, inversion):
    assert [i.etiqueta for i in evolucion.instrumentos(libro, [inversion])] == [
        "FICT", "FUSD", "Cetes ficticios (a plazo)"]
    assert evolucion.primera_fecha(libro, [inversion]) == JUNIO
    assert evolucion.primera_fecha(libro, [inversion], oficial=True) == JUNIO
    assert evolucion.cuentas_de_inversion(libro) == [inversion]


@pytest.mark.parametrize(("clave", "esperado"), [
    ("mes", (date(2026, 8, 1), date(2026, 8, 31))),
    ("mes_pasado", (date(2026, 7, 1), date(2026, 7, 31))),
    ("3m", (date(2026, 6, 1), date(2026, 8, 31))),
    ("6m", (date(2026, 3, 1), date(2026, 8, 31))),
    ("anio", (date(2026, 1, 1), date(2026, 8, 31))),
    ("1a", (date(2025, 9, 1), date(2026, 8, 31))),
    ("5a", (date(2021, 9, 1), date(2026, 8, 31))),
    ("10a", (date(2016, 9, 1), date(2026, 8, 31))),
])
def test_periodos(clave, esperado):
    assert evolucion.rango(clave, date(2026, 8, 31)) == esperado


def test_periodos_no_empiezan_antes_de_tus_datos():
    hoy, inicio = date(2026, 8, 31), date(2026, 6, 15)
    assert evolucion.rango("10a", hoy, inicio) == (inicio, hoy)
    assert evolucion.rango("todo", hoy, inicio) == (inicio, hoy)
    assert evolucion.rango("mes", hoy, inicio) == (date(2026, 8, 1), hoy)
    assert evolucion.rango("rango", hoy, inicio, (date(2026, 9, 30), date(2026, 7, 1))) == (date(2026, 7, 1), hoy)
    assert evolucion.rango("1a", date(2028, 2, 29)) == (date(2027, 3, 1), date(2028, 2, 29))
