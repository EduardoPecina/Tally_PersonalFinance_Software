"""Impuestos, para cualquier país: tus gastos deducibles y el cálculo (y la revisión) de un recibo o factura.

TALLY no sabe las leyes de cada país (y cambian cada año): tú defines las reglas, todas editables y borrables. La
página trae ejemplos para guiarte (México, España, Argentina, Colombia…), pero nada se agrega solo. Todo es una
referencia: lo oficial lo dice tu autoridad fiscal o tu contador.

**Gastos deducibles.** Un *concepto* (gastos médicos, colegiaturas, alquiler…) junta subcategorías de TALLY y dice
qué parte del gasto se deduce (100 %, 40 %…), hasta cuánto al año y si deja fuera lo pagado en efectivo. Además puede
haber un tope total para todos (un monto, o un % de tu ingreso del año). El reporte suma lo de cada año.

**Perfiles de impuestos.** Un *perfil* son los impuestos de un tipo de recibo: cada uno con su nombre, su tasa, sobre
qué se calcula (el subtotal u otro impuesto, como «2/3 del IVA») y si se suma (traslado), se resta (retención) o lo
pagas tú directo al fisco (a tu cargo: no cambia el recibo, como el ISR del RESICO). Con él se calcula un recibo
desde el subtotal o desde lo que recibes, y se revisa uno que te dieron.

**Pagos al fisco.** Un perfil puede recordarte cuánto pagar y hasta cuándo: dices a qué ingresos aplica (sus
subcategorías), cómo los registras (lo que te llega o el subtotal), cada cuándo pagas y la fecha límite. Por cada
periodo, TALLY suma esos ingresos, calcula cada impuesto que te toca pagar (lo que trasladas y lo que es a tu cargo)
menos lo que ya te retuvieron, y te lo recuerda en el Resumen. No registra nada: cuando pagas, lo registras tú (un
gasto en IMPUESTOS) y lo marcas como pagado. Es una estimación: no resta el IVA de tus gastos ni otras deducciones.
"""

from __future__ import annotations

from collections import defaultdict
import calendar
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from motor import categorias
from motor.dinero import a_centavos, a_pesos, formatear
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import (
    ClaseCategoria,
    ConceptoDeducible,
    Impuesto,
    Operacion,
    PerfilImpuestos,
    TipoCuenta,
    TipoOperacion,
)
from motor.textos import normalizar_nombre

CERO = Decimal("0.00")
CENTAVO = Decimal("0.01")
TOLERANCIA = Decimal("1.00")          # diferencia total aceptable al revisar un recibo (redondeos)
AVISO = ("Es una referencia para planear: las reglas cambian cada año y dependen de tu situación. Confirma con tu "
         "autoridad fiscal o tu contador.")


