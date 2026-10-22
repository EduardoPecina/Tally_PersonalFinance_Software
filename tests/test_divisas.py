"""Cuentas en otra moneda y tipos de cambio (motor/divisas.py). Todos los datos son ficticios."""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import AHORA, D
from motor import (
    categorias,
    contabilidad,
    cuentas,
    divisas,
    evolucion,
    importacion,
    metas,
    movimientos,
    perfil,
    portafolio,
    prestamos,
    recurrentes,
    reportes,
    salud,
)
from motor.errores import ErrorValidacion
from motor.importacion import leer
from motor.modelo import Operacion, Partida, TipoCuenta, TipoOperacion
from motor.serializacion import instantanea, libro_desde_instantanea
from motor.sesion import Sesion
from motor.transferencias import registrar_transferencia

INICIO = date(2026, 1, 2)


@pytest.fixture
def lib(libro):
    """Pesos mexicanos, con dólares a 17 en enero y a 18 desde junio, y euros a 20."""
    perfil.configurar(libro, "Usuario Ficticio", "MXN")
    divisas.guardar_tipo(libro, "USD", INICIO, 17)
    divisas.guardar_tipo(libro, "USD", date(2026, 6, 1), "18.00")
    divisas.guardar_tipo(libro, "EUR", INICIO, 20)
    return libro


@pytest.fixture
def ctas(lib):
    debito = cuentas.crear(lib, "Débito Ficticio", "debito", saldo_inicial=10_000, fecha_creacion=INICIO)
    dolares = cuentas.crear(lib, "Dólares Ficticios", "ahorro", saldo_inicial=1_000, fecha_creacion=INICIO,
                            moneda="USD")
    euros = cuentas.crear(lib, "Euros de Viaje", "efectivo", saldo_inicial=100, fecha_creacion=INICIO, moneda="EUR")
    return debito.id, dolares.id, euros.id


def gasto(lib, nombre="ALIMENTOS"):
    return categorias.buscar(lib, nombre).id


# ------------------------------------------------------------------ cuentas


def test_la_cuenta_lleva_su_saldo_en_su_moneda_y_vale_en_la_tuya(lib, ctas):
    _, dolares, _ = ctas
    assert divisas.moneda_de(lib, dolares) == "USD"
    assert cuentas.saldo(lib, dolares) == D(1000)                        # como en tu banco
    assert lib.saldo_en_base(dolares) == 17_000_00                       # lo que valían al entrar (a 17)
    assert divisas.valor(lib, dolares) == 18_000_00                      # lo que valen hoy (a 18)
    assert divisas.valor(lib, dolares, date(2026, 3, 1)) == 17_000_00
    assert divisas.ajuste(lib) == 1_000_00 + 0                           # +1,000 por el dólar (el euro no cambió)
    (inicial,) = lib.operaciones(cuenta_id=dolares)
    assert inicial.partidas_de_cuenta()[0].original == 1_000_00
    assert sum(p.importe for p in inicial.partidas) == 0                 # cuadra en tu moneda
    assert cuentas.saldo_inicial(lib, dolares) == (D(1000), INICIO)


def test_solo_algunas_cuentas_pueden_estar_en_otra_moneda(lib):
    for tipo in ("credito", "prestamo", "bien", "por_cobrar"):
        with pytest.raises(ErrorValidacion, match="van en tu moneda"):
            cuentas.crear(lib, f"Cuenta {tipo}", tipo, moneda="USD")
    assert cuentas.crear(lib, "Inversión en dólares", "inversion", moneda="usd").moneda == "USD"
    assert cuentas.crear(lib, "En mi moneda", "debito", moneda="MXN").moneda == ""        # la tuya: vacía
    with pytest.raises(ErrorValidacion, match="No conozco"):
        cuentas.crear(lib, "Rara", "debito", moneda="XYZ")


def test_sin_tipo_de_cambio_no_se_puede_crear_con_saldo(lib):
    with pytest.raises(ErrorValidacion, match="Falta el tipo de cambio"):
        cuentas.crear(lib, "Libras", "ahorro", saldo_inicial=50, moneda="GBP")
    assert cuentas.buscar(lib, "Libras") is None                         # ni la cuenta queda a medias
    sin_saldo = cuentas.crear(lib, "Libras", "ahorro", moneda="GBP")
    assert divisas.valor(lib, sin_saldo.id) == 0


