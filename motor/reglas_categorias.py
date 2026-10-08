"""Reglas automáticas de categorías: «todo lo que diga OXXO va a TIENDITA».

Una regla dice: si la descripción de un movimiento tiene este texto, va a esta subcategoría (en todas tus
cuentas o solo en una). Se usan:

- al importar el estado de cuenta del banco (``motor/bancos.py``): antes que lo aprendido de tu historial y que
  los comercios conocidos;
- al registrar un movimiento sin subcategoría y al cargar la plantilla de Excel con la subcategoría vacía;
- para corregir tu historial: los movimientos que ya tienes y que la regla mandaría a otra subcategoría.

Cómo se compara: sin mayúsculas, acentos ni signos (``textos.clave``), y el texto debe empezar una palabra:
«UBER» encuentra «UBER EATS» y «UBERTRIP», pero no «SUBERO». Si varias reglas coinciden gana la del texto más
largo (la más precisa: «AMAZON PRIME» antes que «AMAZON»); a igual texto, la de esa cuenta antes que la general.
Una regla solo aplica a movimientos de su tipo: las de gasto a lo que sale (y a las devoluciones), las de ingreso
a lo que entra.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date

from motor.errores import ErrorNoEncontrado, ErrorValidacion
from motor.libro import Libro
from motor.modelo import ClaseCategoria, Operacion, Regla, TipoOperacion
from motor.textos import clave

MINIMO = 2                       # letras o números que debe tener el texto de una regla

# Lo que entra con estas palabras es una devolución: le aplican las reglas de gasto (regresa a ese gasto).
DEVOLUCION = re.compile(r"(?<![A-Z])(DEVOLUCION|REEMBOLSO|REVERS[OA]|CANCELACION|CONTRACARGO)")

# Qué tipo de subcategoría lleva cada movimiento (una devolución regresa dinero a una de gasto).
CLASE_DE_TIPO = {
    TipoOperacion.GASTO: ClaseCategoria.GASTO,
    TipoOperacion.REEMBOLSO: ClaseCategoria.GASTO,
    TipoOperacion.INGRESO: ClaseCategoria.INGRESO,
}

# Palabras que no sirven para una regla sugerida: dicen qué tipo de movimiento es, no de quién.
_GENERICAS = {
    "TRANSFERENCIA", "TRASPASO", "DEPOSITO", "RETIRO", "CAJERO", "EFECTIVO", "NOMINA", "COMISION", "IVA",
    "INTERES", "INTERESES", "DEVOLUCION", "REEMBOLSO", "BANCO", "CLIENTE", "SERVICIO", "SERVICIOS", "VARIOS",
    "TIENDA", "ATM", "TRANSF", "ABONO", "GASTO", "INGRESO", "QUINCENA", "SEMANA", "MES",
}


# ------------------------------------------------------------------ alta, cambios y baja


def normalizar(texto: str) -> str:
    """El texto como se compara: «Oxxo  Gas.» → «OXXO GAS»."""
    return clave(texto or "")


def crear(libro: Libro, texto: str, categoria_id: str, *, cuenta_id: str | None = None,
          hoy: date | None = None) -> Regla:
    regla = Regla(id=libro.nuevo_id(), texto=texto, categoria_id=categoria_id, cuenta_id=cuenta_id or None,
                  creada=hoy or date.today())
    return libro.guardar_regla(_validar(libro, regla))


def editar(libro: Libro, regla_id: str, **cambios) -> Regla:
    if "cuenta_id" in cambios:
        cambios["cuenta_id"] = cambios["cuenta_id"] or None
    actual = libro.regla(regla_id)
    nueva = replace(actual, **cambios)
    if nueva.activa or not cambios.keys() <= {"activa"}:
        nueva = _validar(libro, nueva, original=actual)
    return libro.guardar_regla(nueva)


def eliminar(libro: Libro, regla_id: str) -> None:
    libro.quitar_regla(regla_id)


def _validar(libro: Libro, regla: Regla, original: Regla | None = None) -> Regla:
    regla = replace(regla, texto=normalizar(regla.texto))
    if len(regla.texto.replace(" ", "")) < MINIMO:
        raise ErrorValidacion(f"Escribe al menos {MINIMO} letras o números del texto que aparece en tu banco "
                              "(por ejemplo «OXXO» o «NETFLIX»).")
    categoria = libro.categoria(regla.categoria_id)
    if not categoria.rubro_id or categoria.clase not in (ClaseCategoria.GASTO, ClaseCategoria.INGRESO):
        raise ErrorValidacion("Elige una subcategoría de gasto o de ingreso.")
    if not categoria.activa and (original is None or original.categoria_id != regla.categoria_id):
        raise ErrorValidacion(f"La subcategoría «{categoria.nombre}» está archivada.")
    if regla.cuenta_id is not None:
        cuenta = libro.cuenta(regla.cuenta_id)
        if not cuenta.activa and (original is None or original.cuenta_id != regla.cuenta_id):
            raise ErrorValidacion(f"La cuenta «{cuenta.nombre}» está archivada.")
    for otra in libro.reglas():
        if otra.id != regla.id and otra.texto == regla.texto and otra.cuenta_id == regla.cuenta_id:
            donde = f" en «{libro.cuenta(regla.cuenta_id).nombre}»" if regla.cuenta_id else ""
            raise ErrorValidacion(f"Ya tienes una regla para «{regla.texto}»{donde}: edítala en lugar de crear otra.")
    return regla


def texto_para(descripciones) -> str | None:
    """El texto para una regla nueva a partir de movimientos parecidos: la primera palabra del comercio que tienen
    todos, sin números ni palabras de relleno («COMPRA OXXO 1234» y «OXXO 9876 CENTRO» → «OXXO»)."""
    from motor.bancos import nucleo

    juegos = [nucleo(d) for d in descripciones if d]
    if not juegos:
        return None
    comunes = set(juegos[0]).intersection(*juegos[1:])
    return next((p for p in juegos[0] if p in comunes and len(p) >= 3 and p not in _GENERICAS), None)


def motivo(regla: Regla) -> str:
    """Por qué se sugirió una subcategoría (para la columna «Por qué» de la importación)."""
    return f"Por tu regla «{regla.texto}»"


# ------------------------------------------------------------------ buscar la regla que aplica


class Indice:
    """Las reglas activas listas para buscar rápido (una expresión por tipo y cuenta, hecha una sola vez).

    Úsalo cuando vas a revisar muchos movimientos (una importación, tu historial completo)."""

    def __init__(self, libro: Libro) -> None:
        categorias = {c.id: c for c in libro.categorias()}
        self._reglas: dict[ClaseCategoria, list[Regla]] = defaultdict(list)
        for regla in libro.reglas():
            categoria = categorias.get(regla.categoria_id)
            if regla.activa and categoria is not None and categoria.activa:
                self._reglas[categoria.clase].append(regla)
        self._buscadores: dict[tuple[ClaseCategoria, str | None], tuple[re.Pattern, dict[str, Regla]] | None] = {}
        self._vistas: dict[tuple[str, ClaseCategoria, str | None], Regla | None] = {}   # descripciones repetidas

    def __bool__(self) -> bool:
        return bool(self._reglas)

    def _buscador(self, clase: ClaseCategoria, cuenta_id: str | None):
        llave = (clase, cuenta_id)
        if llave not in self._buscadores:
            por_texto: dict[str, Regla] = {}
            for regla in self._reglas.get(clase, ()):
                if regla.cuenta_id is None:
                    por_texto.setdefault(regla.texto, regla)
            for regla in self._reglas.get(clase, ()):
                if regla.cuenta_id is not None and regla.cuenta_id == cuenta_id:
                    por_texto[regla.texto] = regla          # la de esa cuenta gana a la general
            if por_texto:
                textos = sorted(por_texto, key=lambda t: (-len(t), t))
                # Lookahead: encuentra todas las coincidencias aunque se encimen («AB CD» y «CD EF»).
                patron = re.compile(r"(?<![A-Z0-9])(?=(" + "|".join(re.escape(t) for t in textos) + "))")
                self._buscadores[llave] = (patron, por_texto)
            else:
                self._buscadores[llave] = None
        return self._buscadores[llave]

    def buscar(self, descripcion: str, clase: ClaseCategoria, cuenta_id: str | None = None) -> Regla | None:
        """La regla que aplica a esa descripción (o ``None``)."""
        llave = (descripcion, clase, cuenta_id)
        if llave in self._vistas:
            return self._vistas[llave]
        buscador = self._buscador(clase, cuenta_id)
        regla = None
        if buscador is not None and descripcion:
            patron, por_texto = buscador
            mejor = max((m.group(1) for m in patron.finditer(clave(descripcion))), key=len, default=None)
            regla = por_texto[mejor] if mejor else None
        self._vistas[llave] = regla
        return regla

    def para_importe(self, descripcion: str, centavos: int, cuenta_id: str | None = None) -> Regla | None:
        """Para un renglón del banco o de la plantilla: lo que sale busca reglas de gasto; lo que entra, de
        ingreso (o de gasto, si es la devolución de una compra)."""
        if centavos < 0:
            return self.buscar(descripcion, ClaseCategoria.GASTO, cuenta_id)
        regla = self.buscar(descripcion, ClaseCategoria.INGRESO, cuenta_id)
        if regla is None and DEVOLUCION.search(clave(descripcion or "")):
            regla = self.buscar(descripcion, ClaseCategoria.GASTO, cuenta_id)
        return regla

    def para_operacion(self, op: Operacion) -> Regla | None:
        """La regla que aplica a un movimiento ya registrado (solo gastos, ingresos y devoluciones de una sola
        subcategoría: los repartidos en varias no se tocan)."""
        clase = CLASE_DE_TIPO.get(op.tipo)
        if clase is None or not op.descripcion or len(op.partidas_de_categoria()) != 1:
            return None
        cuentas = op.partidas_de_cuenta()
        return self.buscar(op.descripcion, clase, cuentas[0].cuenta_id if cuentas else None)


def buscar(libro: Libro, descripcion: str, clase: ClaseCategoria, cuenta_id: str | None = None) -> Regla | None:
    """La regla que aplica a una descripción, para un solo movimiento (para muchos, usa :class:`Indice`)."""
    return Indice(libro).buscar(descripcion, clase, cuenta_id)


def categoria_para(libro: Libro, descripcion: str, tipo, cuenta_id: str | None = None) -> str | None:
    """La subcategoría que las reglas dan a un movimiento nuevo de ese tipo (``None`` si ninguna aplica)."""
    clase = CLASE_DE_TIPO.get(TipoOperacion(tipo))
    if clase is None:
        return None
    regla = buscar(libro, descripcion, clase, cuenta_id)
    return regla.categoria_id if regla else None


def probar(libro: Libro, descripcion: str, cuenta_id: str | None = None) -> dict[ClaseCategoria, Regla | None]:
    """Qué pasaría con esa descripción si fuera un gasto y si fuera un ingreso."""
    indice = Indice(libro)
    return {clase: indice.buscar(descripcion, clase, cuenta_id)
            for clase in (ClaseCategoria.GASTO, ClaseCategoria.INGRESO)}


# ------------------------------------------------------------------ tu historial


@dataclass(frozen=True, slots=True)
class Cambio:
    """Un movimiento que ya tienes y que tus reglas mandarían a otra subcategoría."""

    operacion: Operacion
    regla: Regla
    categoria_actual: str
    categoria_nueva: str


def pendientes(libro: Libro, regla_id: str | None = None) -> list[Cambio]:
    """Los movimientos de tu historial con otra subcategoría de la que les dan tus reglas (todas, o solo
    ``regla_id``), del más reciente al más antiguo."""
    indice = Indice(libro)
    if not indice:
        return []
    cambios = []
    for op in reversed(libro.operaciones()):
        regla = indice.para_operacion(op)
        if regla is None or (regla_id is not None and regla.id != regla_id):
            continue
        actual = op.partidas_de_categoria()[0].categoria_id
        if actual != regla.categoria_id:
            cambios.append(Cambio(op, regla, actual, regla.categoria_id))
    return cambios


def aplicar(libro: Libro, cambios: list[Cambio]) -> int:
    """Pasa esos movimientos a la subcategoría de su regla. Regresa cuántos cambió."""
    from motor.movimientos import editar as editar_movimiento

    hechos = 0
    for cambio in cambios:
        try:
            op = libro.operacion(cambio.operacion.id)
        except ErrorNoEncontrado:                # lo borraste mientras tanto
            continue
        if op.partidas_de_categoria() and op.partidas_de_categoria()[0].categoria_id == cambio.categoria_actual:
            editar_movimiento(libro, op.id, categoria_id=cambio.categoria_nueva)
            hechos += 1
    return hechos


def contar(libro: Libro) -> dict[str, int]:
    """Regla → cuántos de tus movimientos encuentra hoy (para la lista de reglas)."""
    indice = Indice(libro)
    cuenta: Counter[str] = Counter()
    if indice:
        for op in libro.operaciones():
            regla = indice.para_operacion(op)
            if regla is not None:
                cuenta[regla.id] += 1
    return dict(cuenta)


# ------------------------------------------------------------------ sugerencias


@dataclass(frozen=True, slots=True)
class Sugerencia:
    """Un texto que se repite en tu historial y casi siempre va a la misma subcategoría."""

    texto: str
    categoria_id: str
    veces: int              # movimientos con ese texto
    iguales: int            # de esos, cuántos ya están en esa subcategoría


def sugerencias(libro: Libro, *, minimo: int = 3, proporcion: float = 0.9, cuantas: int = 8) -> list[Sugerencia]:
    """Reglas que valdría la pena crear: la primera palabra del comercio que se repite al menos ``minimo``
    veces y va a la misma subcategoría en al menos ``proporcion`` de los casos, y que ninguna regla cubre."""
    from motor.bancos import nucleo

    indice = Indice(libro)
    activas = {c.id for c in libro.categorias() if c.activa and c.rubro_id}
    conteo: dict[tuple[str, ClaseCategoria], Counter[str]] = defaultdict(Counter)
    primeras: dict[str, str | None] = {}                 # descripción → la palabra que identifica al comercio
    for op in libro.operaciones():
        clase = CLASE_DE_TIPO.get(op.tipo)
        if clase is None or not op.descripcion or len(op.partidas_de_categoria()) != 1:
            continue
        if op.descripcion not in primeras:
            primeras[op.descripcion] = next((p for p in nucleo(op.descripcion)
                                             if len(p) >= 3 and p not in _GENERICAS), None)
        palabra = primeras[op.descripcion]
        if palabra is None or indice.para_operacion(op) is not None:
            continue
        conteo[(palabra, clase)][op.partidas_de_categoria()[0].categoria_id] += 1
    propuestas = []
    for (texto, _clase), categorias_ in conteo.items():
        veces = sum(categorias_.values())
        categoria_id, iguales = categorias_.most_common(1)[0]
        if veces >= minimo and iguales >= proporcion * veces and categoria_id in activas:
            propuestas.append(Sugerencia(texto, categoria_id, veces, iguales))
    propuestas.sort(key=lambda s: (-s.veces, s.texto))
    return propuestas[:cuantas]
