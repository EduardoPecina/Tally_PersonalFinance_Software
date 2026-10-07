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
    CATEGORIA_BIENES,
    CATEGORIA_SALDO_INICIAL,
    Bien,
    Prestamo,
    Categoria,
    ClaseCategoria,
    Cuenta,
    Grupo,
    InversionPlazo,
    Operacion,
    OperacionValor,
    Fiscal,
    Meta,
    CierreMes,
    Perfil,
    Recurrente,
    Rubro,
)
from motor.reglas import validar_operacion


class Libro:
    def __init__(self, *, reloj: Callable[[], datetime] | None = None) -> None:
        self._reloj = reloj or datetime.now
        self.perfil: Perfil | None = None
        self.fiscal: Fiscal = Fiscal()
        self._cuentas: dict[str, Cuenta] = {}
        self._categorias: dict[str, Categoria] = {}
        self._grupos: dict[str, Grupo] = {}
        self._rubros: dict[str, Rubro] = {}
        self._operaciones: dict[str, Operacion] = {}
        self._valores: dict[str, OperacionValor] = {}
        self._plazos: dict[str, InversionPlazo] = {}
        self._bienes: dict[str, Bien] = {}
        self._prestamos: dict[str, Prestamo] = {}
        self._recurrentes: dict[str, Recurrente] = {}
        self._metas: dict[str, Meta] = {}
        self._cierres: dict[str, CierreMes] = {}
        self._secuencia = 0
        for categoria in (
            Categoria(CATEGORIA_AJUSTE, "AJUSTE DE SALDO", ClaseCategoria.SISTEMA, orden=-2),
            Categoria(CATEGORIA_SALDO_INICIAL, "SALDO INICIAL", ClaseCategoria.SISTEMA, orden=-1),
            Categoria(CATEGORIA_BIENES, "VENTA DE BIENES", ClaseCategoria.SISTEMA, orden=-3),
        ):
            self._categorias[categoria.id] = categoria

    @classmethod
    def desde_estado(
        cls,
        *,
        perfil: Perfil | None,
        grupos: list[Grupo],
        categorias: list[Categoria],
        rubros: list[Rubro] = (),
        cuentas: list[Cuenta],
        operaciones: list[Operacion],
        secuencia: int,
        reloj: Callable[[], datetime] | None = None,
        valores: list[OperacionValor] = (),
        plazos: list[InversionPlazo] = (),
        bienes: list[Bien] = (),
        prestamos: list[Prestamo] = (),
        recurrentes: list[Recurrente] = (),
        metas: list[Meta] = (),
        fiscal: Fiscal | None = None,
        cierres: list[CierreMes] = (),
    ) -> Libro:
        """Reconstruye un libro ya guardado, tal cual (lo usa la persistencia)."""
        libro = cls(reloj=reloj)
        libro.perfil = perfil
        libro._grupos = {g.id: g for g in grupos}
        libro._rubros = {r.id: r for r in rubros}
        libro._categorias.update({c.id: c for c in categorias})
        libro._cuentas = {c.id: c for c in cuentas}
        libro._operaciones = {op.id: op for op in operaciones}
        libro._valores = {v.id: v for v in valores}
        libro._plazos = {p.id: p for p in plazos}
        libro._bienes = {b.cuenta_id: b for b in bienes}
        libro._prestamos = {p.cuenta_id: p for p in prestamos}
        libro._recurrentes = {r.id: r for r in recurrentes}
        libro._metas = {m.id: m for m in metas}
        libro._cierres = {c.id: c for c in cierres}
        libro.fiscal = fiscal or Fiscal()
        libro._secuencia = max([secuencia, *(op.secuencia for op in operaciones)])
        return libro

    @property
    def reloj(self) -> Callable[[], datetime]:
        return self._reloj

    @property
    def secuencia(self) -> int:
        return self._secuencia

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
        if self.tiene_titulos(cuenta_id):
            raise ErrorValidacion("La cuenta tiene títulos o inversiones a plazo; archívala en lugar de borrarla.")
        del self._cuentas[cuenta_id]
        self._bienes.pop(cuenta_id, None)
        self._prestamos.pop(cuenta_id, None)
        for r in [r for r in self._recurrentes.values() if cuenta_id in (r.cuenta_id, r.destino_id)]:
            del self._recurrentes[r.id]
        for m in [m for m in self._metas.values() if m.cuenta_id == cuenta_id]:
            self._metas[m.id] = replace(m, cuenta_id=None)

    # ------------------------------------------------- títulos e inversiones a plazo

    def valores(self, cuenta_id: str | None = None) -> list[OperacionValor]:
        """Compras y ventas de títulos, en orden cronológico."""
        lista = [v for v in self._valores.values() if cuenta_id is None or v.cuenta_id == cuenta_id]
        return sorted(lista, key=lambda v: (v.fecha, v.tipo != "compra", v.id))

    def valor(self, valor_id: str) -> OperacionValor:
        try:
            return self._valores[valor_id]
        except KeyError:
            raise ErrorNoEncontrado("La compra o venta no existe.") from None

    def guardar_valor(self, valor: OperacionValor) -> OperacionValor:
        self.cuenta(valor.cuenta_id)
        self._valores[valor.id] = valor
        return valor

    def quitar_valor(self, valor_id: str) -> None:
        self.valor(valor_id)
        del self._valores[valor_id]

    def plazos(self, cuenta_id: str | None = None) -> list[InversionPlazo]:
        lista = [p for p in self._plazos.values() if cuenta_id is None or p.cuenta_id == cuenta_id]
        return sorted(lista, key=lambda p: (p.fecha_inicio, p.nombre))

    def plazo(self, plazo_id: str) -> InversionPlazo:
        try:
            return self._plazos[plazo_id]
        except KeyError:
            raise ErrorNoEncontrado("La inversión a plazo no existe.") from None

    def guardar_plazo(self, plazo: InversionPlazo) -> InversionPlazo:
        self.cuenta(plazo.cuenta_id)
        self._plazos[plazo.id] = plazo
        return plazo

    def quitar_plazo(self, plazo_id: str) -> None:
        self.plazo(plazo_id)
        del self._plazos[plazo_id]

    # ------------------------------------------------------------------ bienes

    def bienes(self) -> list[Bien]:
        return [self._bienes[c] for c in sorted(self._bienes, key=lambda c: self.cuenta(c).nombre.casefold())]

    def bien(self, cuenta_id: str) -> Bien | None:
        return self._bienes.get(cuenta_id)

    def guardar_bien(self, bien: Bien) -> Bien:
        self.cuenta(bien.cuenta_id)
        self._bienes[bien.cuenta_id] = bien
        return bien

    # --------------------------------------------------------------- préstamos

    def prestamos(self) -> list[Prestamo]:
        return [self._prestamos[c] for c in sorted(self._prestamos, key=lambda c: self.cuenta(c).nombre.casefold())]

    def prestamo(self, cuenta_id: str) -> Prestamo | None:
        return self._prestamos.get(cuenta_id)

    def guardar_prestamo(self, prestamo: Prestamo) -> Prestamo:
        self.cuenta(prestamo.cuenta_id)
        self._prestamos[prestamo.cuenta_id] = prestamo
        return prestamo

    # ------------------------------------------------------- pagos recurrentes

    def recurrentes(self) -> list[Recurrente]:
        return sorted(self._recurrentes.values(), key=lambda r: (not r.activa, r.nombre.casefold()))

    def recurrente(self, recurrente_id: str) -> Recurrente:
        try:
            return self._recurrentes[recurrente_id]
        except KeyError:
            raise ErrorNoEncontrado("Ese pago recurrente no existe.") from None

    def guardar_recurrente(self, recurrente: Recurrente) -> Recurrente:
        self.cuenta(recurrente.cuenta_id)
        self._recurrentes[recurrente.id] = recurrente
        return recurrente

    def quitar_recurrente(self, recurrente_id: str) -> None:
        self.recurrente(recurrente_id)
        del self._recurrentes[recurrente_id]

    # ------------------------------------------------------------------ metas

    def metas(self) -> list[Meta]:
        return sorted(self._metas.values(), key=lambda m: (not m.activa, not m.emergencia, m.creada or date.min,
                                                            m.nombre.casefold()))

    def meta(self, meta_id: str) -> Meta:
        try:
            return self._metas[meta_id]
        except KeyError:
            raise ErrorNoEncontrado("Esa meta no existe.") from None

    def guardar_meta(self, meta: Meta) -> Meta:
        if meta.cuenta_id is not None:
            self.cuenta(meta.cuenta_id)
        self._metas[meta.id] = meta
        return meta

    def quitar_meta(self, meta_id: str) -> None:
        self.meta(meta_id)
        del self._metas[meta_id]

    # ------------------------------------------------------------------ cierres de mes

    def cierres(self) -> list[CierreMes]:
        return sorted(self._cierres.values(), key=lambda c: c.id)

    def cierre(self, cierre_id: str) -> CierreMes | None:
        """El cierre de ese mes («2026-09»), o ``None`` si no lo has cerrado."""
        return self._cierres.get(cierre_id)

    def guardar_cierre(self, cierre: CierreMes) -> CierreMes:
        self._cierres[cierre.id] = cierre
        return cierre

    def quitar_cierre(self, cierre_id: str) -> None:
        if cierre_id not in self._cierres:
            raise ErrorNoEncontrado("Ese mes no está cerrado.")
        del self._cierres[cierre_id]

    def tiene_titulos(self, cuenta_id: str) -> bool:
        return any(v.cuenta_id == cuenta_id for v in self._valores.values()) or any(
            p.cuenta_id == cuenta_id for p in self._plazos.values())

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

    def rubro(self, rubro_id: str) -> Rubro:
        try:
            return self._rubros[rubro_id]
        except KeyError:
            raise ErrorNoEncontrado("La categoría no existe.") from None

    def rubros(self) -> list[Rubro]:
        return sorted(self._rubros.values(), key=lambda r: (r.orden, r.nombre.casefold()))

    def guardar_rubro(self, rubro: Rubro) -> Rubro:
        self._rubros[rubro.id] = rubro
        return rubro

    def quitar_rubro(self, rubro_id: str) -> None:
        self.rubro(rubro_id)
        if any(c.rubro_id == rubro_id for c in self._categorias.values()):
            raise ErrorValidacion("La categoría todavía tiene subcategorías.")
        del self._rubros[rubro_id]

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
        self._seguir_aportes(operacion_id, nueva)
        return nueva

    def eliminar_operacion(self, operacion_id: str) -> Operacion:
        op = self.operacion(operacion_id)
        del self._operaciones[operacion_id]
        self._seguir_aportes(operacion_id, None)
        return op

    def _seguir_aportes(self, operacion_id: str, op: Operacion | None) -> None:
        """Los aportes y retiros de una meta siguen a la transferencia que movió su dinero: si se borra, se quitan
        de la meta; si se corrige, toman su fecha y su importe. Así la meta no dice que hay dinero que no está."""
        for meta in list(self._metas.values()):
            if not any(a.operacion_id == operacion_id for a in meta.aportes):
                continue
            importe = 0 if op is None else sum(p.importe for p in op.partidas if p.importe > 0)
            aportes = tuple(
                a if a.operacion_id != operacion_id
                else replace(a, fecha=op.fecha, centavos=importe if a.centavos > 0 else -importe)
                for a in meta.aportes if op is not None or a.operacion_id != operacion_id
            )
            self._metas[meta.id] = replace(meta, aportes=aportes)

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