def redondear(valor: Decimal) -> Decimal:
    """A centavos como el ROUND de Excel: 0.005 sube."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def leer_tasa(texto) -> Decimal:
    """«16», «16 %», «1.25», «10,5» o una fracción «2/3» (= 66.67 %)."""
    t = str(texto).strip().replace("%", "").replace(",", ".").strip()
    try:
        if "/" in t:
            arriba, abajo = (Decimal(x.strip()) for x in t.split("/", 1))
            return (arriba / abajo * 100).quantize(Decimal("0.0000000001"))
        tasa = Decimal(t)
    except (InvalidOperation, ZeroDivisionError):
        raise ErrorValidacion(f"La tasa «{texto}» no es válida (escribe 16, 1.25 o 2/3).") from None
    if tasa < 0 or tasa > 100:
        raise ErrorValidacion("La tasa debe estar entre 0 % y 100 %.")
    return tasa


def mostrar_tasa(tasa: Decimal) -> str:
    """66.6666666667 → «2/3 (66.67 %)»; 16 → «16 %»."""
    for arriba, abajo in ((2, 3), (1, 3)):
        if abs(tasa - Decimal(arriba) / Decimal(abajo) * 100) < Decimal("0.0001"):
            return f"{arriba}/{abajo} ({tasa.quantize(CENTAVO)} %)"
    return f"{tasa.normalize():f} %"


# ===================================================================== conceptos deducibles


def guardar_concepto(libro: Libro, nombre: str, subcategorias, *, porcentaje=100, tope=None,
                     sin_efectivo: bool = False, notas: str = "", fuera_del_tope: bool = False,
                     concepto_id: str | None = None) -> ConceptoDeducible:
    nombre = normalizar_nombre(nombre)
    ids = tuple(dict.fromkeys(subcategorias))
    if not ids:
        raise ErrorValidacion("Elige al menos una subcategoría.")
    for i in ids:
        if libro.categoria(i).clase is not ClaseCategoria.GASTO:
            raise ErrorValidacion(f"«{libro.categoria(i).nombre}» no es una subcategoría de gasto.")
    parte = leer_tasa(porcentaje)
    if parte == 0:
        raise ErrorValidacion("El porcentaje deducible debe ser mayor que cero.")
    centavos = a_centavos(tope) if tope not in (None, "", 0) else None
    if centavos is not None and centavos <= 0:
        raise ErrorValidacion("El tope debe ser mayor que cero (o déjalo vacío).")
    fiscal = libro.fiscal
    if any(c.nombre.casefold() == nombre.casefold() and c.id != concepto_id for c in fiscal.conceptos):
        raise ErrorValidacion(f"Ya tienes un concepto llamado «{nombre}».")
    concepto = ConceptoDeducible(concepto_id or libro.nuevo_id(), nombre, ids, parte, centavos, sin_efectivo,
                                 notas.strip(), fuera_del_tope)
    conceptos = [c for c in fiscal.conceptos if c.id != concepto.id]
    posicion = next((n for n, c in enumerate(fiscal.conceptos) if c.id == concepto.id), len(conceptos))
    conceptos.insert(posicion, concepto)
    libro.fiscal = replace(fiscal, conceptos=tuple(conceptos))
    return concepto


def eliminar_concepto(libro: Libro, concepto_id: str) -> None:
    libro.fiscal = replace(libro.fiscal, conceptos=tuple(c for c in libro.fiscal.conceptos if c.id != concepto_id))


def ajustar_topes(libro: Libro, *, tope_total=None, tope_porcentaje=None) -> None:
    """El tope para todos los deducibles juntos: un monto al año, un % de tu ingreso, ambos (el menor) o ninguno."""
    total = a_centavos(tope_total) if tope_total not in (None, "", 0) else None
    porcentaje = leer_tasa(tope_porcentaje) if tope_porcentaje not in (None, "", 0) else None
    libro.fiscal = replace(libro.fiscal, tope_total=total, tope_porcentaje=porcentaje)


def quitar_deducibles(libro: Libro) -> None:
    """Borra todos tus conceptos deducibles, el tope total y las notas (para empezar de cero)."""
    libro.fiscal = replace(libro.fiscal, conceptos=(), tope_total=None, tope_porcentaje=None, notas="")


def ajustar_notas(libro: Libro, notas: str) -> None:
    """Tus notas de deducibles (requisitos, dónde revisar los topes de tu país…)."""
    libro.fiscal = replace(libro.fiscal, notas=notas.strip())


@dataclass(frozen=True, slots=True)
class Pago:
    fecha: date
    descripcion: str
    subcategoria: str
    cuenta: str
    importe: Decimal              # positivo; un reembolso, negativo
    en_efectivo: bool
    operacion_id: str = ""        # el movimiento (para sus comprobantes)


@dataclass(slots=True)
class Renglon:
    concepto: ConceptoDeducible
    pagado: Decimal = CERO
    en_efectivo: Decimal = CERO       # lo que no cuenta (si el concepto lo pide)
    considerado: Decimal = CERO       # (pagado − efectivo) × porcentaje
    deducible: Decimal = CERO         # con el tope del concepto
    pagos: list[Pago] = field(default_factory=list)

    @property
    def topado(self) -> bool:
        return self.deducible < self.considerado


@dataclass(frozen=True, slots=True)
class Reporte:
    anio: int
    renglones: list[Renglon]
    suma: Decimal                     # de los deducibles de cada concepto
    ingreso: Decimal                  # tus ingresos del año (para el tope en %)
    tope: Decimal | None              # el tope total que aplica (el menor)
    total: Decimal                    # lo que podrías deducir
    fuera_del_tope: Decimal = CERO    # la parte de conceptos que no entran en el tope total


def ingresos_del_anio(libro: Libro, anio: int) -> Decimal:
    total = 0
    for op in libro.operaciones(date(anio, 1, 1), date(anio, 12, 31)):
        if op.tipo is TipoOperacion.INGRESO:
            total -= sum(p.importe for p in op.partidas_de_categoria())
    return a_pesos(total)


def deducibles(libro: Libro, anio: int, ingreso: Decimal | None = None) -> Reporte:
    """Lo que podrías deducir en ``anio``, concepto por concepto, con sus topes."""
    fiscal = libro.fiscal
    por_subcategoria: dict[str, list[Renglon]] = defaultdict(list)
    renglones = [Renglon(c) for c in fiscal.conceptos]
    for r in renglones:
        for sub in r.concepto.subcategorias:
            por_subcategoria[sub].append(r)
    efectivo: dict[str, int] = defaultdict(int)
    for op in libro.operaciones(date(anio, 1, 1), date(anio, 12, 31)):
        if op.tipo not in (TipoOperacion.GASTO, TipoOperacion.REEMBOLSO):
            continue
        cuenta = _cuenta(libro, op)
        es_efectivo = cuenta is not None and libro.cuenta(cuenta).tipo is TipoCuenta.EFECTIVO
        for p in op.partidas_de_categoria():
            for r in por_subcategoria.get(p.categoria_id, ()):
                r.pagos.append(Pago(op.fecha, op.descripcion, categorias.etiqueta(libro, p.categoria_id),
                                    libro.cuenta(cuenta).nombre if cuenta else "", a_pesos(p.importe), es_efectivo,
                                    op.id))
                r.pagado += a_pesos(p.importe)
                if es_efectivo and r.concepto.sin_efectivo:
                    efectivo[r.concepto.id] += p.importe
    suma = CERO
    for r in renglones:
        r.en_efectivo = a_pesos(efectivo[r.concepto.id])
        r.considerado = max(CERO, redondear((r.pagado - r.en_efectivo) * r.concepto.porcentaje / 100))
        tope = a_pesos(r.concepto.tope) if r.concepto.tope is not None else None
        r.deducible = min(r.considerado, tope) if tope is not None else r.considerado
        suma += r.deducible
    ingreso = ingresos_del_anio(libro, anio) if ingreso is None else ingreso
    topes = []
    if fiscal.tope_total is not None:
        topes.append(a_pesos(fiscal.tope_total))
    if fiscal.tope_porcentaje is not None:
        topes.append(redondear(ingreso * fiscal.tope_porcentaje / 100))
    tope = min(topes) if topes else None
    fuera = sum((r.deducible for r in renglones if r.concepto.fuera_del_tope), CERO)
    dentro = suma - fuera
    total = (min(dentro, tope) if tope is not None else dentro) + fuera
    return Reporte(anio, renglones, suma, ingreso, tope, total, fuera)


def _cuenta(libro: Libro, op: Operacion) -> str | None:
    cuentas = [p.cuenta_id for p in op.partidas_de_cuenta()]
    return cuentas[0] if cuentas else None


# ===================================================================== perfiles de impuestos


def guardar_perfil(libro: Libro, nombre: str, impuestos, *, notas: str = "", perfil_id: str | None = None,
                   subcategorias=(), registro: str = "recibido", frecuencia: str = "", dia_limite: int = 17,
                   meses_despues: int = 1) -> PerfilImpuestos:
    """``impuestos``: lista de ``Impuesto`` (o de dicts con nombre, tasa, sobre, retenido y a_cargo). Lo demás es el
    recordatorio de pago al fisco (sin ``frecuencia``, no hay recordatorio)."""
    nombre = normalizar_nombre(nombre)
    lista = []
    for i in impuestos:
        if isinstance(i, dict):
            i = Impuesto(i.get("nombre", ""), leer_tasa(i.get("tasa", 0)), i.get("sobre", "") or "",
                         bool(i.get("retenido", False)), bool(i.get("a_cargo", False)))
        if i.retenido and i.a_cargo:
            raise ErrorValidacion(f"«{i.nombre}» no puede ser retenido y a tu cargo a la vez.")
        if not str(i.nombre).strip():
            continue
        lista.append(replace(i, nombre=" ".join(str(i.nombre).split()), sobre=i.sobre.strip()))
    if not lista:
        raise ErrorValidacion("Agrega al menos un impuesto.")
    vistos: set[str] = set()
    for i in lista:
        if i.nombre.casefold() in vistos:
            raise ErrorValidacion(f"«{i.nombre}» aparece dos veces.")
        if i.sobre and i.sobre.casefold() not in vistos:
            raise ErrorValidacion(f"«{i.nombre}» se calcula sobre «{i.sobre}», que debe ir antes en la lista.")
        vistos.add(i.nombre.casefold())
    fiscal = libro.fiscal
    if any(p.nombre.casefold() == nombre.casefold() and p.id != perfil_id for p in fiscal.perfiles):
        raise ErrorValidacion(f"Ya tienes un perfil llamado «{nombre}».")
    subcategorias = tuple(dict.fromkeys(subcategorias or ()))
    for categoria_id in subcategorias:
        if libro.categoria(categoria_id).clase is not ClaseCategoria.INGRESO:
            raise ErrorValidacion("El recordatorio de pago al fisco va sobre subcategorías de ingreso.")
    if frecuencia not in FRECUENCIAS_PAGO:
        raise ErrorValidacion("Elige cada cuándo pagas estos impuestos.")
    if registro not in REGISTRO:
        raise ErrorValidacion("Elige cómo registras esos ingresos.")
    if frecuencia and not subcategorias:
        raise ErrorValidacion("Para recordarte el pago al fisco, elige sobre qué ingresos (sus subcategorías).")
    if not 1 <= int(dia_limite) <= 31 or not 0 <= int(meses_despues) <= 12:
        raise ErrorValidacion("La fecha límite es un día del 1 al 31, de 0 a 12 meses después del periodo.")
    previo = next((p for p in fiscal.perfiles if p.id == perfil_id), None)
    desde = (previo.recordatorio_desde if previo is not None and previo.frecuencia else libro.hoy()) \
        if frecuencia else None
    perfil = PerfilImpuestos(perfil_id or libro.nuevo_id(), nombre, tuple(lista), notas.strip(), subcategorias,
                             registro, frecuencia, int(dia_limite), int(meses_despues), desde)
    perfiles = [p for p in fiscal.perfiles if p.id != perfil.id]
    posicion = next((n for n, p in enumerate(fiscal.perfiles) if p.id == perfil.id), len(perfiles))
    perfiles.insert(posicion, perfil)
    libro.fiscal = replace(fiscal, perfiles=tuple(perfiles))
    return perfil


def eliminar_perfil(libro: Libro, perfil_id: str) -> None:
    libro.fiscal = replace(libro.fiscal, perfiles=tuple(p for p in libro.fiscal.perfiles if p.id != perfil_id))


@dataclass(frozen=True, slots=True)
class Desglose:
    subtotal: Decimal
    lineas: list[tuple[Impuesto, Decimal]]      # cada impuesto con su importe (positivo)
    total: Decimal                              # lo que recibes (o pagas): subtotal + traslados − retenciones

    @property
    def trasladados(self) -> Decimal:
        return sum((v for i, v in self.lineas if not i.retenido and not i.a_cargo), CERO)

    @property
    def retenidos(self) -> Decimal:
        return sum((v for i, v in self.lineas if i.retenido), CERO)

    @property
    def a_cargo(self) -> Decimal:
        """Lo que pagas tú directo al fisco (no está en el recibo)."""
        return sum((v for i, v in self.lineas if i.a_cargo), CERO)


def calcular(perfil: PerfilImpuestos, subtotal) -> Desglose:
    """Desde el subtotal (antes de impuestos): cada impuesto y el total."""
    base = redondear(Decimal(str(subtotal)))
    calculados: dict[str, Decimal] = {}
    lineas = []
    for i in perfil.impuestos:
        sobre = base if not i.sobre else calculados.get(i.sobre.casefold(), CERO)
        importe = redondear(sobre * i.tasa / 100)
        calculados[i.nombre.casefold()] = importe
        lineas.append((i, importe))
    total = (base + sum((v for i, v in lineas if not i.retenido and not i.a_cargo), CERO)
             - sum((v for i, v in lineas if i.retenido), CERO))
    return Desglose(base, lineas, total)


def desde_total(perfil: PerfilImpuestos, total) -> Desglose:
    """Desde lo que recibes (o pagas): el subtotal que da ese total, al centavo si se puede."""
    objetivo = redondear(Decimal(str(total)))
    efectiva: dict[str, Decimal] = {}                  # la tasa de cada impuesto sobre el subtotal, sin redondear
    factor = Decimal(1)
    for i in perfil.impuestos:
        efectiva[i.nombre.casefold()] = (efectiva.get(i.sobre.casefold(), CERO) if i.sobre else Decimal(1)) * i.tasa / 100
        if not i.a_cargo:                                   # lo que pagas tú no cambia lo que recibes
            factor += -efectiva[i.nombre.casefold()] if i.retenido else efectiva[i.nombre.casefold()]
    if factor <= 0:
        raise ErrorValidacion("Con esos impuestos no se puede calcular el subtotal.")
    estimado = redondear(objetivo / factor)
    candidatos = [calcular(perfil, estimado + Decimal(d) / 100) for d in range(-3, 4)]
    return min(candidatos, key=lambda d: (abs(d.total - objetivo), abs(d.subtotal - estimado)))


def revisar(perfil: PerfilImpuestos, subtotal, reales: dict[str, Decimal], *,
            tolerancia: Decimal = TOLERANCIA) -> list[str]:
    """Compara lo que dice un recibo con lo que debería ser. Lista vacía si cuadra (dentro de la tolerancia)."""
    esperado = calcular(perfil, subtotal)
    leidos = {k.casefold(): redondear(Decimal(str(v or 0))) for k, v in reales.items()}
    diferencias = [(i, leidos.get(i.nombre.casefold(), CERO), v) for i, v in esperado.lineas
                   if not i.a_cargo]                    # lo que pagas tú no viene en el recibo
    variacion = sum((abs(real - calc) for _, real, calc in diferencias), CERO)
    if variacion <= tolerancia:
        return []
    problemas = []
    for i, real, calc in diferencias:
        if abs(real - calc) > CENTAVO:
            regla = f"{mostrar_tasa(i.tasa)} " + (f"de {i.sobre}" if i.sobre else "del subtotal")
            problemas.append(f"{i.nombre}: dice {formatear(real)}, debería ser {formatear(calc)} ({regla})")
    for i, real, _ in diferencias:
        if i.sobre and real > 0 and leidos.get(i.sobre.casefold(), CERO) == 0:
            problemas.append(f"trae {i.nombre} pero no {i.sobre} (¿se capturó un impuesto en el lugar de otro?)")
    return [f"No cuadra (diferencia total {formatear(variacion)})", *problemas]


# ===================================================================== pagos al fisco

FRECUENCIAS_PAGO = {"": "No me lo recuerdes", "mensual": "Cada mes", "bimestral": "Cada 2 meses",
                    "trimestral": "Cada 3 meses", "semestral": "Cada 6 meses", "anual": "Cada año"}
_MESES_PAGO = {"mensual": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12}
REGISTRO = {"recibido": "Lo que me llega a la cuenta (ya con sus impuestos)",
            "subtotal": "El monto antes de impuestos (el subtotal)"}
DIAS_TRAS_EL_LIMITE = 30            # el aviso sigue (como vencido) hasta 30 días después de la fecha límite
PENDIENTE, VENCIDO, PAGADO, EN_CURSO, SIN_PAGO = "pendiente", "vencido", "pagado", "en curso", "sin pago"
_PALABRAS_DE_RETENCION = {"RETENCION", "RETENIDO", "RETENIDA", "RET", "DE", "DEL", "LA", "EL", "SOBRE"}


@dataclass(frozen=True, slots=True)
class ImpuestoAPagar:
    """Un impuesto que te toca pagar en un periodo: lo que causó menos lo que ya te retuvieron de él."""

    nombre: str
    causado: Decimal
    retenido: Decimal = CERO

    @property
    def a_pagar(self) -> Decimal:
        return max(self.causado - self.retenido, CERO)


@dataclass(frozen=True, slots=True)
class PagoAlFisco:
    perfil: PerfilImpuestos
    desde: date
    hasta: date
    limite: date
    cobrado: Decimal                  # lo que registraste (o esperas, si ``estimado``) en esos ingresos
    base: Decimal                     # antes de impuestos
    impuestos: list[ImpuestoAPagar]
    otras_retenciones: Decimal        # retenciones que no se restan de ningún impuesto de aquí (p. ej. el ISR de
    #                                   honorarios, sin un renglón «a tu cargo»): ya se pagaron por ti
    estimado: bool                    # no registraste esos ingresos: con lo que esperas según tu calendario
    pagado: bool                      # lo marcaste como pagado

    @property
    def total(self) -> Decimal:
        return sum((i.a_pagar for i in self.impuestos), CERO)

    @property
    def clave(self) -> str:
        return clave_de_pago(self.perfil, self.desde)

    def estado(self, hoy: date) -> str:
        if self.pagado:
            return PAGADO
        if hoy <= self.hasta:
            return EN_CURSO
        if self.total <= 0:                                  # terminó y no hay nada que pagar (no cobraste)
            return SIN_PAGO
        return VENCIDO if hoy > self.limite else PENDIENTE


def clave_de_pago(perfil: PerfilImpuestos, desde: date) -> str:
    return f"{perfil.id}:{desde:%Y-%m}"


def periodo(perfil: PerfilImpuestos, dia: date) -> tuple[date, date]:
    """El periodo (mes, bimestre, trimestre… del año calendario) que incluye ``dia``."""
    meses = _MESES_PAGO[perfil.frecuencia]
    primero = (dia.month - 1) // meses * meses + 1
    ultimo = primero + meses - 1
    return date(dia.year, primero, 1), date(dia.year, ultimo, calendar.monthrange(dia.year, ultimo)[1])


def limite(perfil: PerfilImpuestos, hasta: date) -> date:
    """El día ``dia_limite`` del mes que cae ``meses_despues`` meses después de que termina el periodo (el último
    día del mes si es más corto: el 31 en febrero es el 28 o 29)."""
    indice = hasta.year * 12 + hasta.month - 1 + perfil.meses_despues
    anio, mes = divmod(indice, 12)
    return date(anio, mes + 1, min(perfil.dia_limite, calendar.monthrange(anio, mes + 1)[1]))


def pago_del_periodo(libro: Libro, perfil: PerfilImpuestos, desde: date, hasta: date) -> PagoAlFisco:
    """Cuánto le toca pagar al fisco por los ingresos de ``desde`` a ``hasta``."""
    from motor import recurrentes

    ingresos = set(perfil.subcategorias)
    centavos = sum(-p.importe for op in libro.operaciones(desde, hasta) for p in op.partidas_de_categoria()
                   if p.categoria_id in ingresos)
    estimado = False
    if not centavos:                                     # sin ingresos registrados: lo que dice tu calendario
        centavos = sum(recurrentes.monto_en(r, dia) for r in libro.recurrentes()
                       if r.activa and r.tipo is TipoOperacion.INGRESO and r.categoria_id in ingresos
                       for dia in recurrentes.fechas(r, desde, hasta))
        estimado = bool(centavos)
    cobrado = a_pesos(centavos)
    desglose = calcular(perfil, max(cobrado, CERO))
    if cobrado > 0 and perfil.registro == "recibido":
        try:
            desglose = desde_total(perfil, cobrado)
        except ErrorValidacion:                          # un perfil raro: se toma como subtotal
            pass
    impuestos, otras = _a_pagar(desglose)
    return PagoAlFisco(perfil, desde, hasta, limite(perfil, hasta), cobrado, desglose.subtotal, impuestos, otras,
                       estimado, clave_de_pago(perfil, desde) in libro.fiscal.pagados)


def _a_pagar(desglose: Desglose) -> tuple[list[ImpuestoAPagar], Decimal]:
    """Lo que trasladas o es a tu cargo, menos lo que ya te retuvieron *de ese mismo impuesto*: una retención resta
    del impuesto sobre el que se calcula (la de 2/3 del IVA, del IVA) o del que se llama igual sin «Retención»
    (Retención ISR → ISR). Una retención que no corresponde a nada de aquí ya se pagó por ti: no se resta de
    otro."""
    propios = {i.nombre.casefold(): [i.nombre, v, CERO] for i, v in desglose.lineas if not i.retenido}
    otras = CERO
    for i, v in desglose.lineas:
        if not i.retenido:
            continue
        destino = i.sobre.casefold() if i.sobre.casefold() in propios else _mismo_impuesto(i.nombre, propios)
        if destino is None:
            otras += v
        else:
            propios[destino][2] += v
    return [ImpuestoAPagar(n, c, r) for n, c, r in propios.values()], otras


def _mismo_impuesto(retencion: str, propios: dict) -> str | None:
    from motor.textos import clave

    nucleo = set(clave(retencion).split()) - _PALABRAS_DE_RETENCION
    if not nucleo:
        return None
    return next((k for k, (nombre, *_) in propios.items() if nucleo <= set(clave(nombre).split())), None)


def pagos_al_fisco(libro: Libro, perfil: PerfilImpuestos, hoy: date, cuantos: int = 12) -> list[PagoAlFisco]:
    """Los últimos ``cuantos`` periodos (del más reciente al más antiguo), incluido el que va en curso."""
    if not perfil.frecuencia:
        return []
    pagos, dia = [], hoy
    for _ in range(cuantos):
        desde, hasta = periodo(perfil, dia)
        pagos.append(pago_del_periodo(libro, perfil, desde, hasta))
        dia = desde - timedelta(days=1)
    return pagos


def por_pagar(libro: Libro, hoy: date | None = None) -> list[PagoAlFisco]:
    """Lo que te toca pagar al fisco: periodos ya terminados, sin marcar como pagados, desde que termina el periodo
    hasta ``DIAS_TRAS_EL_LIMITE`` días después de la fecha límite. Por fecha límite."""
    hoy = hoy or libro.hoy()
    pendientes = []
    for perfil in libro.fiscal.perfiles:
        for pago in pagos_al_fisco(libro, perfil, hoy, cuantos=4):
            if (pago.estado(hoy) in (PENDIENTE, VENCIDO) and pago.total > 0
                    and hoy <= pago.limite + timedelta(days=DIAS_TRAS_EL_LIMITE)
                    and (perfil.recordatorio_desde is None or pago.limite >= perfil.recordatorio_desde)):
                pendientes.append(pago)
    return sorted(pendientes, key=lambda p: (p.limite, p.perfil.nombre.casefold()))


def marcar_pagado(libro: Libro, clave: str, pagado: bool = True) -> None:
    """«Ya lo pagué» (o deshacerlo). No registra ningún movimiento: el pago lo registras tú."""
    pagados = [c for c in libro.fiscal.pagados if c != clave] + ([clave] if pagado else [])
    libro.fiscal = replace(libro.fiscal, pagados=tuple(pagados[-200:]))
