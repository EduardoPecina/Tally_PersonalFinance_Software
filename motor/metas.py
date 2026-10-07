"""Metas de ahorro y el fondo de emergencia.

- Una **meta** tiene un objetivo, opcionalmente una fecha y la cuenta donde guardas ese dinero. Lo ahorrado es la
  suma de sus aportes (y retiros). Al aportar desde otra cuenta, TALLY registra la transferencia a la cuenta de la
  meta: lo que dice la meta y lo que hay en la cuenta no se separan.
- **Cómo vas**: cuánto falta, cuánto apartar al mes para llegar a tiempo y, a tu ritmo de los últimos 3 meses,
  cuándo la logras.
- **Fondo de emergencia**: una meta especial (solo una) para imprevistos. Lo recomendable es tener de 3 a 6 meses de
  tus gastos esenciales: lo que clasificaste como Necesidad y Compromisos, más los pagos de tus préstamos.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from motor import planeacion, prestamos
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Aporte, ClaseCategoria, Meta, TipoCuenta
from motor.textos import normalizar_nombre
from motor.transferencias import registrar_transferencia

CERO = Decimal("0.00")
GRUPOS_ESENCIALES = ("Necesidad", "Compromisos")
MESES_FONDO = (3, 6)                  # lo recomendable: de 3 a 6 meses de gastos esenciales
MESES_RITMO = 3
INICIAL = "inicial"                   # lo que ya tenías al crear la meta: no cuenta en tu ritmo


# ===================================================================== crear, editar, borrar


def crear(libro: Libro, nombre: str, objetivo, *, cuenta_id: str | None = None, fecha_limite: date | None = None,
          emergencia: bool = False, ya_tengo=0, notas: str = "") -> Meta:
    """Una meta nueva. ``ya_tengo``: lo que ya tienes apartado para ella (no mueve dinero)."""
    hoy = libro.hoy()
    meta = Meta(libro.nuevo_id(), nombre, _positivo(objetivo, "El objetivo"), cuenta_id, fecha_limite, emergencia,
                creada=hoy, notas=notas)
    inicial = a_centavos(ya_tengo or 0)
    if inicial < 0:
        raise ErrorValidacion("Lo que ya tienes no puede ser negativo.")
    if inicial:
        meta = replace(meta, aportes=(Aporte(hoy, inicial, INICIAL),))
    return libro.guardar_meta(_validar(libro, meta))


def editar(libro: Libro, meta_id: str, **cambios) -> Meta:
    if "objetivo" in cambios:
        cambios["objetivo"] = _positivo(cambios["objetivo"], "El objetivo")
    return libro.guardar_meta(_validar(libro, replace(libro.meta(meta_id), **cambios)))


def eliminar(libro: Libro, meta_id: str) -> None:
    """Borra la meta. Las transferencias que hiciste no se borran: el dinero sigue en su cuenta."""
    libro.quitar_meta(meta_id)


def _positivo(monto, que: str) -> int:
    centavos = a_centavos(monto)
    if centavos <= 0:
        raise ErrorValidacion(f"{que} debe ser mayor que cero.")
    return centavos


def _validar(libro: Libro, m: Meta) -> Meta:
    m = replace(m, nombre=normalizar_nombre(m.nombre), notas=m.notas.strip())
    if m.cuenta_id is not None:
        cuenta = libro.cuenta(m.cuenta_id)
        if cuenta.tipo in (TipoCuenta.CREDITO, TipoCuenta.PRESTAMO, TipoCuenta.BIEN):
            raise ErrorValidacion("Guarda el dinero de tu meta en una cuenta de débito, ahorro, inversión o efectivo.")
    if m.emergencia and any(o.emergencia and o.id != m.id for o in libro.metas()):
        raise ErrorValidacion("Ya tienes un fondo de emergencia: solo puede haber uno.")
    if any(o.nombre.casefold() == m.nombre.casefold() and o.id != m.id for o in libro.metas()):
        raise ErrorValidacion(f"Ya tienes una meta llamada «{m.nombre}».")
    return m


# ===================================================================== aportar y retirar


def aportar(libro: Libro, meta_id: str, monto, fecha: date | None = None, *, desde: str | None = None) -> Meta:
    """Suma a la meta. Con ``desde`` (otra cuenta tuya) se registra la transferencia a la cuenta de la meta."""
    meta = libro.meta(meta_id)
    centavos = _positivo(monto, "El aporte")
    fecha = fecha or libro.hoy()
    operacion = ""
    if desde and meta.cuenta_id and desde != meta.cuenta_id:
        op = registrar_transferencia(libro, fecha, desde, meta.cuenta_id, a_pesos(centavos),
                                     f"Aporte a la meta «{meta.nombre}»")
        operacion = op.id
    return libro.guardar_meta(replace(meta, aportes=(*meta.aportes, Aporte(fecha, centavos, operacion))))


def retirar(libro: Libro, meta_id: str, monto, fecha: date | None = None, *, hacia: str | None = None) -> Meta:
    """Saca de la meta (para usarlo). Con ``hacia`` se registra la transferencia desde la cuenta de la meta."""
    meta = libro.meta(meta_id)
    centavos = _positivo(monto, "Lo que retiras")
    if centavos > ahorrado(meta):
        raise ErrorValidacion(f"En «{meta.nombre}» solo tienes {_texto(ahorrado(meta))}.")
    fecha = fecha or libro.hoy()
    operacion = ""
    if hacia and meta.cuenta_id and hacia != meta.cuenta_id:
        op = registrar_transferencia(libro, fecha, meta.cuenta_id, hacia, a_pesos(centavos),
                                     f"Retiro de la meta «{meta.nombre}»")
        operacion = op.id
    return libro.guardar_meta(replace(meta, aportes=(*meta.aportes, Aporte(fecha, -centavos, operacion))))


def _texto(centavos: int) -> str:
    return f"${a_pesos(centavos):,.2f}"


# ===================================================================== cómo vas


def ahorrado(meta: Meta) -> int:
    return sum(a.centavos for a in meta.aportes)


@dataclass(frozen=True, slots=True)
class Estado:
    ahorrado: Decimal
    falta: Decimal
    porcentaje: int                     # 0 a 100
    lograda: bool
    meses_restantes: int | None         # hasta la fecha límite (None si no tiene)
    por_mes: Decimal | None             # lo que hay que apartar al mes para llegar a tiempo
    ritmo: Decimal                      # lo que has apartado en promedio al mes (últimos 3 meses)
    fecha_estimada: date | None         # a ese ritmo, cuándo la logras
    a_tiempo: bool | None               # ¿a tu ritmo llegas antes de la fecha límite?


def estado(meta: Meta, hoy: date) -> Estado:
    junto = ahorrado(meta)
    falta = max(meta.objetivo - junto, 0)
    porcentaje = min(100, int(junto * 100 // meta.objetivo)) if meta.objetivo else 0
    meses = None
    por_mes = None
    if meta.fecha_limite is not None and falta:
        meses = max(1, (meta.fecha_limite.year - hoy.year) * 12 + meta.fecha_limite.month - hoy.month)
        por_mes = (a_pesos(falta) / meses).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    desde = hoy - timedelta(days=30 * MESES_RITMO)
    reciente = sum(a.centavos for a in meta.aportes if a.fecha > desde and a.operacion_id != INICIAL)
    inicio = max(meta.creada or hoy, desde)
    meses_ritmo = max(Decimal(1), Decimal((hoy - inicio).days) / 30)
    ritmo = max(CERO, (a_pesos(reciente) / meses_ritmo).quantize(Decimal("0.01")))
    fecha = None
    if falta and ritmo > 0:
        fecha = hoy + timedelta(days=int((a_pesos(falta) / ritmo * 30).to_integral_value(rounding=ROUND_CEILING)))
    a_tiempo = None
    if meta.fecha_limite is not None and falta:
        a_tiempo = fecha is not None and fecha <= meta.fecha_limite
    return Estado(a_pesos(junto), a_pesos(falta), porcentaje, falta == 0, meses, por_mes, ritmo, fecha, a_tiempo)


@dataclass(frozen=True, slots=True)
class Cuenta:
    cuenta_id: str
    apartado: Decimal                   # lo que tus metas dicen que hay en esa cuenta
    saldo: Decimal                      # lo que realmente hay
    libre: Decimal                      # saldo − apartado (negativo: a tus metas les falta dinero ahí)


def por_cuenta(libro: Libro, hoy: date | None = None) -> list[Cuenta]:
    """Cuánto de cada cuenta está apartado para tus metas, y si alcanza."""
    hoy = hoy or libro.hoy()
    apartado: dict[str, int] = defaultdict(int)
    for m in libro.metas():
        if m.activa and m.cuenta_id:
            apartado[m.cuenta_id] += ahorrado(m)
    resultado = []
    for cuenta_id, centavos in apartado.items():
        saldo = libro.saldo_centavos(cuenta_id, hoy)
        resultado.append(Cuenta(cuenta_id, a_pesos(centavos), a_pesos(saldo), a_pesos(saldo - centavos)))
    return resultado


# ===================================================================== fondo de emergencia


@dataclass(frozen=True, slots=True)
class Fondo:
    esencial_al_mes: Decimal            # gastos esenciales + pagos de préstamos, al mes
    recomendado_minimo: Decimal         # 3 meses
    recomendado_ideal: Decimal          # 6 meses
    meses_cubiertos: Decimal | None     # con lo que tienes en tu fondo (None si no hay fondo o gasto)
    meta: Meta | None


def gasto_esencial(libro: Libro, hoy: date | None = None) -> Decimal:
    """Lo que gastas al mes en lo indispensable (promedio de los últimos 3 meses completos): las subcategorías
    clasificadas como Necesidad y Compromisos, más los pagos de tus préstamos."""
    hoy = hoy or libro.hoy()
    meses = planeacion._meses_con_datos(libro, planeacion.meses_completos(hoy))
    grupos = {g.id for g in libro.grupos() if g.nombre in GRUPOS_ESENCIALES}
    excluir = {c.id for c in libro.categorias() if c.nombre == prestamos.SUBCATEGORIA_INTERESES}
    total = 0
    if meses:
        for op in libro.operaciones(meses[0][0], meses[-1][1]):
            for p in op.partidas_de_categoria():
                categoria = libro.categoria(p.categoria_id)
                if (categoria.clase is ClaseCategoria.GASTO and categoria.grupo_id in grupos
                        and p.categoria_id not in excluir):
                    total += p.importe
        total = total / len(meses)
    return (a_pesos(int(total)) + prestamos.pagos_mensuales(libro, hoy)).quantize(Decimal("0.01"))


def fondo(libro: Libro, hoy: date | None = None) -> Fondo:
    hoy = hoy or libro.hoy()
    esencial = gasto_esencial(libro, hoy)
    meta = next((m for m in libro.metas() if m.emergencia and m.activa), None)
    cubiertos = None
    if meta is not None and esencial > 0:
        cubiertos = (a_pesos(ahorrado(meta)) / esencial).quantize(Decimal("0.1"))
    return Fondo(esencial, (esencial * MESES_FONDO[0]).quantize(Decimal("1"), rounding=ROUND_CEILING),
                 (esencial * MESES_FONDO[1]).quantize(Decimal("1"), rounding=ROUND_CEILING), cubiertos, meta)


def totales(libro: Libro) -> tuple[Decimal, Decimal]:
    """(ahorrado, objetivo) de tus metas activas."""
    activas = [m for m in libro.metas() if m.activa]
    return (a_pesos(sum(ahorrado(m) for m in activas)), a_pesos(sum(m.objetivo for m in activas)))
