"""Revisión de salud de los datos (motor/salud.py). Solo datos ficticios."""

from datetime import date, timedelta

import pytest

from conftest import AHORA
from motor import (cuentas, impuestos, movimientos, perfil, prestamos, reglas_categorias, salud, temporales,
                   transferencias)
from motor.errores import ErrorValidacion
from motor.serializacion import instantanea, libro_desde_instantanea

HOY = AHORA.date()


@pytest.fixture
def base(libro, ctas, cat):
    """Un libro sano: perfil, una tarjeta con todos sus datos y movimientos recientes."""
    perfil.configurar(libro, "Usuario Ficticio")
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 10_000, date(2026, 1, 1))
    cuentas.editar(libro, ctas.credito, tasa_anual=45)
    for cuenta in (ctas.debito, ctas.credito):
        movimientos.registrar_gasto(libro, HOY - timedelta(days=5), cuenta, cat("ALIMENTOS"), 10, "Comida ficticia")
    transferencias.registrar_transferencia(libro, HOY - timedelta(days=5), ctas.debito, ctas.ahorro, 500, "Ahorro")
    return libro


def titulos(libro, **opciones) -> list[str]:
    return [h.titulo for h in salud.revisar(libro, **opciones).hallazgos]


def test_un_libro_sano_no_tiene_hallazgos(base):
    r = salud.revisar(base)
    assert r.hallazgos == [] and r.importantes == 0 and r.revisados["movimientos"] > 0


def test_duplicados(base, ctas, cat):
    a = movimientos.registrar_gasto(base, HOY, ctas.debito, cat("RESTAURANTES"), 250, "TACOS FICTICIOS 123")
    b = movimientos.registrar_gasto(base, HOY - timedelta(days=2), ctas.debito, cat("RESTAURANTES"), 250,
                                    "Tacos ficticios")
    movimientos.registrar_gasto(base, HOY - timedelta(days=20), ctas.debito, cat("RESTAURANTES"), 250, "Tacos")  # lejos
    movimientos.registrar_gasto(base, HOY, ctas.debito, cat("RESTAURANTES"), 251, "Tacos ficticios")  # otro importe
    movimientos.registrar_gasto(base, HOY, ctas.debito, cat("RESTAURANTES"), 250, "Gasolina")  # otra descripción
    (h,) = [h for h in salud.revisar(base).hallazgos if h.clave.startswith("duplicado:")]
    assert h.nivel == salud.REVISAR and set(h.operaciones) == {a.id, b.id} and h.pagina == "historial"
    assert "$250.00" in h.detalle

    salud.ignorar(base, h.clave)                                  # «Está bien así»: ya no sale
    r = salud.revisar(base)
    assert not any(x.clave == h.clave for x in r.hallazgos) and r.ignorados == 1
    assert any(x.clave == h.clave for x in salud.revisar(base, incluir_ignorados=True).hallazgos)
    otro = libro_desde_instantanea(instantanea(base), base.secuencia)      # se guarda en tu perfil
    assert otro.perfil.salud_ignorados == (h.clave,)
    salud.mostrar_todo(base)
    assert any(x.clave == h.clave for x in salud.revisar(base).hallazgos)


def test_cuenta_en_negativo_y_tarjeta_pasada_del_limite(base, ctas, cat):
    movimientos.registrar_gasto(base, HOY, ctas.debito, cat("ALIMENTOS"), 20_000, "Compra ficticia enorme")
    movimientos.registrar_gasto(base, HOY, ctas.credito, cat("ALIMENTOS"), 1_500, "Compra ficticia a crédito")
    r = salud.revisar(base)
    negativo = next(h for h in r.hallazgos if h.titulo == "Cuentas en negativo")
    assert "Banco Ficticio Débito" in negativo.detalle and "débito" in negativo.detalle
    assert any(h.titulo == "Tarjetas pasadas de su límite" for h in r.hallazgos)
    assert r.importantes >= 2


