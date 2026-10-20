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
from functools import lru_cache

from motor.errores import ErrorValidacion

_NO_ALFANUMERICO = re.compile(r"[^0-9A-Z]+")


def normalizar_nombre(nombre: str) -> str:
    """Quita espacios sobrantes (evita «Débito» y « Débito» duplicadas)."""
    limpio = " ".join(str(nombre).split())
    if not limpio:
        raise ErrorValidacion("El nombre no puede estar vacío.")
    return limpio


def _sin_acentos(texto: str, *, conservar_enie: bool) -> str:
    texto = unicodedata.normalize("NFC", str(texto))
    if texto.isascii():                     # lo más común: nada que quitar
        return texto
    separado = unicodedata.normalize("NFD", texto)
    if conservar_enie:                      # la Ñ no es un acento: se vuelve a juntar antes de quitar los demás
        separado = separado.replace("n\u0303", "ñ").replace("N\u0303", "Ñ")
    return "".join(c for c in separado if not unicodedata.combining(c))


def estandarizar(nombre: str) -> str:
    """«  Gastos   médicos » → «GASTOS MEDICOS». Error si queda vacío."""
    limpio = " ".join(_sin_acentos(nombre, conservar_enie=True).upper().split())
    if not limpio:
        raise ErrorValidacion("El nombre no puede estar vacío.")
    return limpio


@lru_cache(maxsize=16_384)
def clave(texto: str) -> str:
    """Forma de comparar nombres: «Cafés & Snacks» → «CAFES SNACKS»; «Niñera» → «NINERA».

    Se recuerda: las mismas descripciones se comparan miles de veces (reglas, duplicados, salud de tus datos)."""
    sencillo = _sin_acentos(texto, conservar_enie=False).upper()
    return " ".join(_NO_ALFANUMERICO.sub(" ", sencillo).split())
