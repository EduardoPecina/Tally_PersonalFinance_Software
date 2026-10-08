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


def test_cuenta_con_movimientos_registrados_a_futuro(libro, ctas, cat):
    cuentas.cambiar_saldo_inicial(libro, ctas.debito, 5_000, date(2026, 1, 1))
    movimientos.registrar_gasto(libro, date(2026, 7, 30), ctas.debito, cat("RENTA"), 4_500, "Renta")   # en 10 días
    movimientos.registrar_ingreso(libro, date(2026, 7, 31), ctas.debito, cat("NOMINA"), 9_000)        # y luego entra
    # Hoy hay $5,000, pero la renta ya registrada deja $500: un gasto de $2,000 hoy no alcanza para pagarla.
    (aviso,) = avisos.antes_de_registrar(libro, HOY, [(ctas.debito, -200_000)])
    assert aviso.mensaje == ("«Banco Ficticio Débito» quedaría en -$1,500.00 el 30/07/2026, con lo que ya registraste "
                             "para esos días. ¿Están bien la cuenta y el importe?")
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.debito, -50_000)]) == []           # $500 sí alcanzan
    # Un gasto después de la nómina se revisa desde ese día: ya no le afecta la renta.
    assert avisos.antes_de_registrar(libro, date(2026, 8, 1), [(ctas.debito, -900_000)]) == []
    (despues,) = avisos.antes_de_registrar(libro, date(2026, 8, 1), [(ctas.debito, -950_100)])
    assert "quedaría en -$1.00." in despues.mensaje                                         # ese mismo día
    # La tarjeta: una compra ya registrada a futuro también cuenta para el límite.
    movimientos.registrar_gasto(libro, date(2026, 7, 25), ctas.credito, cat("ALIMENTOS"), 800)
    (limite,) = avisos.antes_de_registrar(libro, HOY, [(ctas.credito, -30_000)])
    assert limite.clave == LIMITE and "el 25/07/2026" in limite.mensaje and "$1,100.00" in limite.mensaje


def test_solo_avisa_si_este_movimiento_cruza_la_linea(libro, ctas, cat):
    # Ya en negativo (p. ej. aún no registra su nómina): no pide confirmar cada gasto.
    movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, cat("ALIMENTOS"), 200)
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.debito, -5_000)]) == []
    # Una tarjeta que ya pasaba su límite, tampoco.
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.credito, cat("ALIMENTOS"), 1_200)
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.credito, -5_000)]) == []

    # Pero un día así más adelante no apaga el aviso de hoy: $10 el 30/07 y un cero de más en el súper.
    cuentas.cambiar_saldo_inicial(libro, ctas.ahorro, 10_000, date(2026, 1, 1))
    movimientos.registrar_gasto(libro, date(2026, 7, 30), ctas.ahorro, cat("ALIMENTOS"), 10_010)
    (aviso,) = avisos.antes_de_registrar(libro, HOY, [(ctas.ahorro, -5_000_000)])
    assert aviso.mensaje.startswith("«Ahorro Ficticio» quedaría en -$40,000.00. ")
    assert avisos.antes_de_registrar(libro, HOY, [(ctas.ahorro, -5_000)]) == []          # solo el 30/07, ya negativo
    otra = cuentas.crear(libro, "Otra Tarjeta Ficticia", "credito", limite_credito=2_000,
                         fecha_creacion=date(2026, 1, 1)).id
    movimientos.registrar_gasto(libro, date(2026, 7, 25), otra, cat("ALIMENTOS"), 2_100)   # ese día ya lo pasa
    (aviso,) = avisos.antes_de_registrar(libro, HOY, [(otra, -250_000)])
    assert aviso.clave == LIMITE and "tu deuda quedaría en $2,500.00." in aviso.mensaje
    assert avisos.antes_de_registrar(libro, HOY, [(otra, -1_000)]) == []


def test_una_tarjeta_pasaria_su_limite(libro, ctas, cat):
    movimientos.registrar_gasto(libro, date(2026, 7, 5), ctas.credito, cat("ALIMENTOS"), 800)
    (aviso,) = avisos.antes_de_registrar(libro, HOY, [(ctas.credito, -30_000)])
    assert aviso.clave == LIMITE
    assert aviso.mensaje == ("«Tarjeta Ficticia» pasaría su límite de $1,000.00: tu deuda quedaría en $1,100.00. "
                             "¿Están bien la tarjeta y el importe?")
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
