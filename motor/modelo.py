"""Entidades del dominio.

Todas son inmutables (``frozen``); para modificarlas se crea una copia con
``dataclasses.replace`` y se guarda en el ``Libro``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

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
    """El usuario de esta PC y sus preferencias (Configuración)."""

    nombre: str
    creado_en: datetime
    moneda: str = MONEDA
    respaldo_diario: bool = True       # al abrir TALLY, un respaldo automático por día
    respaldos_a_conservar: int = 10    # cuántos respaldos automáticos se guardan
    periodo_inicial: str = "mes_actual"  # el periodo que muestra el Resumen al abrir
    tema: str = "claro"                # claro u oscuro (para descansar la vista)
    icono: str = "claro"               # color del ícono del acceso directo: claro, oscuro, acento o gris
    dias_para_reclamar: int = 45       # cargos temporales: avisar si no te los devuelven en estos días
    clasificaciones: int = 2           # versión del reacomodo de clasificaciones ya aplicado (catalogo.py)
    actualizar_precios: bool = False   # consultar precios de títulos al abrir una cuenta de inversión (solo símbolos)


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
    # Fecha límite de pago: un día fijo del mes (dia_pago) O N días después del corte (dias_para_pagar),
    # contados como naturales o hábiles. Si cae en día inhábil, se recorre al siguiente hábil.
    dia_pago: int | None = None
    dias_para_pagar: int | None = None
    dias_habiles: bool = False
    recorrer_inhabil: bool = True
    # Solo cuentas de inversión con títulos: la ganancia (realizada + no realizada) que ya se pasó al saldo como
    # rendimiento, en centavos. Así «Registrar como rendimiento» solo agrega lo nuevo (motor/portafolio.py).
    plusvalia_registrada: int = 0


class TipoOperacionValor(enum.StrEnum):
    COMPRA = "compra"
    VENTA = "venta"


@dataclass(frozen=True, slots=True)
class OperacionValor:
    """Compra o venta de títulos (acciones, ETF, cripto) dentro de una cuenta de inversión.

    Es un detalle de la cuenta, no un movimiento: comprar acciones con el dinero que ya está en la cuenta no
    cambia su saldo. El dinero entra y sale de la cuenta con transferencias, como siempre.
    """

    id: str
    cuenta_id: str
    fecha: date
    tipo: TipoOperacionValor
    simbolo: str               # como lo cotiza Yahoo Finance: IVVPESO.MX, AAPL, BTC-USD…
    titulos: Decimal           # puede tener decimales (cripto, fracciones de acción)
    precio: Decimal            # por título, en ``moneda``
    moneda: str = MONEDA
    tipo_cambio: Decimal = Decimal(1)   # pesos por unidad de ``moneda`` ese día (1 si es MXN)
    comision: Decimal = Decimal(0)      # en ``moneda``
    notas: str = ""


@dataclass(frozen=True, slots=True)
class InversionPlazo:
    """CETES, pagarés o certificados de depósito: tasa fija; su valor se calcula sin internet."""

    id: str
    cuenta_id: str
    nombre: str
    fecha_inicio: date
    monto: int                 # centavos invertidos
    tasa_anual: Decimal        # % anual (p. ej. 10.5)
    plazo_dias: int
    notas: str = ""


@dataclass(frozen=True, slots=True)
class Grupo:
    """Agrupa categorías (Necesidad, Disfrute, …). Totalmente editable."""

    id: str
    nombre: str
    orden: int = 0


@dataclass(frozen=True, slots=True)
class Rubro:
    """La caja que agrupa subcategorías (SALUD, TECNOLOGIA…). En el portal se llama «Categoría».

    Los movimientos nunca apuntan a un rubro, solo a sus subcategorías (:class:`Categoria`).
    """

    id: str
    nombre: str
    clase: ClaseCategoria  # INGRESO o GASTO
    orden: int = 0
    presupuesto: int | None = None  # gasto mensual que el usuario se propone no rebasar (centavos)


@dataclass(frozen=True, slots=True)
class Categoria:
    """Lo que se asigna a cada movimiento. En el portal se llama «Subcategoría» y vive dentro de un
    :class:`Rubro` (salvo las del sistema). ``grupo_id`` es su clasificación (Necesidad, Disfrute…)."""

    id: str
    nombre: str
    clase: ClaseCategoria
    grupo_id: str | None = None
    activa: bool = True
    # Ingreso principal (p. ej. Nómina): marca el inicio de cada quincena.
    principal: bool = False
    orden: int = 0
    rubro_id: str | None = None


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
    # Compra con tarjeta de crédito a meses sin intereses (0 = de contado). El gasto cuenta completo en la
    # fecha de compra; la tarjeta solo exige una mensualidad en cada corte (motor/tarjetas.py).
    msi: int = 0
    # Devolución (o paso a gasto) de un cargo temporal: el id del cargo que liquida (motor/temporales.py).
    liquida: str = ""

    def partidas_de_cuenta(self) -> tuple[Partida, ...]:
        return tuple(p for p in self.partidas if p.cuenta_id is not None)

    def partidas_de_categoria(self) -> tuple[Partida, ...]:
        return tuple(p for p in self.partidas if p.categoria_id is not None)

    @property
    def orden(self) -> tuple[date, int]:
        """Orden cronológico: fecha y, dentro del día, orden de captura."""
        return (self.fecha, self.secuencia)
