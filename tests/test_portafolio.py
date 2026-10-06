"""Títulos, inversiones a plazo y consulta de precios. Datos ficticios; nunca se sale a internet."""

import json
import urllib.error
from datetime import date
from decimal import Decimal

import pytest

from conftest import D
from motor import cotizaciones, cuentas, portafolio, reportes
from motor.errores import ErrorValidacion
from motor.modelo import TipoCuenta, TipoOperacion
from motor.serializacion import instantanea, libro_desde_instantanea
from motor.transferencias import registrar_transferencia


@pytest.fixture
def inversion(libro, ctas):
    """1,000 pesos de la cuenta de débito a la de inversión."""
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 10_000, date(2026, 1, 1))
    registrar_transferencia(libro, date(2026, 7, 1), ctas.debito, ctas.inversion, 1000, "Aportación")
    return ctas.inversion


def test_comprar_no_cambia_el_saldo_y_lleva_costo_promedio(libro, inversion):
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "ficticia.mx", 2, 300, comision=4)
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 9), "FICTICIA.MX", 1, 350)
    assert cuentas.saldo(libro, inversion) == D(1000)                      # comprar no es gasto ni ingreso
    assert reportes.resumen(libro, date(2026, 7, 1), date(2026, 7, 31)).gastos == 0
    (pos,) = portafolio.posiciones(libro, inversion)
    assert (pos.simbolo, pos.titulos, pos.costo) == ("FICTICIA.MX", D(3), D(954))
    assert pos.costo_promedio == D(318)


def test_vender_calcula_la_ganancia_realizada_y_no_deja_vender_de_mas(libro, inversion):
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "FICT", 4, 100)
    with pytest.raises(ErrorValidacion, match="solo tenías 4"):
        portafolio.registrar_venta(libro, inversion, date(2026, 7, 5), "FICT", 5, 120)
    with pytest.raises(ErrorValidacion, match="solo tenías 0"):
        portafolio.registrar_venta(libro, inversion, date(2026, 7, 1), "FICT", 1, 120)   # antes de comprar
    portafolio.registrar_venta(libro, inversion, date(2026, 7, 5), "FICT", 1, 130, comision=2)
    (pos,) = portafolio.posiciones(libro, inversion)
    assert (pos.titulos, pos.costo, pos.realizada) == (D(3), D(300), D(28))       # 130 − 2 − 100


def test_no_se_puede_borrar_una_compra_si_deja_una_venta_sin_titulos(libro, inversion):
    compra = portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "FICT", 1, 100)
    portafolio.registrar_venta(libro, inversion, date(2026, 7, 5), "FICT", 1, 110)
    with pytest.raises(ErrorValidacion):
        portafolio.eliminar_valor(libro, compra.id)


def test_dolares_y_fracciones(libro, inversion):
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "FICT-USD", "0.5", 100, moneda="usd",
                                tipo_cambio="18.50")
    (pos,) = portafolio.posiciones(libro, inversion)
    assert pos.costo == D("925.00")
    val = portafolio.valuar(libro, inversion, {"FICT-USD": (D(120), "USD")}, {"USD": D(19)})
    assert val.valor_titulos == D("1140.00") and val.ganancia_no_realizada == D("215.00")
    falta = portafolio.valuar(libro, inversion, {"FICT-USD": (D(120), "USD")}, {})
    assert falta.faltan == ["FICT-USD"] and falta.ganancia_total is None
    with pytest.raises(ErrorValidacion, match="tipo de cambio"):
        portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "OTRA", 1, 1, moneda="USD")


def test_validaciones(libro, inversion, ctas):
    for simbolo in ("", "con espacio raro!", "X" * 30):
        with pytest.raises(ErrorValidacion):
            portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), simbolo, 1, 1)
    with pytest.raises(ErrorValidacion, match="mayor que cero"):
        portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "FICT", 0, 1)
    with pytest.raises(ErrorValidacion, match="Inversión"):
        portafolio.registrar_compra(libro, ctas.debito, date(2026, 7, 2), "FICT", 1, 1)


