"""Categorías, subcategorías y clasificaciones.

- **Categoría** (``Rubro``): la caja que agrupa (SALUD, TECNOLOGIA…). Es de gasto o de ingreso.
- **Subcategoría** (``Categoria``): lo que se asigna a cada movimiento (DENTISTA, GASOLINA…). Vive en una
  categoría y es de su mismo tipo.
- **Clasificación** (``Grupo``): Necesidad, Disfrute, Estabilidad… (la «Clasif. Metas» del Excel).

Los nombres de categorías y subcategorías se guardan en MAYÚSCULAS y sin acentos, y no se pueden repetir
(sin importar mayúsculas, acentos, signos ni espacios): una subcategoría existe una sola vez en todo TALLY y
una categoría también. Todo es editable; el catálogo inicial (``motor/catalogo.py``) es un punto de partida.
"""

from __future__ import annotations

from dataclasses import replace

from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Categoria, ClaseCategoria, Grupo, Partida, Rubro
from motor.textos import clave, estandarizar, normalizar_nombre  # noqa: F401 - normalizar_nombre se reexporta

SEPARADOR = " › "

# ------------------------------------------------------------ clasificaciones


def crear_grupo(libro: Libro, nombre: str) -> Grupo:
    nombre = normalizar_nombre(nombre)
    _grupo_libre(libro, nombre)
    orden = max((g.orden for g in libro.grupos()), default=-1) + 1
    return libro.guardar_grupo(Grupo(libro.nuevo_id(), nombre, orden))


def renombrar_grupo(libro: Libro, grupo_id: str, nombre: str) -> Grupo:
    grupo = libro.grupo(grupo_id)
    nombre = normalizar_nombre(nombre)
    _grupo_libre(libro, nombre, excepto=grupo_id)
    return libro.guardar_grupo(replace(grupo, nombre=nombre))


def eliminar_grupo(libro: Libro, grupo_id: str) -> None:
    """Borra la clasificación; sus subcategorías quedan sin clasificación (no se pierde nada)."""
    libro.grupo(grupo_id)
    for categoria in libro.categorias():
        if categoria.grupo_id == grupo_id:
            libro.guardar_categoria(replace(categoria, grupo_id=None))
    libro.quitar_grupo(grupo_id)


def clasificar(libro: Libro, categoria_id: str, grupo_id: str | None) -> Categoria:
    """Pone una subcategoría en una clasificación (``None`` la deja sin clasificación).

    Cada subcategoría está en una sola clasificación: si ya está en otra, no se mueve en silencio; hay que
    quitarla de allá primero (o cambiarla desde «Modificar»).
    """
    categoria = _editable(libro, categoria_id)
    if grupo_id is not None:
        destino = libro.grupo(grupo_id)
        if categoria.grupo_id not in (None, grupo_id):
            actual = libro.grupo(categoria.grupo_id).nombre
            raise ErrorValidacion(f"«{categoria.nombre}» ya está en «{actual}». Quítala de «{actual}» primero "
                                  f"para ponerla en «{destino.nombre}».")
    return libro.guardar_categoria(replace(categoria, grupo_id=grupo_id))


# ------------------------------------------------------- categorías (rubros)


def crear_rubro(libro: Libro, nombre: str, clase: ClaseCategoria) -> Rubro:
    clase = ClaseCategoria(clase)
    if clase is ClaseCategoria.SISTEMA:
        raise ErrorValidacion("Una categoría es de gasto o de ingreso.")
    nombre = estandarizar(nombre)
    _rubro_libre(libro, nombre)
    orden = max((r.orden for r in libro.rubros()), default=-1) + 1
    return libro.guardar_rubro(Rubro(libro.nuevo_id(), nombre, clase, orden))


def renombrar_rubro(libro: Libro, rubro_id: str, nombre: str) -> Rubro:
    rubro = libro.rubro(rubro_id)
    nombre = estandarizar(nombre)
    _rubro_libre(libro, nombre, excepto=rubro_id)
    return libro.guardar_rubro(replace(rubro, nombre=nombre))


def fijar_presupuesto(libro: Libro, rubro_id: str, monto) -> Rubro:
    """Presupuesto mensual de una categoría de gasto. ``None`` o 0 lo quita."""
    from motor.dinero import a_centavos

    rubro = libro.rubro(rubro_id)
    if rubro.clase is not ClaseCategoria.GASTO:
        raise ErrorValidacion("Los presupuestos son para categorías de gasto.")
    centavos = a_centavos(monto) if monto not in (None, "") else 0
    if centavos < 0:
        raise ErrorValidacion("El presupuesto no puede ser negativo.")
    return libro.guardar_rubro(replace(rubro, presupuesto=centavos or None))


def subcategorias(libro: Libro, rubro_id: str) -> list[Categoria]:
    return [c for c in libro.categorias() if c.rubro_id == rubro_id]


