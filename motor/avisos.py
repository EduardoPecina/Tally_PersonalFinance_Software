"""Avisos antes de guardar un movimiento: lo que casi siempre es un error de dedo.

No impiden guardar (a veces es correcto: un sobregiro, una compra que pasa el límite, un pago que registras con
tiempo). El portal los muestra y pide confirmar antes de guardar:

- una cuenta de débito, ahorro, efectivo o inversión **quedaría en negativo** (¿elegiste la cuenta equivocada?
  ¿un cero de más?);
- una tarjeta de crédito **pasaría su límite**;
- la **fecha** es de más de un mes adelante o de hace un año o más (¿el año mal escrito?).

El saldo que se revisa es el de hoy (o el del día del movimiento, si es adelante) con el movimiento incluido.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from motor.dinero import a_pesos, formatear
from motor.libro import Libro
from motor.modelo import TipoCuenta

DIAS_ADELANTE = 31          # más adelante que esto ya no es «el pago del próximo mes»
DIAS_ATRAS = 365            # un año o más atrás: casi siempre es el año mal escrito
SIN_NEGATIVO = frozenset({TipoCuenta.DEBITO, TipoCuenta.AHORRO, TipoCuenta.EFECTIVO, TipoCuenta.INVERSION})
NEGATIVO, LIMITE, FECHA = "negativo", "limite", "fecha"


@dataclass(frozen=True, slots=True)
class Aviso:
    clave: str                 # NEGATIVO, LIMITE o FECHA
    mensaje: str               # para mostrarse tal cual


def antes_de_registrar(libro: Libro, fecha: date, cambios: Iterable[tuple[str, int]]) -> list[Aviso]:
    """Los avisos de un movimiento que aún no se guarda. ``cambios``: (cuenta, centavos) que movería en cada cuenta,
    con signo: −50000 si salen $500 de ella, +50000 si entran."""
    hoy = libro.hoy()
    avisos = []
    if (fecha - hoy).days > DIAS_ADELANTE:
        avisos.append(Aviso(FECHA, f"La fecha es el {fecha:%d/%m/%Y}, dentro de {_tiempo((fecha - hoy).days)}. "
                                   "¿Es correcta?"))
    elif (hoy - fecha).days >= DIAS_ATRAS:
        avisos.append(Aviso(FECHA, f"La fecha es el {fecha:%d/%m/%Y}, hace {_tiempo((hoy - fecha).days)}. "
                                   "¿Es correcta?"))
    por_cuenta: dict[str, int] = defaultdict(int)
    for cuenta_id, centavos in cambios:
        por_cuenta[cuenta_id] += centavos
    al = max(fecha, hoy)
    for cuenta_id, cambio in por_cuenta.items():
        if cambio >= 0:
            continue                                          # si entra dinero, no hay de qué avisar
        cuenta = libro.cuenta(cuenta_id)
        saldo = libro.saldo_centavos(cuenta_id, al) + cambio
        if cuenta.tipo in SIN_NEGATIVO and saldo < 0:
            avisos.append(Aviso(NEGATIVO, f"«{cuenta.nombre}» quedaría en {formatear(a_pesos(saldo))}. "
                                          "¿Es la cuenta correcta?"))
        elif cuenta.tipo is TipoCuenta.CREDITO and cuenta.limite_credito is not None \
                and -saldo > cuenta.limite_credito:
            avisos.append(Aviso(LIMITE, f"«{cuenta.nombre}» pasaría su límite de "
                                        f"{formatear(a_pesos(cuenta.limite_credito))}: deberías "
                                        f"{formatear(a_pesos(-saldo))}."))
    return avisos


def _tiempo(dias: int) -> str:
    """«40 días», «5 meses», «1 año», «10 años»."""
    if dias < 60:
        return f"{dias} días"
    if dias < 365:
        return f"{dias // 30} meses"
    anios = dias // 365
    return "1 año" if anios == 1 else f"{anios} años"