def test_cetes_se_valuan_sin_internet(libro, inversion):
    plazo = portafolio.registrar_plazo(libro, inversion, "Cetes 28 días", date(2026, 7, 1), 1000, "10.8", 28)
    a_medias = portafolio.valor_plazo(plazo, date(2026, 7, 15))
    assert a_medias.interes_hoy == D("4.20") and not a_medias.vencido          # 1000 × 10.8 % × 14 / 360
    vencido = portafolio.valor_plazo(plazo, date(2026, 9, 1))
    assert vencido.vencido and vencido.valor_hoy == vencido.valor_al_vencer == D("1008.40")
    assert vencido.vence == date(2026, 7, 29)


def test_registrar_rendimiento_solo_agrega_lo_nuevo(libro, inversion):
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "FICT", 10, 100)
    val = portafolio.valuar(libro, inversion, {"FICT": (D(110), "MXN")}, {}, date(2026, 7, 20))
    op = portafolio.registrar_rendimiento(libro, inversion, val, date(2026, 7, 20))
    assert op.tipo is TipoOperacion.RENDIMIENTO and cuentas.saldo(libro, inversion) == D(1100)
    assert reportes.resumen(libro, date(2026, 7, 1), date(2026, 7, 31)).ingresos == D(100)

    otra_vez = portafolio.valuar(libro, inversion, {"FICT": (D(110), "MXN")}, {})
    assert otra_vez.por_registrar == 0 and portafolio.registrar_rendimiento(libro, inversion, otra_vez) is None

    baja = portafolio.valuar(libro, inversion, {"FICT": (D(105), "MXN")}, {})
    portafolio.registrar_rendimiento(libro, inversion, baja, date(2026, 7, 25))
    assert cuentas.saldo(libro, inversion) == D(1050)                        # bajó: rendimiento negativo

    portafolio.registrar_venta(libro, inversion, date(2026, 7, 28), "FICT", 10, 105)   # vende todo
    vendido = portafolio.valuar(libro, inversion, {}, {})
    assert vendido.ganancia_realizada == D(50) and vendido.por_registrar == 0  # ya estaba registrada


def test_sin_precio_no_se_registra(libro, inversion):
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "FICT", 1, 100)
    with pytest.raises(ErrorValidacion, match="Falta el precio de: FICT"):
        portafolio.registrar_rendimiento(libro, inversion, portafolio.valuar(libro, inversion, {}, {}))


def test_se_guardan_en_respaldos_y_protegen_la_cuenta(libro, inversion):
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "FICT", "1.5", "99.99", moneda="USD",
                                tipo_cambio="18.1234")
    portafolio.registrar_plazo(libro, inversion, "Pagaré ficticio", date(2026, 7, 1), 500, 9, 91)
    copia = libro_desde_instantanea(instantanea(libro), libro.secuencia, reloj=libro.reloj)
    assert copia.valores() == libro.valores() and copia.plazos() == libro.plazos()
    vacia = cuentas.crear(libro, "Inversión vacía ficticia", TipoCuenta.INVERSION)
    portafolio.registrar_plazo(libro, vacia.id, "Cetes", date(2026, 7, 1), 100, 10, 28)
    assert cuentas.eliminar_cuenta(libro, vacia.id) == cuentas.GUARDADA     # no se borra con títulos dentro


# ------------------------------------------------------------ cotizaciones


def _respuesta(simbolo, precio, moneda="MXN"):
    return json.dumps({"chart": {"result": [{"meta": {
        "symbol": simbolo, "currency": moneda, "regularMarketPrice": precio, "regularMarketTime": 1790000000,
        "longName": f"Empresa ficticia {simbolo}"}}], "error": None}})


