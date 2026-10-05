"""El Libro: el estado completo de las finanzas de una persona.

Guarda cuentas, categorías, grupos, operaciones y perfil en memoria. Toda
operación pasa por :func:`motor.reglas.validar_operacion` antes de guardarse.

La persistencia (Fase 2) se encargará de cargar y guardar un ``Libro``; el
resto del motor solo trabaja contra esta clase.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime

from motor.errores import ErrorNoEncontrado, ErrorValidacion
from motor.modelo import (
    CATEGORIA_AJUSTE,
    CATEGORIA_SALDO_INICIAL,
    Categoria,
    ClaseCategoria,
    Cuenta,
    Grupo,
    Operacion,
    Perfil,
)
from motor.reglas import validar_operacion


class Libro:
    def __init__(self, *, reloj: Callable[[], datetime] | None = None) -> None:
        self._reloj = reloj or datetime.now
        self.perfil: Perfil | None = None
        self._cuentas: dict[str, Cuenta] = {}
        self._categorias: dict[str, Categoria] = {}
        self._grupos: dict[str, Grupo] = {}
        self._operaciones: dict[str, Operacion] = {}
        self._secuencia = 0
        for categoria in (
            Categoria(CATEGORIA_AJUSTE, "Ajuste de saldo", ClaseCategoria.SISTEMA, orden=-2),
            Categoria(CATEGORIA_SALDO_INICIAL, "Saldo inicial", ClaseCategoria.SISTEMA, orden=-1),
        ):
            self._categorias[categoria.id] = categoria

    # ----------------------------------------------------------------- tiempo

    def ahora(self) -> datetime:
        return self._reloj()

    def hoy(self) -> date:
        return self._reloj().date()

    @staticmethod
    def nuevo_id() -> str:
        return uuid.uuid4().hex

    # ----------------------------------------------------------------- cuentas

    def cuenta(self, cuenta_id: str) -> Cuenta:
        try:
            return self._cuentas[cuenta_id]
        except KeyError:
            raise ErrorNoEncontrado("La cuenta no existe.") from None

    def cuentas(self) -> list[Cuenta]:
        return sorted(self._cuentas.values(), key=lambda c: (c.orden, c.nombre.casefold()))

    def guardar_cuenta(self, cuenta: Cuenta) -> Cuenta:
        self._cuentas[cuenta.id] = cuenta
        return cuenta

    def quitar_cuenta(self, cuenta_id: str) -> None:
        self.cuenta(cuenta_id)
        if any(p.cuenta_id == cuenta_id for op in self._operaciones.values() for p in op.partidas):
            raise ErrorValidacion("La cuenta tiene movimientos; archívala en lugar de borrarla.")
        del self._cuentas[cuenta_id]

    # ------------------------------------------------------- categorías/grupos

    def categoria(self, categoria_id: str) -> Categoria:
        try:
            return self._categorias[categoria_id]
        except KeyError:
            raise ErrorNoEncontrado("La categoría no existe.") from None

    def categorias(self) -> list[Categoria]:
        return sorted(self._categorias.values(), key=lambda c: (c.orden, c.nombre.casefold()))

    def guardar_categoria(self, categoria: Categoria) -> Categoria:
        self._categorias[categoria.id] = categoria
        return categoria

    def quitar_categoria(self, categoria_id: str) -> None:
        self.categoria(categoria_id)
        if any(p.categoria_id == categoria_id for op in self._operaciones.values() for p in op.partidas):
            raise ErrorValidacion("La categoría tiene movimientos.")
        del self._categorias[categoria_id]

    def grupo(self, grupo_id: str) -> Grupo:
        try:
            return self._grupos[grupo_id]
        except KeyError:
            raise ErrorNoEncontrado("El grupo no existe.") from None

    def grupos(self) -> list[Grupo]:
        return sorted(self._grupos.values(), key=lambda g: (g.orden, g.nombre.casefold()))

    def guardar_grupo(self, grupo: Grupo) -> Grupo:
        self._grupos[grupo.id] = grupo
        return grupo

    def quitar_grupo(self, grupo_id: str) -> None:
        self.grupo(grupo_id)
        del self._grupos[grupo_id]

    # ------------------------------------------------------------ operaciones

    def operacion(self, operacion_id: str) -> Operacion:
        try:
            return self._operaciones[operacion_id]
        except KeyError:
            raise ErrorNoEncontrado("El movimiento no existe.") from None

    def operaciones(self, desde: date | None = None, hasta: date | None = None) -> list[Operacion]:
        """Operaciones en orden cronológico, opcionalmente en un rango (inclusivo)."""
        ops = (
            op
            for op in self._operaciones.values()
            if (desde is None or op.fecha >= desde) and (hasta is None or op.fecha <= hasta)
        )
        return sorted(ops, key=lambda op: op.orden)

    def agregar_operacion(self, op: Operacion) -> Operacion:
        op = replace(op, fecha=_solo_fecha(op.fecha))
        if op.id and op.id in self._operaciones:
            raise ErrorValidacion("Ya existe un movimiento con ese identificador.")
        validar_operacion(self, op)
        self._secuencia += 1
        momento = self.ahora()
        op = replace(
            op,
            id=op.id or self.nuevo_id(),
            secuencia=self._secuencia,
            creado_en=momento,
            modificado_en=momento,
        )
        self._operaciones[op.id] = op
        return op

    def reemplazar_operacion(self, operacion_id: str, nueva: Operacion) -> Operacion:
        """Sustituye una operación conservando su identidad y su lugar en el orden."""
        original = self.operacion(operacion_id)
        nueva = replace(
            nueva,
            fecha=_solo_fecha(nueva.fecha),
            id=original.id,
            secuencia=original.secuencia,
            creado_en=original.creado_en,
            modificado_en=self.ahora(),
        )
        validar_operacion(self, nueva, original)
        self._operaciones[operacion_id] = nueva
        return nueva

    def eliminar_operacion(self, operacion_id: str) -> Operacion:
        op = self.operacion(operacion_id)
        del self._operaciones[operacion_id]
        return op

    # ------------------------------------------------------------------ saldos

    def saldo_centavos(self, cuenta_id: str, al: date | None = None) -> int:
        """Saldo de la cuenta al final del día ``al`` (o con todo, si es None)."""
        self.cuenta(cuenta_id)
        return sum(
            p.importe
            for op in self._operaciones.values()
            if al is None or op.fecha <= al
            for p in op.partidas
            if p.cuenta_id == cuenta_id
        )


def _solo_fecha(valor: date) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if not isinstance(valor, date):
        raise ErrorValidacion("La fecha no es válida.")
    return valor
