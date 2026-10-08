"""Los atajos de rendimiento (índice de movimientos, saldos acumulados, memoria del guardado) dan exactamente lo mismo
que hacerlo a mano, y se ponen al día con cada cambio. Solo datos ficticios."""

import random
import time
from dataclasses import replace
from datetime import date, timedelta

import pytest

from motor import movimientos, respaldos
from motor.errores import ErrorTally
from motor.modelo import Operacion, Partida, TipoOperacion
from motor.sesion import Sesion
from motor.transferencias import registrar_transferencia


def _a_mano_operaciones(libro, desde=None, hasta=None):
    ops = [op for op in libro._operaciones.values()
           if (desde is None or op.fecha >= desde) and (hasta is None or op.fecha <= hasta)]
    return sorted(ops, key=lambda op: op.orden)


def _a_mano_saldo(libro, cuenta_id, al=None):
    return sum(p.importe for op in libro._operaciones.values() if al is None or op.fecha <= al
               for p in op.partidas if p.cuenta_id == cuenta_id)


@pytest.fixture
def muchos(libro, ctas, cat):
    """Unos cientos de movimientos al azar (con semilla fija), varios el mismo día."""
    azar = random.Random(11)
    inicio = date(2025, 1, 1)
    for _ in range(400):
        dia = inicio + timedelta(days=azar.randint(0, 560))
        if azar.random() < 0.2:
            registrar_transferencia(libro, dia, ctas.debito, ctas.ahorro, azar.randint(1, 500), "Al ahorro")
        else:
            cuenta = azar.choice([ctas.debito, ctas.credito, ctas.ahorro])
            movimientos.registrar_gasto(libro, dia, cuenta, cat("ALIMENTOS"), azar.randint(1, 900), "Ficticio")
    return ctas


def _comparar(libro, ctas):
    assert libro.operaciones() == _a_mano_operaciones(libro)
    for desde, hasta in ((date(2025, 3, 1), date(2025, 3, 31)), (None, date(2025, 6, 15)), (date(2026, 1, 1), None),
                         (date(2024, 1, 1), date(2024, 12, 31)), (date(2025, 5, 5), date(2025, 5, 5))):
        assert libro.operaciones(desde, hasta) == _a_mano_operaciones(libro, desde, hasta)
    for cuenta in (ctas.debito, ctas.credito, ctas.ahorro, ctas.inversion):
        for al in (None, date(2024, 12, 31), date(2025, 1, 1), date(2025, 7, 20), date(2030, 1, 1)):
            assert libro.saldo_centavos(cuenta, al) == _a_mano_saldo(libro, cuenta, al)


def test_el_indice_da_lo_mismo_que_a_mano_y_se_pone_al_dia(libro, muchos, cat):
    _comparar(libro, muchos)
    ops = libro.operaciones()
    nuevo = movimientos.registrar_gasto(libro, date(2025, 3, 15), muchos.debito, cat("CINE"), 77, "Nuevo")
    _comparar(libro, muchos)
    movimientos.editar(libro, ops[10].id, fecha=date(2026, 2, 1), monto=5)            # cambia de fecha e importe
    _comparar(libro, muchos)
    movimientos.eliminar(libro, nuevo.id)
    movimientos.eliminar(libro, ops[20].id)
    _comparar(libro, muchos)


def test_la_lista_que_regresa_se_puede_cambiar_sin_danar_el_indice(libro, muchos):
    lista = libro.operaciones()
    lista.clear()
    assert len(libro.operaciones()) == 400


def test_las_partidas_precalculadas_siguen_al_movimiento(ctas, cat):
    op = Operacion(date(2026, 1, 1), TipoOperacion.GASTO,
                   (Partida(-100, cuenta_id=ctas.debito), Partida(100, categoria_id=cat("CINE"))))
    assert [p.cuenta_id for p in op.partidas_de_cuenta()] == [ctas.debito]
    otra = replace(op, partidas=(Partida(-100, cuenta_id=ctas.credito), Partida(100, categoria_id=cat("CINE"))))
    assert [p.cuenta_id for p in otra.partidas_de_cuenta()] == [ctas.credito]
    assert op == replace(op) and "_de_cuenta" not in repr(op)


# ------------------------------------------------------------------ guardar y deshacer