def test_consultar_trae_precios_y_tipo_de_cambio():
    enviados = []

    def falso(simbolo):
        enviados.append(simbolo)
        return {"FICT.MX": _respuesta("FICT.MX", 52.5), "FUSD": _respuesta("FUSD", 10.25, "USD"),
                "USDMXN=X": _respuesta("USDMXN=X", 18.9)}[simbolo]

    consulta = cotizaciones.consultar(["FICT.MX", "FUSD", "FICT.MX"], enviar=falso)
    precios = consulta.precios
    assert precios["FICT.MX"].precio == D("52.5") and precios["FUSD"].moneda == "USD"
    assert consulta.tipos == {"USD": D("18.9")} and consulta.aviso == "" and not consulta.falla_proveedor
    assert sorted(enviados) == ["FICT.MX", "FUSD", "USDMXN=X"]             # solo símbolos, una vez cada uno


def test_sin_conexion_avisa_de_inmediato():
    llamadas = []

    def sin_red(simbolo):
        llamadas.append(simbolo)
        raise urllib.error.URLError("red bloqueada")

    consulta = cotizaciones.consultar(["A", "B", "C"], enviar=sin_red)
    assert llamadas == ["A"] and consulta.sin_conexion and all(c.sin_conexion for c in consulta.precios.values())
    assert "escribe los precios a mano" in consulta.aviso and consulta.tipos == {}
    assert not consulta.falla_proveedor                                   # no es culpa del proveedor


def test_simbolo_inexistente_y_respuestas_raras():
    def falso(simbolo):
        if simbolo == "NOEXISTE":
            return json.dumps({"chart": {"result": None, "error": {"description": "No data found"}}})
        if simbolo == "ROTO":
            return "<html>cambió</html>"
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)

    consulta = cotizaciones.consultar(["NOEXISTE", "ROTO", "OTRO"], enviar=falso)
    precios = consulta.precios
    assert "revisa el símbolo" in precios["NOEXISTE"].error and "no se pudo leer" in precios["ROTO"].error
    assert "revisa el símbolo" in precios["OTRO"].error and "NOEXISTE" in consulta.aviso
    assert consulta.falla_proveedor                    # hubo conexión y ninguna respuesta sirvió: ¿cambió Yahoo?


def test_enviar_rechaza_simbolos_raros_sin_salir_a_internet():
    with pytest.raises(ValueError):
        cotizaciones.enviar("../../etc")
    assert Decimal(1)  # el módulo no se conecta al importarse


def test_si_el_proveedor_cambia_o_desaparece_se_detecta():
    def caido(simbolo):
        raise urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)

    consulta = cotizaciones.consultar(["FICT", "OTRO"], enviar=caido)
    assert consulta.falla_proveedor and not consulta.sin_conexion
    parcial = cotizaciones.consultar(["FICT", "OTRO"], enviar=lambda s: _respuesta(s, 1) if s == "FICT" else "x")
    assert not parcial.falla_proveedor                                   # uno sí respondió: no es caída general


def test_los_ultimos_precios_se_guardan_en_la_pc_y_sobreviven_sin_conexion(tmp_path):
    ruta = tmp_path / "Datos" / "precios.json"
    buena = cotizaciones.consultar(["FICT.MX", "FUSD"], enviar=lambda s: {
        "FICT.MX": _respuesta("FICT.MX", 52.5), "FUSD": _respuesta("FUSD", 10, "USD"),
        "USDMXN=X": _respuesta("USDMXN=X", 18.9)}[s])
    cotizaciones.guardar(buena, ruta)

    def sin_red(simbolo):
        raise urllib.error.URLError("sin internet")

    cotizaciones.guardar(cotizaciones.consultar(["FICT.MX"], enviar=sin_red), ruta)   # no borra lo anterior
    precios, tipos = cotizaciones.ultimos(ruta)
    assert precios["FICT.MX"].valor == D("52.5") and precios["FUSD"].moneda == "USD" and tipos["USD"].valor == D("18.9")
    guardado = json.loads(ruta.read_text(encoding="utf-8"))
    assert set(guardado["precios"]["FICT.MX"]) == {"valor", "moneda", "actualizado"}  # solo datos públicos
    ruta.write_text("dañado", encoding="utf-8")
    assert cotizaciones.ultimos(ruta) == ({}, {})                         # archivo dañado: se ignora
