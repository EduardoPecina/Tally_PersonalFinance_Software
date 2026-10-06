from datetime import date

from conftest import D, JULIO
from motor import cuentas, movimientos, perfil, reportes
from motor.transferencias import registrar_pago_tarjeta, registrar_transferencia


def test_rango_mes():
    assert reportes.rango_mes(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert reportes.rango_mes(2028, 2) == (date(2028, 2, 1), date(2028, 2, 29))


def test_indicadores(libro, ctas, cat):
    efectivo = cuentas.crear(libro, "Cartera", "efectivo", saldo_inicial=200).id
    por_cobrar = cuentas.crear(libro, "Por cobrar", "por_cobrar").id
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("NOMINA"), 5000)
    registrar_transferencia(libro, date(2026, 7, 1), ctas.debito, ctas.ahorro, 2000)
    registrar_transferencia(libro, date(2026, 7, 1), ctas.debito, ctas.inversion, 1000)
    registrar_transferencia(libro, date(2026, 7, 2), ctas.debito, por_cobrar, 300)
    movimientos.registrar_gasto(libro, date(2026, 7, 3), ctas.credito, cat("ALIMENTOS"), 450)

    i = reportes.indicadores(libro)
    assert i.dinero_disponible == D(1700 + 200)  # débito + efectivo
    assert i.total_en_cuentas == D(1700 + 200 + 2000 + 1000)
    assert i.te_deben == D(300)
    assert i.deuda_tarjetas == D(450)
    assert i.patrimonio_neto == D(1700 + 200 + 2000 + 1000 + 300 - 450)
    assert efectivo


def test_en_disponible_configurable(libro, ctas):
    cuentas.editar(libro, ctas.ahorro, en_disponible=True)
    movimientos.actualizar_saldo(libro, ctas.ahorro, 900, date(2026, 7, 1))
    assert reportes.indicadores(libro).dinero_disponible == D(900)


def test_indicadores_a_una_fecha(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("NOMINA"), 1000)
    movimientos.registrar_ingreso(libro, date(2026, 8, 1), ctas.debito, cat("NOMINA"), 1000)
    assert reportes.indicadores(libro, date(2026, 7, 31)).patrimonio_neto == D(1000)


def test_gastos_por_subcategoria_categoria_clasificacion_y_cuenta(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, cat("ALIMENTOS"), 100)
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.credito, cat("ALIMENTOS"), 50)
    movimientos.registrar_gasto(libro, date(2026, 7, 3), ctas.credito, cat("SNACKS Y ANTOJOS"), 65)
    movimientos.registrar_gasto(libro, date(2026, 7, 4), ctas.ahorro, cat("OTROS GASTOS"), 10)
    registrar_pago_tarjeta(libro, date(2026, 7, 5), ctas.debito, ctas.credito, 115)
    movimientos.registrar_gasto(libro, date(2026, 8, 1), ctas.debito, cat("ALIMENTOS"), 999)

    porcat = reportes.gastos_por_categoria(libro, *JULIO)
    assert [(t.nombre, t.total, t.grupo) for t in porcat] == [
        ("ALIMENTOS", D(150), "Necesidad"),
        ("SNACKS Y ANTOJOS", D(65), "Antojos"),
        ("OTROS GASTOS", D(10), reportes.SIN_GRUPO),
    ]
    assert reportes.gastos_por_grupo(libro, *JULIO) == {
        "Necesidad": D(150), "Antojos": D(65), reportes.SIN_GRUPO: D(10)
    }
    # Por categoría que agrupa: ALIMENTOS y SNACKS Y ANTOJOS están en ALIMENTACION.
    assert [t.rubro for t in porcat] == ["ALIMENTACION", "ALIMENTACION", "VARIOS"]
    assert reportes.gastos_por_rubro(libro, *JULIO) == {"ALIMENTACION": D(215), "VARIOS": D(10)}
    assert reportes.hechos(libro, *JULIO)[0]["rubro"] == "ALIMENTACION"
    assert reportes.gastos_por_cuenta(libro, *JULIO) == {
        ctas.debito: D(100), ctas.credito: D(115), ctas.ahorro: D(10)
    }


