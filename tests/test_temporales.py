"""Cargos temporales (verificaciones de tarjeta que te devuelven). Todos los datos son ficticios."""

from datetime import date

import pytest

from conftest import D
from motor import cuentas, importacion, movimientos, perfil, reportes, temporales
from motor.errores import ErrorValidacion
from motor.modelo import TipoCuenta, TipoOperacion
from motor.serializacion import instantanea, libro_desde_instantanea

JULIO = (date(2026, 7, 1), date(2026, 7, 31))
AGOSTO = (date(2026, 8, 1), date(2026, 8, 31))


def test_el_cargo_no_es_gasto_y_crea_la_cuenta_por_recuperar(libro, ctas):
    assert temporales.cuenta(libro) is None
    op = temporales.registrar(libro, date(2026, 7, 10), ctas.credito, 1, "Tienda Ficticia")
    assert op.tipo is TipoOperacion.TRANSFERENCIA
    por_recuperar = temporales.cuenta(libro)
    assert por_recuperar.tipo is TipoCuenta.POR_COBRAR and por_recuperar.nombre == "POR RECUPERAR"
    assert cuentas.saldo(libro, ctas.credito) == D(-1)                   # la tarjeta sí lo debe
    assert reportes.resumen(libro, *JULIO).gastos == 0
    assert reportes.indicadores(libro).te_deben == D(1)
    (cargo,) = temporales.pendientes(libro, date(2026, 7, 20))
    assert (cargo.operacion_id, cargo.monto, cargo.dias, cargo.vencido) == (op.id, D(1), 10, False)
    assert cargo.cuenta == "Tarjeta Ficticia"


def test_la_devolucion_lo_quita_de_pendientes_sin_tocar_gastos(libro, ctas):
    op = temporales.registrar(libro, date(2026, 7, 28), ctas.credito, "1.00", "Tienda Ficticia")
    devolucion = temporales.devolver(libro, op.id, date(2026, 8, 5))
    assert devolucion.liquida == op.id and devolucion.tipo is TipoOperacion.TRANSFERENCIA
    assert temporales.pendientes(libro) == []
    assert cuentas.saldo(libro, ctas.credito) == 0
    assert cuentas.saldo(libro, temporales.cuenta(libro).id) == 0
    assert reportes.resumen(libro, *JULIO).gastos == 0                   # ningún mes se ensucia
    assert reportes.resumen(libro, *AGOSTO).gastos == 0
    with pytest.raises(ErrorValidacion, match="ya no está pendiente"):
        temporales.devolver(libro, op.id, date(2026, 8, 6))


def test_la_devolucion_puede_llegar_a_otra_cuenta_pero_no_antes_del_cargo(libro, ctas):
    op = temporales.registrar(libro, date(2026, 7, 10), ctas.debito, 50, "Hotel Ficticio")
    with pytest.raises(ErrorValidacion, match="antes del cargo"):
        temporales.devolver(libro, op.id, date(2026, 7, 9))
    temporales.devolver(libro, op.id, date(2026, 7, 15), cuenta_id=ctas.ahorro)
    assert cuentas.saldo(libro, ctas.ahorro) == D(50)


def test_si_no_lo_devuelven_se_pasa_a_gasto(libro, ctas, cat):
    op = temporales.registrar(libro, date(2026, 7, 10), ctas.credito, 30, "Depósito Ficticio")
    gasto = temporales.pasar_a_gasto(libro, op.id, date(2026, 8, 30), cat("OTROS GASTOS"))
    assert gasto.tipo is TipoOperacion.GASTO and gasto.liquida == op.id
    assert temporales.pendientes(libro) == []
    assert reportes.resumen(libro, *AGOSTO).gastos == D(30)               # el gasto cuenta cuando te rindes
    assert cuentas.saldo(libro, temporales.cuenta(libro).id) == 0
    assert cuentas.saldo(libro, ctas.credito) == D(-30)


def test_vencidos_segun_los_dias_para_reclamar(libro, ctas):
    perfil.configurar(libro, "Persona Ficticia")
    temporales.registrar(libro, date(2026, 6, 1), ctas.credito, 1, "Viejo")
    temporales.registrar(libro, date(2026, 7, 15), ctas.credito, 2, "Reciente")
    assert [c.descripcion for c in temporales.vencidos(libro, date(2026, 7, 20))] == ["Viejo"]
    perfil.ajustar(libro, dias_para_reclamar=3)
    assert len(temporales.vencidos(libro, date(2026, 7, 20))) == 2
    with pytest.raises(ErrorValidacion):
        perfil.ajustar(libro, dias_para_reclamar=0)


def test_devoluciones_sin_liga_se_emparejan_por_importe(libro, ctas):
    temporales.registrar(libro, date(2026, 7, 1), ctas.credito, 1, "A")
    temporales.registrar(libro, date(2026, 7, 2), ctas.credito, 5, "B")
    temporales.registrar(libro, date(2026, 7, 3), ctas.debito, 1, "C")
    from motor.transferencias import registrar_transferencia
    registrar_transferencia(libro, date(2026, 7, 9), temporales.cuenta(libro).id, ctas.credito, 1, "Devolución")
    assert [c.descripcion for c in temporales.pendientes(libro)] == ["B", "C"]   # se va el más antiguo de $1


def test_la_liga_sobrevive_al_guardar_editar_y_repetir(libro, ctas):
    op = temporales.registrar(libro, date(2026, 7, 1), ctas.credito, 1, "A")
    devolucion = temporales.devolver(libro, op.id, date(2026, 7, 9))
    copia = libro_desde_instantanea(instantanea(libro), libro.secuencia, reloj=libro.reloj)
    assert copia.operacion(devolucion.id).liquida == op.id
    editada = movimientos.editar(libro, devolucion.id, fecha=date(2026, 7, 10), monto=1)
    assert editada.liquida == op.id
    assert movimientos.duplicar(libro, devolucion.id, date(2026, 7, 11)).liquida == ""


def test_reactiva_la_cuenta_archivada_y_respeta_un_nombre_ocupado(libro, ctas):
    temporales.asegurar_cuenta(libro)
    cuentas.archivar(libro, temporales.cuenta(libro).id)
    temporales.registrar(libro, date(2026, 7, 1), ctas.debito, 1)
    assert temporales.cuenta(libro).activa


def test_nombre_ocupado_por_otra_cuenta(libro, ctas):
    cuentas.crear(libro, "Por recuperar", TipoCuenta.DEBITO)
    with pytest.raises(ErrorValidacion, match="no es de tipo Por cobrar"):
        temporales.registrar(libro, date(2026, 7, 1), ctas.debito, 1)


def test_carga_masiva_con_por_recuperar(libro):
    texto = (
        "CUENTA: Tarjeta Ficticia\nTIPO: CREDITO\n"
        "FECHA\tDESCRIPCION\tSUBCATEGORIA\tCARGO\tABONO\tNOTAS\n"
        "28/07/2026\tVerificación\tPOR RECUPERAR\t1.00\t\t\n"
        "05/08/2026\tDevolución\tpor recuperar\t\t1.00\t\n"
    )
    archivo = importacion.leer(texto)
    assert importacion.desconocidos(libro, archivo) == []
    previa = importacion.vista_previa(libro, archivo)
    assert previa.se_puede_cargar and "POR RECUPERAR" in previa.cuentas_nuevas
    importacion.cargar(libro, archivo)
    assert temporales.pendientes(libro) == []
    assert reportes.resumen(libro, *JULIO).gastos == 0
    assert "POR RECUPERAR" in importacion.plantilla()
