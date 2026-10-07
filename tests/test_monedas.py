"""Tu moneda: el formato de cada país, inversiones con tipo de cambio contra tu moneda y leer importes como
«1.234,56 €». Solo datos ficticios; nunca se sale a internet."""

import json
from datetime import date
from decimal import Decimal

import pytest

from conftest import D
from motor import cotizaciones, cuentas, evolucion, impuestos, metas, monedas, perfil, portafolio
from motor.errores import ErrorValidacion
from motor.importacion import _importe
from motor.modelo import Impuesto, PerfilImpuestos
from motor.serializacion import instantanea, libro_desde_instantanea


@pytest.fixture(autouse=True)
def volver_a_la_de_siempre():
    yield
    monedas.usar(None)


@pytest.mark.parametrize("codigo, positivo, negativo", [
    ("MXN", "$1,234,567.89", "-$1,234,567.89"),
    ("USD", "$1,234,567.89", "-$1,234,567.89"),
    ("EUR", "1.234.567,89 €", "-1.234.567,89 €"),
    ("ARS", "$ 1.234.567,89", "-$ 1.234.567,89"),
    ("COP", "$ 1.234.568", "-$ 1.234.568"),            # sin centavos
    ("CLP", "$1.234.568", "-$1.234.568"),
    ("PEN", "S/ 1,234,567.89", "-S/ 1,234,567.89"),
    ("GTQ", "Q1,234,567.89", "-Q1,234,567.89"),
    ("CRC", "₡1.234.567,89", "-₡1.234.567,89"),
])
def test_el_formato_de_cada_pais(codigo, positivo, negativo):
    m = monedas.usar(codigo)
    assert monedas.formatear(Decimal("1234567.89")) == positivo == m.ejemplo
    assert monedas.formatear(Decimal("-1234567.89")) == negativo
    assert monedas.formatear(Decimal("-0.001")) == monedas.formatear(0)          # sin «-0»


def test_toda_la_app_usa_la_moneda_elegida(libro, ctas, cat):
    from motor.dinero import formatear

    monedas.usar("EUR")
    assert formatear(D("1600")) == "1.600,00 €"
    meta = metas.crear(libro, "Viaje", 1_000)
    with pytest.raises(ErrorValidacion, match="solo tienes 0,00 €"):   # los mensajes del motor también
        metas.retirar(libro, meta.id, 200)
    iva = PerfilImpuestos("x", "Ficticio", (Impuesto("IVA", D(21)),))
    assert impuestos.revisar(iva, 1_000, {"IVA": 200})[0] == "No cuadra (diferencia total 10,00 €)"


def test_elegir_la_moneda_en_el_perfil(libro):
    perfil.configurar(libro, "Usuario Ficticio", "ars")
    assert libro.perfil.moneda == "ARS" and monedas.de(libro) == "ARS"
    perfil.ajustar(libro, moneda="CLP")
    assert libro_desde_instantanea(instantanea(libro)).perfil.moneda == "CLP"
    with pytest.raises(ErrorValidacion, match="No conozco la moneda"):
        perfil.ajustar(libro, moneda="XYZ")
    assert monedas.usar("XYZ").codigo == "MXN"                       # una desconocida deja la de siempre


@pytest.mark.parametrize("texto, centavos", [
    ("$1,234.50", 123450), ("1.234,50 €", 123450), ("1 234,50", 123450), ("S/ 99.90", 9990),
    ("(150.00)", -15000), ("-1.234,5", -123450), ("1234,5", 123450),
])
def test_leer_importes_de_cualquier_pais(texto, centavos):
    assert _importe(texto) == centavos


def test_un_punto_de_miles_segun_tu_moneda():
    monedas.usar("EUR")
    assert _importe("1.234") == 123400                               # en España, 1.234 son mil doscientos…
    monedas.usar("MXN")
    with pytest.raises(ErrorValidacion, match="más de dos decimales"):
        _importe("1.234")                                            # …en México sería un error de captura


# ------------------------------------------------------------------ inversiones contra tu moneda


