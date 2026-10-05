"""Categorías y grupos de categorías.

Todo es personalizable; el catálogo inicial es solo un punto de partida.
"""

from __future__ import annotations

from dataclasses import replace

from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Categoria, ClaseCategoria, Grupo, Partida

GRUPOS_INICIALES = ("Necesidad", "Disfrute", "Estabilidad", "Inversión", "Dádivas")

# (nombre, clase, grupo, principal)
CATALOGO_INICIAL: tuple[tuple[str, ClaseCategoria, str | None, bool], ...] = (
    ("Nómina", ClaseCategoria.INGRESO, None, True),
    ("Freelance", ClaseCategoria.INGRESO, None, False),
    ("Bonos", ClaseCategoria.INGRESO, None, False),
    ("Intereses y rendimientos", ClaseCategoria.INGRESO, None, False),
    ("Ventas", ClaseCategoria.INGRESO, None, False),
    ("Otros ingresos", ClaseCategoria.INGRESO, None, False),
    ("Alimentos", ClaseCategoria.GASTO, "Necesidad", False),
    ("Snacks y antojos", ClaseCategoria.GASTO, "Disfrute", False),
    ("Vivienda", ClaseCategoria.GASTO, "Necesidad", False),
    ("Hogar y mantenimiento", ClaseCategoria.GASTO, "Necesidad", False),
    ("Mejoras del hogar", ClaseCategoria.GASTO, "Disfrute", False),
    ("Transporte", ClaseCategoria.GASTO, "Necesidad", False),
    ("Salud y cuidado personal", ClaseCategoria.GASTO, "Necesidad", False),
    ("Educación", ClaseCategoria.GASTO, "Inversión", False),
    ("Insumos de trabajo", ClaseCategoria.GASTO, "Estabilidad", False),
    ("Recargas y telefonía", ClaseCategoria.GASTO, "Necesidad", False),
    ("Servicios de software", ClaseCategoria.GASTO, "Necesidad", False),
    ("Suscripciones y streaming", ClaseCategoria.GASTO, "Disfrute", False),
    ("Compras en línea", ClaseCategoria.GASTO, "Disfrute", False),
    ("Hardware y entretenimiento", ClaseCategoria.GASTO, "Disfrute", False),
    ("Regalos", ClaseCategoria.GASTO, "Dádivas", False),
    ("Gastos financieros", ClaseCategoria.GASTO, "Necesidad", False),
    ("Retiros de efectivo", ClaseCategoria.GASTO, "Necesidad", False),
    ("Otros gastos", ClaseCategoria.GASTO, None, False),
)


def normalizar_nombre(nombre: str) -> str:
    """Quita espacios sobrantes (evita «ALIMENTOS» y « ALIMENTOS» duplicadas)."""
    limpio = " ".join(str(nombre).split())
    if not limpio:
        raise ErrorValidacion("El nombre no puede estar vacío.")
    return limpio


# ------------------------------------------------------------------- grupos


def crear_grupo(libro: Libro, nombre: str) -> Grupo:
    nombre = normalizar_nombre(nombre)
    if any(g.nombre.casefold() == nombre.casefold() for g in libro.grupos()):
        raise ErrorValidacion(f"Ya existe el grupo «{nombre}».")
    orden = max((g.orden for g in libro.grupos()), default=-1) + 1
    return libro.guardar_grupo(Grupo(libro.nuevo_id(), nombre, orden))


def renombrar_grupo(libro: Libro, grupo_id: str, nombre: str) -> Grupo:
    grupo = libro.grupo(grupo_id)
    nombre = normalizar_nombre(nombre)
    if any(g.id != grupo_id and g.nombre.casefold() == nombre.casefold() for g in libro.grupos()):
        raise ErrorValidacion(f"Ya existe el grupo «{nombre}».")
    return libro.guardar_grupo(replace(grupo, nombre=nombre))


def eliminar_grupo(libro: Libro, grupo_id: str) -> None:
    """Borra el grupo; sus categorías quedan sin grupo (no se pierde nada)."""
    libro.grupo(grupo_id)
    for categoria in libro.categorias():
        if categoria.grupo_id == grupo_id:
            libro.guardar_categoria(replace(categoria, grupo_id=None))
    libro.quitar_grupo(grupo_id)


# --------------------------------------------------------------- categorías


def crear(
    libro: Libro,
    nombre: str,
    clase: ClaseCategoria,
    *,
    grupo_id: str | None = None,
    principal: bool = False,
) -> Categoria:
    clase = ClaseCategoria(clase)
    if clase is ClaseCategoria.SISTEMA:
        raise ErrorValidacion("No se pueden crear categorías del sistema.")
    nombre = normalizar_nombre(nombre)
    _nombre_libre(libro, nombre, clase)
    if grupo_id is not None:
        libro.grupo(grupo_id)
    _validar_principal(clase, principal)
    orden = max((c.orden for c in libro.categorias()), default=-1) + 1
    return libro.guardar_categoria(
        Categoria(libro.nuevo_id(), nombre, clase, grupo_id=grupo_id, principal=principal, orden=orden)
    )


_SIN_CAMBIO = object()


