"""Tu moneda: la de tu país (Configuración → Tu perfil). TALLY muestra todo con su símbolo y su formato: en México
``$1,234.56``, en España ``1.234,56 €``, en Argentina ``$ 1.234,56``, en Chile ``$1.235``…

Por dentro todo sigue en centavos (``int``): la moneda solo cambia cómo se ve, no los importes. Por eso conviene
elegirla al empezar; cambiarla después no convierte nada (no es un tipo de cambio).

Tu moneda es la base: TALLY suma todo en ella. Una cuenta puede estar en otra (dólares, euros…) y un título en otra;
se convierten con el tipo de cambio contra la tuya (motor/divisas.py). Las monedas de Europa y los dólares de
Estados Unidos y Canadá están aquí sobre todo para eso.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from motor.errores import ErrorValidacion

BASE = "MXN"            # la de quien no ha elegido (TALLY nació en México)


@dataclass(frozen=True, slots=True)
class Moneda:
    codigo: str
    nombre: str
    paises: str
    simbolo: str
    decimales: int = 2
    miles: str = ","
    decimal: str = "."
    despues: bool = False          # el símbolo va después del número: 1.234,56 €
    espacio: bool = False          # un espacio entre el símbolo y el número: $ 1.234,56
    internacional: str = ""        # el símbolo cuando no es tu moneda, para no confundirla: US$, CA$, MX$, SEK…

    @property
    def etiqueta(self) -> str:
        return f"{self.nombre} ({self.codigo}) · {self.paises}"

    @property
    def ejemplo(self) -> str:
        return formatear(Decimal("1234567.89"), self)


MONEDAS: dict[str, Moneda] = {m.codigo: m for m in (
    Moneda("MXN", "Peso mexicano", "México", "$", internacional="MX$"),
    Moneda("USD", "Dólar estadounidense", "Estados Unidos, Ecuador, El Salvador, Panamá, Puerto Rico", "$",
           internacional="US$"),
    Moneda("EUR", "Euro", "España", "€", miles=".", decimal=",", despues=True, espacio=True),
    Moneda("ARS", "Peso argentino", "Argentina", "$", miles=".", decimal=",", espacio=True, internacional="ARS"),
    Moneda("COP", "Peso colombiano", "Colombia", "$", decimales=0, miles=".", decimal=",", espacio=True,
           internacional="COP"),
    Moneda("CLP", "Peso chileno", "Chile", "$", decimales=0, miles=".", decimal=",", internacional="CLP"),
    Moneda("PEN", "Sol", "Perú", "S/", espacio=True),
    Moneda("UYU", "Peso uruguayo", "Uruguay", "$", miles=".", decimal=",", espacio=True, internacional="UYU"),
    Moneda("PYG", "Guaraní", "Paraguay", "₲", decimales=0, miles=".", decimal=",", espacio=True),
    Moneda("BOB", "Boliviano", "Bolivia", "Bs", miles=".", decimal=",", espacio=True, internacional="BOB"),
    Moneda("VES", "Bolívar", "Venezuela", "Bs.", miles=".", decimal=",", espacio=True, internacional="VES"),
    Moneda("GTQ", "Quetzal", "Guatemala", "Q"),
    Moneda("HNL", "Lempira", "Honduras", "L", espacio=True),
    Moneda("NIO", "Córdoba", "Nicaragua", "C$", espacio=True),
    Moneda("CRC", "Colón", "Costa Rica", "₡", miles=".", decimal=","),
    Moneda("DOP", "Peso dominicano", "República Dominicana", "RD$"),
    Moneda("CUP", "Peso cubano", "Cuba", "$", internacional="CUP"),
    # Para cuentas en otra moneda (motor/divisas.py): los dólares de Norteamérica y las monedas de Europa.
    Moneda("CAD", "Dólar canadiense", "Canadá", "$", internacional="CA$"),
    Moneda("GBP", "Libra esterlina", "Reino Unido", "£"),
    Moneda("CHF", "Franco suizo", "Suiza", "CHF", miles="'", espacio=True),
    Moneda("SEK", "Corona sueca", "Suecia", "kr", miles=" ", decimal=",", despues=True, espacio=True,
           internacional="SEK"),
    Moneda("NOK", "Corona noruega", "Noruega", "kr", miles=" ", decimal=",", despues=True, espacio=True,
           internacional="NOK"),
    Moneda("DKK", "Corona danesa", "Dinamarca", "kr.", miles=".", decimal=",", despues=True, espacio=True,
           internacional="DKK"),
    Moneda("PLN", "Zloty polaco", "Polonia", "zł", miles=" ", decimal=",", despues=True, espacio=True),
    Moneda("CZK", "Corona checa", "Chequia", "Kč", miles=" ", decimal=",", despues=True, espacio=True),
    Moneda("HUF", "Forinto húngaro", "Hungría", "Ft", decimales=0, miles=" ", decimal=",", despues=True,
           espacio=True),
    Moneda("RON", "Leu rumano", "Rumania", "lei", miles=".", decimal=",", despues=True, espacio=True),
)}

_activa: Moneda = MONEDAS[BASE]


def moneda(codigo: str) -> Moneda:
    try:
        return MONEDAS[(codigo or BASE).strip().upper()]
    except KeyError:
        raise ErrorValidacion(f"No conozco la moneda «{codigo}». Elige una de la lista.") from None


def usar(codigo: str | None) -> Moneda:
    """La moneda con la que se muestra todo (la de tu perfil). Una desconocida deja la de siempre."""
    global _activa
    _activa = MONEDAS.get((codigo or BASE).strip().upper(), MONEDAS[BASE])
    return _activa


def activa() -> Moneda:
    return _activa


def de(libro) -> str:
    """El código de la moneda del libro (la de tu perfil)."""
    return libro.perfil.moneda if libro.perfil and libro.perfil.moneda in MONEDAS else BASE


def redondo(valor: Decimal | int) -> Decimal:
    """El número «redondo» (1, 2 o 5 por una potencia de 10) más grande que no pasa de ``valor``: 116 → 100,
    232 → 200, 30,000 → 20,000. Sirve para umbrales que valgan igual en cualquier moneda (se calculan con tus
    propios gastos)."""
    valor = Decimal(valor)
    if valor < 1:
        return Decimal(1)
    potencia = Decimal(10) ** (len(str(int(valor))) - 1)
    return max(paso * potencia for paso in (1, 2, 5) if paso * potencia <= valor)


def numero(importe: Decimal | int, m: Moneda | None = None, decimales: int | None = None) -> str:
    """El número con los separadores de la moneda, sin símbolo: ``1.234,56``."""
    m = m or _activa
    dec = m.decimales if decimales is None else decimales
    valor = abs(Decimal(importe)).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    texto = f"{valor:,.{dec}f}"
    return texto.replace(",", "\0").replace(".", m.decimal).replace("\0", m.miles)


def en_moneda(importe: Decimal | int, codigo: str, decimales: int | None = None) -> str:
    """Un importe en la moneda ``codigo`` (la de una cuenta). Si no es tu moneda, con su símbolo internacional para
    no confundirla con la tuya: ``US$1,200.00`` junto a ``$20,640.00``."""
    m = moneda(codigo)
    if m.codigo != _activa.codigo and m.internacional:
        # Un código de letras va separado del número: «CLP 75.456», no «CLP75.456».
        m = replace(m, simbolo=m.internacional, espacio=m.espacio or m.internacional.isalpha())
    return formatear(importe, m, decimales)


def formatear(importe: Decimal | int, m: Moneda | None = None, decimales: int | None = None) -> str:
    """``$1,234.56``, ``1.234,56 €``, ``$ 1.234``… (con ``-`` adelante si es negativo)."""
    m = m or _activa
    texto = numero(importe, m, decimales)
    signo = "-" if Decimal(importe) < 0 and texto.strip("0.,") else ""
    if m.despues:
        return f"{signo}{texto}{' ' if m.espacio else ''}{m.simbolo}"
    return f"{signo}{m.simbolo}{' ' if m.espacio else ''}{texto}"
