"""Pagos recurrentes, calendario, flujo de 30 días y detección de suscripciones. Solo datos ficticios."""

from datetime import date
from decimal import Decimal

import pytest

from conftest import D
from motor import cuentas, movimientos, recurrentes
from motor.errores import ErrorValidacion
from motor.modelo import TipoOperacion
from motor.recurrentes import PAGADO, PENDIENTE, PRESTAMO, TARJETA, VENCIDO
from motor.serializacion import instantanea, libro_desde_instantanea
from motor.transferencias import registrar_transferencia

HOY = date(2026, 7, 20)


def gasto(libro, ctas, cat, nombre="Renta Ficticia", monto=8000, frecuencia="mensual", inicio=date(2026, 1, 5),
          **extra):
    return recurrentes.crear(libro, nombre, "gasto", monto, ctas.debito, frecuencia, inicio,
                             categoria_id=cat(extra.pop("subcategoria", "RENTA")), **extra)


# ------------------------------------------------------------------ crear


def test_crear_editar_eliminar_y_guardar(libro, ctas, cat):
    r = gasto(libro, ctas, cat, suscripcion=False, notas="  ficticia  ")
    assert (r.nombre, r.monto, r.tipo, r.notas) == ("Renta Ficticia", 800_000, TipoOperacion.GASTO, "ficticia")
    r = recurrentes.editar(libro, r.id, monto="8,500.00", frecuencia="bimestral")
    assert (r.monto, r.frecuencia) == (850_000, "bimestral")
    copia = libro_desde_instantanea(instantanea(libro))
    assert copia.recurrente(r.id) == r
    recurrentes.eliminar(libro, r.id)
    assert libro.recurrentes() == []


def test_validaciones(libro, ctas, cat):
    with pytest.raises(ErrorValidacion, match="mayor que cero"):
        gasto(libro, ctas, cat, monto=0)
    with pytest.raises(ErrorValidacion, match="no es una subcategoría de gasto"):
        gasto(libro, ctas, cat, subcategoria="NOMINA")
    with pytest.raises(ErrorValidacion, match="cada cuánto"):
        gasto(libro, ctas, cat, frecuencia="diario")
    with pytest.raises(ErrorValidacion, match="antes de la primera"):
        gasto(libro, ctas, cat, fin=date(2025, 1, 1))
    with pytest.raises(ErrorValidacion, match="distintas"):
        recurrentes.crear(libro, "Ahorro", "transferencia", 100, ctas.debito, "mensual", HOY, destino_id=ctas.debito)
    with pytest.raises(ErrorValidacion, match="a qué cuenta"):
        recurrentes.crear(libro, "Ahorro", "transferencia", 100, ctas.debito, "mensual", HOY)
    with pytest.raises(ErrorValidacion):
        recurrentes.crear(libro, "Pago", "reembolso", 100, ctas.debito, "mensual", HOY, categoria_id=cat("RENTA"))


# ------------------------------------------------------------------ fechas


@pytest.mark.parametrize("frecuencia, inicio, esperadas", [
    ("mensual", date(2026, 1, 31), [date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30)]),
    ("quincenal", date(2026, 1, 1), [date(2026, 7, 31), date(2026, 8, 15), date(2026, 8, 31), date(2026, 9, 15),
                                     date(2026, 9, 30)]),
    ("semanal", date(2026, 7, 3), [date(2026, 7, 24), date(2026, 7, 31), date(2026, 8, 7)]),
    ("catorcenal", date(2026, 7, 3), [date(2026, 7, 31), date(2026, 8, 14), date(2026, 8, 28)]),
    ("bimestral", date(2026, 3, 10), [date(2026, 9, 10)]),
    ("anual", date(2025, 8, 29), [date(2026, 8, 29)]),
])
def test_fechas(libro, ctas, cat, frecuencia, inicio, esperadas):
    r = gasto(libro, ctas, cat, frecuencia=frecuencia, inicio=inicio)
    assert recurrentes.fechas(r, date(2026, 7, 21), date(2026, 9, 30))[:len(esperadas)] == esperadas


