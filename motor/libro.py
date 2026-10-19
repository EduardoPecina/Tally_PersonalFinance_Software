"""El Libro: el estado completo de las finanzas de una persona.

Guarda cuentas, categorías, grupos, operaciones y perfil en memoria. Toda
operación pasa por :func:`motor.reglas.validar_operacion` antes de guardarse.

La persistencia (Fase 2) se encargará de cargar y guardar un ``Libro``; el
resto del motor solo trabaja contra esta clase.
"""

from __future__ import annotations

import uuid
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime

from motor.errores import ErrorDatos, ErrorNoEncontrado, ErrorValidacion
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
    Comprobante,
    Regla,
    Perfil,
    Recurrente,
    Rubro,
    RubroContable,
    RUBROS_CONTABLES_BASE,
    RUBROS_CONTABLES_FIJOS,
)
from motor.reglas import validar_operacion

_CONTABLES_BASE = {r.id: r for r in RUBROS_CONTABLES_BASE}


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
        # Índices que se arman al pedirlos y se tiran con cada cambio de movimientos (ver _movimientos_cambiaron):
        # los movimientos en orden con sus fechas (para buscar un rango con bisect), los de cada cuenta y el saldo
        # acumulado de cada cuenta. Con años de datos, el Resumen pide cientos de saldos y rangos en cada vista.
        self._orden: tuple[list[Operacion], list[date]] | None = None
        self._por_cuenta: dict[str, tuple[list[Operacion], list[date]]] | None = None
        self._acumulados: dict[str, tuple[list[date], list[int]]] | None = None
        self._valores: dict[str, OperacionValor] = {}
        self._plazos: dict[str, InversionPlazo] = {}
        self._bienes: dict[str, Bien] = {}
        self._prestamos: dict[str, Prestamo] = {}
        self._recurrentes: dict[str, Recurrente] = {}
        self._metas: dict[str, Meta] = {}
        self._cierres: dict[str, CierreMes] = {}
        self._reglas: dict[str, Regla] = {}
        self._comprobantes: dict[str, Comprobante] = {}
        # Los del usuario y lo que les cambió a los de TALLY (otro nombre, o borrado): los de TALLY vienen en el programa.
        self._rubros_contables: dict[str, RubroContable] = {}
        # Archivos de comprobantes agregados y aún sin guardar: la persistencia los escribe en la misma transacción
        # que sus datos (o se descartan con el libro si algo falla).
        self._archivos_nuevos: dict[str, bytes] = {}
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
        reglas: list[Regla] = (),
        comprobantes: list[Comprobante] = (),
        rubros_contables: list[RubroContable] = (),
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
        libro._reglas = {r.id: r for r in reglas}
        libro._comprobantes = {c.id: c for c in comprobantes}
        libro._rubros_contables = {r.id: r for r in rubros_contables}
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
        for r in [r for r in self._reglas.values() if r.cuenta_id == cuenta_id]:
            del self._reglas[r.id]                 # una regla de esa cuenta ya no tiene a qué aplicarse

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

    # ------------------------------------------------------------------ comprobantes

    def comprobantes(self, operacion_id: str | None = None) -> list[Comprobante]:
        lista = [c for c in self._comprobantes.values() if operacion_id is None or c.operacion_id == operacion_id]
        return sorted(lista, key=lambda c: (c.agregado or datetime.min, c.nombre, c.id))

    def comprobante(self, comprobante_id: str) -> Comprobante:
        try:
            return self._comprobantes[comprobante_id]
        except KeyError:
            raise ErrorNoEncontrado("Ese comprobante no existe.") from None

    def guardar_comprobante(self, comprobante: Comprobante, contenido: bytes | None = None) -> Comprobante:
        """``contenido``: el archivo, al agregarlo (se escribe al guardar el libro)."""
        self.operacion(comprobante.operacion_id)
        if contenido is None and comprobante.id not in self._comprobantes:
            raise ErrorValidacion("Falta el archivo del comprobante.")
        self._comprobantes[comprobante.id] = comprobante
        if contenido is not None:
            self._archivos_nuevos[comprobante.id] = contenido
        return comprobante

    def quitar_comprobante(self, comprobante_id: str) -> None:
        self.comprobante(comprobante_id)
        del self._comprobantes[comprobante_id]
        self._archivos_nuevos.pop(comprobante_id, None)

    def poner_archivos(self, archivos: dict[str, bytes]) -> None:
        """Los archivos de los comprobantes que ya tiene el libro (al restaurar un respaldo): se escriben al
        guardarlo. Deben estar todos."""
        faltan = [c.nombre for c in self._comprobantes.values() if c.id not in archivos]
        if faltan:
            raise ErrorDatos(f"Faltan los archivos de {len(faltan)} comprobante(s) (por ejemplo «{faltan[0]}»).")
        self._archivos_nuevos = {i: archivos[i] for i in self._comprobantes}

    def archivos_nuevos(self) -> dict[str, bytes]:
        """Los archivos agregados que aún no se guardan (los usa la persistencia)."""
        return dict(self._archivos_nuevos)

    def archivos_guardados(self) -> None:
        self._archivos_nuevos.clear()

    # ------------------------------------------------------------------ reglas de categorías

    def reglas(self) -> list[Regla]:
        return sorted(self._reglas.values(), key=lambda r: (r.texto, r.cuenta_id or "", r.id))

    def regla(self, regla_id: str) -> Regla:
        try:
            return self._reglas[regla_id]
        except KeyError:
            raise ErrorNoEncontrado("Esa regla no existe.") from None

    def guardar_regla(self, regla: Regla) -> Regla:
        self.categoria(regla.categoria_id)
        if regla.cuenta_id is not None:
            self.cuenta(regla.cuenta_id)
        self._reglas[regla.id] = regla
        return regla

    def quitar_regla(self, regla_id: str) -> None:
        self.regla(regla_id)
        del self._reglas[regla_id]

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

    def rubros_contables(self) -> list[RubroContable]:
        """Los de TALLY (sin los que borró el usuario) y los del usuario: primero los de ingreso, cada clase en su
        orden."""
        todos = (self._contable(i) for i in {**_CONTABLES_BASE, **self._rubros_contables})
        return sorted([r for r in todos if not r.borrado],
                      key=lambda r: (r.clase is not ClaseCategoria.INGRESO, r.orden, r.nombre.casefold()))

    def rubros_contables_propios(self) -> list[RubroContable]:
        """Lo que se guarda: los que creó el usuario y lo que les cambió a los de TALLY (otro nombre, o borrado)."""
        return list(self._rubros_contables.values())

    def rubros_contables_borrados(self) -> list[RubroContable]:
        """Los de TALLY que borró el usuario (se pueden recuperar)."""
        return [r for r in map(self._contable, _CONTABLES_BASE) if r.borrado]

    def rubro_contable(self, rubro_contable_id: str) -> RubroContable:
        rubro = self._contable(rubro_contable_id)
        if rubro is None or rubro.borrado:
            raise ErrorNoEncontrado("Ese rubro contable no existe.")
        return rubro

    def hay_rubro_contable(self, rubro_contable_id: str) -> bool:
        rubro = self._rubros_contables.get(rubro_contable_id)
        return not rubro.borrado if rubro else rubro_contable_id in _CONTABLES_BASE

    def guardar_rubro_contable(self, rubro: RubroContable) -> RubroContable:
        base = _CONTABLES_BASE.get(rubro.id)
        if base is not None:
            if rubro.clase is not base.clase:
                raise ErrorValidacion("Un rubro contable de TALLY no cambia de ingreso a gasto ni al revés.")
            if rubro.nombre == base.nombre and not rubro.borrado:
                self._rubros_contables.pop(rubro.id, None)          # como lo trae TALLY: no hay nada que guardar
                return base
            rubro = replace(base, nombre=rubro.nombre, borrado=rubro.borrado, descripcion="")
        self._rubros_contables[rubro.id] = rubro
        return self._contable(rubro.id)

    def quitar_rubro_contable(self, rubro_contable_id: str) -> None:
        """Lo borra; sus subcategorías vuelven a donde TALLY las acomoda solo. Uno de TALLY queda como borrado (se
        puede recuperar); los fijos, donde cae lo que no está en otro rubro, no se borran."""
        rubro = self.rubro_contable(rubro_contable_id)
        if rubro_contable_id in RUBROS_CONTABLES_FIJOS:
            raise ErrorValidacion(f"«{rubro.nombre}» no se puede borrar: ahí va lo que no está en otro rubro. "
                                  "Sí lo puedes renombrar.")
        if rubro_contable_id in _CONTABLES_BASE:
            self.guardar_rubro_contable(replace(rubro, borrado=True))
        else:
            del self._rubros_contables[rubro_contable_id]
        for c in [c for c in self._categorias.values() if c.rubro_contable_id == rubro_contable_id]:
            self._categorias[c.id] = replace(c, rubro_contable_id=None)

    def recuperar_rubro_contable(self, rubro_contable_id: str) -> RubroContable:
        """Uno de TALLY que se había borrado vuelve con su nombre original."""
        guardado = self._rubros_contables.get(rubro_contable_id)
        if rubro_contable_id not in _CONTABLES_BASE or guardado is None or not guardado.borrado:
            raise ErrorNoEncontrado("Ese rubro contable de TALLY no está borrado.")
        del self._rubros_contables[rubro_contable_id]
        return _CONTABLES_BASE[rubro_contable_id]

    def _contable(self, rubro_contable_id: str) -> RubroContable | None:
        """Tal como está (aunque esté borrado): uno de TALLY, con lo que le cambió el usuario."""
        base, guardado = _CONTABLES_BASE.get(rubro_contable_id), self._rubros_contables.get(rubro_contable_id)
        if base is None or guardado is None:
            return base or guardado
        return replace(base, nombre=guardado.nombre, borrado=guardado.borrado)

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

    def operaciones(self, desde: date | None = None, hasta: date | None = None,
                    cuenta_id: str | None = None) -> list[Operacion]:
        """Operaciones en orden cronológico, opcionalmente en un rango (inclusivo) y solo las que mueven una cuenta.
        Una lista nueva cada vez."""
        ops, fechas = self._ordenadas() if cuenta_id is None else self._de_cuenta(cuenta_id)
        inicio = bisect_left(fechas, desde) if desde is not None else 0
        fin = bisect_right(fechas, hasta) if hasta is not None else len(ops)
        return ops[inicio:fin]

    def _ordenadas(self) -> tuple[list[Operacion], list[date]]:
        if self._orden is None:
            ops = sorted(self._operaciones.values(), key=lambda op: op.orden)
            self._orden = (ops, [op.fecha for op in ops])
        return self._orden

    def _de_cuenta(self, cuenta_id: str) -> tuple[list[Operacion], list[date]]:
        if self._por_cuenta is None:
            self._por_cuenta = {}
            for op in self._ordenadas()[0]:
                for p in op.partidas:
                    if p.cuenta_id is not None:
                        ops, fechas = self._por_cuenta.setdefault(p.cuenta_id, ([], []))
                        if not ops or ops[-1] is not op:          # una vez aunque la mueva en dos partidas
                            ops.append(op)
                            fechas.append(op.fecha)
        return self._por_cuenta.get(cuenta_id, ([], []))

    def _movimientos_cambiaron(self) -> None:
        self._orden = None
        self._por_cuenta = None
        self._acumulados = None

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
        self._movimientos_cambiaron()
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
        self._movimientos_cambiaron()
        self._seguir_aportes(operacion_id, nueva)
        return nueva

    def eliminar_operacion(self, operacion_id: str) -> Operacion:
        op = self.operacion(operacion_id)
        del self._operaciones[operacion_id]
        self._movimientos_cambiaron()
        self._seguir_aportes(operacion_id, None)
        for c in [c for c in self._comprobantes.values() if c.operacion_id == operacion_id]:
            self.quitar_comprobante(c.id)           # sus comprobantes se van con él
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
        if self._acumulados is None:
            self._acumulados = {}
            for op in self._ordenadas()[0]:
                for p in op.partidas:
                    if p.cuenta_id is not None:
                        fechas, totales = self._acumulados.setdefault(p.cuenta_id, ([], []))
                        fechas.append(op.fecha)
                        totales.append((totales[-1] if totales else 0) + p.importe)
        fechas, totales = self._acumulados.get(cuenta_id, ((), ()))
        if not totales:
            return 0
        if al is None:
            return totales[-1]
        i = bisect_right(fechas, _solo_fecha(al))
        return totales[i - 1] if i else 0


def _solo_fecha(valor: date) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if not isinstance(valor, date):
        raise ErrorValidacion("La fecha no es válida.")
    return valor