@pytest.fixture
def sesion(tmp_path, monkeypatch):
    monkeypatch.setenv("TALLY_RAIZ", str(tmp_path))
    s = Sesion(tmp_path / "Datos" / "tally.db")
    from motor import categorias, cuentas, perfil

    with s.cambio() as lib:
        perfil.configurar(lib, "Usuario Ficticio")
        if not lib.categorias() or not categorias.buscar(lib, "CINE"):
            categorias.cargar_catalogo_inicial(lib)
        debito = cuentas.crear(lib, "Débito Ficticio", "debito", saldo_inicial=1000, fecha_creacion=date(2026, 1, 1)).id
        cine = categorias.buscar(lib, "CINE").id
        for dia in range(1, 29):
            movimientos.registrar_gasto(lib, date(2026, 2, dia), debito, cine, dia, f"Ficticio {dia}")
    return s, debito, cine


def test_guardar_solo_anota_lo_que_cambio(sesion):
    s, debito, cine = sesion
    antes = len(s.almacen.bitacora())
    with s.cambio():
        pass                                                        # nada
    assert len(s.almacen.bitacora()) == antes
    viejo = s.libro.operaciones(date(2026, 2, 3), date(2026, 2, 3))[0]
    with s.cambio() as lib:
        movimientos.editar(lib, viejo.id, descripcion="Corregido")
    (registro,) = s.almacen.bitacora(limite=1)
    assert (registro.accion, registro.entidad_id, registro.despues["descripcion"]) == ("editar", viejo.id,
                                                                                         "Corregido")
    assert len(s.almacen.bitacora()) == antes + 1
    otra = Sesion(s.almacen.ruta)                                   # lo guardado es lo que se ve al reabrir
    assert otra.libro.operacion(viejo.id).descripcion == "Corregido"
    assert [op.id for op in otra.libro.operaciones()] == [op.id for op in s.libro.operaciones()]


def test_un_error_deshace_todo_y_reusa_lo_guardado(sesion):
    s, debito, cine = sesion
    guardados = {op.id: op for op in s.libro.operaciones()}
    with pytest.raises(ErrorTally):
        with s.cambio() as lib:
            movimientos.registrar_gasto(lib, date(2026, 3, 1), debito, cine, 50, "Se va a deshacer")
            movimientos.registrar_gasto(lib, date(2026, 3, 1), debito, cine, -5, "Inválido")
    assert {op.id for op in s.libro.operaciones()} == set(guardados)
    assert all(s.libro.operacion(i) is op for i, op in guardados.items())   # los mismos objetos, sin reconvertir
    with s.cambio() as lib:
        movimientos.registrar_gasto(lib, date(2026, 3, 2), debito, cine, 60, "Después del error")
    assert len(Sesion(s.almacen.ruta).libro.operaciones()) == len(guardados) + 1


def test_el_respaldo_compacto_se_restaura_igual(sesion, tmp_path):
    s, debito, cine = sesion
    ruta = respaldos.crear(s, tmp_path / "Respaldos")
    with s.cambio() as lib:
        movimientos.registrar_gasto(lib, date(2026, 3, 5), debito, cine, 99, "Después del respaldo")
    respaldos.restaurar(s, ruta, carpeta_seguridad=tmp_path / "Seguridad")
    assert len(s.libro.operaciones()) == 29 and s.libro.saldo_centavos(debito) == (1000 - sum(range(1, 29))) * 100
    with s.cambio() as lib:                                         # y se sigue guardando bien después
        movimientos.registrar_gasto(lib, date(2026, 3, 6), debito, cine, 1, "Tras restaurar")
    assert len(Sesion(s.almacen.ruta).libro.operaciones()) == 30


def test_con_miles_de_movimientos_sigue_siendo_rapido(libro, ctas, cat):
    """Con unos 10 años de datos, consultar y guardar no se arrastra (márgenes amplios para cualquier PC)."""
    alimentos = cat("ALIMENTOS")
    dia = date(2016, 1, 1)
    while len(libro._operaciones) < 20_000:
        movimientos.registrar_gasto(libro, dia, ctas.debito, alimentos, 10, "Ficticio")
        movimientos.registrar_gasto(libro, dia, ctas.credito, alimentos, 20, "Ficticio")
        dia += timedelta(days=1)
    libro.operaciones(), libro.saldo_centavos(ctas.debito)                     # arma el índice una vez
    inicio = time.perf_counter()
    for mes in range(1, 13):
        libro.operaciones(date(2024, mes, 1), date(2024, mes, 28))
        for cuenta in (ctas.debito, ctas.credito, ctas.ahorro):
            libro.saldo_centavos(cuenta, date(2024, mes, 28))
    assert time.perf_counter() - inicio < 0.5                       # a mano eran ~30 recorridos de 20,000