def eliminar_rubro(libro: Libro, rubro_id: str, *, mover_a: str | None = None) -> None:
    """Borra una categoría. Si tiene subcategorías, pasan (con sus movimientos) a la categoría ``mover_a``."""
    rubro = libro.rubro(rubro_id)
    contenido = subcategorias(libro, rubro_id)
    if contenido:
        if mover_a is None:
            raise ErrorValidacion(f"«{rubro.nombre}» tiene subcategorías; elige a qué categoría pasarlas.")
        destino = libro.rubro(mover_a)
        if destino.id == rubro_id or destino.clase is not rubro.clase:
            raise ErrorValidacion("Las subcategorías solo pueden pasar a otra categoría del mismo tipo.")
        for categoria in contenido:
            libro.guardar_categoria(replace(categoria, rubro_id=destino.id))
    libro.quitar_rubro(rubro_id)


def buscar_rubro(libro: Libro, nombre: str) -> Rubro | None:
    buscada = clave(nombre)
    return next((r for r in libro.rubros() if clave(r.nombre) == buscada), None)


# --------------------------------------------------------------- subcategorías


def crear(
    libro: Libro,
    nombre: str,
    rubro_id: str,
    *,
    grupo_id: str | None = None,
    principal: bool = False,
) -> Categoria:
    """Crea una subcategoría dentro de la categoría ``rubro_id`` (y de su mismo tipo)."""
    if rubro_id is None:
        raise ErrorValidacion("Elige en qué categoría va la subcategoría.")
    rubro = libro.rubro(rubro_id)
    nombre = estandarizar(nombre)
    _nombre_libre(libro, nombre)
    if grupo_id is not None:
        libro.grupo(grupo_id)
    _validar_principal(rubro.clase, principal)
    orden = max((c.orden for c in libro.categorias()), default=-1) + 1
    return libro.guardar_categoria(
        Categoria(libro.nuevo_id(), nombre, rubro.clase, grupo_id=grupo_id, principal=principal, orden=orden,
                  rubro_id=rubro.id)
    )


_SIN_CAMBIO = object()


def editar(
    libro: Libro,
    categoria_id: str,
    *,
    nombre: str | None = None,
    rubro_id: str | object = _SIN_CAMBIO,
    grupo_id: str | None | object = _SIN_CAMBIO,
    principal: bool | None = None,
    orden: int | None = None,
    secundario: bool | None = None,
) -> Categoria:
    categoria = _editable(libro, categoria_id)
    cambios: dict = {}
    if nombre is not None:
        nombre = estandarizar(nombre)
        _nombre_libre(libro, nombre, excepto=categoria_id)
        cambios["nombre"] = nombre
    if rubro_id is not _SIN_CAMBIO:
        if rubro_id is None or libro.rubro(rubro_id).clase is not categoria.clase:
            raise ErrorValidacion("La subcategoría solo puede pasar a otra categoría del mismo tipo.")
        cambios["rubro_id"] = rubro_id
    if grupo_id is not _SIN_CAMBIO:
        if grupo_id is not None:
            libro.grupo(grupo_id)
        cambios["grupo_id"] = grupo_id
    if principal is not None:
        _validar_principal(categoria.clase, principal)
        cambios["principal"] = principal
    if orden is not None:
        cambios["orden"] = orden
    if secundario is not None:
        if secundario and categoria.clase is not ClaseCategoria.INGRESO:
            raise ErrorValidacion("Solo una subcategoría de ingreso puede ser un ingreso secundario.")
        cambios["secundario"] = bool(secundario)
    return libro.guardar_categoria(replace(categoria, **cambios))


def archivar(libro: Libro, categoria_id: str) -> Categoria:
    """Oculta la subcategoría para movimientos nuevos; su historial se conserva."""
    return libro.guardar_categoria(replace(_editable(libro, categoria_id), activa=False))


def reactivar(libro: Libro, categoria_id: str) -> Categoria:
    return libro.guardar_categoria(replace(_editable(libro, categoria_id), activa=True))


def en_uso(libro: Libro, categoria_id: str) -> bool:
    return any(p.categoria_id == categoria_id for op in libro.operaciones() for p in op.partidas)