def test_cambiar_la_moneda_solo_sin_movimientos(lib, ctas):
    debito, dolares, _ = ctas
    nueva = cuentas.crear(lib, "Otra", "ahorro", saldo_inicial=500, fecha_creacion=INICIO)
    cuentas.cambiar_moneda(lib, nueva.id, "EUR")
    assert cuentas.saldo(lib, nueva.id) == D(500) and divisas.valor(lib, nueva.id) == 10_000_00   # 500 € a 20
    cuentas.cambiar_moneda(lib, nueva.id, "")
    assert lib.cuenta(nueva.id).moneda == "" and divisas.valor(lib, nueva.id) == 500_00
    registrar_transferencia(lib, date(2026, 2, 1), debito, dolares, 170)
    with pytest.raises(ErrorValidacion, match="ya no se puede cambiar"):
        cuentas.cambiar_moneda(lib, dolares, "EUR")
    with pytest.raises(ErrorValidacion, match="van en tu moneda"):
        cuentas.cambiar_tipo(lib, dolares, TipoCuenta.CREDITO)


def test_tu_moneda_no_cambia_si_tienes_cuentas_en_otra(lib, ctas):
    with pytest.raises(ErrorValidacion, match="cuentas en otra moneda"):
        perfil.ajustar(lib, moneda="USD")
    perfil.ajustar(lib, moneda="MXN")                                     # la misma: no pasa nada


# -------------------------------------------------------------- movimientos


def test_gasto_repartido_en_dolares(lib, ctas):
    _, dolares, _ = ctas
    op = movimientos.registrar_gasto(lib, date(2026, 7, 1), dolares,
                                     reparto=[(gasto(lib), "30.00"), (gasto(lib, "RESTAURANTES"), "20.01")])
    (cuenta,) = op.partidas_de_cuenta()
    assert (cuenta.original, cuenta.importe) == (-50_01, -900_18)        # 50.01 dólares a 18
    assert sorted(p.importe for p in op.partidas_de_categoria()) == [360_18, 540_00]    # en proporción
    detalle = movimientos.describir(op)
    assert detalle.monto == D("50.01")
    assert sorted(m for _, m in detalle.reparto) == [D("20.01"), D("30.00")]     # en dólares, como lo escribiste
    assert reportes.resumen(lib, date(2026, 7, 1), date(2026, 7, 31)).gastos == D("900.18")


def test_transferencias_entre_monedas(lib, ctas):
    debito, dolares, euros = ctas
    dia = date(2026, 7, 2)
    calculada = registrar_transferencia(lib, dia, debito, dolares, 1_800)               # 1,800 pesos → 100 dólares
    assert {p.cuenta_id: (p.importe, p.original) for p in calculada.partidas} == {
        debito: (-1_800_00, None), dolares: (1_800_00, 100_00)}
    real = registrar_transferencia(lib, dia, debito, dolares, 1_800, llega="99.10")     # con la comisión del banco
    assert movimientos.describir(real).llega == D("99.10")
    regreso = registrar_transferencia(lib, dia, dolares, debito, 10)                    # 10 dólares → 180 pesos
    assert movimientos.describir(regreso).llega == D(180)
    a_euros = registrar_transferencia(lib, dia, dolares, euros, 100)                    # 1,800 pesos → 90 euros
    assert {p.cuenta_id: p.original for p in a_euros.partidas} == {dolares: -100_00, euros: 90_00}
    entre_dolares = registrar_transferencia(
        lib, dia, dolares, cuentas.crear(lib, "Más dólares", "efectivo", moneda="USD").id, 5)
    assert sorted(p.original for p in entre_dolares.partidas) == [-5_00, 5_00]
    assert movimientos.describir(entre_dolares).llega is None
    with pytest.raises(ErrorValidacion, match="misma moneda"):
        divisas.transferencia(lib, dia, dolares, entre_dolares.partidas[1].cuenta_id, 5, 6)
    assert cuentas.saldo(lib, dolares) == D(1000) + D(100) + D("99.10") - 10 - 100 - 5