def test_fechas_con_inicio_y_fin(libro, ctas, cat):
    r = gasto(libro, ctas, cat, inicio=date(2026, 8, 5), fin=date(2026, 10, 5))
    assert recurrentes.fechas(r, date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 8, 5), date(2026, 9, 5), date(2026, 10, 5)]
    assert recurrentes.siguiente(r, date(2026, 9, 6)) == date(2026, 10, 5)
    assert recurrentes.siguiente(r, date(2026, 10, 6)) is None


def test_costos_al_mes_y_al_anio(libro, ctas, cat):
    netflix = gasto(libro, ctas, cat, "Streaming Ficticio", 219, subcategoria="STREAMING DE VIDEO", suscripcion=True)
    anual = gasto(libro, ctas, cat, "Nube Ficticia", 1200, frecuencia="anual", subcategoria="ALMACENAMIENTO EN LA NUBE",
                  suscripcion=True)
    gasto(libro, ctas, cat, "Gimnasio Ficticio", 100, frecuencia="semanal", subcategoria="GIMNASIO")
    assert recurrentes.al_mes(anual) == D(100) and recurrentes.al_anio(netflix) == D(2628)
    t = recurrentes.totales(libro)
    assert t.suscripciones == 2 and t.suscripciones_al_mes == D(319) and t.suscripciones_al_anio == D(3828)
    assert t.gastos_al_mes == D("752.33")                     # 219 + 100 + 100 × 52 / 12


# ------------------------------------------------------------------ pagado, registrar


def test_pagado_por_un_movimiento_parecido(libro, ctas, cat):
    luz = gasto(libro, ctas, cat, "Luz Ficticia", 500, frecuencia="bimestral", inicio=date(2026, 3, 10),
                subcategoria="LUZ")
    movimientos.registrar_gasto(libro, date(2026, 5, 12), ctas.debito, cat("LUZ"), 640, "Recibo")   # cambió el monto
    movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, cat("LUZ"), 2000, "Otra cosa")  # demasiado
    dias = recurrentes.fechas(luz, date(2026, 1, 1), date(2026, 7, 31))
    hechos = recurrentes.pagos(libro, luz, dias)
    assert list(hechos) == [date(2026, 5, 10)]


def test_un_movimiento_cubre_una_sola_fecha(libro, ctas, cat):
    r = gasto(libro, ctas, cat, "Semanal", 100, frecuencia="semanal", inicio=date(2026, 7, 6), subcategoria="DESPENSA")
    movimientos.registrar_gasto(libro, date(2026, 7, 10), ctas.debito, cat("DESPENSA"), 100, "Una vez")
    hechos = recurrentes.pagos(libro, r, recurrentes.fechas(r, date(2026, 7, 1), date(2026, 7, 20)))
    assert len(hechos) == 1


def test_registrar_gasto_ingreso_y_transferencias(libro, ctas, cat):
    renta = gasto(libro, ctas, cat)
    op = recurrentes.registrar(libro, renta.id, date(2026, 7, 5))
    assert op.tipo is TipoOperacion.GASTO and op.descripcion == "Renta Ficticia"
    assert libro.saldo_centavos(ctas.debito) == -800_000
    nomina = recurrentes.crear(libro, "Nómina Ficticia", "ingreso", 10_000, ctas.debito, "quincenal", HOY,
                               categoria_id=cat("NOMINA"))
    assert recurrentes.registrar(libro, nomina.id, date(2026, 7, 15), 9_800).tipo is TipoOperacion.INGRESO
    ahorro = recurrentes.crear(libro, "Al ahorro", "transferencia", 500, ctas.debito, "mensual", HOY,
                               destino_id=ctas.ahorro)
    assert recurrentes.registrar(libro, ahorro.id, HOY).tipo is TipoOperacion.TRANSFERENCIA
    tarjeta = recurrentes.crear(libro, "Pago tarjeta", "transferencia", 300, ctas.debito, "mensual", HOY,
                                destino_id=ctas.credito)
    assert recurrentes.registrar(libro, tarjeta.id, HOY).tipo is TipoOperacion.PAGO_TARJETA


