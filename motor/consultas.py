"""Consultas para mostrar información: historial con filtros y etiquetas en español.

Aquí vive todo lo que el portal necesita para listar movimientos, para que la
interfaz no tenga que interpretar partidas ni decidir signos.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from motor import categorias
from motor.dinero import a_pesos
from motor.libro import Libro
from motor.modelo import ClaseCategoria, Operacion, TipoCuenta, TipoOperacion
from motor.movimientos import describir

ETIQUETA_TIPO_OPERACION = {
    TipoOperacion.GASTO: "Gasto",
    TipoOperacion.INGRESO: "Ingreso",
    TipoOperacion.REEMBOLSO: "Reembolso",
    TipoOperacion.TRANSFERENCIA: "Transferencia",
    TipoOperacion.PAGO_TARJETA: "Pago de tarjeta",
    TipoOperacion.RENDIMIENTO: "Rendimiento",
    TipoOperacion.AJUSTE: "Ajuste de saldo",
    TipoOperacion.SALDO_INICIAL: "Saldo inicial",
}

ETIQUETA_TIPO_CUENTA = {
    TipoCuenta.DEBITO: "Débito",
    TipoCuenta.AHORRO: "Ahorro",
    TipoCuenta.CREDITO: "Tarjeta de crédito",
    TipoCuenta.EFECTIVO: "Efectivo",
    TipoCuenta.INVERSION: "Inversión",
    TipoCuenta.POR_COBRAR: "Por cobrar",
    TipoCuenta.OTRA: "Otra",
}

ETIQUETA_CLASE = {
    ClaseCategoria.GASTO: "Gasto",
    ClaseCategoria.INGRESO: "Ingreso",
    ClaseCategoria.SISTEMA: "Sistema",
}

# Efecto de cada tipo en tu dinero, para mostrarlo: "-" sale, "+" entra, "↔" se mueve.
_SENTIDO = {
    TipoOperacion.GASTO: "-",
    TipoOperacion.INGRESO: "+",
    TipoOperacion.REEMBOLSO: "+",
    TipoOperacion.TRANSFERENCIA: "↔",
    TipoOperacion.PAGO_TARJETA: "↔",
}

ORDENES = {
    "fecha_desc": "Más recientes primero",
    "fecha_asc": "Más antiguos primero",
    "monto_desc": "Mayor importe primero",
    "monto_asc": "Menor importe primero",
}


@dataclass(frozen=True, slots=True)
class FilaMovimiento:
    id: str
    fecha: date
    tipo: TipoOperacion
    tipo_etiqueta: str
    descripcion: str
    notas: str
    cuenta: str
    cuenta_destino: str
    categoria: str  # subcategoría(s)
    monto: Decimal  # siempre positivo
    sentido: str  # "-", "+" o "↔"
    rubro: str = ""  # la categoría que agrupa a la subcategoría

    @property
    def importe_con_signo(self) -> Decimal:
        """Negativo si el dinero salió, positivo si entró; las transferencias van en positivo."""
        return -self.monto if self.sentido == "-" else self.monto


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).casefold()


def fila(libro: Libro, op: Operacion) -> FilaMovimiento:
    detalle = describir(op)
    ids = [detalle.categoria_id] if detalle.categoria_id is not None else [cat_id for cat_id, _ in detalle.reparto]
    categoria = ", ".join(libro.categoria(cat_id).nombre for cat_id in ids)
    rubro = ", ".join(dict.fromkeys(r for cat_id in ids if (r := categorias.nombre_rubro(libro, cat_id))))
    sentido = _SENTIDO.get(op.tipo) or ("+" if detalle.monto >= 0 else "-")
    return FilaMovimiento(
        id=op.id,
        fecha=op.fecha,
        tipo=op.tipo,
        tipo_etiqueta=ETIQUETA_TIPO_OPERACION[op.tipo],
        descripcion=op.descripcion,
        notas=op.notas,
        cuenta=libro.cuenta(detalle.cuenta_id).nombre,
        cuenta_destino=libro.cuenta(detalle.cuenta_destino_id).nombre if detalle.cuenta_destino_id else "",
        categoria=categoria,
        monto=abs(detalle.monto),
        sentido=sentido,
        rubro=rubro,
    )


def buscar(
    libro: Libro,
    *,
    texto: str = "",
    cuentas: Iterable[str] = (),
    categorias: Iterable[str] = (),
    tipos: Iterable[TipoOperacion | str] = (),
    desde: date | None = None,
    hasta: date | None = None,
    orden: str = "fecha_desc",
) -> list[FilaMovimiento]:
    """Movimientos que cumplen todos los filtros indicados (los vacíos no filtran).

    - ``texto`` busca en descripción, notas, cuenta y categoría, sin importar
      mayúsculas ni acentos.
    - ``cuentas`` incluye el movimiento si la cuenta es el origen o el destino.
    """
    cuentas, categorias = set(cuentas), set(categorias)
    tipos = {TipoOperacion(t) for t in tipos}
    buscado = _normalizar(texto.strip())
    filas = []
    for op in libro.operaciones(desde, hasta):
        if tipos and op.tipo not in tipos:
            continue
        if cuentas and not any(p.cuenta_id in cuentas for p in op.partidas):
            continue
        if categorias and not any(p.categoria_id in categorias for p in op.partidas):
            continue
        f = fila(libro, op)
        if buscado:
            pajar = _normalizar(" ".join((f.descripcion, f.notas, f.cuenta, f.cuenta_destino, f.categoria, f.rubro)))
            if buscado not in pajar:
                continue
        filas.append(f)

    if orden not in ORDENES:
        orden = "fecha_desc"
    if orden.startswith("monto"):
        filas.sort(key=lambda f: f.monto, reverse=orden == "monto_desc")
    elif orden == "fecha_desc":
        filas.reverse()
    return filas


def total(filas: Iterable[FilaMovimiento]) -> dict[str, Decimal]:
    """Suma de lo listado por sentido: entradas, salidas y movimientos entre cuentas."""
    resultado = {"+": Decimal(0), "-": Decimal(0), "↔": Decimal(0)}
    for f in filas:
        resultado[f.sentido] += f.monto
    return {clave: a_pesos(int(valor * 100)) for clave, valor in resultado.items()}


# ------------------------------------------------------------ por cuenta


@dataclass(frozen=True, slots=True)
class FilaCuenta:
    """Un renglón del estado de cuenta: como en el Excel, con el saldo después de cada movimiento."""

    id: str
    fecha: date
    tipo: TipoOperacion
    tipo_etiqueta: str
    descripcion: str
    detalle: str              # «SALUD › DENTISTA», «→ Ahorro», «← Débito»…
    cargo: Decimal            # salió de la cuenta (0 si no)
    abono: Decimal            # entró a la cuenta (0 si no)
    saldo: Decimal            # saldo de la cuenta después de este movimiento (negativo en crédito = deuda)
    msi: int = 0


def movimientos_de_cuenta(libro: Libro, cuenta_id: str, desde: date | None = None,
                          hasta: date | None = None) -> list[FilaCuenta]:
    """Los movimientos de una cuenta con su saldo corrido, del más reciente al más antiguo.

    El saldo se calcula con todo el historial (aunque se pida un rango), así que siempre coincide con el real.
    """
    libro.cuenta(cuenta_id)
    filas, saldo = [], 0
    for op in libro.operaciones(hasta=hasta):
        propias = [p for p in op.partidas_de_cuenta() if p.cuenta_id == cuenta_id]
        if not propias:
            continue
        importe = sum(p.importe for p in propias)
        saldo += importe
        if desde is not None and op.fecha < desde:
            continue
        otras = [p for p in op.partidas_de_cuenta() if p.cuenta_id != cuenta_id]
        if otras:
            flecha = "→" if importe < 0 else "←"
            detalle = f"{flecha} {libro.cuenta(otras[0].cuenta_id).nombre}"
        else:
            detalle = ", ".join(categorias.etiqueta(libro, p.categoria_id) for p in op.partidas_de_categoria())
        filas.append(FilaCuenta(
            id=op.id, fecha=op.fecha, tipo=op.tipo, tipo_etiqueta=ETIQUETA_TIPO_OPERACION[op.tipo],
            descripcion=op.descripcion, detalle=detalle, cargo=a_pesos(max(0, -importe)),
            abono=a_pesos(max(0, importe)), saldo=a_pesos(saldo), msi=op.msi,
        ))
    return list(reversed(filas))
