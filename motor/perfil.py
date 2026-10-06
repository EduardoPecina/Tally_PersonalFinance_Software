"""Perfil local del usuario (solo su nombre, para la bienvenida).

No hay cuentas de usuario ni inicio de sesión: el perfil vive en el mismo
archivo de datos que las finanzas.
"""

from __future__ import annotations

from dataclasses import replace

from motor.libro import Libro
from motor.modelo import Perfil
from motor.textos import normalizar_nombre


def necesita_bienvenida(libro: Libro) -> bool:
    """True la primera vez que se abre TALLY (aún no hay perfil)."""
    return libro.perfil is None


def configurar(libro: Libro, nombre: str) -> Perfil:
    nombre = normalizar_nombre(nombre)
    if libro.perfil is None:
        libro.perfil = Perfil(nombre=nombre, creado_en=libro.ahora())
    else:
        libro.perfil = replace(libro.perfil, nombre=nombre)
    return libro.perfil
