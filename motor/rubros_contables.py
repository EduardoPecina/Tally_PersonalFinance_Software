"""Rubros contables: en qué renglón de tu Contabilidad técnica cae cada subcategoría.

El Estado de Resultados, el «día a día» del Flujo de efectivo y la Balanza juntan tus subcategorías en rubros
contables: **Ingresos por tu trabajo**, **Ingresos por inversiones y rentas**, **Otros ingresos**, **Gastos de vida**,
**Gastos financieros** e **Impuestos** (los de TALLY, fijos), más los que crees tú (de ingreso o de gasto).

Cada subcategoría está en uno solo. Si no la has movido, TALLY la acomoda solo (:func:`automatico`):

1. por su **nombre** («INTERESES DE TARJETAS» → Gastos financieros; «PREDIAL» → Impuestos; «NOMINA» → trabajo);
2. por el nombre de su **categoría** (todo lo de FINANZAS → Gastos financieros; INGRESOS INDEPENDIENTES → trabajo);
3. si nada de eso lo dice: Gastos de vida u Otros ingresos.

Al **crear** una subcategoría que nada de eso delata, si moviste a la mayoría de sus hermanas a un mismo rubro, va
con ellas (:func:`al_crear`): si pasaste casi todo HOGAR a tu rubro «Vivienda», una subcategoría nueva de HOGAR
también va ahí. Las que están donde están por su propio nombre (ISR en Impuestos) no arrastran a las demás.

Solo cambia cómo se agrupa: las sumas, el Balance y las «sumas iguales» de la Balanza no cambian. El Balance no
depende de las subcategorías sino del tipo de cada cuenta (motor/contabilidad.py: ``clasificar_cuenta``).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import (
    RC_FINANCIEROS,
    RC_IMPUESTOS,
    RC_INVERSIONES,
    RC_OTROS_INGRESOS,
    RC_TRABAJO,
    RC_VIDA,
    RUBROS_CONTABLES_BASE,
    Categoria,
    ClaseCategoria,
    RubroContable,
)
from motor.textos import clave, normalizar_nombre

INICIAL = {ClaseCategoria.INGRESO: RC_OTROS_INGRESOS, ClaseCategoria.GASTO: RC_VIDA}
BASE = frozenset(r.id for r in RUBROS_CONTABLES_BASE)

# Por el nombre de la subcategoría, en este orden (la primera que coincide). Una palabra coincide si alguna palabra
# del nombre empieza con ella («INTERES» → «INTERESES»); las de 3 letras o menos, solo completas («ISR»).
_POR_NOMBRE = {
    ClaseCategoria.GASTO: (
        (RC_IMPUESTOS, ("IMPUESTO", "PREDIAL", "TENENCIA", "ISR", "IVA", "SAT", "CONTRIBUCION")),
        (RC_FINANCIEROS, ("INTERES", "COMISION", "ANUALIDAD", "FINANCIER", "MORATORIO", "BANCARI")),
        (RC_VIDA, ("SEGURO",)),                        # el seguro de vida de FINANZAS es un gasto de vida
    ),
    ClaseCategoria.INGRESO: (
        (RC_INVERSIONES, ("INTERES", "RENDIMIENTO", "DIVIDENDO", "RENTA", "RENTAS", "ARRENDAMIENTO", "INVERSION",
                          "CETES", "PLUSVALIA", "CUPON")),
        (RC_TRABAJO, ("NOMINA", "SUELDO", "SALARIO", "AGUINALDO", "BONO", "PRIMA", "UTILIDADES", "HORAS", "VALES",
                      "FREELANCE", "HONORARIO", "PROPINA", "NEGOCIO", "COMISION", "FINIQUITO", "LIQUIDACION")),
    ),
}
# Por el nombre de su categoría (si el de la subcategoría no dijo nada).
_POR_CATEGORIA = {
    ClaseCategoria.GASTO: (
        (RC_IMPUESTOS, ("IMPUESTO",)),
        (RC_FINANCIEROS, ("FINANZA", "FINANCIER", "BANCO", "BANCARI")),
    ),
    ClaseCategoria.INGRESO: (
        (RC_TRABAJO, ("SUELDO", "NOMINA", "SALARIO", "PRESTACION", "INDEPENDIENTE", "TRABAJO", "NEGOCIO",
                      "HONORARIO", "FREELANCE")),
        (RC_INVERSIONES, ("INVERSION", "RENTA", "RENTAS", "RENDIMIENTO", "DIVIDENDO")),
    ),
}

POR_NOMBRE, POR_CATEGORIA, POR_OMISION, ELEGIDO = (
    "por su nombre", "por su categoría", "donde va casi todo", "lo elegiste tú")


def todos(libro: Libro, clase: ClaseCategoria | None = None) -> list[RubroContable]:
    return [r for r in libro.rubros_contables() if clase is None or r.clase is clase]


def es_de_tally(rubro: RubroContable) -> bool:
    return rubro.id in BASE


# ------------------------------------------------------------------ dónde va cada subcategoría


def sugerencia(libro: Libro, nombre: str, clase: ClaseCategoria, rubro_id: str | None = None) -> tuple[str, str]:
    """(rubro contable, por qué) para una subcategoría con ese nombre en esa categoría, sin ver a sus hermanas."""
    palabras_del_nombre = clave(nombre).split()
    for rubro_contable, palabras in _POR_NOMBRE.get(clase, ()):
        if _dice(palabras_del_nombre, palabras):
            return rubro_contable, POR_NOMBRE
    if rubro_id is not None:
        palabras_de_la_categoria = clave(libro.rubro(rubro_id).nombre).split()
        for rubro_contable, palabras in _POR_CATEGORIA.get(clase, ()):
            if _dice(palabras_de_la_categoria, palabras):
                return rubro_contable, POR_CATEGORIA
    return INICIAL[clase], POR_OMISION


def automatico(libro: Libro, categoria: Categoria) -> RubroContable:
    """Donde TALLY acomoda la subcategoría si el usuario no la ha movido."""
    return libro.rubro_contable(sugerencia(libro, categoria.nombre, categoria.clase, categoria.rubro_id)[0])


def de(libro: Libro, categoria_id: str) -> RubroContable:
    """El rubro contable de una subcategoría de ingreso o de gasto (el elegido o el automático)."""
    categoria = libro.categoria(categoria_id)
    if categoria.clase not in INICIAL:
        raise ErrorValidacion("Las subcategorías del sistema no van en un rubro contable.")
    return libro.rubro_contable(categoria.rubro_contable_id) if categoria.rubro_contable_id else automatico(
        libro, categoria)


def motivo(libro: Libro, categoria_id: str) -> str:
    """Por qué está donde está (para explicarlo en pantalla)."""
    categoria = libro.categoria(categoria_id)
    if categoria.rubro_contable_id:
        return ELEGIDO
    return sugerencia(libro, categoria.nombre, categoria.clase, categoria.rubro_id)[1]


def asignaciones(libro: Libro) -> dict[str, RubroContable]:
    """El rubro contable de cada subcategoría de ingreso y de gasto (para armar los reportes de una vez)."""
    return {c.id: de(libro, c.id) for c in libro.categorias() if c.clase in INICIAL}


def al_crear(libro: Libro, categoria: Categoria) -> Categoria:
    """Una subcategoría recién creada que su nombre y su categoría no delatan va a donde moviste a la mayoría de sus
    hermanas (si las moviste tú a un mismo rubro). Se guarda como elegida: no cambia si después mueves a las demás."""
    rubro_contable, por_que = sugerencia(libro, categoria.nombre, categoria.clase, categoria.rubro_id)
    hermanas = [c for c in libro.categorias() if c.rubro_id == categoria.rubro_id and c.id != categoria.id]
    movidas = [c.rubro_contable_id for c in hermanas if c.rubro_contable_id]
    if por_que != POR_OMISION or not movidas:
        return categoria
    (mayoria, cuantas), = Counter(movidas).most_common(1)
    if mayoria == rubro_contable or cuantas * 2 <= len(hermanas):
        return categoria
    return libro.guardar_categoria(replace(categoria, rubro_contable_id=mayoria))


def asignar(libro: Libro, categoria_id: str, rubro_contable_id: str | None) -> Categoria:
    """Pone la subcategoría en ese rubro contable. ``None`` (o el mismo que TALLY elegiría): que la acomode TALLY."""
    categoria = libro.categoria(categoria_id)
    if categoria.clase not in INICIAL:
        raise ErrorValidacion("Las subcategorías del sistema no van en un rubro contable.")
    if rubro_contable_id is not None:
        rubro = libro.rubro_contable(rubro_contable_id)
        if rubro.clase is not categoria.clase:
            tipo = "ingreso" if categoria.clase is ClaseCategoria.INGRESO else "gasto"
            raise ErrorValidacion(f"«{categoria.nombre}» es de {tipo}: solo puede ir en un rubro de {tipo}.")
        if rubro.id == automatico(libro, categoria).id:
            rubro_contable_id = None
    return libro.guardar_categoria(replace(categoria, rubro_contable_id=rubro_contable_id))


def restablecer(libro: Libro, clase: ClaseCategoria | None = None) -> int:
    """Que TALLY vuelva a acomodar todas (o las de una clase). Devuelve cuántas cambiaron de lugar."""
    cambiadas = 0
    for c in libro.categorias():
        if c.rubro_contable_id and (clase is None or c.clase is clase):
            cambiadas += de(libro, c.id).id != automatico(libro, c).id
            libro.guardar_categoria(replace(c, rubro_contable_id=None))
    return cambiadas


# ------------------------------------------------------------------ los del usuario


def crear(libro: Libro, nombre: str, clase: ClaseCategoria | str) -> RubroContable:
    clase = ClaseCategoria(clase)
    if clase not in INICIAL:
        raise ErrorValidacion("Un rubro contable es de ingreso o de gasto.")
    nombre = normalizar_nombre(nombre)
    _nombre_libre(libro, nombre)
    orden = max((r.orden for r in todos(libro, clase)), default=0) + 1
    return libro.guardar_rubro_contable(RubroContable(libro.nuevo_id(), nombre, clase, max(orden, 100)))


def renombrar(libro: Libro, rubro_contable_id: str, nombre: str) -> RubroContable:
    rubro = libro.rubro_contable(rubro_contable_id)
    if es_de_tally(rubro):
        raise ErrorValidacion("Los rubros contables de TALLY no se pueden renombrar.")
    nombre = normalizar_nombre(nombre)
    _nombre_libre(libro, nombre, excepto=rubro.id)
    return libro.guardar_rubro_contable(replace(rubro, nombre=nombre))


def eliminar(libro: Libro, rubro_contable_id: str) -> int:
    """Lo borra; sus subcategorías vuelven a donde TALLY las acomoda. Devuelve cuántas eran."""
    cuantas = sum(c.rubro_contable_id == rubro_contable_id for c in libro.categorias())
    libro.quitar_rubro_contable(rubro_contable_id)
    return cuantas


# ------------------------------------------------------------------ internos


def _dice(del_nombre: list[str], palabras: tuple[str, ...]) -> bool:
    return any(p == t if len(p) <= 3 else t.startswith(p) for t in del_nombre for p in palabras)


def _nombre_libre(libro: Libro, nombre: str, excepto: str | None = None) -> None:
    if any(r.id != excepto and clave(r.nombre) == clave(nombre) for r in libro.rubros_contables()):
        raise ErrorValidacion(f"Ya hay un rubro contable «{nombre}».")