def test_editar_y_duplicar_vuelven_a_convertir(lib, ctas):
    debito, dolares, _ = ctas
    op = movimientos.registrar_gasto(lib, date(2026, 7, 1), dolares, gasto(lib), 10)
    assert op.partidas_de_cuenta()[0].importe == -180_00
    movida = movimientos.editar(lib, op.id, fecha=date(2026, 3, 1))                     # en marzo el dólar valía 17
    assert movida.partidas_de_cuenta()[0].importe == -170_00
    assert movimientos.editar(lib, op.id, monto=20).partidas_de_cuenta()[0].original == -20_00
    copia = movimientos.duplicar(lib, op.id, date(2026, 7, 5))
    assert copia.partidas_de_cuenta()[0].importe == -360_00
    t = registrar_transferencia(lib, date(2026, 7, 2), debito, dolares, 1_800, llega=99)
    movida = movimientos.editar(lib, t.id, fecha=date(2026, 7, 3))                      # conserva lo que llegó
    assert movimientos.describir(movida).llega == D(99)
    assert movimientos.describir(movimientos.editar(lib, t.id, llega=98)).llega == D(98)


def test_cambiar_un_movimiento_a_una_cuenta_de_otra_moneda_conserva_su_valor(lib, ctas):
    debito, dolares, euros = ctas
    dia = date(2026, 7, 1)
    op = movimientos.registrar_gasto(lib, dia, debito, gasto(lib), 180)
    a_dolares = movimientos.editar(lib, op.id, cuenta_id=dolares)                       # 180 pesos = 10 dólares
    assert [(p.importe, p.original) for p in a_dolares.partidas_de_cuenta()] == [(-180_00, -10_00)]
    assert movimientos.describir(movimientos.editar(lib, op.id, cuenta_id=debito)).monto == D(180)
    repartido = movimientos.registrar_gasto(lib, dia, debito,
                                            reparto=[(gasto(lib), 90), (gasto(lib, "RESTAURANTES"), 270)])
    detalle = movimientos.describir(movimientos.editar(lib, repartido.id, cuenta_id=dolares))
    assert detalle.monto == D(20) and sorted(m for _, m in detalle.reparto) == [D(5), D(15)]
    ingreso = movimientos.registrar_ingreso(lib, dia, dolares, gasto(lib, "NOMINA"), 100)
    assert movimientos.describir(movimientos.editar(lib, ingreso.id, cuenta_id=euros)).monto == D(90)
    t = registrar_transferencia(lib, dia, debito, euros, 1_800)                         # 1,800 pesos → 90 euros
    volteada = movimientos.editar(lib, t.id, cuenta_id=dolares, cuenta_destino_id=debito)
    assert {p.cuenta_id: (p.importe, p.original) for p in volteada.partidas} == {
        dolares: (-1_800_00, -100_00), debito: (1_800_00, None)}
    assert movimientos.editar(lib, op.id, cuenta_id=dolares, monto=7).partidas_de_cuenta()[0].original == -7_00
    cambio = registrar_transferencia(lib, dia, dolares, debito, 10, llega=175)            # el banco te dio 175
    otra_de_pesos = cuentas.crear(lib, "Otra de pesos", "ahorro", fecha_creacion=INICIO).id
    otros_dolares = cuentas.crear(lib, "Otros dólares", "efectivo", fecha_creacion=INICIO, moneda="USD").id
    assert movimientos.describir(movimientos.editar(lib, cambio.id, cuenta_destino_id=otra_de_pesos)).llega == D(175)
    assert movimientos.describir(movimientos.editar(lib, cambio.id, cuenta_id=otros_dolares)).llega == D(175)
    a_euros = movimientos.editar(lib, cambio.id, cuenta_destino_id=euros)               # otra moneda: se calcula
    assert movimientos.describir(a_euros).llega == D(9)


def test_sin_tu_moneda_aun_no_hay_cuentas_en_otra(libro):
    with pytest.raises(ErrorValidacion, match="Primero elige tu moneda"):
        cuentas.crear(libro, "Dólares Ficticios", "ahorro", moneda="USD")
    assert cuentas.listar(libro) == []


def test_ajustar_el_saldo_en_dolares(lib, ctas):
    _, dolares, _ = ctas
    op = movimientos.actualizar_saldo(lib, dolares, "1012.50", date(2026, 7, 1))
    assert op.partidas_de_cuenta()[0].original == 12_50 and cuentas.saldo(lib, dolares) == D("1012.50")


def test_pasar_un_gasto_en_dolares_a_transferencia(lib, ctas):
    debito, dolares, _ = ctas
    op = movimientos.registrar_ingreso(lib, date(2026, 7, 1), dolares, gasto(lib, "NOMINA"), 100)
    nueva = movimientos.a_transferencia(lib, op.id, debito)                             # vino de tu débito
    assert {p.cuenta_id: (p.importe, p.original) for p in nueva.partidas} == {
        debito: (-1_800_00, None), dolares: (1_800_00, 100_00)}


