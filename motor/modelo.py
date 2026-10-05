"""Entidades del dominio.

Todas son inmutables (``frozen``); para modificarlas se crea una copia con
``dataclasses.replace`` y se guarda en el ``Libro``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime

from motor.config import MONEDA


class TipoCuenta(enum.StrEnum):
    DEBITO = "debito"
    AHORRO = "ahorro"
    CREDITO = "credito"
    EFECTIVO = "efectivo"
    INVERSION = "inversion"
    POR_COBRAR = "por_cobrar"
    OTRA = "otra"


# Cuentas que cuentan como "dinero disponible" salvo que el usuario diga otra cosa.
TIPOS_DISPONIBLES_POR_DEFECTO = frozenset({TipoCuenta.DEBITO, TipoCuenta.EFECTIVO})
# Cuentas que suman en "Total en cuentas".
TIPOS_EN_CUENTAS = frozenset(
    {TipoCuenta.DEBITO, TipoCuenta.AHORRO, TipoCuenta.EFECTIVO, TipoCuenta.INVERSION, TipoCuenta.OTRA}
)
# Destinos que cuentan como "apartado a ahorro".
TIPOS_AHORRO = frozenset({TipoCuenta.AHORRO, TipoCuenta.INVERSION})


class ClaseCategoria(enum.StrEnum):
    INGRESO = "ingreso"
    GASTO = "gasto"
    SISTEMA = "sistema"


class TipoOperacion(enum.StrEnum):
    GASTO = "gasto"
    INGRESO = "ingreso"
    REEMBOLSO = "reembolso"
    TRANSFERENCIA = "transferencia"
    PAGO_TARJETA = "pago_tarjeta"
    RENDIMIENTO = "rendimiento"
    AJUSTE = "ajuste"
    SALDO_INICIAL = "saldo_inicial"


# Categorías del sistema: existen siempre, no se pueden borrar ni renombrar y
# nunca cuentan como ingreso ni como gasto.
CATEGORIA_AJUSTE = "sistema-ajuste"
CATEGORIA_SALDO_INICIAL = "sistema-saldo-inicial"


@dataclass(frozen=True, slots=True)
class Perfil:
    nombre: str
    creado_en: datetime
    moneda: str = MONEDA


@dataclass(frozen=True, slots=True)
class Cuenta:
    id: str
    nombre: str
    tipo: TipoCuenta
    fecha_creacion: date
    en_disponible: bool
    moneda: str = MONEDA
    activa: bool = True
    institucion: str = ""
    notas: str = ""
    orden: int = 0
    # Solo para cuentas de crédito; todos opcionales. Importes en centavos.
    limite_credito: int | None = None
    dia_corte: int | None = None
    dia_pago: int | None = None


@dataclass(frozen=True, slots=True)
class Grupo:
    """Agrupa categorías (Necesidad, Disfrute, …). Totalmente editable."""

    id: str
    nombre: str
    orden: int = 0


@dataclass(frozen=True, slots=True)
class Categoria:
    id: str
    nombre: str
    clase: ClaseCategoria
    grupo_id: str | None = None
    activa: bool = True
    # Ingreso principal (p. ej. Nómina): marca el inicio de cada quincena.
    principal: bool = False
    orden: int = 0


@dataclass(frozen=True, slots=True)
class Partida:
    """Una línea de una operación. Afecta a una cuenta o a una categoría."""

    importe: int  # centavos, con signo
    cuenta_id: str | None = None
    categoria_id: str | None = None

    def __post_init__(self) -> None:
        if (self.cuenta_id is None) == (self.categoria_id is None):
            raise ValueError("Una partida afecta a una cuenta o a una categoría, no a ambas ni a ninguna.")
        if isinstance(self.importe, bool) or not isinstance(self.importe, int):
            raise ValueError("El importe de una partida debe ser un entero en centavos.")


@dataclass(frozen=True, slots=True)
class Operacion:
    """Lo que el usuario registra. Sus partidas siempre suman cero."""

    fecha: date
    tipo: TipoOperacion
    partidas: tuple[Partida, ...]
    descripcion: str = ""
    notas: str = ""
    # Los asigna el Libro al guardar.
    id: str = ""
    secuencia: int = 0
    creado_en: datetime | None = None
    modificado_en: datetime | None = None

    def partidas_de_cuenta(self) -> tuple[Partida, ...]:
        return tuple(p for p in self.partidas if p.cuenta_id is not None)

    def partidas_de_categoria(self) -> tuple[Partida, ...]:
        return tuple(p for p in self.partidas if p.categoria_id is not None)

    @property
    def orden(self) -> tuple[date, int]:
        """Orden cronológico: fecha y, dentro del día, orden de captura."""
        return (self.fecha, self.secuencia)
