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


ETIQUETA_ENTIDAD = {
    "perfil": "Perfil",
    "grupo": "Grupo",
    "categoria": "Categoría",
    "cuenta": "Cuenta",
    "operacion": "Movimiento",
    "respaldo": "Respaldo",
}
ETIQUETA_ACCION = {CREAR: "Creó", EDITAR: "Editó", BORRAR: "Borró", RESTAURAR: "Restauró"}
_CAMPOS = {
    "nombre": "nombre", "descripcion": "descripción", "notas": "notas", "fecha": "fecha",
    "partidas": "importe/cuenta/categoría", "tipo": "tipo", "activa": "activa/archivada",
    "grupo_id": "grupo", "principal": "ingreso principal", "orden": "orden",
    "en_disponible": "cuenta como disponible", "institucion": "institución",
    "limite_credito": "límite", "dia_corte": "día de corte", "dia_pago": "día de pago",
    "dias_para_pagar": "días para pagar", "dias_habiles": "días hábiles", "recorrer_inhabil": "recorrer a día hábil",
}
_IGNORAR = {"modificado_en", "secuencia", "creado_en"}


def resumen(registro: Registro | Cambio) -> str:
    """Una línea legible: «Editó Movimiento «Pizza» (importe/cuenta/categoría, descripción)»."""
    datos = registro.despues or registro.antes or {}
    nombre = datos.get("nombre") or datos.get("descripcion") or datos.get("archivo") or ""
    texto = f"{ETIQUETA_ACCION.get(registro.accion, registro.accion)} {ETIQUETA_ENTIDAD.get(registro.entidad, registro.entidad)}"
    if nombre:
        texto += f" «{nombre}»"
    if registro.accion == EDITAR:
        campos = sorted(_CAMPOS.get(c, c) for c in campos_modificados(registro) if c not in _IGNORAR)
        if campos:
            texto += f" ({', '.join(campos)})"
    return texto
