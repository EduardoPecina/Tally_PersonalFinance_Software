"""Préstamos: personal, de auto, hipoteca, de nómina, de un familiar… cuánto debes, cuánto pagar y cómo salir.

Un préstamo es una cuenta de tipo ``PRESTAMO`` (su saldo negativo es lo que debes) más cómo se contrató
(``modelo.Prestamo``): monto solicitado, tasa anual, plazo, IVA sobre los intereses y, si tu contrato lo dice, el
pago pactado.

- **Contratarlo**: el dinero sale del préstamo hacia la cuenta donde llegó (o hacia un bien, como un auto). Si el
  banco te cobró comisión por apertura, se descuenta de lo que recibiste y es gasto. Si ya lo tenías, escribe lo
  que debes hoy (su saldo inicial).
- **Cada pago** se registra en dos partes que siempre cuadran: los **intereses + IVA + cargos** (mora, comisión,
  seguro) son **gasto** y se suman a la deuda, y el **pago completo** es una transferencia de tu cuenta al
  préstamo. Lo que baja la deuda es la diferencia: el **capital**. Si pagas menos que los intereses, la deuda
  sube, como en la vida real.
- Los cálculos (pago mensual, tabla de amortización, simulaciones) usan el método francés: pago fijo, con
  intereses sobre lo que aún debes. Son **estimaciones**: cada banco redondea a su manera; lo oficial es tu
  estado de cuenta.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from motor import categorias, cuentas
from motor.dinero import a_centavos, a_pesos, formatear
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import ClaseCategoria, Operacion, Prestamo, TipoCuenta, TipoOperacion
from motor.movimientos import registrar_gasto
from motor.transferencias import registrar_transferencia

CERO = Decimal(0)
CENTAVO = Decimal("0.01")
DIAS_DE_ADELANTO = 7         # un pago hasta 7 días antes de la fecha cuenta como el de ese mes
MAXIMO_MESES = 600
SUBCATEGORIA_INTERESES = "INTERESES DE PRESTAMOS"
SUBCATEGORIA_CARGOS = "COMISIONES BANCARIAS"
CAPACIDAD_SANA = Decimal(30)    # % del ingreso que se recomienda destinar como máximo a pagar deudas
CAPACIDAD_LIMITE = Decimal(40)


@dataclass(frozen=True, slots=True)
class Clase:
    nombre: str
    con_iva: bool = True        # en México los intereses de un préstamo hipotecario no llevan IVA
    ayuda: str = ""


CLASES: dict[str, Clase] = {
    "personal": Clase("Préstamo personal"),
    "auto": Clase("Crédito de auto", ayuda="Si el dinero se fue directo a la agencia, elige tu auto (un bien) como "
                                           "destino: así tu auto vale lo que pagaste por él."),
    "hipoteca": Clase("Hipoteca o crédito de vivienda", con_iva=False,
                      ayuda="En México los intereses de una hipoteca no llevan IVA."),
    "nomina": Clase("Crédito de nómina"),
    "familiar": Clase("Préstamo de un familiar o amigo", con_iva=False,
                      ayuda="Si no te cobra intereses, pon tasa 0."),
    "otro": Clase("Otro"),
}


# ------------------------------------------------------------------ registrar


def crear(libro: Libro, nombre: str, clase: str, monto, tasa_anual, plazo_meses: int, fecha_inicio: date, *,
          destino: str | None = None, deuda_actual=None, iva=None, pago_pactado=None, dia_pago: int | None = None,
          cat=None, comision_apertura=0, institucion: str = "") -> Prestamo:
    """Un préstamo nuevo.

    - Con ``destino``: lo acabas de recibir; ``monto`` (menos la comisión por apertura) llega a esa cuenta o bien.
    - Sin ``destino``: ya lo tenías; ``deuda_actual`` es lo que debes hoy (si no se da, se estima con la tabla).
    """
    if clase not in CLASES:
        raise ErrorValidacion("Elige qué tipo de préstamo es.")
    datos = _datos(clase, monto, tasa_anual, plazo_meses, fecha_inicio, iva, pago_pactado, dia_pago, cat)
    if datos.fecha_inicio > libro.hoy():
        raise ErrorValidacion("La fecha del préstamo no puede ser futura.")
    comision = a_centavos(comision_apertura or 0)
    if comision < 0 or comision >= datos.monto:
        raise ErrorValidacion("La comisión por apertura debe ser menor que el monto.")
    cuenta = cuentas.crear(libro, nombre, TipoCuenta.PRESTAMO, fecha_creacion=fecha_inicio, en_disponible=False,
                           institucion=institucion)
    prestamo = libro.guardar_prestamo(replace(datos, cuenta_id=cuenta.id))
    if destino:
        registrar_transferencia(libro, fecha_inicio, cuenta.id, destino, a_pesos(datos.monto - comision),
                                f"Préstamo recibido: {cuenta.nombre}")
        if comision:
            registrar_gasto(libro, fecha_inicio, cuenta.id, _subcategoria(libro, SUBCATEGORIA_CARGOS),
                            a_pesos(comision), f"Comisión por apertura: {cuenta.nombre}")
    else:
        hoy = libro.hoy()
        deuda = a_centavos(deuda_actual) if deuda_actual not in (None, "") else a_centavos(
            saldo_segun_tabla(libro, prestamo, hoy))
        if deuda < 0:
            raise ErrorValidacion("Lo que debes no puede ser negativo.")
        if deuda:
            cuentas.cambiar_saldo_inicial(libro, cuenta.id, a_pesos(-deuda), hoy)
    return prestamo


def configurar(libro: Libro, cuenta_id: str, *, monto=None, tasa_anual=None, plazo_meses=None, fecha_inicio=None,
               iva: object = "", pago_pactado: object = "", dia_pago: object = "", cat: object = "",
               clase: str | None = None) -> Prestamo:
    """Corrige los datos del contrato (no cambia movimientos: solo los cálculos)."""
    p = _prestamo(libro, cuenta_id)
    nuevo = _datos(clase if clase in CLASES else p.clase,
                   a_pesos(p.monto) if monto is None else monto,
                   p.tasa_anual if tasa_anual is None else tasa_anual,
                   p.plazo_meses if plazo_meses is None else plazo_meses,
                   p.fecha_inicio if fecha_inicio is None else fecha_inicio,
                   p.iva if iva == "" else iva,
                   (a_pesos(p.pago_pactado) if p.pago_pactado else None) if pago_pactado == "" else pago_pactado,
                   p.dia_pago if dia_pago == "" else dia_pago,
                   p.cat if cat == "" else cat)
    return libro.guardar_prestamo(replace(nuevo, cuenta_id=cuenta_id))


def estimar_interes(libro: Libro, cuenta_id: str, fecha: date | None = None) -> tuple[Decimal, Decimal]:
    """(intereses, IVA) de un mes sobre lo que debes a ``fecha``: deuda × tasa anual / 12."""
    p = _prestamo(libro, cuenta_id)
    deuda = deuda_al(libro, cuenta_id, fecha or libro.hoy())
    interes = (deuda * p.tasa_anual / 100 / 12).quantize(CENTAVO)
    return interes, (interes * iva_de(libro, p) / 100).quantize(CENTAVO)


def registrar_pago(libro: Libro, cuenta_id: str, fecha: date, total, cuenta_origen: str, *, interes=None, iva=None,
                   cargos=0, categoria_cargos: str | None = None, descripcion: str = "") -> list[Operacion]:
    """Un pago al préstamo. ``interes`` e ``iva`` como dice tu estado de cuenta (si no, se estiman); ``cargos``:
    mora, cargo por retraso, comisión o seguro que venían en el pago. Lo demás es capital.

    Devuelve los movimientos: el gasto (intereses + IVA + cargos, si hay) y la transferencia del pago.
    """
    p = _prestamo(libro, cuenta_id)
    nombre = libro.cuenta(cuenta_id).nombre
    pago = a_centavos(total)
    if pago <= 0:
        raise ErrorValidacion("El pago debe ser mayor que cero.")
    if interes is None:
        interes_estimado, iva_estimado = estimar_interes(libro, cuenta_id, fecha)
        interes = interes_estimado
        iva = iva_estimado if iva is None else iva
    elif iva is None:
        iva = (Decimal(str(interes)) * iva_de(libro, p) / 100).quantize(CENTAVO)
    partes = [(a_centavos(interes), _subcategoria(libro, SUBCATEGORIA_INTERESES)),
              (a_centavos(iva), _subcategoria(libro, SUBCATEGORIA_INTERESES)),
              (a_centavos(cargos or 0), categoria_cargos or _subcategoria(libro, SUBCATEGORIA_CARGOS))]
    if any(c < 0 for c, _ in partes):
        raise ErrorValidacion("Intereses, IVA y cargos no pueden ser negativos.")
    juntas: dict[str, int] = {}
    for centavos, categoria_id in partes:
        if centavos:
            juntas[categoria_id] = juntas.get(categoria_id, 0) + centavos
    capital = pago - sum(juntas.values())
    detalle = (f"capital {_texto(capital)}, intereses {_texto(partes[0][0])}, IVA {_texto(partes[1][0])}"
               + (f", cargos {_texto(partes[2][0])}" if partes[2][0] else ""))
    ops = []
    if juntas:
        ops.append(registrar_gasto(libro, fecha, cuenta_id, reparto=[(c, a_pesos(v)) for c, v in juntas.items()],
                                   descripcion=f"Intereses y cargos: {nombre}", notas=detalle))
    ops.append(registrar_transferencia(libro, fecha, cuenta_origen, cuenta_id, a_pesos(pago),
                                       descripcion or f"Pago de {nombre}", detalle))
    return ops


def registrar_cargo(libro: Libro, cuenta_id: str, fecha: date, monto, *, categoria_id: str | None = None,
                    descripcion: str = "") -> Operacion:
    """Un cargo que el banco sumó a tu deuda sin que pagaras: mora, cargo por retraso, comisión, seguro."""
    _prestamo(libro, cuenta_id)
    return registrar_gasto(libro, fecha, cuenta_id, categoria_id or _subcategoria(libro, SUBCATEGORIA_CARGOS), monto,
                           descripcion or f"Cargo: {libro.cuenta(cuenta_id).nombre}")


# ------------------------------------------------------------------ calcular


def iva_de(libro: Libro, p: Prestamo) -> Decimal:
    if p.iva is not None:
        return p.iva
    if not CLASES.get(p.clase, CLASES["otro"]).con_iva:
        return CERO
    return libro.perfil.iva if libro.perfil else Decimal(16)


def tasa_mensual(libro: Libro, p: Prestamo) -> Decimal:
    """La tasa de cada mes, con el IVA de los intereses: tasa anual / 12 × (1 + IVA)."""
    return p.tasa_anual / 100 / 12 * (1 + iva_de(libro, p) / 100)


def pago_calculado(monto: Decimal, tasa_mes: Decimal, meses: int) -> Decimal:
    """Pago fijo (método francés) para liquidar ``monto`` en ``meses`` a ``tasa_mes``."""
    if meses <= 0:
        return monto
    if tasa_mes == 0:
        return (monto / meses).quantize(CENTAVO)
    factor = (1 + tasa_mes) ** meses
    return (monto * tasa_mes * factor / (factor - 1)).quantize(CENTAVO)


def pago_mensual(libro: Libro, p: Prestamo) -> Decimal:
    """El pactado si lo registraste; si no, el que da la tabla."""
    if p.pago_pactado:
        return a_pesos(p.pago_pactado)
    return pago_calculado(a_pesos(p.monto), tasa_mensual(libro, p), p.plazo_meses)


@dataclass(frozen=True, slots=True)
class Mes:
    numero: int
    fecha: date
    pago: Decimal
    interes: Decimal
    iva: Decimal
    capital: Decimal
    saldo: Decimal          # lo que debes después del pago


def amortizacion(libro: Libro, p: Prestamo) -> list[Mes]:
    """La tabla del contrato: del monto solicitado, mes por mes, con el pago mensual."""
    return _simular(libro, p, a_pesos(p.monto), pago_mensual(libro, p), p.fecha_inicio, maximo=p.plazo_meses + 240)


def saldo_segun_tabla(libro: Libro, p: Prestamo, dia: date) -> Decimal:
    """Lo que deberías según la tabla del contrato si pagaste a tiempo hasta ``dia``."""
    saldo = a_pesos(p.monto)
    for mes in amortizacion(libro, p):
        if mes.fecha > dia:
            break
        saldo = mes.saldo
    return saldo


def deuda_al(libro: Libro, cuenta_id: str, dia: date | None = None) -> Decimal:
    return a_pesos(max(0, -libro.saldo_centavos(cuenta_id, dia)))


@dataclass(frozen=True, slots=True)
class Proyeccion:
    pago: Decimal                # lo que pagas cada mes en esta proyección
    meses: int | None            # None = con ese pago nunca terminas (no alcanza ni para los intereses)
    intereses: Decimal           # intereses + IVA que pagarías de aquí al final
    fin: date | None
    tabla: list[Mes]

    @property
    def alcanza(self) -> bool:
        return self.meses is not None


def proyectar(libro: Libro, cuenta_id: str, *, pago=None, extra_mensual=0, abono_unico=0,
              hoy: date | None = None) -> Proyeccion:
    """¿Cuándo terminas y cuánto pagas de intereses si desde hoy pagas ``pago`` (o el mensual) + ``extra_mensual``
    cada mes, y abonas ``abono_unico`` hoy?"""
    p = _prestamo(libro, cuenta_id)
    hoy = hoy or libro.hoy()
    deuda = deuda_al(libro, cuenta_id, hoy) - Decimal(str(abono_unico or 0))
    mensual = (Decimal(str(pago)) if pago not in (None, "") else pago_mensual(libro, p)) + Decimal(
        str(extra_mensual or 0))
    if deuda <= 0:
        return Proyeccion(mensual, 0, CERO, hoy, [])
    inicio = _sumar_meses(_siguiente_pago(p, hoy), -1, p.dia_pago)     # así el primer pago es el próximo
    tabla = _simular(libro, p, deuda, mensual, inicio, maximo=MAXIMO_MESES)
    if not tabla or tabla[-1].saldo > 0:
        return Proyeccion(mensual, None, sum((m.interes + m.iva for m in tabla), CERO), None, tabla)
    return Proyeccion(mensual, len(tabla), sum((m.interes + m.iva for m in tabla), CERO), tabla[-1].fecha, tabla)


def pago_para_terminar_en(libro: Libro, cuenta_id: str, meses: int, hoy: date | None = None) -> Decimal:
    """Cuánto pagar al mes para liquidar lo que debes hoy en ``meses``."""
    p = _prestamo(libro, cuenta_id)
    return pago_calculado(deuda_al(libro, cuenta_id, hoy), tasa_mensual(libro, p), max(int(meses), 1))


@dataclass(frozen=True, slots=True)
class Estado:
    deuda: Decimal
    pago_mensual: Decimal
    interes_del_mes: Decimal       # intereses + IVA de un mes sobre lo que debes hoy
    meses_contrato_restantes: int  # lo que falta del plazo contratado
    proyeccion: Proyeccion         # con el pago mensual
    pagado: Decimal                # lo que has pagado (todas las transferencias al préstamo)
    intereses_pagados: Decimal     # intereses, IVA y cargos que se han sumado a la deuda
    proximo_pago: date | None
    sugerencias: list[tuple[str, Proyeccion]]

    @property
    def liquidado(self) -> bool:
        return self.deuda == 0


def estado(libro: Libro, cuenta_id: str, hoy: date | None = None) -> Estado:
    p = _prestamo(libro, cuenta_id)
    hoy = hoy or libro.hoy()
    deuda = deuda_al(libro, cuenta_id, hoy)
    interes, iva = estimar_interes(libro, cuenta_id, hoy)
    transcurridos = _meses_entre(p.fecha_inicio, hoy)
    restantes = max(p.plazo_meses - transcurridos, 0)
    base = proyectar(libro, cuenta_id, hoy=hoy)
    pagado = cargos = 0
    for op in libro.operaciones(hasta=hoy):
        for partida in op.partidas:
            if partida.cuenta_id != cuenta_id:
                continue
            if op.tipo is TipoOperacion.TRANSFERENCIA and partida.importe > 0:
                pagado += partida.importe
            elif op.tipo is TipoOperacion.GASTO:
                cargos -= partida.importe
    sugerencias = []
    if deuda and base.alcanza:
        for nombre, extra in (("+10 % al mes", base.pago * Decimal("0.10")), ("+25 % al mes", base.pago / 4)):
            sugerencias.append((nombre, proyectar(libro, cuenta_id, extra_mensual=extra.quantize(CENTAVO), hoy=hoy)))
    return Estado(deuda, base.pago, interes + iva, restantes, base, a_pesos(pagado), a_pesos(cargos),
                  _proximo_pendiente(libro, p, hoy) if deuda else None, sugerencias)


def pagos_mensuales(libro: Libro, hoy: date | None = None) -> Decimal:
    """Lo que pagas al mes por todos tus préstamos que aún debes (para la capacidad de pago)."""
    total = CERO
    for p in libro.prestamos():
        if libro.cuenta(p.cuenta_id).activa and deuda_al(libro, p.cuenta_id, hoy):
            total += pago_mensual(libro, p)
    return total


def meses_restantes(libro: Libro, cuenta_id: str, hoy: date | None = None) -> int | None:
    """Cuántos meses te faltan con el pago mensual (None si con ese pago no terminas)."""
    return proyectar(libro, cuenta_id, hoy=hoy).meses


# ---------------------------------------------------------------- internos


def _simular(libro: Libro, p: Prestamo, saldo: Decimal, pago: Decimal, desde: date, *, maximo: int) -> list[Mes]:
    tasa = p.tasa_anual / 100 / 12
    iva = iva_de(libro, p) / 100
    tabla = []
    for numero in range(1, maximo + 1):
        interes = (saldo * tasa).quantize(CENTAVO)
        impuesto = (interes * iva).quantize(CENTAVO)
        cuota = min(pago, saldo + interes + impuesto)
        capital = cuota - interes - impuesto
        if 0 < saldo - capital <= 1:                 # centavos de redondeo: se liquidan en este pago
            cuota, capital = saldo + interes + impuesto, saldo
        if capital <= 0 and cuota < saldo + interes + impuesto:
            tabla.append(Mes(numero, _sumar_meses(desde, numero, p.dia_pago), cuota, interes, impuesto, capital,
                             saldo - capital))
            break                                    # no alcanza ni para los intereses: la deuda no baja
        saldo -= capital
        tabla.append(Mes(numero, _sumar_meses(desde, numero, p.dia_pago), cuota, interes, impuesto, capital, saldo))
        if saldo <= 0:
            break
    return tabla


def _sumar_meses(dia: date, meses: int, dia_pago: int | None = None) -> date:
    total = dia.year * 12 + dia.month - 1 + meses
    anio, mes = divmod(total, 12)
    siguiente = date(anio + (mes + 1) // 12, (mes + 1) % 12 + 1, 1)
    ultimo = (siguiente - timedelta(days=1)).day
    return date(anio, mes + 1, min(dia_pago or dia.day, ultimo))


def _meses_entre(inicio: date, fin: date) -> int:
    meses = (fin.year - inicio.year) * 12 + fin.month - inicio.month
    return meses - (1 if fin.day < inicio.day else 0)


def _proximo_pendiente(libro: Libro, p: Prestamo, hoy: date) -> date:
    """El próximo pago que te falta: hoy o después, y si ya lo adelantaste (un pago en los 7 días antes), el
    siguiente. Así Deudas, el Calendario y el Resumen dicen lo mismo."""
    fecha = _siguiente_pago(p, hoy - timedelta(days=1))
    adelantado = any(op.tipo is TipoOperacion.TRANSFERENCIA
                     and any(pa.cuenta_id == p.cuenta_id and pa.importe > 0 for pa in op.partidas)
                     for op in libro.operaciones(fecha - timedelta(days=DIAS_DE_ADELANTO), hoy))
    return _siguiente_pago(p, fecha) if adelantado else fecha


def _siguiente_pago(p: Prestamo, hoy: date) -> date:
    """La fecha del próximo pago (día de pago del contrato, o el día en que empezó)."""
    numero = max(_meses_entre(p.fecha_inicio, hoy), 0)
    while True:
        fecha = _sumar_meses(p.fecha_inicio, numero, p.dia_pago)
        if fecha > hoy or numero > 1200:
            return fecha
        numero += 1


def _datos(clase, monto, tasa_anual, plazo_meses, fecha_inicio, iva, pago_pactado, dia_pago, cat) -> Prestamo:
    centavos = a_centavos(monto)
    if centavos <= 0:
        raise ErrorValidacion("El monto que solicitaste debe ser mayor que cero.")
    tasa = _numero(tasa_anual, "La tasa anual")
    if tasa > 1000:
        raise ErrorValidacion("La tasa es anual, en %: por ejemplo 24 para 24 %.")
    if isinstance(plazo_meses, bool) or not 1 <= int(plazo_meses) <= MAXIMO_MESES:
        raise ErrorValidacion(f"El plazo va de 1 a {MAXIMO_MESES} meses.")
    pactado = a_centavos(pago_pactado) if pago_pactado not in (None, "", 0) else None
    if pactado is not None and pactado <= 0:
        raise ErrorValidacion("El pago pactado debe ser mayor que cero.")
    if dia_pago not in (None, "", 0) and not 1 <= int(dia_pago) <= 31:
        raise ErrorValidacion("El día de pago va de 1 a 31.")
    return Prestamo("", clase, centavos, tasa, int(plazo_meses), fecha_inicio,
                    _numero(iva, "El IVA") if iva not in (None, "") else None, pactado,
                    int(dia_pago) if dia_pago not in (None, "", 0) else None,
                    _numero(cat, "El CAT") if cat not in (None, "", 0) else None)


def _prestamo(libro: Libro, cuenta_id: str) -> Prestamo:
    p = libro.prestamo(cuenta_id)
    if p is None:
        raise ErrorValidacion("Esa cuenta no es un préstamo.")
    return p


def _subcategoria(libro: Libro, nombre: str) -> str:
    encontrada = categorias.buscar(libro, nombre, ClaseCategoria.GASTO)
    if encontrada is None:
        raise ErrorValidacion(f"No encuentro la subcategoría de gasto «{nombre}». Créala en Categorías → Gastos.")
    return encontrada.id


def _numero(valor, que: str) -> Decimal:
    try:
        numero = Decimal(str(valor).replace(",", "").replace("%", "").strip())
    except (InvalidOperation, ValueError):
        raise ErrorValidacion(f"{que}: «{valor}» no es un número.") from None
    if not numero.is_finite() or numero < 0:
        raise ErrorValidacion(f"{que} no puede ser negativo.")
    return numero


def _texto(centavos: int) -> str:
    return formatear(a_pesos(centavos))