# ------------------------------------------------------------------ calendario y flujo


def test_calendario_con_pagados_vencidos_y_pendientes(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 20_000, date(2026, 1, 1))
    renta = gasto(libro, ctas, cat, inicio=date(2026, 1, 7))
    gasto(libro, ctas, cat, "Internet Ficticio", 600, inicio=date(2026, 1, 12), subcategoria="INTERNET")
    recurrentes.crear(libro, "Nómina Ficticia", "ingreso", 12_000, ctas.debito, "quincenal", date(2026, 1, 1),
                      categoria_id=cat("NOMINA"))
    recurrentes.registrar(libro, renta.id, date(2026, 7, 6))
    eventos = [e for e in recurrentes.calendario(libro, HOY) if e.clase == "recurrente"]
    resumen = [(e.fecha, e.nombre, e.estado) for e in eventos]
    assert (date(2026, 7, 7), "Renta Ficticia", PAGADO) in resumen          # tocaba el 7, se pagó el 6
    assert (date(2026, 7, 12), "Internet Ficticio", VENCIDO) in resumen
    assert (date(2026, 7, 15), "Nómina Ficticia", VENCIDO) in resumen
    assert (date(2026, 8, 7), "Renta Ficticia", PENDIENTE) in resumen
    assert [e.fecha for e in eventos] == sorted(e.fecha for e in eventos)

    f = recurrentes.flujo(libro, HOY)
    assert f.disponible == 2_000_000 - 800_000
    # Hoy: lo vencido (internet −600 y nómina +12,000 del 15). Luego nómina el 31, renta e internet en agosto, nómina 15.
    assert dict(f.dias)[HOY] == 1_200_000 - 60_000 + 1_200_000
    assert f.entra == 1_200_000 * 3 and f.sale == 60_000 * 2 + 800_000
    assert f.final == 1_200_000 + f.entra - f.sale and not f.negativo


def test_el_flujo_avisa_si_llegarias_a_negativo(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 1_000, date(2026, 1, 1))
    gasto(libro, ctas, cat, inicio=date(2026, 1, 25))
    f = recurrentes.flujo(libro, HOY)
    assert f.negativo and f.minimo == (date(2026, 7, 25), 100_000 - 800_000)


def test_lo_que_no_mueve_tu_disponible(libro, ctas, cat):
    """Una suscripción con tarjeta no baja tu disponible hoy; pasar al ahorro sí; pagos ya hechos no cuentan."""
    recurrentes.crear(libro, "Streaming", "gasto", 219, ctas.credito, "mensual", date(2026, 1, 25),
                      categoria_id=cat("STREAMING DE VIDEO"), suscripcion=True)
    recurrentes.crear(libro, "Al ahorro", "transferencia", 1000, ctas.debito, "mensual", date(2026, 1, 25),
                      destino_id=ctas.ahorro)
    f = recurrentes.flujo(libro, HOY)
    efectos = {e.nombre: recurrentes.efecto(libro, e) for e in f.eventos if e.fecha == date(2026, 7, 25)}
    assert efectos == {"Streaming": 0, "Al ahorro": -100_000}


def test_tarjetas_y_prestamos_en_el_calendario(libro, ctas, cat):
    from motor import prestamos

    movimientos.registrar_gasto(libro, date(2026, 6, 20), ctas.credito, cat("DESPENSA"), 400, "Súper")   # ciclo jun
    movimientos.registrar_gasto(libro, date(2026, 7, 10), ctas.credito, cat("DESPENSA"), 150, "Súper")   # ciclo jul
    p = prestamos.crear(libro, "Préstamo Ficticio", "personal", 12_000, 24, 12, date(2026, 1, 10),
                        destino=ctas.debito)
    eventos = recurrentes.calendario(libro, HOY, dias=40)
    tarjeta = [(e.fecha, e.centavos, e.estado) for e in eventos if e.clase == TARJETA]
    assert tarjeta == [(date(2026, 7, 23), -40_000, PENDIENTE), (date(2026, 8, 24), -15_000, PENDIENTE)]  # domingo → lunes
    prestamo = [e for e in eventos if e.clase == PRESTAMO]
    assert [e.fecha for e in prestamo] == [date(2026, 8, 10)] and prestamo[0].centavos < 0
    # Pagada la tarjeta, el evento queda como pagado.
    registrar_transferencia(libro, date(2026, 7, 21), ctas.debito, ctas.credito, 400)
    tarjeta = [e.estado for e in recurrentes.calendario(libro, date(2026, 7, 22), dias=10) if e.clase == TARJETA]
    assert tarjeta[0] == PAGADO
    assert p.cuenta_id


