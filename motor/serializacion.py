"""Conversión entre entidades del motor y diccionarios JSON.

Es el formato estable que usan la base de datos, los respaldos y la
bitácora. Fechas en ISO 8601, importes en centavos enteros.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from motor.errores import ErrorDatos
from motor.libro import Libro
from motor.modelo import (
    Categoria,
    ClaseCategoria,
    Cuenta,
    Grupo,
    Operacion,
    Partida,
    Perfil,
    TipoCuenta,
    TipoOperacion,
)

# Tipos de entidad, en el orden en que se cargan.
ENTIDADES = ("perfil", "grupo", "categoria", "cuenta", "operacion")
ID_PERFIL = "perfil"


def _fecha(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def _momento(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


def _iso(valor: date | datetime | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat(timespec="seconds")
    return valor.isoformat()


# ---------------------------------------------------------------- a dict


def perfil_a_dict(p: Perfil) -> dict:
    return {"nombre": p.nombre, "moneda": p.moneda, "creado_en": _iso(p.creado_en)}


def grupo_a_dict(g: Grupo) -> dict:
    return {"id": g.id, "nombre": g.nombre, "orden": g.orden}


def categoria_a_dict(c: Categoria) -> dict:
    return {
        "id": c.id, "nombre": c.nombre, "clase": c.clase.value, "grupo_id": c.grupo_id,
        "activa": c.activa, "principal": c.principal, "orden": c.orden,
    }


def cuenta_a_dict(c: Cuenta) -> dict:
    return {
        "id": c.id, "nombre": c.nombre, "tipo": c.tipo.value, "fecha_creacion": _iso(c.fecha_creacion),
        "en_disponible": c.en_disponible, "moneda": c.moneda, "activa": c.activa,
        "institucion": c.institucion, "notas": c.notas, "orden": c.orden,
        "limite_credito": c.limite_credito, "dia_corte": c.dia_corte, "dia_pago": c.dia_pago,
    }


def operacion_a_dict(op: Operacion) -> dict:
    return {
        "id": op.id, "fecha": _iso(op.fecha), "tipo": op.tipo.value,
        "partidas": [
            {"importe": p.importe, "cuenta_id": p.cuenta_id, "categoria_id": p.categoria_id} for p in op.partidas
        ],
        "descripcion": op.descripcion, "notas": op.notas, "secuencia": op.secuencia,
        "creado_en": _iso(op.creado_en), "modificado_en": _iso(op.modificado_en),
    }


# ---------------------------------------------------------------- desde dict


def perfil_desde_dict(d: dict) -> Perfil:
    return Perfil(nombre=d["nombre"], moneda=d.get("moneda", "MXN"), creado_en=_momento(d["creado_en"]))


def grupo_desde_dict(d: dict) -> Grupo:
    return Grupo(id=d["id"], nombre=d["nombre"], orden=d.get("orden", 0))


def categoria_desde_dict(d: dict) -> Categoria:
    return Categoria(
        id=d["id"], nombre=d["nombre"], clase=ClaseCategoria(d["clase"]), grupo_id=d.get("grupo_id"),
        activa=d.get("activa", True), principal=d.get("principal", False), orden=d.get("orden", 0),
    )


def cuenta_desde_dict(d: dict) -> Cuenta:
    return Cuenta(
        id=d["id"], nombre=d["nombre"], tipo=TipoCuenta(d["tipo"]), fecha_creacion=_fecha(d["fecha_creacion"]),
        en_disponible=d["en_disponible"], moneda=d.get("moneda", "MXN"), activa=d.get("activa", True),
        institucion=d.get("institucion", ""), notas=d.get("notas", ""), orden=d.get("orden", 0),
        limite_credito=d.get("limite_credito"), dia_corte=d.get("dia_corte"), dia_pago=d.get("dia_pago"),
    )


def operacion_desde_dict(d: dict) -> Operacion:
    return Operacion(
        id=d["id"], fecha=_fecha(d["fecha"]), tipo=TipoOperacion(d["tipo"]),
        partidas=tuple(
            Partida(importe=p["importe"], cuenta_id=p.get("cuenta_id"), categoria_id=p.get("categoria_id"))
            for p in d["partidas"]
        ),
        descripcion=d.get("descripcion", ""), notas=d.get("notas", ""), secuencia=d.get("secuencia", 0),
        creado_en=_momento(d.get("creado_en")), modificado_en=_momento(d.get("modificado_en")),
    )


# ---------------------------------------------------------------- libro

Instantanea = dict[str, dict[str, dict]]
"""``{tipo_de_entidad: {id: datos}}``: el estado completo de un libro."""


def instantanea(libro: Libro) -> Instantanea:
    return {
        "perfil": {ID_PERFIL: perfil_a_dict(libro.perfil)} if libro.perfil else {},
        "grupo": {g.id: grupo_a_dict(g) for g in libro.grupos()},
        "categoria": {c.id: categoria_a_dict(c) for c in libro.categorias()},
        "cuenta": {c.id: cuenta_a_dict(c) for c in libro.cuentas()},
        "operacion": {op.id: operacion_a_dict(op) for op in libro.operaciones()},
    }


def libro_desde_instantanea(
    datos: Instantanea, secuencia: int = 0, *, reloj: Callable[[], datetime] | None = None
) -> Libro:
    """Reconstruye un libro y verifica que esté íntegro; si no, ``ErrorDatos``."""
    try:
        perfil = datos.get("perfil", {}).get(ID_PERFIL)
        libro = Libro.desde_estado(
            perfil=perfil_desde_dict(perfil) if perfil else None,
            grupos=[grupo_desde_dict(d) for d in datos.get("grupo", {}).values()],
            categorias=[categoria_desde_dict(d) for d in datos.get("categoria", {}).values()],
            cuentas=[cuenta_desde_dict(d) for d in datos.get("cuenta", {}).values()],
            operaciones=[operacion_desde_dict(d) for d in datos.get("operacion", {}).values()],
            secuencia=secuencia,
            reloj=reloj,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ErrorDatos(f"Los datos guardados están dañados o incompletos ({error}).") from error
    problemas = verificar_integridad(libro)
    if problemas:
        raise ErrorDatos("Los datos guardados no cuadran: " + "; ".join(problemas[:5]))
    return libro


def verificar_integridad(libro: Libro) -> list[str]:
    """Problemas estructurales del libro (vacía si todo está bien)."""
    problemas = []
    cuentas = {c.id for c in libro.cuentas()}
    categorias = {c.id for c in libro.categorias()}
    grupos = {g.id for g in libro.grupos()}
    for categoria in libro.categorias():
        if categoria.grupo_id is not None and categoria.grupo_id not in grupos:
            problemas.append(f"la categoría «{categoria.nombre}» apunta a un grupo inexistente")
    for op in libro.operaciones():
        if sum(p.importe for p in op.partidas) != 0:
            problemas.append(f"el movimiento del {op.fecha} no suma cero")
        for p in op.partidas:
            if p.cuenta_id is not None and p.cuenta_id not in cuentas:
                problemas.append(f"el movimiento del {op.fecha} usa una cuenta inexistente")
            if p.categoria_id is not None and p.categoria_id not in categorias:
                problemas.append(f"el movimiento del {op.fecha} usa una categoría inexistente")
    return problemas

