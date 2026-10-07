"""Títulos, inversiones a plazo y consulta de precios. Datos ficticios; nunca se sale a internet."""

import json
import urllib.error
from datetime import date, datetime, timezone
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


def test_el_rendimiento_se_registra_con_el_valor_oficial_al_centavo(libro, inversion):
    portafolio.registrar_compra(libro, inversion, date(2026, 7, 2), "FICT", 10, 100)
    val = portafolio.valuar(libro, inversion, {"FICT": (D(110), "MXN")}, {}, date(2026, 7, 20))
    assert portafolio.valor_estimado(libro, inversion, val) == D(1100)         # referencia, no se registra
    op = portafolio.ajustar_a_valor_oficial(libro, inversion, "1099.37", date(2026, 7, 15))   # lo que dice la app
    assert op.tipo is TipoOperacion.RENDIMIENTO and op.fecha == date(2026, 7, 15)
    assert "1,099.37" in op.descripcion and cuentas.saldo(libro, inversion) == D("1099.37")
    assert reportes.resumen(libro, date(2026, 7, 1), date(2026, 7, 31)).ingresos == D("99.37")
    assert libro.cuenta(inversion).plusvalia_registrada == 9937

    assert portafolio.ajustar_a_valor_oficial(libro, inversion, D("1099.37"), date(2026, 7, 15)) is None  # ya cuadra
    portafolio.ajustar_a_valor_oficial(libro, inversion, 1050, date(2026, 7, 20))          # bajó: pérdida
    assert cuentas.saldo(libro, inversion) == D(1050)
    assert libro.cuenta(inversion).plusvalia_registrada == 5000


def test_el_valor_oficial_cuenta_contra_el_saldo_de_ese_dia(libro, inversion, ctas):
    registrar_transferencia(libro, date(2026, 7, 10), ctas.debito, inversion, 500, "Otra aportación")
    portafolio.ajustar_a_valor_oficial(libro, inversion, 1020, date(2026, 7, 5))   # antes de la aportación
    assert cuentas.saldo(libro, inversion, date(2026, 7, 5)) == D(1020)
    assert cuentas.saldo(libro, inversion) == D(1520)
    with pytest.raises(ErrorValidacion, match="futura"):
        portafolio.ajustar_a_valor_oficial(libro, inversion, 1000, date(2026, 8, 1))
    with pytest.raises(ErrorValidacion):
        portafolio.ajustar_a_valor_oficial(libro, inversion, -5)
    with pytest.raises(ErrorValidacion, match="Inversión"):
        portafolio.ajustar_a_valor_oficial(libro, ctas.debito, 100)


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


# ------------------------------------------------------- historial de precios


def _historial(simbolo, cierres, moneda="MXN"):
    """Respuesta ficticia con cierres diarios: {fecha: precio} (con huecos y nulos, como el real)."""
    tiempos = [int(datetime(d.year, d.month, d.day, 14, 30, tzinfo=timezone.utc).timestamp()) for d in cierres]
    return json.dumps({"chart": {"result": [{
        "meta": {"symbol": simbolo, "currency": moneda, "gmtoffset": -21600},
        "timestamp": tiempos + [tiempos[-1] + 86400],
        "indicators": {"quote": [{"close": [float(p) for p in cierres.values()] + [None]}]}}], "error": None}})


def test_el_historial_solo_envia_simbolo_y_periodo_estandar():
    enviados = []

    def falso(simbolo, rango):
        enviados.append((simbolo, rango))
        if simbolo == "USDMXN=X":
            return _historial(simbolo, {date(2026, 7, 1): D("18.5"), date(2026, 7, 2): D("18.7")})
        return _historial(simbolo, {date(2026, 7, 1): D(10), date(2026, 7, 2): D("10.5")}, "USD")

    consulta = cotizaciones.consultar_historial({"FUSD": date(2026, 2, 1)}, date(2026, 7, 20), enviar=falso)
    assert enviados == [("FUSD", "6mo"), ("USDMXN=X", "6mo")]          # nunca la fecha exacta ni cantidades
    serie = consulta.series["FUSD"]
    assert serie.moneda == "USD" and serie.cierres == {date(2026, 7, 1): D(10), date(2026, 7, 2): D("10.5")}
    assert consulta.series["USDMXN=X"].cierres[date(2026, 7, 2)] == D("18.7") and consulta.aviso == ""
    assert [cotizaciones.rango_para(date(2026, 7, 1), date(2026, 7, 20)), cotizaciones.rango_para(
        date(2020, 1, 1), date(2026, 7, 20)), cotizaciones.rango_para(date(2000, 1, 1), date(2026, 7, 20))] == [
        "1mo", "10y", "max"]
    with pytest.raises(ValueError):
        cotizaciones.enviar_historial("FUSD", "15y")                    # solo periodos conocidos
    with pytest.raises(ValueError):
        cotizaciones.enviar_historial("../x", "1y")


def test_el_historial_sin_conexion_no_insiste_y_se_guarda_en_la_pc(tmp_path):
    llamadas = []

    def sin_red(simbolo, rango):
        llamadas.append(simbolo)
        raise urllib.error.URLError("red bloqueada")

    consulta = cotizaciones.consultar_historial({"A": date(2026, 7, 1), "B": date(2026, 7, 1)}, date(2026, 7, 20),
                                                enviar=sin_red)
    assert llamadas == ["A"] and consulta.sin_conexion and "guardados" in consulta.aviso

    ruta = tmp_path / "historial_precios.json"
    primera = cotizaciones.consultar_historial({"FICT": date(2026, 7, 1)}, date(2026, 7, 20), enviar=lambda s, r:
                                               _historial(s, {date(2026, 7, 1): D(10)}))
    cotizaciones.guardar_historial(primera, ruta)
    segunda = cotizaciones.consultar_historial({"FICT": date(2026, 7, 2)}, date(2026, 7, 20), enviar=lambda s, r:
                                               _historial(s, {date(2026, 7, 2): D(11)}))
    cotizaciones.guardar_historial(segunda, ruta)
    guardado = cotizaciones.historial_guardado(ruta)
    assert guardado["FICT"].cierres == {date(2026, 7, 1): D(10), date(2026, 7, 2): D(11)}   # se juntan
    assert cotizaciones.desde_pendiente("FICT", date(2026, 7, 1), guardado) == date(2026, 7, 2)  # solo lo nuevo
    assert cotizaciones.desde_pendiente("FICT", date(2025, 1, 1), guardado) == date(2025, 1, 1)  # falta lo viejo
    assert set(json.loads(ruta.read_text(encoding="utf-8"))["series"]["FICT"]) == {"moneda", "actualizado", "cierres"}
    ruta.write_text("dañado", encoding="utf-8")
    assert cotizaciones.historial_guardado(ruta) == {}


def test_respuestas_raras_del_historial():
    vacia = cotizaciones.leer_historial("X", json.dumps({"chart": {"result": None, "error": {"description": "No"}}}))
    assert "revisa el símbolo" in vacia.error and not vacia.falla_proveedor
    assert cotizaciones.leer_historial("X", "<html>").falla_proveedor
    sin_precios = json.dumps({"chart": {"result": [{"meta": {}, "timestamp": [1], "indicators": {"quote": [
        {"close": [None]}]}}]}})
    assert cotizaciones.leer_historial("X", sin_precios).falla_proveedor
