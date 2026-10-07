"""Funciones del motor que usa el portal: historial, periodos, evolución y ayudas."""

from datetime import date

import pytest

from conftest import D, JULIO
from motor import auditoria, categorias, consultas, cuentas, movimientos, reportes, tarjetas
from motor.dinero import a_centavos
from motor.modelo import TipoOperacion
from motor.sesion import Sesion
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia


@pytest.fixture
def mes(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, cat("NOMINA"), 5000, "Nómina julio")
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.credito, cat("ALIMENTOS"), 300, "Pizza", "con amigos")
    movimientos.registrar_gasto(libro, date(2026, 7, 9), ctas.debito, cat("TRANSPORTE"), 80, "Taxi aeropuerto")
    registrar_transferencia(libro, date(2026, 7, 15), ctas.debito, ctas.ahorro, 2000, "Al ahorro")
    registrar_pago_tarjeta(libro, date(2026, 7, 20), ctas.debito, ctas.credito, 300, "Pago TDC")
    movimientos.registrar_reembolso(libro, date(2026, 7, 21), ctas.credito, cat("ALIMENTOS"), 50, "Devolución")
    return libro


# ----------------------------------------------------------------- historial


def test_buscar_sin_filtros_mas_recientes_primero(mes):
    filas = consultas.buscar(mes)
    assert [f.descripcion for f in filas][:2] == ["Devolución", "Pago TDC"]
    assert len(filas) == 6


def test_buscar_texto_sin_acentos_ni_mayusculas(mes):
    assert [f.descripcion for f in consultas.buscar(mes, texto="AEROPUERTO")] == ["Taxi aeropuerto"]
    assert [f.descripcion for f in consultas.buscar(mes, texto="NOMINA")] == ["Nómina julio"]
    assert [f.descripcion for f in consultas.buscar(mes, texto="amigos")] == ["Pizza"]  # busca en notas


def test_buscar_por_cuenta_incluye_origen_y_destino(mes, ctas):
    descripciones = {f.descripcion for f in consultas.buscar(mes, cuentas=[ctas.credito])}
    assert descripciones == {"Pizza", "Pago TDC", "Devolución"}


def test_buscar_por_categoria_tipo_y_fechas(mes, cat):
    assert {f.descripcion for f in consultas.buscar(mes, categorias=[cat("ALIMENTOS")])} == {"Pizza", "Devolución"}
    assert [f.descripcion for f in consultas.buscar(mes, tipos=["transferencia"])] == ["Al ahorro"]
    filas = consultas.buscar(mes, desde=date(2026, 7, 10), hasta=date(2026, 7, 15), orden="fecha_asc")
    assert [f.descripcion for f in filas] == ["Nómina julio", "Al ahorro"]


def test_orden_por_importe(mes):
    assert consultas.buscar(mes, orden="monto_desc")[0].descripcion == "Nómina julio"
    assert consultas.buscar(mes, orden="monto_asc")[0].descripcion == "Devolución"
    assert consultas.buscar(mes, orden="no_existe")[0].descripcion == "Devolución"


def test_sentido_y_totales(mes):
    filas = {f.descripcion: f for f in consultas.buscar(mes)}
    assert (filas["Pizza"].sentido, filas["Pizza"].importe_con_signo) == ("-", D(-300))
    assert filas["Nómina julio"].sentido == "+"
    assert filas["Devolución"].sentido == "+"
    assert filas["Al ahorro"].sentido == "↔" and filas["Al ahorro"].cuenta_destino == "Ahorro Ficticio"
    assert consultas.total(filas.values()) == {"+": D(5050), "-": D(380), "↔": D(2300)}


def test_fila_de_ajuste_y_repartido(libro, ctas, cat):
    movimientos.actualizar_saldo(libro, ctas.debito, -20, date(2026, 7, 1))
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito,
                                reparto=[(cat("ALIMENTOS"), 10), (cat("REGALOS"), 5)])
    ajuste, repartido = consultas.buscar(libro, orden="fecha_asc")
    assert (ajuste.sentido, ajuste.monto, ajuste.tipo_etiqueta) == ("-", D(20), "Ajuste de saldo")
    assert repartido.categoria == "ALIMENTOS, REGALOS" and repartido.monto == D(15)


# ------------------------------------------------------------------ periodos


def test_rango_periodo(libro, cat, ctas):
    hoy = date(2026, 7, 20)
    assert reportes.rango_periodo(libro, "mes_actual", hoy) == JULIO
    assert reportes.rango_periodo(libro, "mes_anterior", hoy) == (date(2026, 6, 1), date(2026, 6, 30))
    assert reportes.rango_periodo(libro, "anio", hoy) == (date(2026, 1, 1), date(2026, 12, 31))
    assert reportes.rango_periodo(libro, "12_meses", hoy) == (date(2025, 8, 1), date(2026, 7, 31))
    assert reportes.rango_periodo(libro, "quincena", hoy) == (date(2026, 7, 16), date(2026, 7, 31))
    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, cat("NOMINA"), 1)
    assert reportes.rango_periodo(libro, "quincena", hoy) == (date(2026, 7, 15), hoy)
    assert reportes.rango_periodo(libro, "desconocido", hoy) == JULIO
    assert reportes.rango_periodo(libro, "mes_anterior", date(2026, 1, 10)) == (date(2025, 12, 1), date(2025, 12, 31))


