"""Guía de primeros pasos: lo que conviene configurar para sacarle jugo a TALLY, y cuánto llevas.

Cada paso se marca **solo**, con tus datos (no hay que palomearlo): en cuanto agregas tu primera meta, el paso de
metas queda hecho. Los pasos opcionales no cuentan para el avance. Si ya no quieres verla en el Resumen, la ocultas
(se guarda en tu perfil) y sigue en Guía y ayuda.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import TipoCuenta, TipoOperacion

MOVIMIENTOS_PARA_EMPEZAR = 10


@dataclass(frozen=True, slots=True)
class Paso:
    clave: str
    titulo: str
    porque: str               # para qué sirve, en una frase
    pagina: str               # dónde se hace (portal/navegacion.py)
    hecho: bool
    opcional: bool = False


@dataclass(frozen=True, slots=True)
class Avance:
    pasos: list[Paso]

    @property
    def obligatorios(self) -> list[Paso]:
        return [p for p in self.pasos if not p.opcional]

    @property
    def hechos(self) -> int:
        return sum(p.hecho for p in self.obligatorios)

    @property
    def total(self) -> int:
        return len(self.obligatorios)

    @property
    def completo(self) -> bool:
        return self.hechos == self.total

    @property
    def siguiente(self) -> Paso | None:
        return next((p for p in self.obligatorios if not p.hecho), None)


def avance(libro: Libro, *, con_contrasena: bool | None = None) -> Avance:
    """Los pasos y cuáles ya hiciste. ``con_contrasena``: si tus datos tienen contraseña (lo sabe el almacén)."""
    cuentas = [c for c in libro.cuentas() if c.activa]
    tarjetas = [c for c in cuentas if c.tipo is TipoCuenta.CREDITO]
    movimientos = sum(op.tipo is not TipoOperacion.SALDO_INICIAL for op in libro.operaciones())
    recurrentes = libro.recurrentes()
    perfil = libro.perfil
    pasos = [
        Paso("cuentas", "Agrega tus cuentas",
             "Tus tarjetas de débito y crédito, ahorro y efectivo, con lo que tienen (o debes) hoy.",
             "cuentas", bool(cuentas)),
        Paso("movimientos", "Registra o importa tus movimientos",
             "Lo que gastas y lo que te entra. Lo más rápido: importa el estado de cuenta de tu banco (Cargar "
             "datos) o sube tu historial con la plantilla de Excel.",
             "cargar", movimientos >= MOVIMIENTOS_PARA_EMPEZAR),
        Paso("ingreso", "Dile a TALLY cuánto ganas",
             "Tu nómina o ingresos fijos: con eso calcula tus quincenas, cuánto puedes gastar y si tus deudas "
             "son sanas.", "ingresos",
             any(r.tipo is TipoOperacion.INGRESO for r in recurrentes) or bool(perfil and perfil.ingreso_esperado)),
        Paso("fijos", "Agrega tus pagos fijos",
             "Renta, luz, internet, suscripciones…: el Calendario te avisa antes de cada uno y ves si te alcanza.",
             "calendario", any(r.tipo is not TipoOperacion.INGRESO for r in recurrentes)),
        Paso("tarjetas", "Completa los datos de tus tarjetas",
             "Día de corte, fecha límite y tasa: así sabes cuánto pagar para no generar intereses.",
             "cuentas", all(c.dia_corte and (c.dia_pago or c.dias_para_pagar) and c.tasa_anual for c in tarjetas)),
        Paso("presupuestos", "Ponte presupuestos",
             "Cuánto quieres gastar al mes en cada categoría; TALLY te sugiere montos con lo que sueles gastar.",
             "presupuestos", any(r.presupuesto for r in libro.rubros())),
        Paso("metas", "Crea tu fondo de emergencia o una meta",
             "Lo que quieres juntar y para cuándo: TALLY te dice cuánto apartar al mes.", "metas",
             bool(libro.metas())),
        Paso("reglas", "Crea reglas automáticas", "«Todo lo que diga OXXO va a SNACKS»: tus importaciones se "
             "acomodan solas.", "categorias", bool(libro.reglas()), opcional=True),
        Paso("deudas", "Arma tu plan para salir de deudas", "Cuánto pagar a cada tarjeta o préstamo y cuándo "
             "terminas.", "deudas", bool(perfil and perfil.plan_deudas),
             opcional=not any(c.tipo in (TipoCuenta.CREDITO, TipoCuenta.PRESTAMO) for c in cuentas)),
        Paso("cierre", "Revisa tu primer cierre de mes", "Cómo te fue, qué falta registrar y qué hacer el mes que "
             "sigue.", "cierre", bool(libro.cierres()), opcional=True),
        Paso("contrasena", "Ponle contraseña a tus datos", "Si alguien más usa tu computadora. Guarda bien tu Kit de "
             "emergencia.", "configuracion", bool(con_contrasena), opcional=True),
    ]
    return Avance(pasos)


def ocultar(libro: Libro, oculta: bool = True) -> None:
    """La guía ya no sale en el Resumen (sigue en Guía y ayuda)."""
    if libro.perfil is None:
        raise ErrorValidacion("Primero escribe tu nombre en la bienvenida.")
    libro.perfil = replace(libro.perfil, guia_oculta=oculta)


def se_muestra_en_el_resumen(libro: Libro, avance_: Avance) -> bool:
    return bool(libro.perfil) and not libro.perfil.guia_oculta and not avance_.completo
