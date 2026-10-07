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
    BIEN = "bien"            # casa, auto, laptop… (motor/bienes.py): su valor baja con la depreciación
    PRESTAMO = "prestamo"    # préstamo personal, de auto, hipoteca… (motor/prestamos.py): negativo = deuda


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
CATEGORIA_BIENES = "sistema-bienes"     # ganancia o pérdida al vender un bien (motor/bienes.py)
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
    iva: Decimal = Decimal(16)         # % de IVA/VAT de tu país: se cobra sobre los intereses (tarjetas, préstamos)
    ingreso_esperado: int | None = None  # centavos al mes; None = el promedio de tus ingresos fijos (planeacion.py)
    meta_ahorro: int = 10              # % del ingreso que quieres ahorrar (presupuestos sugeridos)


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
    # Solo tarjetas de crédito, opcionales: para estimar intereses y el pago mínimo (motor/tarjetas.py).
    tasa_anual: Decimal | None = None  # tasa de interés anual ordinaria, en %
    cat: Decimal | None = None         # CAT (o TAE, CAE, CFT…): informativo
    tasa_incluye_iva: bool = False     # si la tasa ya trae el IVA incluido


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
    # Ingreso secundario fijo (renta que cobras, honorarios de cada mes…): cuenta en el ingreso esperado.
    secundario: bool = False


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


class MetodoDepreciacion(enum.StrEnum):
    LINEA_RECTA = "linea_recta"      # pierde lo mismo cada año hasta su valor de rescate
    DECRECIENTE = "decreciente"      # pierde un % de lo que vale cada año (más al principio): autos
    NINGUNA = "ninguna"              # casa, terreno: su valor cambia solo con avalúos


@dataclass(frozen=True, slots=True)
class Avaluo:
    """Lo que vale el bien en una fecha según un avalúo o el mercado (plusvalía o minusvalía)."""

    fecha: date
    valor: int               # centavos


@dataclass(frozen=True, slots=True)
class Bien:
    """Cómo se valúa una cuenta de tipo ``BIEN``. Su id es el de la cuenta. Ver motor/bienes.py.

    El costo (compra, mejoras) son movimientos de la cuenta; la depreciación y los avalúos se **calculan** con
    estos datos, no se guardan como movimientos.
    """

    cuenta_id: str
    clase: str                                   # auto, computadora, casa… (bienes.CLASES)
    metodo: MetodoDepreciacion
    vida_anios: Decimal = Decimal(0)             # línea recta
    tasa_anual: Decimal = Decimal(0)             # decreciente, en %
    rescate: Decimal = Decimal(0)                # % del costo que conserva al final
    avaluos: tuple[Avaluo, ...] = ()
    fecha_baja: date | None = None               # lo vendiste o lo diste de baja
    operaciones_baja: tuple[str, ...] = ()       # los movimientos de la venta (para deshacerla)

    @property
    def id(self) -> str:
        return self.cuenta_id


@dataclass(frozen=True, slots=True)
class Prestamo:
    """Cómo se contrató un préstamo (cuenta de tipo ``PRESTAMO``; su id es el de la cuenta). Ver motor/prestamos.py.

    Lo que debes hoy sale de los movimientos de la cuenta; esto solo sirve para calcular el pago, la tabla de
    amortización y las simulaciones.
    """

    cuenta_id: str
    clase: str                       # personal, auto, hipoteca, nomina, otro (prestamos.CLASES)
    monto: int                       # lo que solicitaste, en centavos
    tasa_anual: Decimal              # tasa de interés anual ordinaria, en %
    plazo_meses: int
    fecha_inicio: date
    iva: Decimal | None = None       # % de IVA sobre los intereses; None = el de tu perfil; 0 = sin IVA (hipoteca)
    pago_pactado: int | None = None  # centavos al mes, si tu contrato dice otro (seguros incluidos…)
    dia_pago: int | None = None
    cat: Decimal | None = None       # informativo

    @property
    def id(self) -> str:
        return self.cuenta_id