# ------------------------------------------------------------------ detectar


def test_detectar_suscripciones_y_nomina(libro, ctas, cat):
    for mes in range(2, 8):
        movimientos.registrar_gasto(libro, date(2026, mes, 3), ctas.credito, cat("STREAMING DE VIDEO"), 219,
                                    f"NETFLIX.COM {mes}")
        movimientos.registrar_gasto(libro, date(2026, mes, 8 + mes), ctas.debito, cat("DESPENSA"), 300 + 97 * mes,
                                    "SUPER FICTICIO")                                    # no es fijo
    for dia in (date(2026, 5, 15), date(2026, 5, 31), date(2026, 6, 15), date(2026, 6, 30), date(2026, 7, 15)):
        movimientos.registrar_ingreso(libro, dia, ctas.debito, cat("NOMINA"), 9_000, "PAGO DE NOMINA")
    sugerencias = recurrentes.detectar(libro, HOY)
    assert [(s.nombre, s.frecuencia, s.monto, s.suscripcion) for s in sugerencias] == [
        ("NETFLIX.COM 7", "mensual", D(219), True), ("PAGO DE NOMINA", "quincenal", D(9_000), False)]
    assert sugerencias[0].siguiente == date(2026, 8, 3) and sugerencias[1].siguiente == date(2026, 7, 31)
    recurrentes.agregar_sugerencia(libro, sugerencias[0])
    assert [s.nombre for s in recurrentes.detectar(libro, HOY)] == ["PAGO DE NOMINA"]   # ya no la sugiere


def test_eliminar_una_subcategoria_mueve_los_recurrentes(libro, ctas, cat):
    from motor import categorias

    r = gasto(libro, ctas, cat, subcategoria="TV DE PAGA")
    categorias.eliminar(libro, cat("TV DE PAGA"))
    assert libro.recurrente(r.id).categoria_id is None and not libro.recurrente(r.id).activa
    assert Decimal(0) == recurrentes.totales(libro).gastos_al_mes


def test_pagos_ya_registrados_con_fecha_futura(libro, ctas, cat):
    """Un pago programado (registrado con fecha futura) cuenta en su día y el calendario lo da por pagado."""
    from motor import prestamos

    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 20_000, date(2026, 1, 1))
    p = prestamos.crear(libro, "Préstamo Ficticio", "personal", 12_000, 24, 12, date(2026, 1, 10))
    pago = recurrentes.calendario(libro, HOY)[0]
    assert pago.clase == PRESTAMO and pago.estado == PENDIENTE and pago.fecha == date(2026, 8, 10)
    registrar_transferencia(libro, date(2026, 8, 9), ctas.debito, p.cuenta_id, 1_000)
    gasto(libro, ctas, cat, "Luz Ficticia", 300, inicio=date(2026, 1, 25), subcategoria="LUZ")
    movimientos.registrar_gasto(libro, date(2026, 7, 26), ctas.debito, cat("LUZ"), 300, "Programado")
    f = recurrentes.flujo(libro, HOY)
    assert f.disponible == 2_000_000
    assert [e.estado for e in f.eventos if e.clase == PRESTAMO] == [PAGADO]
    assert dict(f.dias)[date(2026, 7, 26)] == 2_000_000 - 30_000
    assert dict(f.dias)[date(2026, 8, 9)] == 2_000_000 - 30_000 - 100_000