def test_el_libro_rechaza_importes_que_no_cuadran(lib, ctas):
    debito, dolares, _ = ctas
    malas = [
        (Partida(-100, cuenta_id=dolares, original=5), Partida(100, cuenta_id=debito)),        # signo distinto
        (Partida(-100, cuenta_id=debito, original=-100), Partida(100, cuenta_id=dolares, original=6)),  # tu moneda
    ]
    for partidas in malas:
        with pytest.raises(ErrorValidacion):
            lib.agregar_operacion(Operacion(date(2026, 7, 1), TipoOperacion.TRANSFERENCIA, partidas))
    divisas.guardar_tipo(lib, "COP", INICIO, "0.0045")
    colombianos = cuentas.crear(lib, "Pesos colombianos", "efectivo", moneda="COP").id
    with pytest.raises(ErrorValidacion, match="da cero"):
        movimientos.registrar_gasto(lib, date(2026, 7, 1), colombianos, gasto(lib), "0.01")


# --------------------------------------------------------- tipos de cambio


def test_el_tipo_de_cambio_de_cada_dia(lib):
    assert divisas.tipo(lib, "USD", date(2025, 12, 1)) == 17                 # antes del primero: el primero
    assert divisas.tipo(lib, "USD", date(2026, 5, 31)) == 17
    assert divisas.tipo(lib, "USD", date(2026, 6, 1)) == 18
    assert divisas.tipo(lib, "MXN") == 1 and divisas.tipo(lib, "GBP") is None
    with pytest.raises(ErrorValidacion, match="futura"):
        divisas.guardar_tipo(lib, "USD", AHORA.date() + timedelta(days=1), 19)
    with pytest.raises(ErrorValidacion, match="mayor que cero"):
        divisas.guardar_tipo(lib, "USD", INICIO, 0)
    with pytest.raises(ErrorValidacion, match="tu moneda"):
        divisas.guardar_tipo(lib, "MXN", INICIO, 1)
    assert divisas.leer_tipo(17.123456789) == D("17.12345679")


def test_lo_de_internet_no_pisa_lo_que_escribiste(lib):
    cambiados = divisas.de_internet(lib, {"USD": {INICIO: D("17.5"), date(2026, 2, 1): D("17.25")},
                                          "MXN": {INICIO: D(1)}, "XYZ": {INICIO: D(3)}})
    assert cambiados == 1
    assert divisas.tipo(lib, "USD", INICIO) == 17                            # el tuyo manda
    assert divisas.tipo(lib, "USD", date(2026, 2, 1)) == D("17.25")
    assert divisas.de_internet(lib, {"USD": {date(2026, 2, 1): D("17.25")}}) == 0


def _historial(simbolo, cierres, moneda="MXN"):
    tiempos = [int(datetime(d.year, d.month, d.day, 14, 30, tzinfo=timezone.utc).timestamp()) for d in cierres]
    return json.dumps({"chart": {"result": [{
        "meta": {"symbol": simbolo, "currency": moneda, "gmtoffset": 0}, "timestamp": tiempos,
        "indicators": {"quote": [{"close": [float(p) for p in cierres.values()]}]}}], "error": None}})


def test_consultar_trae_el_par_o_lo_cruza_con_el_dolar():
    dia = date(2026, 7, 1)
    enviados = []

    def falso(simbolo, rango):
        enviados.append(simbolo)
        respuestas = {"USDMXN=X": {dia: 18.0}, "EURMXN=X": {dia: 20.0}, "USDCUP=X": {dia: 24.0}}
        if simbolo not in respuestas:
            return json.dumps({"chart": {"result": None, "error": {"description": "No data found"}}})
        return _historial(simbolo, respuestas[simbolo])

    consulta = divisas.consultar({"USD": dia, "EUR": dia, "CUP": dia}, "MXN", dia, falso)
    assert consulta.series["USD"] == {dia: D(18)} and consulta.series["EUR"] == {dia: D(20)}
    assert consulta.series["CUP"] == {dia: D("0.75")}                         # 18 pesos ÷ 24 pesos cubanos
    assert not consulta.aviso and all(s.endswith("=X") for s in enviados)    # solo pares de monedas


