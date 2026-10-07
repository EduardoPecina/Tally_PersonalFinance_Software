"""Tus ingresos: el principal (la nómina), los que se repiten, cuánto te llega cada vez y cuánto tiene que durarte.

- **Ingreso principal**: una subcategoría de ingreso marcada como principal con su recurrente (motor/recurrentes.py):
  cada cuánto te pagan, a qué cuenta y cuánto. En quincena, la 1.ª (la del 15) y la 2.ª (la de fin de mes) pueden
  ser distintas por centavos (retenciones, redondeos…).
- **Fin de semana**: si el día de pago cae en sábado o domingo, muchas empresas pagan el viernes antes. Por eso no
  todas las quincenas duran lo mismo: si el 15 cae en domingo te pagan el viernes 13 y ese dinero tiene que durarte
  hasta fin de mes, 18 días en vez de 15.
- **Periodos**: cada pago y cuántos días tiene que durarte; avisa de los más largos de lo normal.
- **Hasta tu próximo pago**: con tu dinero disponible y lo que te toca pagar y cobrar antes, cuánto puedes gastar al
  día hasta que te vuelvan a pagar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from motor import categorias, recurrentes
from motor.dinero import a_pesos
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import ClaseCategoria, Recurrente, TipoOperacion

FRECUENCIAS = ("quincenal", "catorcenal", "semanal", "mensual")
DIAS_NORMALES = {"quincenal": Decimal("15.2"), "catorcenal": Decimal(14), "semanal": Decimal(7),
                 "mensual": Decimal("30.4")}
HOLGURA = Decimal("1.5")       # un periodo es «largo» si dura más de lo normal + 1.5 días


def principal(libro: Libro) -> Recurrente | None:
    """El recurrente de tu ingreso principal (el de la subcategoría marcada como principal)."""
    ids = {c.id for c in libro.categorias() if c.principal}
    activos = [r for r in libro.recurrentes() if r.tipo is TipoOperacion.INGRESO and r.categoria_id in ids]
    return next((r for r in activos if r.activa), activos[0] if activos else None)


def fijos(libro: Libro) -> list[Recurrente]:
    """Tus ingresos que se repiten (el principal primero)."""
    lista = [r for r in libro.recurrentes() if r.tipo is TipoOperacion.INGRESO]
    p = principal(libro)
    return sorted(lista, key=lambda r: (p is None or r.id != p.id, not r.activa, r.nombre.casefold()))


def guardar(libro: Libro, nombre: str, categoria_id: str, monto, cuenta_id: str, frecuencia: str, *,
            monto_2=None, inicio: date | None = None, fin_de_semana: str = "", es_principal: bool = False,
            recurrente_id: str | None = None) -> Recurrente:
    """Crea (o edita) un ingreso que se repite. El principal marca su subcategoría como tu ingreso principal; los
    demás, como ingresos secundarios fijos (cuentan en tu ingreso esperado)."""
    if frecuencia not in recurrentes.FRECUENCIAS:
        raise ErrorValidacion("Elige cada cuánto te pagan.")
    if not categoria_id:
        raise ErrorValidacion("Elige la subcategoría de ingreso.")
    if inicio is None:
        inicio = libro.recurrente(recurrente_id).inicio if recurrente_id else libro.hoy().replace(day=1)
    datos = dict(nombre=nombre or libro.categoria(categoria_id).nombre, tipo=TipoOperacion.INGRESO, monto=monto,
                 cuenta_id=cuenta_id, frecuencia=frecuencia, inicio=inicio, categoria_id=categoria_id,
                 monto_2=monto_2 if frecuencia == "quincenal" else None, fin_de_semana=fin_de_semana)
    if recurrente_id:
        r = recurrentes.editar(libro, recurrente_id, **datos)
    else:
        r = recurrentes.crear(libro, **datos)
    if es_principal:
        for c in libro.categorias():
            if c.clase is ClaseCategoria.INGRESO and c.rubro_id:
                es = c.id == categoria_id
                if c.principal != es or (es and c.secundario):
                    categorias.editar(libro, c.id, principal=es, secundario=False if es else None)
    else:
        c = libro.categoria(categoria_id)
        if not c.principal and not c.secundario:
            categorias.editar(libro, c.id, secundario=True)
    return r


# ------------------------------------------------------------------ periodos


@dataclass(frozen=True, slots=True)
class Periodo:
    pago: date                 # el día que te pagan (ya movido si caía en fin de semana)
    monto: Decimal             # lo que te llega (estimado)
    siguiente: date            # el día del siguiente pago
    quincena: int              # 1 o 2 (0 si no es quincenal)
    normal: Decimal            # los días que dura un periodo normal

    @property
    def dias(self) -> int:
        """Los días que tiene que durarte (del día de pago al día antes del siguiente)."""
        return (self.siguiente - self.pago).days

    @property
    def hasta(self) -> date:
        """El último día que tiene que durarte."""
        return self.siguiente - timedelta(days=1)

    @property
    def por_dia(self) -> Decimal:
        return (self.monto / self.dias).quantize(Decimal("0.01")) if self.dias else self.monto

    @property
    def largo(self) -> bool:
        return self.dias > self.normal + HOLGURA

    @property
    def dias_de_mas(self) -> int:
        return max(0, self.dias - int(self.normal.to_integral_value()))


def periodos(r: Recurrente, hoy: date, n: int = 6) -> list[Periodo]:
    """El periodo en el que estás (desde tu último pago) y los ``n − 1`` siguientes."""
    fechas_ = recurrentes.fechas(r, hoy - timedelta(days=70), hoy + timedelta(days=60 * n))
    pasadas = [d for d in fechas_ if d <= hoy]
    desde = fechas_.index(pasadas[-1]) if pasadas else 0
    fechas_ = fechas_[desde:desde + n + 1]
    normal = DIAS_NORMALES.get(r.frecuencia, Decimal(365) / 12 * {"bimestral": 2, "trimestral": 3, "semestral": 6,
                                                                    "anual": 12}.get(r.frecuencia, 1))
    return [Periodo(a, a_pesos(recurrentes.monto_en(r, a)), b,
                    recurrentes.quincena(r, a) if r.frecuencia == "quincenal" else 0, normal)
            for a, b in zip(fechas_, fechas_[1:])]


# ------------------------------------------------------------ hasta tu próximo pago


@dataclass(frozen=True, slots=True)
class HastaElProximo:
    proximo: date              # tu próximo pago
    monto: Decimal             # lo que te llega ese día
    dias: int                  # los días que faltan (hoy incluido, el día de pago no)
    disponible: Decimal        # tu dinero disponible hoy
    queda: Decimal             # lo que te quedaría el día antes del pago, con lo que toca pagar y cobrar antes

    @property
    def por_dia(self) -> Decimal:
        return max((self.queda / self.dias).quantize(Decimal("0.01")), Decimal(0)) if self.dias else self.queda

    @property
    def compromisos(self) -> Decimal:
        """Lo que se te va en pagos (menos lo que cobras) antes de tu próximo pago."""
        return self.disponible - self.queda


def hasta_el_proximo_pago(libro: Libro, hoy: date | None = None) -> HastaElProximo | None:
    hoy = hoy or libro.hoy()
    r = principal(libro)
    if r is None or not r.activa:
        return None
    proximo = recurrentes.siguiente(r, hoy + timedelta(days=1))
    if proximo is None:
        return None
    dias = (proximo - hoy).days
    f = recurrentes.flujo(libro, hoy, dias - 1)
    return HastaElProximo(proximo, a_pesos(recurrentes.monto_en(r, proximo)), dias, a_pesos(f.disponible),
                          a_pesos(f.final))