def eliminar(libro: Libro, categoria_id: str, *, reasignar_a: str | None = None) -> None:
    """Borra una subcategoría.

    Si tiene movimientos, hay que indicar a qué subcategoría (del mismo tipo)
    pasan; en la práctica es juntarlas.
    """
    categoria = _editable(libro, categoria_id)
    if en_uso(libro, categoria_id):
        if reasignar_a is None:
            raise ErrorValidacion(f"«{categoria.nombre}» tiene movimientos; elige a qué subcategoría pasarlos.")
        destino = libro.categoria(reasignar_a)
        if destino.id == categoria_id or destino.clase is not categoria.clase:
            raise ErrorValidacion("Los movimientos solo pueden pasar a otra subcategoría del mismo tipo.")
        for op in libro.operaciones():
            if any(p.categoria_id == categoria_id for p in op.partidas):
                partidas = tuple(
                    Partida(p.importe, categoria_id=destino.id) if p.categoria_id == categoria_id else p
                    for p in op.partidas
                )
                libro.reemplazar_operacion(op.id, replace(op, partidas=_fusionar(partidas)))
    for r in libro.recurrentes():                     # los pagos recurrentes pasan a la otra (o quedan sin elegir)
        if r.categoria_id == categoria_id:
            libro.guardar_recurrente(replace(r, categoria_id=reasignar_a, activa=r.activa and reasignar_a is not None))
    libro.quitar_categoria(categoria_id)


def para_tipo(libro: Libro, tipo) -> list[Categoria]:
    """Subcategorías activas que se pueden elegir para un tipo de movimiento, ordenadas por categoría."""
    from motor.modelo import TipoOperacion

    tipo = TipoOperacion(tipo)
    if tipo in (TipoOperacion.GASTO, TipoOperacion.REEMBOLSO):
        clase = ClaseCategoria.GASTO
    elif tipo in (TipoOperacion.INGRESO, TipoOperacion.RENDIMIENTO):
        clase = ClaseCategoria.INGRESO
    else:
        return []
    return ordenadas(libro, [c for c in libro.categorias() if c.clase is clase and c.activa])


def ordenadas(libro: Libro, lista: list[Categoria]) -> list[Categoria]:
    """En el orden de sus categorías y, dentro de cada una, en el suyo."""
    orden_rubro = {r.id: r.orden for r in libro.rubros()}
    return sorted(lista, key=lambda c: (orden_rubro.get(c.rubro_id, -1), c.orden, c.nombre))


def nombre_rubro(libro: Libro, categoria_id: str) -> str:
    """Nombre de la categoría de una subcategoría ("" para las del sistema)."""
    rubro_id = libro.categoria(categoria_id).rubro_id
    return libro.rubro(rubro_id).nombre if rubro_id else ""


def etiqueta(libro: Libro, categoria_id: str) -> str:
    """«SALUD › DENTISTA»: para listas donde se elige una subcategoría."""
    categoria = libro.categoria(categoria_id)
    rubro = nombre_rubro(libro, categoria_id)
    return f"{rubro}{SEPARADOR}{categoria.nombre}" if rubro else categoria.nombre


def buscar(libro: Libro, nombre: str, clase: ClaseCategoria | None = None) -> Categoria | None:
    """Busca una subcategoría por nombre, sin importar mayúsculas, acentos ni espacios."""
    buscada = clave(nombre)
    for categoria in libro.categorias():
        if clave(categoria.nombre) == buscada and (clase is None or categoria.clase is clase):
            return categoria
    return None


def cargar_catalogo_inicial(libro: Libro) -> None:
    """Crea las clasificaciones, categorías y subcategorías sugeridas. Solo actúa sobre un libro vacío."""
    from motor import catalogo

    catalogo.cargar(libro)


# ---------------------------------------------------------------- internos


def _editable(libro: Libro, categoria_id: str) -> Categoria:
    categoria = libro.categoria(categoria_id)
    if categoria.clase is ClaseCategoria.SISTEMA:
        raise ErrorValidacion("Las subcategorías del sistema no se pueden modificar.")
    return categoria


def _nombre_libre(libro: Libro, nombre: str, excepto: str | None = None) -> None:
    for c in libro.categorias():
        if c.id != excepto and clave(c.nombre) == clave(nombre):
            donde = f" (en {libro.rubro(c.rubro_id).nombre})" if c.rubro_id else ""
            raise ErrorValidacion(f"Ya existe la subcategoría «{c.nombre}»{donde}. No se puede agregar dos veces.")


def _rubro_libre(libro: Libro, nombre: str, excepto: str | None = None) -> None:
    for r in libro.rubros():
        if r.id != excepto and clave(r.nombre) == clave(nombre):
            raise ErrorValidacion(f"Ya existe la categoría «{r.nombre}». No se puede agregar dos veces.")


def _grupo_libre(libro: Libro, nombre: str, excepto: str | None = None) -> None:
    for g in libro.grupos():
        if g.id != excepto and clave(g.nombre) == clave(nombre):
            raise ErrorValidacion(f"Ya existe la clasificación «{g.nombre}».")


def _validar_principal(clase: ClaseCategoria, principal: bool) -> None:
    if principal and clase is not ClaseCategoria.INGRESO:
        raise ErrorValidacion("Solo una subcategoría de ingreso puede ser el ingreso principal.")


def _fusionar(partidas: tuple[Partida, ...]) -> tuple[Partida, ...]:
    """Une partidas que quedaron repetidas en la misma subcategoría tras una fusión."""
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