def test_consultar_sin_conexion_y_sin_datos():
    def sin_red(simbolo, rango):
        raise OSError("sin red ficticia")

    consulta = divisas.consultar({"USD": date(2026, 7, 1)}, "MXN", date(2026, 7, 1), sin_red)
    assert consulta.sin_conexion and not consulta.series
    nada = divisas.consultar({"VES": date(2026, 7, 1)}, "MXN", date(2026, 7, 1),
                             lambda s, r: json.dumps({"chart": {"result": None, "error": None}}))
    assert "escríbelo a mano" in nada.aviso
    assert divisas.consultar({}, "MXN", date(2026, 7, 1)).series == {}


def test_que_pedir_a_internet(lib, ctas):
    hoy = AHORA.date()
    assert divisas.pendientes(lib, hoy) == {"EUR": INICIO, "USD": date(2026, 6, 1)}
    divisas.de_internet(lib, {"USD": {hoy: D(18)}, "EUR": {hoy: D(20)}})
    assert divisas.pendientes(lib, hoy) == {}


# ------------------------------------------------------- patrimonio y reportes


def test_patrimonio_e_indicadores_al_tipo_de_cambio_de_cada_dia(lib, ctas):
    ind = reportes.indicadores(lib)
    assert ind.patrimonio_neto == D(10_000 + 18_000 + 2_000)
    assert ind.por_tipo_de_cambio == D(1_000)
    assert reportes.indicadores(lib, date(2026, 3, 1)).patrimonio_neto == D(10_000 + 17_000 + 2_000)
    puntos = {p.fecha: p.patrimonio_neto for p in reportes.evolucion(lib, date(2026, 5, 30), date(2026, 6, 2))}
    assert puntos[date(2026, 5, 31)] == D(29_000) and puntos[date(2026, 6, 1)] == D(30_000)


def test_la_contabilidad_cuadra_con_la_diferencia_por_tipo_de_cambio(lib, ctas):
    debito, dolares, euros = ctas
    movimientos.registrar_gasto(lib, date(2026, 7, 1), dolares, gasto(lib), 50)
    registrar_transferencia(lib, date(2026, 7, 2), debito, euros, 2_000)
    hoy = AHORA.date()
    situacion = contabilidad.situacion(lib, [hoy, date(2026, 3, 31)], INICIO)
    assert situacion.cuadra
    nombres = {r.nombre: r.importes for r in situacion.renglones}
    # Los 1,000 dólares iniciales subieron un peso cada uno (también los 50 que se gastaron cuando ya valían 18).
    assert nombres["Diferencia por tipo de cambio · Dólares Ficticios"] == (D(1000), D(0))
    resultados = contabilidad.resultados(lib, [(INICIO, hoy)])
    cambio = next(r for r in resultados.cambios_de_valor if r.nombre == contabilidad.TIPO_DE_CAMBIO)
    assert cambio.importes == (D(1000),)
    assert [m.importe for m in contabilidad.movimientos(lib, cambio.origen)] == [D(1000)]
    assert contabilidad.balanza(lib, date(2026, 4, 1), hoy).cuadra
    flujo = contabilidad.flujo(lib, [(date(2026, 4, 1), hoy)])
    assert flujo.cuadra and contabilidad.FLUJO_CAMBIO in flujo.secciones()


def test_el_historial_muestra_las_dos_cifras(lib, ctas):
    from motor import consultas

    _, dolares, _ = ctas
    movimientos.registrar_gasto(lib, date(2026, 7, 1), dolares, gasto(lib), 50, "Comida ficticia")
    (fila,) = consultas.buscar(lib, texto="Comida ficticia")
    assert (fila.monto, fila.moneda, fila.monto_original) == (D(900), "USD", D(50))
    estado = consultas.movimientos_de_cuenta(lib, dolares)
    assert (estado[0].cargo, estado[0].saldo) == (D(50), D(950))            # el estado de cuenta, en dólares


# ---------------------------------------------- inversiones, metas, préstamos


