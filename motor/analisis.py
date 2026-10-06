"""Análisis: tablas dinámicas (pivots) y los datos de las gráficas.

Funciona como una tabla dinámica de Excel sobre tus movimientos: eliges qué va en las **filas** (categoría,
subcategoría, clasificación, cuenta…), qué va en las **columnas** (mes, año, trimestre o nada) y qué se
**suma** (gastos, ingresos o el balance), en el rango de fechas y las cuentas que quieras.

Las cifras salen de las mismas partidas que todos los reportes: una transferencia o un pago de tarjeta nunca
cuenta como gasto. Opcionalmente se puede agregar lo que apartaste a ahorro e inversión como una fila más
(como la fila AHORRO de tu Excel), claramente separada de los gastos.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from motor import categorias
from motor.dinero import a_pesos
from motor.libro import Libro
from motor.modelo import TIPOS_AHORRO, ClaseCategoria

FILAS = {
    "rubro": "Categoría",
    "categoria": "Subcategoría",
    "grupo": "Clasificación",
    "cuenta": "Cuenta",
    "clase": "Ingreso o gasto",
}
COLUMNAS = {
    "mes": "Mes",
    "trimestre": "Trimestre",
    "anio": "Año",
    "ninguna": "Solo el total",
    "rubro": "Categoría",
    "grupo": "Clasificación",
    "cuenta": "Cuenta",
}
MEDIDAS = {
    "gastos": "Gastos",
    "ingresos": "Ingresos",
    "todo": "Ingresos y gastos (por separado)",
    "balance": "Balance (ingresos − gastos)",
}
APARTADO = "APARTADO A AHORRO E INVERSION"
SIN_CLASIFICACION = "Sin clasificación"
MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
TOTAL = "Total"


@dataclass(frozen=True, slots=True)
class Pivot:
    filas: list[str]                       # etiquetas de las filas, de mayor a menor total
    columnas: list[str]                    # etiquetas de las columnas, en orden (meses en orden cronológico)
    valores: dict[tuple[str, str], Decimal]
    total_fila: dict[str, Decimal]         # total de cada fila (la última columna de Excel)
    total_columna: dict[str, Decimal]      # «Suma total» de cada columna
    total: Decimal

    def valor(self, fila: str, columna: str) -> Decimal | None:
        return self.valores.get((fila, columna))

    @property
    def vacia(self) -> bool:
        return not self.filas


def _columna(clave: str, fecha: date, dims: dict[str, str]) -> tuple[str, str]:
    """(orden, etiqueta) de la columna de un hecho."""
    if clave == "mes":
        return f"{fecha:%Y-%m}", f"{MESES[fecha.month - 1]} {fecha.year}"
    if clave == "trimestre":
        t = (fecha.month - 1) // 3 + 1
        return f"{fecha.year}-{t}", f"T{t} {fecha.year}"
    if clave == "anio":
        return str(fecha.year), str(fecha.year)
    if clave == "ninguna":
        return "", TOTAL
    return dims[clave], dims[clave]


def hechos(libro: Libro, desde: date | None = None, hasta: date | None = None, cuentas: set[str] | None = None,
           *, incluir_apartado: bool = False) -> list[tuple[date, dict[str, str], ClaseCategoria | None, int]]:
    """(fecha, dimensiones, clase, centavos en sentido natural) por cada partida de subcategoría.

    Gastos e ingresos son positivos; un reembolso resta del gasto. Con ``incluir_apartado``, las
    transferencias netas hacia ahorro/inversión salen como filas de clase ``None``.
    """
    resultado = []
    for op in libro.operaciones(desde, hasta):
        de_cuenta = op.partidas_de_cuenta()
        if cuentas and not any(p.cuenta_id in cuentas for p in de_cuenta):
            continue
        cuenta = libro.cuenta(de_cuenta[0].cuenta_id).nombre if len(de_cuenta) == 1 else ""
        for p in op.partidas_de_categoria():
            categoria = libro.categoria(p.categoria_id)
            if categoria.clase is ClaseCategoria.SISTEMA:
                continue
            grupo = libro.grupo(categoria.grupo_id).nombre if categoria.grupo_id else SIN_CLASIFICACION
            dims = {"rubro": categorias.nombre_rubro(libro, categoria.id), "categoria": categoria.nombre,
                    "grupo": grupo, "cuenta": cuenta,
                    "clase": "GASTOS" if categoria.clase is ClaseCategoria.GASTO else "INGRESOS"}
            monto = p.importe if categoria.clase is ClaseCategoria.GASTO else -p.importe
            resultado.append((op.fecha, dims, categoria.clase, monto))
        if incluir_apartado and len(de_cuenta) == 2 and not op.partidas_de_categoria():
            tipos = [libro.cuenta(p.cuenta_id).tipo in TIPOS_AHORRO for p in de_cuenta]
            if any(tipos) and not all(tipos):
                ahorro = next(p for p, es in zip(de_cuenta, tipos) if es)
                origen = next(p for p, es in zip(de_cuenta, tipos) if not es)
                if cuentas and origen.cuenta_id not in cuentas and ahorro.cuenta_id not in cuentas:
                    continue
                dims = {"rubro": APARTADO, "categoria": APARTADO, "grupo": APARTADO,
                        "cuenta": libro.cuenta(origen.cuenta_id).nombre, "clase": APARTADO}
                resultado.append((op.fecha, dims, None, ahorro.importe))
    return resultado


def pivot(
    libro: Libro,
    *,
    filas: str = "rubro",
    columnas: str = "mes",
    medida: str = "gastos",
    desde: date | None = None,
    hasta: date | None = None,
    cuentas: set[str] | None = None,
    incluir_apartado: bool = False,
) -> Pivot:
    """La tabla dinámica. ``desde``/``hasta`` en ``None`` = todo el historial."""
    if filas not in FILAS or columnas not in COLUMNAS or medida not in MEDIDAS:
        raise ValueError("Opción de tabla dinámica no válida.")
    celdas: dict[tuple[str, str], int] = defaultdict(int)
    orden_columnas: dict[str, str] = {}
    apartado = incluir_apartado and medida in ("gastos", "todo")
    for fecha, dims, clase, monto in hechos(libro, desde, hasta, cuentas, incluir_apartado=apartado):
        if clase is None:
            valor = monto                                  # lo apartado a ahorro, en su propia fila
        elif medida == "gastos":
            if clase is not ClaseCategoria.GASTO:
                continue
            valor = monto
        elif medida == "ingresos":
            if clase is not ClaseCategoria.INGRESO:
                continue
            valor = monto
        elif medida == "todo":
            valor = monto
        else:                                              # balance
            valor = monto if clase is ClaseCategoria.INGRESO else -monto
        orden, etiqueta = _columna(columnas, fecha, dims)
        orden_columnas[etiqueta] = orden
        celdas[(dims[filas], etiqueta)] += valor

    total_fila: dict[str, int] = defaultdict(int)
    total_columna: dict[str, int] = defaultdict(int)
    for (fila, columna), valor in celdas.items():
        total_fila[fila] += valor
        total_columna[columna] += valor
    nombres_filas = sorted(total_fila, key=lambda f: (f == APARTADO, -total_fila[f], f))
    nombres_columnas = sorted(orden_columnas, key=lambda c: (orden_columnas[c], c))
    if columnas in ("rubro", "grupo", "cuenta"):
        nombres_columnas = sorted(total_columna, key=lambda c: (-total_columna[c], c))
    return Pivot(
        filas=nombres_filas,
        columnas=nombres_columnas,
        valores={k: a_pesos(v) for k, v in celdas.items()},
        total_fila={k: a_pesos(v) for k, v in total_fila.items()},
        total_columna={k: a_pesos(v) for k, v in total_columna.items()},
        total=a_pesos(sum(total_fila.values())),
    )


def meses_con_datos(libro: Libro) -> tuple[date, date] | None:
    """Primer y último día con movimientos (para ofrecer «todo el historial»)."""
    operaciones = libro.operaciones()
    return (operaciones[0].fecha, operaciones[-1].fecha) if operaciones else None