@pytest.fixture
def argentina(libro, ctas):
    perfil.configurar(libro, "Usuario Ficticio", "ARS")
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 100_000, date(2026, 1, 1))
    return ctas


def test_comprar_en_tu_moneda_y_en_dolares(libro, argentina):
    local = portafolio.registrar_compra(libro, argentina.inversion, date(2026, 7, 1), "FICT.BA", 10, 100)
    assert (local.moneda, local.tipo_cambio) == ("ARS", 1)
    with pytest.raises(ErrorValidacion, match="cuántos ARS por 1 USD"):
        portafolio.registrar_compra(libro, argentina.inversion, date(2026, 7, 1), "FUSD", 1, 10, moneda="USD")
    portafolio.registrar_compra(libro, argentina.inversion, date(2026, 7, 1), "FUSD", 2, 10, moneda="USD",
                                tipo_cambio=1_000)
    v = portafolio.valuar(libro, argentina.inversion, {"FICT.BA": (D(120), "ARS"), "FUSD": (D(11), "USD")},
                          {"USD": D(1_100)})
    assert v.valor_titulos == D(1_200) + D(24_200)                   # 10 × 120 + 2 × 11 × 1,100


def test_el_historial_usa_el_tipo_de_cambio_contra_tu_moneda(libro, argentina):
    portafolio.registrar_compra(libro, argentina.inversion, date(2026, 7, 1), "FUSD", 2, 10, moneda="USD",
                                tipo_cambio=1_000)
    mercado = {"FUSD": ("USD", {date(2026, 7, 10): D(11)}),
               "USDMXN=X": ("MXN", {date(2026, 7, 10): D(20)}),       # de otra moneda: no se usa
               "USDARS=X": ("ARS", {date(2026, 7, 10): D(1_200)})}
    evo = evolucion.por_titulo(libro, [argentina.inversion], date(2026, 7, 1), date(2026, 7, 20), mercado)
    assert evolucion.resultado(evo).valor_final == D(26_400)          # 2 × 11 × 1,200


def _respuesta(simbolo, precio, moneda):
    return json.dumps({"chart": {"result": [{"meta": {
        "symbol": simbolo, "currency": moneda, "regularMarketPrice": precio, "regularMarketTime": 1790000000}}],
        "error": None}})


def test_consultar_el_tipo_de_cambio_contra_tu_moneda(tmp_path):
    enviados = []

    def falso(simbolo):
        enviados.append(simbolo)
        return {"FUSD": _respuesta("FUSD", 10, "USD"), "FICT.BA": _respuesta("FICT.BA", 500, "ARS"),
                "USDARS=X": _respuesta("USDARS=X", 1_150, "ARS")}[simbolo]

    consulta = cotizaciones.consultar(["FUSD", "FICT.BA"], enviar=falso, base="ARS")
    assert consulta.tipos == {"USD": D(1_150)} and sorted(enviados) == ["FICT.BA", "FUSD", "USDARS=X"]
    ruta = tmp_path / "precios.json"
    cotizaciones.guardar(consulta, ruta)
    _, tipos = cotizaciones.ultimos(ruta)
    assert tipos["USD"].moneda == "ARS"
    mercado = cotizaciones.mercado_guardado(tmp_path / "no_hay.json", ruta, base="ARS")
    assert "USDARS=X" in mercado
    assert "USDMXN=X" not in cotizaciones.mercado_guardado(tmp_path / "no_hay.json", ruta, base="MXN")


def test_el_excel_lleva_tu_simbolo():
    exportar = pytest.importorskip("portal.componentes.exportar")
    assert exportar.formato_dinero() == '"$"#,##0.00;-"$"#,##0.00'
    monedas.usar("EUR")
    assert exportar.formato_dinero() == '#,##0.00 "€";-#,##0.00 "€"'
    monedas.usar("CLP")
    assert exportar.formato_dinero() == '"$"#,##0;-"$"#,##0'


def test_numeros_redondos_para_umbrales():
    assert [monedas.redondo(x) for x in (D(116), D(232), D(65), D(30_000), D("0.5"), D(9))] == [
        100, 200, 50, 20_000, 1, 5]