def test_ingresos_por_categoria(libro, ctas, cat):
    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, cat("NOMINA"), 5000)
    movimientos.registrar_ingreso(libro, date(2026, 7, 31), ctas.debito, cat("NOMINA"), 5000)
    movimientos.registrar_ingreso(libro, date(2026, 7, 20), ctas.debito, cat("VENTAS"), 1100)
    totales = [(t.nombre, t.total) for t in reportes.ingresos_por_categoria(libro, *JULIO)]
    assert totales == [("NOMINA", D(10_000)), ("VENTAS", D(1100))]


def test_hechos(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.credito, cat("ALIMENTOS"), 100, "Pizza")
    movimientos.registrar_reembolso(libro, date(2026, 7, 2), ctas.credito, cat("ALIMENTOS"), 30)
    movimientos.registrar_ingreso(libro, date(2026, 7, 3), ctas.debito, cat("NOMINA"), 500)
    registrar_transferencia(libro, date(2026, 7, 4), ctas.debito, ctas.ahorro, 200)

    filas = reportes.hechos(libro, *JULIO)
    assert [(f["categoria"], f["clase"], f["monto"], f["cuenta"]) for f in filas] == [
        ("ALIMENTOS", "gasto", D(100), "Tarjeta Ficticia"),
        ("ALIMENTOS", "gasto", D(-30), "Tarjeta Ficticia"),
        ("NOMINA", "ingreso", D(500), "Banco Ficticio Débito"),
    ]
    assert filas[0]["mes"] == 7 and filas[0]["grupo"] == "Necesidad" and filas[0]["descripcion"] == "Pizza"


def test_sobrantes_de_quincena(libro, ctas, cat):
    """Sustituye las filas HISTORICO: lo que quedaba antes de cada nómina."""
    nomina, alimentos = cat("NOMINA"), cat("ALIMENTOS")
    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, nomina, 5000)
    registrar_transferencia(libro, date(2026, 7, 15), ctas.debito, ctas.ahorro, 4000)
    movimientos.registrar_gasto(libro, date(2026, 7, 20), ctas.debito, alimentos, 800)
    # Ese mismo día gasta antes de que caiga la nómina: el orden de captura importa.
    movimientos.registrar_gasto(libro, date(2026, 7, 31), ctas.debito, alimentos, 100)
    movimientos.registrar_ingreso(libro, date(2026, 7, 31), ctas.debito, nomina, 5000)
    movimientos.registrar_ingreso(libro, date(2026, 8, 3), ctas.debito, cat("VENTAS"), 50)

    sobrantes = reportes.sobrantes_de_quincena(libro, ctas.debito)
    assert [(s.fecha, s.sobrante) for s in sobrantes] == [
        (date(2026, 7, 15), D(0)),
        (date(2026, 7, 31), D(100)),
    ]


def test_quincena_de(libro, ctas, cat):
    nomina = cat("NOMINA")
    movimientos.registrar_ingreso(libro, date(2026, 7, 15), ctas.debito, nomina, 1)
    movimientos.registrar_ingreso(libro, date(2026, 7, 31), ctas.debito, nomina, 1)
    assert reportes.quincena_de(libro, date(2026, 7, 1)) is None
    assert reportes.quincena_de(libro, date(2026, 7, 20)) == (date(2026, 7, 15), date(2026, 7, 30))
    assert reportes.quincena_de(libro, date(2026, 8, 5)) == (date(2026, 7, 31), None)


def test_perfil_de_bienvenida(libro):
    assert perfil.necesita_bienvenida(libro)
    perfil.configurar(libro, "  Usuario   Ficticio ")
    assert libro.perfil.nombre == "Usuario Ficticio"
    assert not perfil.necesita_bienvenida(libro)
    creado = libro.perfil.creado_en
    perfil.configurar(libro, "Otro Nombre")
    assert libro.perfil.nombre == "Otro Nombre" and libro.perfil.creado_en == creado
