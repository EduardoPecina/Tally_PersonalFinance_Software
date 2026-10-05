"""Bitácora de cambios: qué se modificó, valor anterior, valor nuevo y cuándo.

Los cambios se obtienen comparando el estado guardado con el nuevo, así que
ninguna función del motor tiene que acordarse de registrarlos. No se guarda
nada sobre el usuario más allá de sus propios datos financieros.
"""

from __future__ import annotations

from dataclasses import dataclass

from motor.serializacion import ENTIDADES, Instantanea

CREAR = "crear"
EDITAR = "editar"
BORRAR = "borrar"
RESTAURAR = "restaurar"


@dataclass(frozen=True, slots=True)
class Cambio:
    entidad: str  # perfil, grupo, categoria, cuenta, operacion o respaldo
    entidad_id: str
    accion: str  # crear, editar, borrar o restaurar
    antes: dict | None
    despues: dict | None


@dataclass(frozen=True, slots=True)
class Registro:
    """Un renglón de la bitácora ya guardado."""

    id: int
    fecha_hora: str
    entidad: str
    entidad_id: str
    accion: str
    antes: dict | None
    despues: dict | None


def diferencias(antes: Instantanea, despues: Instantanea) -> list[Cambio]:
    """Cambios necesarios para pasar del estado ``antes`` al ``despues``."""
    cambios = []
    for entidad in ENTIDADES:
        previos = antes.get(entidad, {})
        nuevos = despues.get(entidad, {})
        for entidad_id in sorted(previos.keys() | nuevos.keys()):
            a, d = previos.get(entidad_id), nuevos.get(entidad_id)
            if a == d:
                continue
            accion = CREAR if a is None else BORRAR if d is None else EDITAR
            cambios.append(Cambio(entidad, entidad_id, accion, a, d))
    return cambios


def campos_modificados(registro: Registro | Cambio) -> dict[str, tuple]:
    """``{campo: (anterior, nuevo)}`` de una edición."""
    antes, despues = registro.antes or {}, registro.despues or {}
    return {
        campo: (antes.get(campo), despues.get(campo))
        for campo in antes.keys() | despues.keys()
        if antes.get(campo) != despues.get(campo)
    }
