"""Nombres: limpieza, estandarización y comparación.

- :func:`normalizar_nombre` solo quita espacios sobrantes (cuentas, perfil, clasificaciones).
- :func:`estandarizar` es la forma en que se guardan categorías y subcategorías: MAYÚSCULAS y sin acentos
  (la Ñ se conserva: no es un acento). «Gastos médicos» → «GASTOS MEDICOS».
- :func:`clave` sirve para comparar: ignora mayúsculas, acentos, la tilde de la Ñ, signos y espacios. Así
  «Café/Snacks», «CAFE SNACKS» y «cafe   snacks» son lo mismo y no se pueden agregar dos veces.
"""

from __future__ import annotations

import re
import unicodedata

from motor.errores import ErrorValidacion


def normalizar_nombre(nombre: str) -> str:
    """Quita espacios sobrantes (evita «Débito» y « Débito» duplicadas)."""
    limpio = " ".join(str(nombre).split())
    if not limpio:
        raise ErrorValidacion("El nombre no puede estar vacío.")
    return limpio


def _sin_acentos(texto: str, *, conservar_enie: bool) -> str:
    letras = []
    for letra in unicodedata.normalize("NFC", str(texto)):
        if conservar_enie and letra in "ñÑ":
            letras.append(letra)
        else:
            letras.append("".join(c for c in unicodedata.normalize("NFD", letra) if not unicodedata.combining(c)))
    return "".join(letras)


def estandarizar(nombre: str) -> str:
    """«  Gastos   médicos » → «GASTOS MEDICOS». Error si queda vacío."""
    limpio = " ".join(_sin_acentos(nombre, conservar_enie=True).upper().split())
    if not limpio:
        raise ErrorValidacion("El nombre no puede estar vacío.")
    return limpio


def clave(texto: str) -> str:
    """Forma de comparar nombres: «Cafés & Snacks» → «CAFES SNACKS»; «Niñera» → «NINERA»."""
    sencillo = _sin_acentos(texto, conservar_enie=False).upper()
    return " ".join(re.sub(r"[^0-9A-Z]+", " ", sencillo).split())
