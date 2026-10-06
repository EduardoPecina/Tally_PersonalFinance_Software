"""Tarjetas de crédito: deuda, crédito disponible y ciclos de corte.

Una TDC es una cuenta más. Una compra con ella es un gasto en la fecha de la
compra; pagarla es una transferencia (ver ``motor.transferencias``).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from motor import calendario
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Cuenta, Operacion, TipoCuenta
from motor.movimientos import actualizar_saldo


def deuda(libro: Libro, tarjeta_id: str, al: date | None = None) -> Decimal:
    """Lo que se debe en la tarjeta (0 si tiene saldo a favor)."""
    _tarjeta(libro, tarjeta_id)
    return a_pesos(max(0, -libro.saldo_centavos(tarjeta_id, al)))


def credito_disponible(libro: Libro, tarjeta_id: str, al: date | None = None) -> Decimal | None:
    """Límite + saldo. ``None`` si la tarjeta no tiene límite registrado."""
    tarjeta = _tarjeta(libro, tarjeta_id)
    if tarjeta.limite_credito is None:
        return None
    return a_pesos(tarjeta.limite_credito + libro.saldo_centavos(tarjeta_id, al))


def actualizar_deuda(libro: Libro, tarjeta_id: str, deuda_real, fecha: date) -> Operacion | None:
    """Ajusta la tarjeta para que su deuda en ``fecha`` sea ``deuda_real``."""
    _tarjeta(libro, tarjeta_id)
    return actualizar_saldo(libro, tarjeta_id, -a_pesos(a_centavos(deuda_real)), fecha)


# ------------------------------------------------------------------- ciclos


def _dia_en_mes(anio: int, mes: int, dia: int) -> date:
    """El día indicado del mes, o el último si el mes es más corto."""
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def _mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def _mes_anterior(anio: int, mes: int) -> tuple[int, int]:
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def ciclo_de(fecha: date, dia_corte: int) -> tuple[date, date]:
    """Primer y último día del ciclo que contiene ``fecha``.

    El ciclo termina el día de corte (incluido). Con corte el día 3, el 10 de
    julio pertenece al ciclo 4 jul – 3 ago.
    """
    corte = _dia_en_mes(fecha.year, fecha.month, dia_corte)
    if fecha > corte:
        corte = _dia_en_mes(*_mes_siguiente(fecha.year, fecha.month), dia_corte)
    corte_anterior = _dia_en_mes(*_mes_anterior(corte.year, corte.month), dia_corte)
    return corte_anterior + timedelta(days=1), corte


@dataclass(frozen=True, slots=True)
class ResumenCiclo:
    inicio: date
    fin: date  # día de corte
    fecha_limite_pago: date | None
    saldo_inicial: Decimal  # saldo al cerrar el ciclo anterior (negativo = deuda)
    cargos: Decimal  # compras, comisiones… (positivo)
    abonos: Decimal  # pagos y devoluciones dentro del ciclo (positivo)
    saldo_al_corte: Decimal
    deuda_al_corte: Decimal
    pagado_despues_del_corte: Decimal
    por_liquidar: Decimal  # lo que falta pagar para no generar intereses
    msi_por_vencer: Decimal = Decimal("0.00")  # mensualidades futuras de compras a MSI (no se pagan en este corte)

    @property
    def pago_para_no_generar_intereses(self) -> Decimal:
        """Deuda al corte menos las mensualidades de MSI que aún no vencen."""
        return max(Decimal("0.00"), self.deuda_al_corte - self.msi_por_vencer)


def resumen_ciclo(libro: Libro, tarjeta_id: str, fecha: date | None = None, *, hasta: date | None = None) -> ResumenCiclo:
    """Estado del ciclo de la tarjeta que contiene ``fecha`` (hoy por defecto).

    ``hasta`` limita los pagos posteriores al corte que se toman en cuenta
    para calcular lo que falta por liquidar (hoy por defecto).
    """
    tarjeta = _tarjeta(libro, tarjeta_id)
    if tarjeta.dia_corte is None:
        raise ErrorValidacion(f"La tarjeta «{tarjeta.nombre}» no tiene día de corte registrado.")
    hoy = libro.hoy()
    inicio, fin = ciclo_de(fecha or hoy, tarjeta.dia_corte)
    hasta = hasta or hoy

    cargos = abonos = pagos_posteriores = 0
    for op in libro.operaciones(desde=inicio):
        for p in op.partidas:
            if p.cuenta_id != tarjeta_id:
                continue
            if op.fecha <= fin:
                if p.importe < 0:
                    cargos -= p.importe
                else:
                    abonos += p.importe
            elif op.fecha <= hasta and p.importe > 0:
                pagos_posteriores += p.importe

    saldo_al_corte = libro.saldo_centavos(tarjeta_id, fin)
    deuda_al_corte = max(0, -saldo_al_corte)
    diferido = min(deuda_al_corte, sum(c.restante_centavos for c in _compras_msi(libro, tarjeta, fin)))
    exigible = deuda_al_corte - diferido
    return ResumenCiclo(
        inicio=inicio,
        fin=fin,
        fecha_limite_pago=fecha_limite_pago(tarjeta, fin),
        saldo_inicial=a_pesos(libro.saldo_centavos(tarjeta_id, inicio - timedelta(days=1))),
        cargos=a_pesos(cargos),
        abonos=a_pesos(abonos),
        saldo_al_corte=a_pesos(saldo_al_corte),
        deuda_al_corte=a_pesos(deuda_al_corte),
        pagado_despues_del_corte=a_pesos(pagos_posteriores),
        por_liquidar=a_pesos(max(0, exigible - pagos_posteriores)),
        msi_por_vencer=a_pesos(diferido),
    )


# ------------------------------------------------------- meses sin intereses


@dataclass(frozen=True, slots=True)
class CompraMSI:
    """Una compra a meses sin intereses y cómo va al corte indicado."""

    operacion_id: str
    fecha: date
    descripcion: str
    total: Decimal
    meses: int
    mensualidad: Decimal
    cobradas: int                # mensualidades que ya entraron en algún corte
    restante_centavos: int       # lo que aún no se cobra
    ultima: date | None          # corte en el que entra la última mensualidad

    @property
    def restante(self) -> Decimal:
        return a_pesos(self.restante_centavos)

    @property
    def terminada(self) -> bool:
        return self.cobradas >= self.meses


def _cortes_hasta(fecha: date, dia_corte: int, corte: date) -> int:
    """Cuántos cortes hay desde el que cierra el ciclo de ``fecha`` hasta ``corte`` (incluidos)."""
    _, siguiente = ciclo_de(fecha, dia_corte)
    cuenta = 0
    while siguiente <= corte:
        cuenta += 1
        siguiente = _dia_en_mes(*_mes_siguiente(siguiente.year, siguiente.month), dia_corte)
    return cuenta


def _compras_msi(libro: Libro, tarjeta: Cuenta, corte: date) -> list[CompraMSI]:
    """Compras a MSI hechas hasta ``corte``. Cada corte cobra una mensualidad, empezando por el que cierra el
    ciclo de la compra (la primera mensualidad lleva los centavos que no dividen exacto)."""
    if tarjeta.dia_corte is None:
        return []
    compras = []
    for op in libro.operaciones(hasta=corte):
        if not op.msi:
            continue
        total = -sum(p.importe for p in op.partidas_de_cuenta() if p.cuenta_id == tarjeta.id)
        if total <= 0:
            continue
        base, sobrante = divmod(total, op.msi)
        cobradas = min(op.msi, _cortes_hasta(op.fecha, tarjeta.dia_corte, corte))
        cobrado = base * cobradas + (sobrante if cobradas else 0)
        primera = ciclo_de(op.fecha, tarjeta.dia_corte)[1]
        ultima = primera
        for _ in range(op.msi - 1):
            ultima = _dia_en_mes(*_mes_siguiente(ultima.year, ultima.month), tarjeta.dia_corte)
        compras.append(CompraMSI(op.id, op.fecha, op.descripcion, a_pesos(total), op.msi, a_pesos(base),
                                 cobradas, total - cobrado, ultima))
    return compras


def compras_a_msi(libro: Libro, tarjeta_id: str, hoy: date | None = None, *, incluir_terminadas: bool = False
                  ) -> list[CompraMSI]:
    """Las compras a MSI de la tarjeta, con lo que falta por cobrar a hoy (las vigentes, por omisión)."""
    tarjeta = _tarjeta(libro, tarjeta_id)
    compras = _compras_msi(libro, tarjeta, hoy or libro.hoy())
    return [c for c in compras if incluir_terminadas or not c.terminada]


def ciclo_por_pagar(libro: Libro, tarjeta_id: str, hoy: date | None = None) -> ResumenCiclo | None:
    """El último ciclo ya cortado: el que hay que liquidar. ``None`` si la tarjeta no tiene día de corte."""
    tarjeta = _tarjeta(libro, tarjeta_id)
    if tarjeta.dia_corte is None:
        return None
    hoy = hoy or libro.hoy()
    inicio, fin = ciclo_de(hoy, tarjeta.dia_corte)
    return resumen_ciclo(libro, tarjeta_id, hoy if fin == hoy else inicio - timedelta(days=1), hasta=hoy)


def ciclo_actual(libro: Libro, tarjeta_id: str, hoy: date | None = None) -> ResumenCiclo | None:
    """El ciclo en curso (aún sin cortar). ``None`` si la tarjeta no tiene día de corte."""
    if _tarjeta(libro, tarjeta_id).dia_corte is None:
        return None
    hoy = hoy or libro.hoy()
    return resumen_ciclo(libro, tarjeta_id, hoy, hasta=hoy)


# ------------------------------------------------------------------- estado


AL_CORRIENTE, POR_PAGAR, VENCIDA, SIN_FECHA, SIN_CORTE = "al_corriente", "por_pagar", "vencida", "sin_fecha", "sin_corte"


@dataclass(frozen=True, slots=True)
class EstadoTarjeta:
    """Cómo va una tarjeta hoy: lo que se ve en el estado de cuenta del banco."""

    limite: Decimal | None            # línea de crédito (None si no se registró)
    deuda: Decimal                    # lo que se debe hoy
    saldo_a_favor: Decimal
    disponible: Decimal | None        # línea − deuda + saldo a favor
    uso: Decimal | None               # deuda / línea (0.37 = 37 %); puede pasar de 1 si se excedió
    corte: ResumenCiclo | None        # el último corte (lo que hay que pagar)
    actual: ResumenCiclo | None       # el ciclo en curso
    situacion: str                    # AL_CORRIENTE, POR_PAGAR, VENCIDA, SIN_FECHA o SIN_CORTE
    dias_para_pagar: int | None       # días que faltan para la fecha límite (negativo si ya pasó)

    @property
    def excedida(self) -> bool:
        return self.limite is not None and self.deuda > self.limite


def estado(libro: Libro, tarjeta_id: str, hoy: date | None = None) -> EstadoTarjeta:
    """Línea, deuda, disponible, uso de la línea, último corte y si ya se pagó.

    - **Por pagar** (para no generar intereses): lo que falta de la deuda al último corte.
    - **Vencida**: queda algo por pagar y ya pasó la fecha límite.
    """
    tarjeta = _tarjeta(libro, tarjeta_id)
    hoy = hoy or libro.hoy()
    saldo = libro.saldo_centavos(tarjeta_id, hoy)
    limite = tarjeta.limite_credito
    corte = ciclo_por_pagar(libro, tarjeta_id, hoy)
    actual = ciclo_actual(libro, tarjeta_id, hoy)
    dias = None
    if corte is None:
        situacion = SIN_CORTE
    elif not corte.por_liquidar:
        situacion = AL_CORRIENTE
    elif corte.fecha_limite_pago is None:
        situacion = SIN_FECHA
    else:
        dias = (corte.fecha_limite_pago - hoy).days
        situacion = VENCIDA if dias < 0 else POR_PAGAR
    return EstadoTarjeta(
        limite=a_pesos(limite) if limite is not None else None,
        deuda=a_pesos(max(0, -saldo)),
        saldo_a_favor=a_pesos(max(0, saldo)),
        disponible=a_pesos(limite + saldo) if limite is not None else None,
        uso=(Decimal(max(0, -saldo)) / Decimal(limite)).quantize(Decimal("0.0001")) if limite else None,
        corte=corte,
        actual=actual,
        situacion=situacion,
        dias_para_pagar=dias,
    )


def pagos_proximos(libro: Libro, hoy: date | None = None, dias: int = 5) -> list[tuple[Cuenta, EstadoTarjeta]]:
    """Tarjetas con el pago vencido o que vence en los próximos ``dias`` (para avisar en el Resumen)."""
    hoy = hoy or libro.hoy()
    avisos = []
    for tarjeta in libro.cuentas():
        if tarjeta.tipo is not TipoCuenta.CREDITO or not tarjeta.activa:
            continue
        actual = estado(libro, tarjeta.id, hoy)
        if actual.situacion == VENCIDA or (actual.situacion == POR_PAGAR and actual.dias_para_pagar <= dias):
            avisos.append((tarjeta, actual))
    return sorted(avisos, key=lambda a: a[1].dias_para_pagar)


def describir_regla_pago(tarjeta: Cuenta) -> str:
    """La regla de pago en palabras, p. ej. «10 días naturales después del corte (si es inhábil, el siguiente
    día hábil)». Vacía si la tarjeta no tiene regla."""
    if tarjeta.dias_para_pagar is not None:
        tipo = "hábiles" if tarjeta.dias_habiles else "naturales"
        texto = f"{tarjeta.dias_para_pagar} días {tipo} después del corte"
    elif tarjeta.dia_pago is not None:
        texto = f"el día {tarjeta.dia_pago} de cada mes"
    else:
        return ""
    return texto + (" (si es inhábil, el siguiente día hábil)" if tarjeta.recorrer_inhabil else "")


def fecha_limite_pago(tarjeta: Cuenta, corte: date) -> date | None:
    """Fecha límite para pagar lo del corte, según la regla de la tarjeta.

    - ``dias_para_pagar``: N días después del corte, naturales o hábiles (``dias_habiles``).
      Ej. «hasta 10 días naturales contados a partir de la fecha de corte».
    - ``dia_pago``: un día fijo del mes (el siguiente después del corte).
    - Si ``recorrer_inhabil`` y la fecha cae en sábado, domingo o día inhábil bancario, se recorre al
      siguiente día hábil («se considerará el día hábil siguiente»).

    ``None`` si la tarjeta no tiene regla de pago.
    """
    if tarjeta.dias_para_pagar is not None:
        if tarjeta.dias_habiles:
            limite = calendario.sumar_dias_habiles(corte, tarjeta.dias_para_pagar)
        else:
            limite = corte + timedelta(days=tarjeta.dias_para_pagar)
    elif tarjeta.dia_pago is not None:
        limite = _dia_en_mes(corte.year, corte.month, tarjeta.dia_pago)
        if limite <= corte:
            limite = _dia_en_mes(*_mes_siguiente(corte.year, corte.month), tarjeta.dia_pago)
    else:
        return None
    return calendario.siguiente_habil(limite) if tarjeta.recorrer_inhabil else limite


def _tarjeta(libro: Libro, tarjeta_id: str) -> Cuenta:
    cuenta = libro.cuenta(tarjeta_id)
    if cuenta.tipo is not TipoCuenta.CREDITO:
        raise ErrorValidacion(f"«{cuenta.nombre}» no es una tarjeta de crédito.")
    return cuenta