@pytest.mark.parametrize("desde, hasta, anterior", [
    (date(2026, 7, 1), date(2026, 7, 31), (date(2026, 6, 1), date(2026, 6, 30))),          # un mes
    (date(2026, 3, 1), date(2026, 3, 31), (date(2026, 2, 1), date(2026, 2, 28))),
    (date(2025, 1, 1), date(2025, 12, 31), (date(2024, 1, 1), date(2024, 12, 31))),        # el anterior es bisiesto
    (date(2028, 1, 1), date(2028, 12, 31), (date(2027, 1, 1), date(2027, 12, 31))),        # este es bisiesto
    (date(2025, 11, 1), date(2026, 10, 31), (date(2024, 11, 1), date(2025, 10, 31))),      # últimos 12 meses
    (date(2026, 4, 1), date(2026, 6, 30), (date(2026, 1, 1), date(2026, 3, 31))),          # un trimestre
    (date(2026, 7, 16), date(2026, 7, 31), (date(2026, 7, 1), date(2026, 7, 15))),         # 2.ª quincena: la 1.ª
    (date(2026, 3, 1), date(2026, 3, 15), (date(2026, 2, 16), date(2026, 2, 28))),         # 1.ª: la 2.ª de febrero
    (date(2027, 10, 8), date(2028, 10, 7), (date(2026, 10, 8), date(2027, 10, 7))),        # un año exacto
    (date(2027, 3, 1), date(2028, 2, 29), (date(2026, 3, 1), date(2027, 2, 28))),
    (date(2026, 7, 10), date(2026, 7, 19), (date(2026, 6, 30), date(2026, 7, 9))),         # otro rango: los 10 días antes
])
def test_periodo_anterior(desde, hasta, anterior):
    assert reportes.periodo_anterior(desde, hasta) == anterior


def test_comparar_a_la_mitad_del_periodo_usa_los_mismos_dias(libro, ctas, cat):
    for dia, monto in ((date(2026, 6, 5), 500), (date(2026, 6, 25), 1_000), (date(2026, 7, 5), 300)):
        movimientos.registrar_gasto(libro, dia, ctas.debito, cat("ALIMENTOS"), monto)
    c = reportes.comparar(libro, *JULIO, hoy=date(2026, 7, 20))          # del 1 al 20 de julio vs. del 1 al 20 de junio
    assert (c.al, c.desde_anterior, c.hasta_anterior) == (date(2026, 7, 20), date(2026, 6, 1), date(2026, 6, 20))
    assert (c.actual.gastos, c.anterior.gastos, c.diferencia.gastos) == (D(300), D(500), D(-200))
    completo = reportes.comparar(libro, *JULIO, hoy=date(2026, 7, 31))   # ya terminó: el mes completo
    assert (completo.al, completo.anterior.gastos, completo.diferencia.gastos) == (None, D(1_500), D(-1_200))
    assert reportes.comparar(libro, *JULIO, hoy=date(2026, 8, 3)).al is None
    marzo = reportes.comparar(libro, date(2026, 3, 1), date(2026, 3, 31), hoy=date(2026, 3, 30))
    assert marzo.hasta_anterior == date(2026, 2, 28)                      # el 30 de marzo → fin de febrero
    quincena = reportes.comparar(libro, date(2026, 7, 16), date(2026, 7, 31), hoy=date(2026, 7, 20))
    assert (quincena.desde_anterior, quincena.hasta_anterior) == (date(2026, 7, 1), date(2026, 7, 5))
    anio = reportes.comparar(libro, date(2026, 1, 1), date(2026, 12, 31), hoy=date(2026, 7, 20))
    assert (anio.desde_anterior, anio.hasta_anterior) == (date(2025, 1, 1), date(2025, 7, 20))


def test_comparar(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 6, 5), ctas.debito, cat("ALIMENTOS"), 500)
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.debito, cat("ALIMENTOS"), 300)
    c = reportes.comparar(libro, *JULIO)
    assert (c.actual.gastos, c.anterior.gastos, c.diferencia.gastos) == (D(300), D(500), D(-200))
    assert (c.desde_anterior, c.hasta_anterior) == (date(2026, 6, 1), date(2026, 6, 30))


