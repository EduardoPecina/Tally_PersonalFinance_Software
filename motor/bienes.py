"""Bienes: casa, auto, laptop, muebles… lo que tienes y no es dinero, con su depreciación y su plusvalía.

Un bien es una cuenta de tipo ``BIEN`` más sus datos de valuación (``modelo.Bien``):

- **Costo** = movimientos de la cuenta (fuente de verdad): comprarlo es una transferencia de tu banco (o tarjeta)
  al bien, no un gasto, porque cambias dinero por una cosa y tu patrimonio no baja. Una **mejora** (remodelación,
  motor nuevo) es otra transferencia al bien: sube su costo. Si ya lo tenías, su valor de hoy es su saldo inicial.
- **Depreciación** (lo que pierde con el tiempo) y **avalúos** (lo que vale según el mercado) se **calculan**:
  no se guardan como movimientos, así no llenan tu Historial ni cuentan como gasto en tu Resumen. Aparecen en
  Contabilidad Técnica (Situación financiera, Resultados y Balanza).

Métodos (pensados para una persona, no las tasas fiscales):

- **Línea recta**: pierde lo mismo cada año hasta su valor de rescate. Ej.: una laptop de $25,000, 4 años,
  10 % de rescate, pierde $5,625 al año y al final vale $2,500.
- **Decreciente**: pierde un % de lo que vale cada año, más al principio, como los autos. Nunca baja de su rescate.
- **Ninguna**: casa o terreno; su valor cambia solo con avalúos.

Cada compra o mejora se deprecia desde su fecha. Un **avalúo** fija el valor del bien en su fecha (la diferencia
es plusvalía o minusvalía) y desde ahí se deprecia lo que le queda de vida. Al **venderlo**, la diferencia entre
el precio y su valor ese día es ganancia o pérdida, y la cuenta queda en ceros.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation

from motor import cuentas
from motor.dinero import a_centavos, a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.transferencias import registrar_transferencia
from motor.modelo import (
    CATEGORIA_BIENES,
    Avaluo,
    Bien,
    MetodoDepreciacion,
    Operacion,
    Partida,
    TipoCuenta,
    TipoOperacion,
)

CERO = Decimal(0)
DIAS_ANIO = Decimal("365.25")


@dataclass(frozen=True, slots=True)
class Clase:
    nombre: str
    metodo: MetodoDepreciacion
    vida_anios: Decimal = CERO
    tasa_anual: Decimal = CERO
    rescate: Decimal = CERO
    ayuda: str = ""


# Valores sugeridos para una persona (no fiscales). El usuario los puede cambiar en cada bien.
CLASES: dict[str, Clase] = {
    "auto": Clase("Auto o moto", MetodoDepreciacion.DECRECIENTE, tasa_anual=Decimal(15), rescate=Decimal(10),
                  ayuda="Un auto pierde cerca de 15 % de su valor cada año, más al principio."),
    "computadora": Clase("Computadora o laptop", MetodoDepreciacion.LINEA_RECTA, Decimal(4), rescate=Decimal(10)),
    "celular": Clase("Celular o tablet", MetodoDepreciacion.LINEA_RECTA, Decimal(3), rescate=Decimal(10)),
    "electronica": Clase("Electrodomésticos y electrónica", MetodoDepreciacion.LINEA_RECTA, Decimal(7),
                         rescate=Decimal(5)),
    "muebles": Clase("Muebles", MetodoDepreciacion.LINEA_RECTA, Decimal(10), rescate=Decimal(10)),
    "casa": Clase("Casa o departamento", MetodoDepreciacion.NINGUNA,
                  ayuda="No se deprecia: registra avalúos para ver su plusvalía. Las remodelaciones son mejoras."),
    "terreno": Clase("Terreno", MetodoDepreciacion.NINGUNA, ayuda="No se deprecia: registra avalúos."),
    "otro": Clase("Otro", MetodoDepreciacion.LINEA_RECTA, Decimal(5)),
}
METODOS = {MetodoDepreciacion.LINEA_RECTA: "Línea recta (pierde lo mismo cada año)",
           MetodoDepreciacion.DECRECIENTE: "Decreciente (pierde un % de lo que vale cada año)",
           MetodoDepreciacion.NINGUNA: "No se deprecia (casa, terreno)"}


# ------------------------------------------------------------------ registrar


def crear(libro: Libro, nombre: str, clase: str, fecha: date, valor, *, cuenta_pago: str | None = None,
          descripcion: str = "") -> Bien:
    """Un bien nuevo. Con ``cuenta_pago`` lo **compraste** ese día con esa cuenta (transferencia); sin ella, **ya
    lo tenías** y ``valor`` es lo que vale hoy (su saldo inicial: patrimonio)."""
    if clase not in CLASES:
        raise ErrorValidacion("Elige qué tipo de bien es.")
    if a_centavos(valor) <= 0:
        raise ErrorValidacion("El valor del bien debe ser mayor que cero.")
    sugerido = CLASES[clase]
    cuenta = cuentas.crear(libro, nombre, TipoCuenta.BIEN, fecha_creacion=fecha, en_disponible=False,
                           **({} if cuenta_pago else {"saldo_inicial": valor, "fecha_saldo_inicial": fecha}))
    bien = libro.guardar_bien(Bien(cuenta.id, clase, sugerido.metodo, sugerido.vida_anios, sugerido.tasa_anual,
                                   sugerido.rescate))
    if cuenta_pago:
        _transferir(libro, fecha, cuenta_pago, cuenta.id, valor, descripcion or f"Compra de {cuenta.nombre}")
    return bien


def crear_desde_gasto(libro: Libro, operacion_id: str, nombre: str, clase: str) -> Operacion:
    """Un bien nuevo a partir de un gasto que fue su compra (ver :func:`convertir_gasto`)."""
    if clase not in CLASES:
        raise ErrorValidacion("Elige qué tipo de bien es.")
    op = libro.operacion(operacion_id)
    sugerido = CLASES[clase]
    cuenta = cuentas.crear(libro, nombre, TipoCuenta.BIEN, fecha_creacion=op.fecha, en_disponible=False)
    libro.guardar_bien(Bien(cuenta.id, clase, sugerido.metodo, sugerido.vida_anios, sugerido.tasa_anual,
                            sugerido.rescate))
    return convertir_gasto(libro, operacion_id, cuenta.id)


def configurar(libro: Libro, cuenta_id: str, *, metodo=None, vida_anios=None, tasa_anual=None, rescate=None,
               clase: str | None = None) -> Bien:
    """Cambia cómo se deprecia (todo se recalcula: no hay movimientos que corregir)."""
    bien = _bien(libro, cuenta_id)
    nuevo = replace(
        bien,
        clase=clase if clase in CLASES else bien.clase,
        metodo=MetodoDepreciacion(metodo) if metodo is not None else bien.metodo,
        vida_anios=_numero(vida_anios, "La vida útil") if vida_anios is not None else bien.vida_anios,
        tasa_anual=_numero(tasa_anual, "El % anual") if tasa_anual is not None else bien.tasa_anual,
        rescate=_numero(rescate, "El % de rescate") if rescate is not None else bien.rescate,
    )
    if nuevo.metodo is MetodoDepreciacion.LINEA_RECTA and not 0 < nuevo.vida_anios <= 100:
        raise ErrorValidacion("La vida útil va de más de 0 a 100 años.")
    if nuevo.metodo is MetodoDepreciacion.DECRECIENTE and not 0 < nuevo.tasa_anual < 100:
        raise ErrorValidacion("El % que pierde cada año va de más de 0 a menos de 100.")
    if not 0 <= nuevo.rescate < 100:
        raise ErrorValidacion("El % de rescate va de 0 a menos de 100.")
    return libro.guardar_bien(nuevo)


def registrar_mejora(libro: Libro, cuenta_id: str, fecha: date, monto, cuenta_pago: str,
                     descripcion: str = "") -> Operacion:
    """Remodelación, motor nuevo, ampliación…: sube el valor del bien (no es gasto)."""
    bien = _activo(libro, cuenta_id)
    return _transferir(libro, fecha, cuenta_pago, bien.cuenta_id, monto,
                       descripcion or f"Mejora a {libro.cuenta(cuenta_id).nombre}")


def registrar_avaluo(libro: Libro, cuenta_id: str, fecha: date, valor) -> Bien:
    """El bien vale ``valor`` en ``fecha`` según un avalúo o el mercado. La diferencia es plusvalía (o minusvalía)."""
    bien = _activo(libro, cuenta_id)
    centavos = a_centavos(valor)
    if centavos < 0:
        raise ErrorValidacion("El valor del avalúo no puede ser negativo.")
    if fecha > libro.hoy():
        raise ErrorValidacion("La fecha del avalúo no puede ser futura.")
    if fecha < libro.cuenta(cuenta_id).fecha_creacion:
        raise ErrorValidacion("El avalúo no puede ser de antes de que tuvieras el bien.")
    avaluos = tuple(sorted([*(a for a in bien.avaluos if a.fecha != fecha), Avaluo(fecha, centavos)],
                           key=lambda a: a.fecha))
    return libro.guardar_bien(replace(bien, avaluos=avaluos))


def quitar_avaluo(libro: Libro, cuenta_id: str, fecha: date) -> Bien:
    bien = _activo(libro, cuenta_id)
    return libro.guardar_bien(replace(bien, avaluos=tuple(a for a in bien.avaluos if a.fecha != fecha)))


def vender(libro: Libro, cuenta_id: str, fecha: date, precio, cuenta_destino: str | None = None) -> Bien:
    """Lo vendiste en ``precio`` (0 = lo tiraste, lo regalaste o se perdió). El dinero llega a ``cuenta_destino``;
    la diferencia contra su valor ese día es ganancia o pérdida, y la cuenta del bien queda en ceros."""
    bien = _activo(libro, cuenta_id)
    precio_centavos = a_centavos(precio)
    if precio_centavos < 0:
        raise ErrorValidacion("El precio de venta no puede ser negativo.")
    if precio_centavos and not cuenta_destino:
        raise ErrorValidacion("Elige a qué cuenta llegó el dinero de la venta.")
    if fecha > libro.hoy():
        raise ErrorValidacion("La fecha de venta no puede ser futura.")
    if any(op.fecha > fecha and any(p.cuenta_id == cuenta_id for p in op.partidas) for op in libro.operaciones()):
        raise ErrorValidacion("El bien tiene movimientos después de esa fecha; la venta debe ser la última.")
    nombre = libro.cuenta(cuenta_id).nombre
    valor = a_centavos(valuar(libro, cuenta_id, fecha).valor)
    ids = []
    if precio_centavos:
        ids.append(_transferir(libro, fecha, cuenta_id, cuenta_destino, a_pesos(precio_centavos),
                               f"Venta de {nombre}").id)
    resultado = valor - precio_centavos              # lo que falta sacar de la cuenta: pérdida (+) o ganancia (−)
    if resultado:
        op = libro.agregar_operacion(Operacion(
            fecha=fecha, tipo=TipoOperacion.AJUSTE,
            partidas=(Partida(-resultado, cuenta_id=cuenta_id), Partida(resultado, categoria_id=CATEGORIA_BIENES)),
            descripcion=f"{'Pérdida' if resultado > 0 else 'Ganancia'} al vender {nombre}"))
        ids.append(op.id)
    return libro.guardar_bien(replace(bien, fecha_baja=fecha, operaciones_baja=tuple(ids)))


def deshacer_venta(libro: Libro, cuenta_id: str) -> Bien:
    bien = _bien(libro, cuenta_id)
    if bien.fecha_baja is None:
        raise ErrorValidacion("Este bien no está vendido.")
    for op_id in bien.operaciones_baja:
        if any(op.id == op_id for op in libro.operaciones()):
            libro.eliminar_operacion(op_id)
    return libro.guardar_bien(replace(bien, fecha_baja=None, operaciones_baja=()))


def convertir_gasto(libro: Libro, operacion_id: str, cuenta_id: str) -> Operacion:
    """Un gasto que en realidad fue la compra (o mejora) de un bien: se vuelve transferencia de la misma cuenta
    al bien, con la misma fecha y descripción. Deja de contar como gasto y sube el valor del bien."""
    op = libro.operacion(operacion_id)
    if op.tipo is not TipoOperacion.GASTO:
        raise ErrorValidacion("Solo un gasto se puede convertir en un bien.")
    if op.msi:
        raise ErrorValidacion("Es una compra a meses sin intereses: quítale los meses antes de convertirla.")
    if op.liquida:
        raise ErrorValidacion("Este gasto cierra un cargo temporal; no se puede convertir en un bien.")
    (pago,) = op.partidas_de_cuenta()
    _activo(libro, cuenta_id)
    nueva = replace(op, tipo=TipoOperacion.TRANSFERENCIA, liquida="",
                    partidas=(Partida(pago.importe, cuenta_id=pago.cuenta_id),
                              Partida(-pago.importe, cuenta_id=cuenta_id)))
    return libro.reemplazar_operacion(operacion_id, nueva)


# ------------------------------------------------------------------ valuar


@dataclass(frozen=True, slots=True)
class Valuacion:
    costo: Decimal              # lo que pagaste (compra + mejoras), en pesos
    depreciacion: Decimal       # lo que ha perdido con el tiempo (acumulado)
    revaluacion: Decimal        # plusvalía (+) o minusvalía (−) por avalúos (acumulado)

    @property
    def valor(self) -> Decimal:
        """Lo que vale hoy: costo − depreciación ± avalúos."""
        return self.costo - self.depreciacion + self.revaluacion


@dataclass(slots=True)
class _Capa:
    inicio: date
    base: Decimal
    rescate: Decimal
    vida: Decimal

    def depreciacion(self, bien: Bien, dia: date) -> Decimal:
        anios = Decimal(max((dia - self.inicio).days, 0)) / DIAS_ANIO
        depreciable = max(self.base - self.rescate, CERO)
        if bien.metodo is MetodoDepreciacion.LINEA_RECTA:
            if self.vida <= 0:
                return CERO
            return min(depreciable * anios / self.vida, depreciable)
        if bien.metodo is MetodoDepreciacion.DECRECIENTE and self.base > 0:
            restante = self.base * (1 - bien.tasa_anual / 100) ** anios
            return self.base - max(restante, self.rescate)
        return CERO


def valuar(libro: Libro, cuenta_id: str, dia: date) -> Valuacion:
    """Costo, depreciación y avalúos del bien al final de ``dia``."""
    bien = _bien(libro, cuenta_id)
    costo = a_pesos(libro.saldo_centavos(cuenta_id, dia))
    eventos = []                        # (fecha, orden, tipo, importe): compras/mejoras antes que avalúos del día
    for op in libro.operaciones(hasta=dia):
        if op.id in bien.operaciones_baja:
            continue
        entrada = sum(p.importe for p in op.partidas if p.cuenta_id == cuenta_id)
        if entrada > 0:
            eventos.append((op.fecha, 0, "costo", a_pesos(entrada)))
    eventos += [(a.fecha, 1, "avaluo", a_pesos(a.valor)) for a in bien.avaluos if a.fecha <= dia]
    if bien.fecha_baja and bien.fecha_baja <= dia:
        eventos.append((bien.fecha_baja, 2, "baja", CERO))
    eventos.sort(key=lambda e: (e[0], e[1]))

    capas: list[_Capa] = []
    congelada = revaluacion = CERO
    primera: date | None = None
    for fecha, _, tipo, importe in eventos:
        if tipo == "costo":
            primera = primera or fecha
            capas.append(_Capa(fecha, importe, importe * bien.rescate / 100, bien.vida_anios))
            continue
        hasta_hoy = sum((c.depreciacion(bien, fecha) for c in capas), CERO)
        congelada += hasta_hoy
        if tipo == "baja":
            capas = []
            break
        valor_antes = sum((c.base for c in capas), CERO) - hasta_hoy
        revaluacion += importe - valor_antes
        usados = Decimal((fecha - (primera or fecha)).days) / DIAS_ANIO
        capas = [_Capa(fecha, importe, importe * bien.rescate / 100, max(bien.vida_anios - usados, CERO))]
    depreciacion = congelada + sum((c.depreciacion(bien, dia) for c in capas), CERO)
    centavo = Decimal("0.01")
    return Valuacion(costo, depreciacion.quantize(centavo), revaluacion.quantize(centavo))


def ajuste_de_valor(libro: Libro, dia: date) -> int:
    """Centavos que la depreciación y los avalúos de todos los bienes suman (o restan) a tu patrimonio a ``dia``."""
    total = 0
    for bien in libro.bienes():
        v = valuar(libro, bien.cuenta_id, dia)
        total += a_centavos(v.revaluacion) - a_centavos(v.depreciacion)
    return total


# ---------------------------------------------------------------- internos


def _bien(libro: Libro, cuenta_id: str) -> Bien:
    bien = libro.bien(cuenta_id)
    if bien is None:
        raise ErrorValidacion("Esa cuenta no es un bien.")
    return bien


def _activo(libro: Libro, cuenta_id: str) -> Bien:
    bien = _bien(libro, cuenta_id)
    if bien.fecha_baja is not None:
        raise ErrorValidacion(f"«{libro.cuenta(cuenta_id).nombre}» ya se vendió; deshaz la venta para cambiarlo.")
    if not libro.cuenta(cuenta_id).activa:
        raise ErrorValidacion(f"«{libro.cuenta(cuenta_id).nombre}» está eliminado; restáuralo para cambiarlo.")
    return bien


def _transferir(libro: Libro, fecha: date, origen: str, destino: str, monto, descripcion: str) -> Operacion:
    return registrar_transferencia(libro, fecha, origen, destino, monto, descripcion)


def _numero(valor, que: str) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErrorValidacion(f"{que}: «{valor}» no es un número.") from None
    if not numero.is_finite() or numero < 0:
        raise ErrorValidacion(f"{que} no puede ser negativo.")
    return numero