def test_inversion_en_dolares(lib):
    cuenta = cuentas.crear(lib, "Broker Ficticio", "inversion", saldo_inicial=1_000, fecha_creacion=INICIO,
                           moneda="USD").id
    portafolio.registrar_compra(lib, cuenta, date(2026, 2, 1), "FICT", 10, 50, moneda="USD")    # sin tipo de cambio
    (posicion,) = portafolio.posiciones(lib, cuenta)
    assert posicion.costo == D(500)                                          # en dólares
    valuacion = portafolio.valuar(lib, cuenta, {"FICT": (D(60), "USD")}, {"USD": D(18)})
    assert valuacion.valor_titulos == D(600) and valuacion.ganancia_no_realizada == D(100)
    en_pesos = portafolio.valuar(lib, cuenta, {"FICT": (D(1080), "MXN")}, {"USD": D(18)})
    assert en_pesos.valor_titulos == D(600)                                  # 10 × 1,080 pesos ÷ 18
    op = portafolio.ajustar_a_valor_oficial(lib, cuenta, "1100", date(2026, 7, 1))
    assert op.partidas_de_cuenta()[0].original == 100_00 and op.partidas_de_cuenta()[0].importe == 1_800_00
    assert "US$1,100.00" in op.descripcion
    assert reportes.resumen(lib, date(2026, 7, 1), date(2026, 7, 31)).ingresos == D(1800)
    evo = evolucion.oficial(lib, [cuenta], date(2026, 5, 31), date(2026, 7, 1))
    assert evo.valores["Broker Ficticio"][0] == D(17_000) and evo.valores["Broker Ficticio"][-1] == D(19_800)


def test_metas_y_prestamos_pagados_desde_dolares(lib, ctas):
    debito, dolares, _ = ctas
    meta = metas.crear(lib, "Viaje Ficticio", 9_000, cuenta_id=dolares)
    metas.aportar(lib, meta.id, 1_800, date(2026, 7, 1), desde=debito)        # 1,800 pesos → 100 dólares
    assert cuentas.saldo(lib, dolares) == D(1_100)
    metas.aportar(lib, meta.id, 900, date(2026, 7, 1), desde=cuentas.crear(
        lib, "Más dólares", "ahorro", saldo_inicial=100, fecha_creacion=INICIO, moneda="USD").id)
    assert cuentas.saldo(lib, dolares) == D(1_150)                           # 900 pesos = 50 dólares
    (por_cuenta,) = metas.por_cuenta(lib)
    assert por_cuenta.saldo == D(1_150 * 18)                                 # en tu moneda, como la meta
    prestamo = prestamos.crear(lib, "Préstamo Ficticio", "personal", 10_000, 12, 12, INICIO, deuda_actual=5_000)
    prestamos.registrar_pago(lib, prestamo.cuenta_id, AHORA.date(), 1_800, dolares, interes=0, iva=0)
    assert cuentas.saldo(lib, dolares) == D(1_050)                           # 1,800 pesos = 100 dólares
    assert prestamos.deuda_al(lib, prestamo.cuenta_id, AHORA.date()) == D(3_200)


def test_recurrentes_en_dolares_cuentan_en_tu_moneda(lib, ctas):
    _, dolares, _ = ctas
    cuentas.editar(lib, dolares, en_disponible=True)
    r = recurrentes.crear(lib, "Suscripción Ficticia", "gasto", 10, dolares, "mensual", date(2026, 7, 25),
                          categoria_id=gasto(lib), suscripcion=True)
    assert recurrentes.al_mes(r) == D(10) and recurrentes.al_mes(r, lib) == D(180)
    assert recurrentes.totales(lib).suscripciones_al_mes == D(180)
    flujo = recurrentes.flujo(lib, AHORA.date(), 10)
    assert flujo.disponible - flujo.final == 180_00
    op = recurrentes.registrar(lib, r.id, date(2026, 7, 25))
    assert op.partidas_de_cuenta()[0].original == -10_00
    assert recurrentes.pagos(lib, r, [date(2026, 7, 25)])[date(2026, 7, 25)].id == op.id


# ------------------------------------------------------------- importar


def test_cargar_un_bloque_en_dolares_sin_duplicar(lib, ctas):
    texto = (
        "CUENTA: Dólares Ficticios\nFECHA\tDESCRIPCION\tSUBCATEGORIA\tCARGO\tABONO\tNOTAS\n"
        "01/07/2026\tComida ficticia\tALIMENTOS\t50.00\t\t\n"
        "02/07/2026\tDe mi débito\tDébito Ficticio\t\t100.00\t\n"
    )
    importacion.cargar(lib, leer(texto))
    _, dolares, _ = ctas
    assert cuentas.saldo(lib, dolares) == D(1_050)                           # los importes del bloque, en dólares
    debito = lib.cuenta(ctas[0])
    assert cuentas.saldo(lib, debito.id) == D(10_000 - 1_800)               # lo que salió del débito
    otra_vez = importacion.vista_previa(lib, leer(texto))
    assert otra_vez.contar(importacion.YA_ESTABA) == 2 and not otra_vez.nuevos