def test_evolucion(mes):
    puntos = reportes.evolucion(mes, *JULIO)
    assert len(puntos) == 31 and puntos[-1].fecha == date(2026, 7, 31)
    assert (puntos[0].patrimonio_neto, puntos[1].patrimonio_neto) == (0, D(-300))  # pizza con TDC el día 2
    assert puntos[-1].patrimonio_neto == reportes.indicadores(mes, date(2026, 7, 31)).patrimonio_neto
    semanal = reportes.evolucion(mes, date(2026, 1, 1), date(2026, 7, 31))
    assert 25 < len(semanal) < 35 and semanal[-1].fecha == date(2026, 7, 31)
    mensual = reportes.evolucion(mes, date(2025, 1, 15), date(2026, 7, 31))
    assert mensual[0].fecha == date(2025, 1, 31) and len(mensual) == 19
    assert reportes.evolucion(mes, date(2026, 7, 31), date(2026, 7, 1))[0].fecha == date(2026, 7, 1)


# --------------------------------------------------------------- ayudantes


def test_categorias_para_tipo(libro):
    clases = {t: {c.clase.value for c in categorias.para_tipo(libro, t)} for t in TipoOperacion}
    assert clases[TipoOperacion.GASTO] == clases[TipoOperacion.REEMBOLSO] == {"gasto"}
    assert clases[TipoOperacion.INGRESO] == clases[TipoOperacion.RENDIMIENTO] == {"ingreso"}
    assert clases[TipoOperacion.TRANSFERENCIA] == set()
    alimentos = categorias.buscar(libro, "ALIMENTOS")
    categorias.archivar(libro, alimentos.id)
    assert alimentos.id not in [c.id for c in categorias.para_tipo(libro, "gasto")]


def test_saldo_inicial_y_movimientos_de_cuenta(libro, cat):
    cuenta = cuentas.crear(libro, "Débito", "debito", saldo_inicial=700, fecha_creacion=date(2026, 7, 1))
    assert cuentas.saldo_inicial(libro, cuenta.id) == (D(700), date(2026, 7, 1))
    assert not cuentas.tiene_movimientos(libro, cuenta.id)
    movimientos.registrar_gasto(libro, date(2026, 7, 2), cuenta.id, cat("ALIMENTOS"), 1)
    assert cuentas.tiene_movimientos(libro, cuenta.id)
    sin = cuentas.crear(libro, "Vacía", "efectivo")
    assert cuentas.saldo_inicial(libro, sin.id) is None


def test_ciclo_por_pagar_y_actual(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 6, 20), ctas.credito, cat("ALIMENTOS"), 400)
    movimientos.registrar_gasto(libro, date(2026, 7, 10), ctas.credito, cat("ALIMENTOS"), 100)
    por_pagar = tarjetas.ciclo_por_pagar(libro, ctas.credito, date(2026, 7, 20))
    assert (por_pagar.inicio, por_pagar.fin, por_pagar.por_liquidar) == (date(2026, 6, 4), date(2026, 7, 3), D(400))
    actual = tarjetas.ciclo_actual(libro, ctas.credito, date(2026, 7, 20))
    assert (actual.inicio, actual.cargos) == (date(2026, 7, 4), D(100))
    # El mismo día del corte, lo que hay que pagar es el ciclo que corta hoy.
    assert tarjetas.ciclo_por_pagar(libro, ctas.credito, date(2026, 8, 3)).fin == date(2026, 8, 3)
    sin_corte = cuentas.crear(libro, "Sin corte", "credito").id
    assert tarjetas.ciclo_por_pagar(libro, sin_corte) is None and tarjetas.ciclo_actual(libro, sin_corte) is None


def test_resumen_de_bitacora():
    edicion = auditoria.Cambio("operacion", "x", auditoria.EDITAR,
                               {"descripcion": "Pizza", "notas": "", "modificado_en": "a"},
                               {"descripcion": "Pizza", "notas": "rica", "modificado_en": "b"})
    assert auditoria.resumen(edicion) == "Editó Movimiento «Pizza» (notas)"
    assert auditoria.resumen(auditoria.Cambio("cuenta", "y", auditoria.CREAR, None, {"nombre": "Débito"})) == \
        "Creó Cuenta «Débito»"
    assert auditoria.resumen(auditoria.Cambio("grupo", "z", auditoria.BORRAR, {"nombre": "Metas"}, None)) == \
        "Borró Clasificación «Metas»"


def test_apartar_archivo_danado(tmp_path):
    ruta = tmp_path / "Datos" / "tally.db"
    assert Sesion.apartar_archivo_danado(ruta) is None
    ruta.parent.mkdir()
    ruta.write_bytes(b"basura")
    (tmp_path / "Datos" / "tally.db-wal").write_bytes(b"x")
    apartado = Sesion.apartar_archivo_danado(ruta)
    assert apartado.read_bytes() == b"basura" and apartado.name.startswith("tally_danado_")
    assert not ruta.exists() and apartado.with_name(apartado.name + "-wal").exists()


def test_importes_float_con_residuo_binario():
    assert a_centavos(59.94 + 0.01) == 5995
    assert a_centavos(0.1 + 0.2) == 30