def test_fechas_raras(base, ctas, cat):
    futura = movimientos.registrar_gasto(base, HOY + timedelta(days=60), ctas.debito, cat("ALIMENTOS"), 5, "Futuro")
    vieja = movimientos.registrar_gasto(base, date(2001, 3, 1), ctas.debito, cat("ALIMENTOS"), 5, "Viejo")
    movimientos.registrar_gasto(base, HOY + timedelta(days=20), ctas.debito, cat("ALIMENTOS"), 5, "Próximo")  # normal
    r = salud.revisar(base)
    assert {h.operaciones for h in r.hallazgos if h.titulo.startswith("Fechas")} == {(futura.id,), (vieja.id,)}


def test_cargos_temporales_sin_devolver(base, ctas):
    temporales.registrar(base, HOY - timedelta(days=90), ctas.credito, 30, "Verificación ficticia")
    assert "Cargos temporales que no te han devuelto" in titulos(base)


def test_genericas_sin_descripcion_y_reglas(base, ctas, cat):
    for i in range(3):
        movimientos.registrar_gasto(base, HOY, ctas.debito, cat("OTROS GASTOS"), 10 + i, f"Algo {i}")
    for i in range(5):
        movimientos.registrar_gasto(base, HOY, ctas.debito, cat("ALIMENTOS"), 20 + i, "")
    reglas_categorias.crear(base, "COMIDA FICTICIA", cat("RESTAURANTES"))
    r = {h.titulo: h for h in salud.revisar(base).hallazgos}
    assert r["Movimientos en OTROS GASTOS"].cuantos == 3
    assert r["Movimientos sin descripción"].cuantos == 5
    assert r["Movimientos que tus reglas acomodarían distinto"].cuantos == 2 and \
        r["Movimientos que tus reglas acomodarían distinto"].pagina == "categorias"
    assert all(h.nivel == salud.MEJORAR for h in r.values())


def test_tarjetas_y_prestamos_incompletos(base, ctas, cat):
    nueva = cuentas.crear(base, "TDC Sin Datos", "credito", fecha_creacion=HOY)
    movimientos.registrar_gasto(base, HOY, nueva.id, cat("ALIMENTOS"), 5, "Algo")
    sin_datos = cuentas.crear(base, "Préstamo Ficticio Viejo", "prestamo", fecha_creacion=HOY, en_disponible=False)
    r = salud.revisar(base)
    tarjeta = next(h for h in r.hallazgos if h.titulo == "Tarjetas con datos incompletos")
    assert "día de corte" in tarjeta.detalle and "tasa de interés" in tarjeta.detalle
    assert any(h.clave == f"prestamo:{sin_datos.id}" for h in r.hallazgos)
    prestamos.crear(base, "Préstamo Ficticio Bien", "personal", 10_000, 20, 12, date(2026, 1, 1), deuda_actual=5_000)
    assert sum(h.titulo == "Préstamos sin sus datos" for h in salud.revisar(base).hallazgos) == 1


def test_cuentas_sin_movimientos(base, ctas):
    vieja = cuentas.crear(base, "Cuenta Olvidada Ficticia", "debito", fecha_creacion=date(2025, 1, 1))
    r = salud.revisar(base)
    assert [h.clave for h in r.hallazgos if h.titulo == "Cuentas sin movimientos"] == [
        f"sin_uso:{vieja.id}:2025-01-01"]


def test_deducibles_sin_comprobante(base, ctas, cat):
    impuestos.guardar_concepto(base, "Médicos ficticios", [cat("DENTISTA")])
    movimientos.registrar_gasto(base, HOY, ctas.debito, cat("DENTISTA"), 900, "Dentista ficticio")
    h = next(h for h in salud.revisar(base).hallazgos if h.titulo == "Deducibles sin comprobante")
    assert h.cuantos == 1 and h.pagina == "impuestos"


def test_datos_que_no_cuadran_no_se_pueden_ignorar(base, monkeypatch):
    from motor import serializacion

    monkeypatch.setattr(serializacion, "verificar_integridad", lambda libro: ["algo no cuadra (simulado)"])
    (h,) = [h for h in salud.revisar(base).hallazgos if h.nivel == salud.ERROR]
    assert not h.se_puede_ignorar
    salud.ignorar(base, h.clave)
    assert any(x.nivel == salud.ERROR for x in salud.revisar(base).hallazgos)


def test_ignorar_sin_perfil(libro):
    with pytest.raises(ErrorValidacion):
        salud.ignorar(libro, "algo")