@dataclass(frozen=True, slots=True)
class Recurrente:
    """Un pago o ingreso que se repite: renta, luz, Netflix, la nómina… (motor/recurrentes.py).

    Es un recordatorio con su importe estimado: no mueve dinero hasta que lo registras.
    """

    id: str
    nombre: str
    tipo: TipoOperacion            # GASTO, INGRESO o TRANSFERENCIA (a otra cuenta tuya, p. ej. al ahorro)
    monto: int                     # centavos estimados (positivo)
    cuenta_id: str                 # de dónde sale (o a dónde entra, si es ingreso)
    frecuencia: str                # semanal, catorcenal, quincenal, mensual, bimestral, trimestral, semestral, anual
    inicio: date                   # la primera vez (marca el día del mes o de la semana)
    categoria_id: str | None = None   # gasto o ingreso
    destino_id: str | None = None     # transferencia: a qué cuenta
    fin: date | None = None
    suscripcion: bool = False
    activa: bool = True
    notas: str = ""
    monto_2: int | None = None     # quincenal: el importe de la 2.ª quincena, si es distinto (centavos)
    fin_de_semana: str = ""        # si cae en sábado o domingo: "antes" (el viernes), "despues" (el lunes) o "" (igual)


@dataclass(frozen=True, slots=True)
class Aporte:
    fecha: date
    centavos: int                  # + aporte, − retiro
    operacion_id: str = ""         # la transferencia que movió el dinero (si la hubo)


@dataclass(frozen=True, slots=True)
class Meta:
    """Una meta de ahorro (o el fondo de emergencia), ver motor/metas.py. Lo ahorrado es la suma de sus aportes."""

    id: str
    nombre: str
    objetivo: int                  # centavos
    cuenta_id: str | None = None   # dónde guardas ese dinero (opcional)
    fecha_limite: date | None = None
    emergencia: bool = False
    aportes: tuple[Aporte, ...] = ()
    creada: date | None = None
    activa: bool = True            # False: lograda o archivada
    notas: str = ""


@dataclass(frozen=True, slots=True)
class ConceptoDeducible:
    """Un tipo de gasto que puedes deducir de tus impuestos (gastos médicos, colegiaturas…), ver motor/impuestos.py.
    Sirve para cualquier país: tú eliges qué subcategorías cuentan, qué parte y hasta cuánto."""

    id: str
    nombre: str
    subcategorias: tuple[str, ...]
    porcentaje: Decimal = Decimal(100)   # qué parte del gasto se deduce
    tope: int | None = None              # centavos al año
    sin_efectivo: bool = False           # solo cuenta si no se pagó en efectivo
    notas: str = ""
    fuera_del_tope: bool = False         # no entra en el tope total (p. ej. colegiaturas en México)


@dataclass(frozen=True, slots=True)
class Impuesto:
    nombre: str                          # IVA, ISR, IRPF, Ganancias…
    tasa: Decimal                        # en %
    sobre: str = ""                      # "" = sobre el subtotal; o el nombre de otro impuesto (p. ej. 2/3 del IVA)
    retenido: bool = False               # True: se resta (retención); False: se suma (traslado)


@dataclass(frozen=True, slots=True)
class PerfilImpuestos:
    """Los impuestos de un tipo de recibo o factura (honorarios, arrendamiento, venta…)."""

    id: str
    nombre: str
    impuestos: tuple[Impuesto, ...]
    notas: str = ""


@dataclass(frozen=True, slots=True)
class CierreMes:
    """Un mes que marcaste como cerrado (motor/cierre.py). No bloquea nada: guarda cómo estaban sus números al
    cerrarlo, para mostrarte después lo que cambió (un movimiento que registraste tarde, una corrección…)."""

    id: str                        # «2026-09»
    cerrado_en: datetime
    ingresos: int                  # centavos, al cerrar
    gastos: int
    patrimonio: int                # al último día del mes
    movimientos: int               # cuántos movimientos tenía el mes
    notas: str = ""


@dataclass(frozen=True, slots=True)
class Fiscal:
    """Tus ajustes de impuestos (uno por libro)."""

    conceptos: tuple[ConceptoDeducible, ...] = ()
    perfiles: tuple[PerfilImpuestos, ...] = ()
    tope_total: int | None = None          # centavos al año, para todos los deducibles juntos
    tope_porcentaje: Decimal | None = None  # % de tu ingreso del año
    notas: str = ""