def editar(
    libro: Libro,
    categoria_id: str,
    *,
    nombre: str | None = None,
    grupo_id: str | None | object = _SIN_CAMBIO,
    principal: bool | None = None,
    orden: int | None = None,
) -> Categoria:
    categoria = _editable(libro, categoria_id)
    cambios: dict = {}
    if nombre is not None:
        nombre = normalizar_nombre(nombre)
        _nombre_libre(libro, nombre, categoria.clase, excepto=categoria_id)
        cambios["nombre"] = nombre
    if grupo_id is not _SIN_CAMBIO:
        if grupo_id is not None:
            libro.grupo(grupo_id)
        cambios["grupo_id"] = grupo_id
    if principal is not None:
        _validar_principal(categoria.clase, principal)
        cambios["principal"] = principal
    if orden is not None:
        cambios["orden"] = orden
    return libro.guardar_categoria(replace(categoria, **cambios))


def archivar(libro: Libro, categoria_id: str) -> Categoria:
    """Oculta la categoría para movimientos nuevos; su historial se conserva."""
    return libro.guardar_categoria(replace(_editable(libro, categoria_id), activa=False))


def reactivar(libro: Libro, categoria_id: str) -> Categoria:
    return libro.guardar_categoria(replace(_editable(libro, categoria_id), activa=True))


def en_uso(libro: Libro, categoria_id: str) -> bool:
    return any(p.categoria_id == categoria_id for op in libro.operaciones() for p in op.partidas)


def eliminar(libro: Libro, categoria_id: str, *, reasignar_a: str | None = None) -> None:
    """Borra una categoría.

    Si tiene movimientos, hay que indicar a qué categoría (de la misma clase)
    pasan; en la práctica es una fusión de categorías.
    """
    categoria = _editable(libro, categoria_id)
    if en_uso(libro, categoria_id):
        if reasignar_a is None:
            raise ErrorValidacion(f"«{categoria.nombre}» tiene movimientos; elige a qué categoría pasarlos.")
        destino = libro.categoria(reasignar_a)
        if destino.id == categoria_id or destino.clase is not categoria.clase:
            raise ErrorValidacion("Los movimientos solo pueden pasar a otra categoría del mismo tipo.")
        for op in libro.operaciones():
            if any(p.categoria_id == categoria_id for p in op.partidas):
                partidas = tuple(
                    Partida(p.importe, categoria_id=destino.id) if p.categoria_id == categoria_id else p
                    for p in op.partidas
                )
                libro.reemplazar_operacion(op.id, replace(op, partidas=_fusionar(partidas)))
    libro.quitar_categoria(categoria_id)


def para_tipo(libro: Libro, tipo) -> list[Categoria]:
    """Categorías activas que se pueden elegir para un tipo de movimiento."""
    from motor.modelo import TipoOperacion

    tipo = TipoOperacion(tipo)
    if tipo in (TipoOperacion.GASTO, TipoOperacion.REEMBOLSO):
        clase = ClaseCategoria.GASTO
    elif tipo in (TipoOperacion.INGRESO, TipoOperacion.RENDIMIENTO):
        clase = ClaseCategoria.INGRESO
    else:
        return []
    return [c for c in libro.categorias() if c.clase is clase and c.activa]


def buscar(libro: Libro, nombre: str, clase: ClaseCategoria | None = None) -> Categoria | None:
    """Busca una categoría por nombre, sin importar mayúsculas ni espacios."""
    clave = normalizar_nombre(nombre).casefold()
    for categoria in libro.categorias():
        if categoria.nombre.casefold() == clave and (clase is None or categoria.clase is clase):
            return categoria
    return None


def cargar_catalogo_inicial(libro: Libro) -> None:
    """Crea los grupos y categorías sugeridos. Solo actúa sobre un libro vacío."""
    if libro.grupos() or any(c.clase is not ClaseCategoria.SISTEMA for c in libro.categorias()):
        return
    grupos = {nombre: crear_grupo(libro, nombre).id for nombre in GRUPOS_INICIALES}
    for nombre, clase, grupo, principal in CATALOGO_INICIAL:
        crear(libro, nombre, clase, grupo_id=grupos.get(grupo) if grupo else None, principal=principal)


# ---------------------------------------------------------------- internos


def _editable(libro: Libro, categoria_id: str) -> Categoria:
    categoria = libro.categoria(categoria_id)
    if categoria.clase is ClaseCategoria.SISTEMA:
        raise ErrorValidacion("Las categorías del sistema no se pueden modificar.")
    return categoria


def _nombre_libre(libro: Libro, nombre: str, clase: ClaseCategoria, excepto: str | None = None) -> None:
    for c in libro.categorias():
        if c.id != excepto and c.clase is clase and c.nombre.casefold() == nombre.casefold():
            raise ErrorValidacion(f"Ya existe la categoría «{nombre}».")


def _validar_principal(clase: ClaseCategoria, principal: bool) -> None:
    if principal and clase is not ClaseCategoria.INGRESO:
        raise ErrorValidacion("Solo una categoría de ingreso puede ser el ingreso principal.")


def _fusionar(partidas: tuple[Partida, ...]) -> tuple[Partida, ...]:
    """Une partidas que quedaron repetidas en la misma categoría tras una fusión."""
    resultado: list[Partida] = []
    for p in partidas:
        previa = next(
            (i for i, r in enumerate(resultado) if p.categoria_id is not None and r.categoria_id == p.categoria_id),
            None,
        )
        if previa is None:
            resultado.append(p)
        else:
            resultado[previa] = Partida(resultado[previa].importe + p.importe, categoria_id=p.categoria_id)
    return tuple(resultado)