# --------------------------------------------------------------- guardar


def test_se_guarda_y_se_lee_igual(lib, ctas, tmp_path):
    _, dolares, _ = ctas
    movimientos.registrar_gasto(lib, date(2026, 7, 1), dolares, gasto(lib), 50)
    copia = libro_desde_instantanea(instantanea(lib))
    assert copia.tipos_cambio() == lib.tipos_cambio()
    assert copia.cuenta(dolares).moneda == "USD"
    assert copia.operaciones() == lib.operaciones()
    sesion = Sesion(tmp_path / "Datos" / "tally.db", reloj=lambda: AHORA)
    with sesion.cambio() as nuevo:
        perfil.configurar(nuevo, "Usuario Ficticio")
        divisas.guardar_tipo(nuevo, "USD", INICIO, 17)
        cuentas.crear(nuevo, "Dólares", "ahorro", saldo_inicial=10, fecha_creacion=INICIO, moneda="USD")
    leido = Sesion(tmp_path / "Datos" / "tally.db", reloj=lambda: AHORA).libro
    cuenta = cuentas.buscar(leido, "Dólares")
    assert cuentas.saldo(leido, cuenta.id) == D(10) and divisas.valor(leido, cuenta.id) == 170_00


def test_los_datos_de_antes_quedan_en_tu_moneda(lib, ctas):
    """Antes de la 0.32 «moneda» de la cuenta no se usaba (siempre MXN, aunque tu moneda fuera otra)."""
    datos = instantanea(lib)
    datos["cuenta"] = {i: {**{k: v for k, v in d.items() if k != "divisa"}, "moneda": "MXN"}
                       for i, d in datos["cuenta"].items() if "divisa" not in d}
    datos["operacion"] = {i: d for i, d in datos["operacion"].items()
                          if all(p.get("cuenta_id") in datos["cuenta"] or p.get("cuenta_id") is None
                                 for p in d["partidas"])}
    datos["perfil"]["perfil"]["moneda"] = "EUR"
    viejo = libro_desde_instantanea(datos)
    assert all(c.moneda == "" for c in viejo.cuentas()) and not divisas.cuentas_en_otra_moneda(viejo)


# --------------------------------------------------------------- salud


def test_salud_avisa_si_falta_o_esta_viejo_el_tipo_de_cambio(lib, ctas):
    claves = {h.clave.split(":")[0] for h in salud.revisar(lib, AHORA.date()).hallazgos}
    assert "tipo_viejo" in claves                                            # el último es de junio
    cuentas.crear(lib, "Libras", "ahorro", moneda="GBP")
    claves = {h.clave for h in salud.revisar(lib, AHORA.date()).hallazgos}
    assert "sin_tipo:GBP" in claves


# ------------------------------------------------- índices de saldos al azar


def test_los_saldos_en_las_dos_monedas_coinciden_con_recorrer_todo(lib, ctas):
    rnd = random.Random(7)
    ids = list(ctas)
    for paso in range(150):
        dia = INICIO + timedelta(days=rnd.randint(0, 190))
        origen, destino = rnd.sample(ids, 2)
        if rnd.random() < 0.5:
            movimientos.registrar_gasto(lib, dia, origen, gasto(lib), rnd.randint(1, 50))
        else:
            registrar_transferencia(lib, dia, origen, destino, rnd.randint(1, 50),
                                    llega=rnd.choice([None, rnd.randint(1, 900)]))
        if paso % 25 == 0:
            for cuenta_id in ids:
                al = INICIO + timedelta(days=rnd.randint(0, 190))
                partidas = [p for op in lib.operaciones() if op.fecha <= al for p in op.partidas
                            if p.cuenta_id == cuenta_id]
                assert lib.saldo_centavos(cuenta_id, al) == sum(p.en_su_moneda for p in partidas)
                assert lib.saldo_en_base(cuenta_id, al) == sum(p.importe for p in partidas)
    assert all(sum(p.importe for p in op.partidas) == 0 for op in lib.operaciones())
    assert contabilidad.situacion(lib, [AHORA.date()]).cuadra
