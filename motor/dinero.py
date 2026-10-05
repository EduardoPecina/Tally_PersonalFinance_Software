"""Conversión de importes.

Internamente todo importe es un ``int`` en centavos. Hacia fuera (API del
motor y reportes) se usa ``Decimal`` en pesos con dos decimales.
"""

from decimal import Decimal, InvalidOperation

from motor.errores import ErrorValidacion

_CENTAVO = Decimal("0.01")


def a_centavos(valor: Decimal | int | float | str) -> int:
    """Convierte un importe en pesos a centavos enteros.

    Acepta ``Decimal``, ``int``, ``float`` o texto como ``"$1,234.56"``.
    Rechaza importes con más de dos decimales en lugar de redondearlos en
    silencio.
    """
    if isinstance(valor, bool):
        raise ErrorValidacion("El importe debe ser un número.")
    if isinstance(valor, Decimal):
        numero = valor
    elif isinstance(valor, int):
        numero = Decimal(valor)
    elif isinstance(valor, float):
        # Un float no representa centavos exactos (59.94 + 0.01 puede dar 59.950000000000003):
        # se toleran residuos binarios, pero no un tercer decimal real.
        numero = Decimal(repr(valor))
        if numero.is_finite() and abs(numero - numero.quantize(_CENTAVO)) < Decimal("0.000001"):
            numero = numero.quantize(_CENTAVO)
    elif isinstance(valor, str):
        texto = valor.strip().replace("$", "").replace(",", "").replace(" ", "")
        try:
            numero = Decimal(texto)
        except InvalidOperation:
            raise ErrorValidacion(f"«{valor}» no es un importe válido.") from None
    else:
        raise ErrorValidacion("El importe debe ser un número.")

    if not numero.is_finite():
        raise ErrorValidacion("El importe debe ser un número finito.")
    redondeado = numero.quantize(_CENTAVO)
    if redondeado != numero:
        raise ErrorValidacion("El importe no puede tener más de dos decimales.")
    return int(redondeado * 100)


def a_pesos(centavos: int) -> Decimal:
    """Convierte centavos enteros a pesos con dos decimales."""
    return (Decimal(centavos) / 100).quantize(_CENTAVO)


def formatear(importe: Decimal | int) -> str:
    """Da formato ``$1,234.56`` (o ``-$1,234.56``) a un importe en pesos."""
    pesos = Decimal(importe).quantize(_CENTAVO)
    signo = "-" if pesos < 0 else ""
    return f"{signo}${abs(pesos):,.2f}"
