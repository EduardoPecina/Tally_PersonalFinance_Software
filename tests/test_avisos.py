"""Avisos antes de guardar un movimiento (motor/avisos.py). Solo datos ficticios."""

from datetime import date, timedelta

from conftest import AHORA
from motor import avisos, cuentas, movimientos
from motor.avisos import FECHA, LIMITE, NEGATIVO

HOY = AHORA.date()                     # 20/07/2026


def claves(lista):
    return [a.clave for a in lista]


def test_sin_avisos_si_todo_cuadra(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 1_000, date(2026, 1, 1))
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.debito, -100_000)]) == []     # queda en $0: está bien
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.debito, 500_000)]) == []      # si entra, nunca avisa
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.credito, -100_000)]) == []    # justo el límite


def test_una_cuenta_quedaria_en_negativo(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 1_000, date(2026, 1, 1))
    efectivo = cuentas.crear(libro, "Efectivo Ficticio", "efectivo", fecha_creacion=date(2026, 1, 1)).id
    (aviso,) = avisos.antes_de_registrar(libro, HOY, [(ctas.debito, -150_000)])
    assert aviso.clave == NEGATIVO and aviso.mensaje.startswith("«Banco Ficticio Débito» quedaría en -$500.00.")
    assert claves(avisos.antes_de_registrar(libro, HOY, [(efectivo, -1)])) == [NEGATIVO]
    for tipo in ("ahorro", "inversion"):
        cuenta = getattr(ctas, tipo)
        assert claves(avisos.antes_de_registrar(libro, HOY, [(cuenta, -1)])) == [NEGATIVO]
    # Una transferencia: avisa de la cuenta de la que sale, no de la que recibe.
    assert claves(avisos.antes_de_registrar(libro, HOY, [(ctas.debito, -200_000), (ctas.ahorro, 200_000)])) \
        == [NEGATIVO]


def test_cuenta_ya_en_negativo_y_movimientos_de_otros_dias(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 1_000, date(2026, 1, 1))
    movimientos.registrar_gasto(libro, date(2026, 8, 5), ctas.debito, cat("ALIMENTOS"), 900)   # adelante, en agosto
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.debito, -50_000)]) == []           # hoy aún hay $1,000
    (aviso,) = avisos.antes_de_registrar(libro, date(2026, 8, 10), [(ctas.debito, -50_000)])
    assert "-$400.00" in aviso.mensaje                                                      # ese día ya no


def test_una_tarjeta_pasaria_su_limite(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("ALIMENTOS"), 800)
    (aviso,) = avisos.antes_de_registrar(libro, HOY, [(ctas.credito, -30_000)])
    assert aviso.clave == LIMITE
    assert aviso.mensaje == "«Tarjeta Ficticia» pasaría su límite de $1,000.00: deberías $1,100.00."
    sin_limite = cuentas.crear(libro, "Tarjeta Sin Límite", "credito", fecha_creacion=date(2026, 1, 1)).id
    assert avisos.antes_de_registrar(libro, HOY, [(sin_limite, -99_999_900)]) == []        # sin límite registrado
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.credito, 80_000)]) == []          # pagarla no avisa


def test_fecha_muy_adelante_o_muy_atras(libro, ctas):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 1_000, date(2026, 1, 1))
    gasto = [(ctas.debito, -100)]
    assert avisos.antes_de_registrar(libro, HOY + timedelta(days=31), gasto) == []         # el pago del próximo mes
    (aviso,) = avisos.antes_de_registrar(libro, HOY + timedelta(days=40), gasto)
    assert aviso.clave == FECHA and aviso.mensaje == "La fecha es el 29/08/2026, dentro de 40 días. ¿Es correcta?"
    assert "dentro de 1 año" in avisos.antes_de_registrar(libro, date(2027, 7, 20), gasto)[0].mensaje
    assert "dentro de 36 años" in avisos.antes_de_registrar(libro, date(2062, 7, 20), gasto)[0].mensaje
    assert avisos.antes_de_registrar(libro, date(2025, 7, 21), gasto) == []                # hace 364 días
    (atras,) = avisos.antes_de_registrar(libro, date(2025, 7, 20), [(ctas.debito, 100)])   # el año mal escrito
    assert atras.clave == FECHA and "hace 1 año" in atras.mensaje
    assert "hace 10 años" in avisos.antes_de_registrar(libro, date(2016, 7, 20), gasto)[0].mensaje


def test_varios_avisos_juntos(libro, ctas):
    lista = avisos.antes_de_registrar(libro, date(2062, 7, 20), [(ctas.debito, -100), (ctas.credito, -200_000)])
    assert claves(lista) == [FECHA, NEGATIVO, LIMITE]
