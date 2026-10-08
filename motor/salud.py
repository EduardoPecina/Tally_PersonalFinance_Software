"""Revisión de salud de tus datos: lo que probablemente está mal o incompleto, para que tus reportes digan la verdad.

No cambia nada por su cuenta. Cada hallazgo dice qué pasa, por qué importa y dónde se arregla. Si algo está bien
así (dos cafés iguales el mismo día, una cuenta que de verdad está en negativo), lo marcas como «Está bien así» y
ya no vuelve a salir (se guarda en tu perfil; puedes volver a mostrar todo).

Qué revisa:

- 🔴 **Datos que no cuadran** (``serializacion.verificar_integridad``): nunca debería pasar; restaura un respaldo.
- 🟠 **Por revisar**: movimientos que parecen **duplicados**; cuentas de débito, ahorro o efectivo **en negativo**;
  tarjetas **pasadas de su límite**; **fechas** muy adelante o muy atrás; cargos temporales que **no te han
  devuelto**.
- 🔵 **Para mejorar**: movimientos en OTROS GASTOS / OTROS INGRESOS o **sin descripción**; tarjetas **sin día de
  corte o sin tasa**; préstamos sin sus datos; cuentas **sin movimientos** hace meses; tus **reglas** que dicen otra
  subcategoría; deducibles del año **sin comprobante**.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from motor import categorias, temporales
from motor.consultas import ETIQUETA_TIPO_CUENTA
from motor.dinero import a_pesos, formatear
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import Operacion, TipoCuenta, TipoOperacion

ERROR, REVISAR, MEJORAR = "error", "revisar", "mejorar"
NIVELES = {ERROR: ("🔴", "No cuadra"), REVISAR: ("🟠", "Por revisar"), MEJORAR: ("🔵", "Para mejorar")}
DIAS_DUPLICADO = 3               # dos movimientos iguales a lo más con estos días de diferencia
DIAS_ADELANTE = 31
ANIOS_ATRAS = 15
DIAS_SIN_USO = 120
SIN_NEGATIVO = (TipoCuenta.DEBITO, TipoCuenta.AHORRO, TipoCuenta.EFECTIVO)
GENERICAS = ("OTROS GASTOS", "OTROS INGRESOS")


@dataclass(frozen=True, slots=True)
class Hallazgo:
    clave: str                   # estable: para marcarlo como «Está bien así»
    nivel: str                   # ERROR, REVISAR o MEJORAR
    titulo: str
    detalle: str
    pagina: str = ""             # dónde se arregla (portal/navegacion.py)
    operaciones: tuple[str, ...] = ()
    cuantos: int = 0             # para los que agrupan muchos movimientos
    se_puede_ignorar: bool = True


@dataclass(frozen=True, slots=True)
class Revision:
    hallazgos: list[Hallazgo]
    ignorados: int = 0
    revisados: dict[str, int] = field(default_factory=dict)

    def por_nivel(self, nivel: str) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.nivel == nivel]

    @property
    def importantes(self) -> int:
        """Cuántos son 🔴 o 🟠 (los que se avisan en el Resumen)."""
        return sum(h.nivel in (ERROR, REVISAR) for h in self.hallazgos)


def revisar(libro: Libro, hoy: date | None = None, *, incluir_ignorados: bool = False) -> Revision:
    hoy = hoy or libro.hoy()
    hallazgos = [
        *_integridad(libro), *_duplicados(libro), *_negativos(libro, hoy), *_limites(libro, hoy),
        *_fechas(libro, hoy), *_temporales(libro, hoy), *_retiros(libro), *_genericas(libro), *_sin_descripcion(libro),
        *_tarjetas_incompletas(libro), *_prestamos_sin_datos(libro), *_sin_uso(libro, hoy), *_reglas(libro),
        *_deducibles(libro, hoy),
    ]
    ignorados = set(libro.perfil.salud_ignorados) if libro.perfil else set()
    visibles = [h for h in hallazgos if incluir_ignorados or not (h.se_puede_ignorar and h.clave in ignorados)]
    orden = {ERROR: 0, REVISAR: 1, MEJORAR: 2}
    visibles.sort(key=lambda h: (orden[h.nivel], h.titulo))
    revisados = {"movimientos": len(libro.operaciones()), "cuentas": len(libro.cuentas())}
    return Revision(visibles, len(hallazgos) - len(visibles), revisados)


def ignorar(libro: Libro, clave: str) -> None:
    """«Está bien así»: ese hallazgo ya no se muestra."""
    if libro.perfil is None:
        raise ErrorValidacion("Primero escribe tu nombre en la bienvenida.")
    if clave not in libro.perfil.salud_ignorados:
        libro.perfil = replace(libro.perfil, salud_ignorados=(*libro.perfil.salud_ignorados, clave)[-500:])


def mostrar_todo(libro: Libro) -> None:
    """Vuelve a mostrar lo que marcaste como «Está bien así»."""
    if libro.perfil is not None:
        libro.perfil = replace(libro.perfil, salud_ignorados=())


# ------------------------------------------------------------------ las revisiones


def _integridad(libro: Libro) -> list[Hallazgo]:
    from motor.serializacion import verificar_integridad

    problemas = verificar_integridad(libro)
    if not problemas:
        return []
    return [Hallazgo("integridad", ERROR, "Hay datos que no cuadran",
                     "; ".join(problemas[:5]) + ". Restaura tu respaldo más reciente (Respaldos y bitácora).",
                     "respaldos", se_puede_ignorar=False)]


def _firma(op: Operacion) -> tuple:
    return (op.tipo, tuple(sorted((p.cuenta_id or "", p.importe) for p in op.partidas_de_cuenta())))


def _parecidas(a: Operacion, b: Operacion) -> bool:
    from motor.bancos import nucleo

    if a.descripcion.strip().upper() == b.descripcion.strip().upper():
        return True
    pa, pb = set(nucleo(a.descripcion)), set(nucleo(b.descripcion))
    return bool(pa and pb and (pa & pb) and len(pa & pb) * 2 >= min(len(pa), len(pb)))


def _duplicados(libro: Libro) -> list[Hallazgo]:
    """Mismo tipo, mismas cuentas e importes, a lo más 3 días y descripción igual o casi igual."""
    grupos: dict[tuple, list[Operacion]] = defaultdict(list)
    for op in libro.operaciones():
        if op.tipo not in (TipoOperacion.SALDO_INICIAL, TipoOperacion.AJUSTE):
            grupos[_firma(op)].append(op)
    hallazgos = []
    nombres = {c.id: c.nombre for c in libro.cuentas()}
    for lista in grupos.values():
        for i, a in enumerate(lista):                              # en orden de fecha (como los da el libro)
            for b in lista[i + 1:]:
                if (b.fecha - a.fecha).days > DIAS_DUPLICADO:
                    break
                if not _parecidas(a, b):
                    continue
                cuenta = nombres.get(a.partidas_de_cuenta()[0].cuenta_id, "")
                importe = formatear(a_pesos(max(abs(p.importe) for p in a.partidas_de_cuenta())))
                cuando = (f"el {a.fecha:%d/%m/%Y}" if a.fecha == b.fecha
                          else f"el {a.fecha:%d/%m/%Y} y el {b.fecha:%d/%m/%Y}")
                hallazgos.append(Hallazgo(
                    f"duplicado:{a.id}:{b.id}", REVISAR, "Movimientos que parecen duplicados",
                    f"«{a.descripcion or 'sin descripción'}» por {importe} en {cuenta}, {cuando}. Si lo registraste "
                    "dos veces, borra uno en el Historial; si de verdad fueron dos, marca «Está bien así».",
                    "historial", (a.id, b.id)))
    return hallazgos


def _negativos(libro: Libro, hoy: date) -> list[Hallazgo]:
    from motor import cuentas

    hallazgos = []
    for c in libro.cuentas():
        if c.activa and c.tipo in SIN_NEGATIVO:
            saldo = cuentas.saldo(libro, c.id, hoy)
            if saldo < 0:
                hallazgos.append(Hallazgo(
                    f"negativo:{c.id}:{hoy:%Y-%m}", REVISAR, "Cuentas en negativo",
                    f"«{c.nombre}» tiene {formatear(saldo)} hoy. Una cuenta de "
                    f"{ETIQUETA_TIPO_CUENTA.get(c.tipo, c.tipo.value).lower()} casi nunca queda en negativo: ¿falta registrar un ingreso o una transferencia, o un gasto se fue a la cuenta "
                    "equivocada?", "cuentas"))
    return hallazgos


def _limites(libro: Libro, hoy: date) -> list[Hallazgo]:
    from motor import tarjetas

    hallazgos = []
    for c in libro.cuentas():
        if c.activa and c.tipo is TipoCuenta.CREDITO and c.limite_credito:
            deuda = tarjetas.deuda(libro, c.id, hoy)
            if deuda > a_pesos(c.limite_credito):
                hallazgos.append(Hallazgo(
                    f"limite:{c.id}:{hoy:%Y-%m}", REVISAR, "Tarjetas pasadas de su límite",
                    f"«{c.nombre}» debe {formatear(deuda)} y su límite es {formatear(a_pesos(c.limite_credito))}. "
                    "¿Falta registrar un pago o cambió tu límite? (Cuentas → Editar).", "cuentas"))
    return hallazgos


def _fechas(libro: Libro, hoy: date) -> list[Hallazgo]:
    adelante = [op for op in libro.operaciones(desde=hoy + timedelta(days=DIAS_ADELANTE + 1))]
    atras = [op for op in libro.operaciones(hasta=date(hoy.year - ANIOS_ATRAS, 12, 31))
             if op.tipo is not TipoOperacion.SALDO_INICIAL]
    hallazgos = []
    for op in adelante:
        hallazgos.append(Hallazgo(
            f"fecha:{op.id}", REVISAR, "Fechas muy adelante",
            f"«{op.descripcion or 'sin descripción'}» tiene fecha {op.fecha:%d/%m/%Y}. ¿El año o el mes mal "
            "escrito? Un pago futuro está bien si ya lo programaste.", "historial", (op.id,)))
    for op in atras:
        hallazgos.append(Hallazgo(
            f"fecha:{op.id}", REVISAR, "Fechas muy antiguas",
            f"«{op.descripcion or 'sin descripción'}» tiene fecha {op.fecha:%d/%m/%Y}. ¿El año mal escrito?",
            "historial", (op.id,)))
    return hallazgos


def _temporales(libro: Libro, hoy: date) -> list[Hallazgo]:
    vencidos = temporales.vencidos(libro, hoy)
    if not vencidos:
        return []
    total = sum((c.monto for c in vencidos), a_pesos(0))
    return [Hallazgo(f"temporales:{hoy:%Y-%m}", REVISAR, "Cargos temporales que no te han devuelto",
                     f"{len(vencidos)} cargo(s) por {formatear(total)} llevan más de lo normal sin regresar. Reclámalos "
                     "o pásalos a gasto (en el Resumen).", "inicio", cuantos=len(vencidos))]


def _retiros(libro: Libro) -> list[Hallazgo]:
    from motor import efectivo

    ops = efectivo.pendientes(libro)
    if not ops:
        return []
    destino = efectivo.convertible(libro, ops[0])
    total = sum((abs(op.partidas_de_cuenta()[0].importe) for op in ops), 0)
    return [Hallazgo(f"efectivo:{len(ops)}", REVISAR, "Retiros de efectivo guardados como gasto",
                     f"{len(ops)} retiro(s) de efectivo por {formatear(a_pesos(total))} cuentan como gasto, pero tienes "
                     f"tu cuenta «{destino.nombre}»: ese dinero pasó a tu cartera y lo gastas después. Pásalos a tu "
                     "cuenta de efectivo y tus gastos y tu saldo quedan bien.", "historial",
                     tuple(op.id for op in ops[:50]), len(ops))]


def _genericas(libro: Libro) -> list[Hallazgo]:
    ids = {c.id: c.nombre for c in (categorias.buscar(libro, n) for n in GENERICAS) if c is not None}
    if not ids:
        return []
    conteo: dict[str, list[str]] = defaultdict(list)
    for op in libro.operaciones():
        for p in op.partidas_de_categoria():
            if p.categoria_id in ids:
                conteo[p.categoria_id].append(op.id)
                break
    hallazgos = []
    for categoria_id, ops in conteo.items():
        hallazgos.append(Hallazgo(
            f"genericas:{categoria_id}:{len(ops) // 10}", MEJORAR, f"Movimientos en {ids[categoria_id]}",
            f"{len(ops)} movimiento(s) están en {ids[categoria_id]}: tus reportes no dicen en qué fue ese dinero. "
            "Pásalos a su subcategoría en el Historial, o crea reglas automáticas para que la próxima vez se "
            "acomoden solos (Categorías › ⚡ Reglas automáticas).", "historial", tuple(ops[-50:]), len(ops)))
    return hallazgos


def _sin_descripcion(libro: Libro) -> list[Hallazgo]:
    ops = [op.id for op in libro.operaciones()
           if op.tipo in (TipoOperacion.GASTO, TipoOperacion.INGRESO) and not op.descripcion.strip()]
    if len(ops) < 5:
        return []
    return [Hallazgo(f"sin_descripcion:{len(ops) // 10}", MEJORAR, "Movimientos sin descripción",
                     f"{len(ops)} gasto(s) o ingreso(s) no dicen qué fueron. Con una descripción («Súper», «Uber») "
                     "los encuentras al buscar y TALLY aprende a sugerirte la subcategoría.", "historial",
                     tuple(ops[-50:]), len(ops))]


def _tarjetas_incompletas(libro: Libro) -> list[Hallazgo]:
    hallazgos = []
    for c in libro.cuentas():
        if not (c.activa and c.tipo is TipoCuenta.CREDITO):
            continue
        falta = [que for que, ok in (("día de corte", c.dia_corte), ("fecha límite de pago", c.dia_pago or
                                                                     c.dias_para_pagar),
                                     ("tasa de interés", c.tasa_anual)) if not ok]
        if falta:
            hallazgos.append(Hallazgo(
                f"tarjeta:{c.id}:{'+'.join(falta)}", MEJORAR, "Tarjetas con datos incompletos",
                f"A «{c.nombre}» le falta: {', '.join(falta)}. Sin eso no se calculan bien sus pagos, el mínimo, "
                "los intereses ni tu plan de deudas (Cuentas → Editar; la tasa, en Deudas).",
                "deudas" if falta == ["tasa de interés"] else "cuentas"))
    return hallazgos


def _prestamos_sin_datos(libro: Libro) -> list[Hallazgo]:
    con_datos = {p.cuenta_id for p in libro.prestamos()}
    return [Hallazgo(f"prestamo:{c.id}", MEJORAR, "Préstamos sin sus datos",
                     f"«{c.nombre}» es un préstamo pero no tiene tasa, plazo ni pago: regístralos en Deudas para "
                     "ver cuándo terminas y cuánto pagas de intereses.", "deudas")
            for c in libro.cuentas() if c.activa and c.tipo is TipoCuenta.PRESTAMO and c.id not in con_datos]


def _sin_uso(libro: Libro, hoy: date) -> list[Hallazgo]:
    ultima: dict[str, date] = {}
    for op in libro.operaciones(hasta=hoy):
        if op.tipo is TipoOperacion.SALDO_INICIAL:
            continue
        for p in op.partidas_de_cuenta():
            ultima[p.cuenta_id] = op.fecha
    hallazgos = []
    for c in libro.cuentas():
        if not c.activa or c.tipo in (TipoCuenta.BIEN, TipoCuenta.PRESTAMO, TipoCuenta.INVERSION):
            continue
        fecha = ultima.get(c.id)
        desde = fecha or c.fecha_creacion
        if (hoy - desde).days > DIAS_SIN_USO:
            hace = f"desde el {fecha:%d/%m/%Y}" if fecha else "desde que la creaste"
            hallazgos.append(Hallazgo(
                f"sin_uso:{c.id}:{desde.isoformat()}", MEJORAR, "Cuentas sin movimientos",
                f"«{c.nombre}» no tiene movimientos {hace}. Si ya no la usas, archívala (Cuentas); si sí, quizá te "
                "falta registrar o importar sus movimientos.", "cuentas"))
    return hallazgos


def _reglas(libro: Libro) -> list[Hallazgo]:
    from motor import reglas_categorias

    if not libro.reglas():
        return []
    cambios = reglas_categorias.pendientes(libro)
    if not cambios:
        return []
    return [Hallazgo(f"reglas:{len(cambios) // 10}", MEJORAR, "Movimientos que tus reglas acomodarían distinto",
                     f"{len(cambios)} movimiento(s) están en otra subcategoría de la que dicen tus reglas "
                     "automáticas. Revísalos y corrígelos de un jalón en Categorías › ⚡ Reglas automáticas.",
                     "categorias", tuple(c.operacion.id for c in cambios[:50]), len(cambios))]


def _deducibles(libro: Libro, hoy: date) -> list[Hallazgo]:
    if not libro.fiscal.conceptos:
        return []
    from motor import comprobantes

    faltan = comprobantes.sin_comprobante(libro, hoy.year)
    if not faltan:
        return []
    return [Hallazgo(f"deducibles:{hoy.year}:{len(faltan) // 5}", MEJORAR, "Deducibles sin comprobante",
                     f"{len(faltan)} pago(s) deducibles de {hoy.year} no tienen su comprobante adjunto. Sin él, tu "
                     "autoridad fiscal puede no aceptarlos (Impuestos › 📎 Comprobantes).", "impuestos",
                     tuple(d.pago.operacion_id for d in faltan[:50]), len(faltan))]
