"""Catálogo inicial de categorías y subcategorías, y su puesta al día en datos de versiones anteriores.

Las **categorías** (``Rubro`` en el motor) agrupan **subcategorías** (``Categoria``), que son lo que se asigna a
cada movimiento. Todo es editable; el catálogo es solo un punto de partida amplio, pensado para personas
jóvenes y adultas en México. Incluye las categorías originales de TALLY (las del Excel de su autor).

Cada subcategoría trae una **clasificación** sugerida (Necesidad, Disfrute…), equivalente a la columna
«Clasif. Metas» del Excel.
"""

from __future__ import annotations

from dataclasses import replace

from motor.libro import Libro
from motor.modelo import Categoria, ClaseCategoria, Grupo, Rubro
from motor.textos import clave, estandarizar

GRUPOS_INICIALES = ("Necesidad", "Disfrute", "Estabilidad", "Inversión", "Dádivas")

_N, _D, _E, _I, _DA = GRUPOS_INICIALES
G, I = ClaseCategoria.GASTO, ClaseCategoria.INGRESO

# (categoría, clase, ((subcategoría, clasificación), ...)). La nómina es el ingreso principal (quincenas).
CATALOGO: tuple[tuple[str, ClaseCategoria, tuple[tuple[str, str | None], ...]], ...] = (
    ("ALIMENTACION", G, (
        ("DESPENSA", _N), ("ALIMENTOS", _N), ("RESTAURANTES", _D), ("COMIDA A DOMICILIO", _D),
        ("SNACKS Y ANTOJOS", _D), ("CAFETERIAS", _D), ("COMIDA EN EL TRABAJO O ESCUELA", _N),
        ("AGUA PURIFICADA", _N),
    )),
    ("HOGAR", G, (
        ("RENTA", _N), ("HIPOTECA", _N), ("VIVIENDA", _N), ("CUOTA DE MANTENIMIENTO", _N), ("PREDIAL", _N),
        ("HOGAR Y MANTENIMIENTO", _N), ("MEJORAS DEL HOGAR", _D), ("MUEBLES Y DECORACION", _D),
        ("ARTICULOS DE LIMPIEZA", _N), ("SERVICIO DOMESTICO", _N), ("SEGURO DE CASA", _E),
    )),
    ("SERVICIOS", G, (
        ("LUZ", _N), ("AGUA", _N), ("GAS", _N), ("INTERNET", _N), ("RECARGAS Y TELEFONIA", _N), ("TV DE PAGA", _D),
    )),
    ("MOVILIDAD", G, (
        ("TRANSPORTE", _N), ("GASOLINA", _N), ("TRANSPORTE PUBLICO", _N), ("TAXI Y APPS DE VIAJE", _N),
        ("ESTACIONAMIENTO", _N), ("CASETAS", _N), ("MANTENIMIENTO DEL AUTO", _N), ("SEGURO DEL AUTO", _E),
        ("TENENCIA Y VERIFICACION", _N), ("PAGO DEL AUTO", _N), ("LAVADO DEL AUTO", _D),
    )),
    ("SALUD", G, (
        ("SALUD Y CUIDADO PERSONAL", _N), ("CONSULTAS MEDICAS", _N), ("MEDICINAS Y FARMACIA", _N),
        ("DENTISTA", _N), ("ANALISIS Y ESTUDIOS", _N), ("HOSPITAL", _N), ("SEGURO DE GASTOS MEDICOS", _E),
        ("LENTES Y OPTICA", _N), ("PSICOLOGIA Y TERAPIA", _N),
    )),
    ("CUIDADO PERSONAL", G, (
        ("CORTE DE CABELLO Y ESTETICA", _N), ("COSMETICOS E HIGIENE", _N), ("SPA Y MASAJES", _D),
    )),
    ("DEPORTE Y BIENESTAR", G, (
        ("GIMNASIO", _I), ("CLASES Y DEPORTES", _I), ("EQUIPO DEPORTIVO", _D), ("SUPLEMENTOS", _D),
    )),
    ("ROPA Y CALZADO", G, (
        ("ROPA", _N), ("CALZADO", _N), ("ACCESORIOS", _D), ("LAVANDERIA Y TINTORERIA", _N),
    )),
    ("TECNOLOGIA", G, (
        ("HARDWARE Y ENTRETENIMIENTO", _D), ("CELULARES Y TABLETS", _D), ("COMPUTADORAS Y ACCESORIOS", _I),
        ("VIDEOJUEGOS", _D), ("SERVICIOS DE SOFTWARE", _N), ("REPARACION DE EQUIPOS", _N),
    )),
    ("SUSCRIPCIONES", G, (
        ("SUSCRIPCIONES Y STREAMING", _D), ("STREAMING DE VIDEO", _D), ("MUSICA", _D),
        ("ALMACENAMIENTO EN LA NUBE", _N), ("MEMBRESIAS", _D),
    )),
    ("ENTRETENIMIENTO", G, (
        ("CINE", _D), ("CONCIERTOS Y EVENTOS", _D), ("BARES Y FIESTAS", _D), ("SALIDAS Y PASEOS", _D),
        ("LIBROS Y REVISTAS", _D), ("PASATIEMPOS", _D), ("LOTERIA Y APUESTAS", _D),
    )),
    ("COMPRAS", G, (
        ("COMPRAS EN LINEA", _D), ("TIENDAS DEPARTAMENTALES", _D), ("PAPELERIA", _N),
    )),
    ("VIAJES", G, (
        ("VUELOS", _D), ("HOSPEDAJE", _D), ("TRANSPORTE EN VIAJES", _D), ("COMIDA EN VIAJES", _D),
        ("TOURS Y ACTIVIDADES", _D),
    )),
    ("ESTUDIOS", G, (
        ("EDUCACION", _I), ("COLEGIATURAS", _I), ("CURSOS Y CERTIFICACIONES", _I), ("IDIOMAS", _I),
        ("LIBROS Y MATERIAL ESCOLAR", _I),
    )),
    ("TRABAJO", G, (
        ("INSUMOS DE TRABAJO", _E), ("CUOTAS PROFESIONALES", _E), ("COMIDAS DE TRABAJO", _N),
    )),
    ("HIJOS", G, (
        ("GUARDERIA", _N), ("ROPA INFANTIL", _N), ("JUGUETES", _D), ("PAÑALES Y ARTICULOS DE BEBE", _N),
        ("NIÑERA", _N), ("MESADAS", _DA), ("ACTIVIDADES EXTRAESCOLARES", _I),
    )),
    ("MASCOTAS", G, (
        ("ALIMENTO PARA MASCOTAS", _N), ("VETERINARIO", _N), ("ESTETICA DE MASCOTAS", _D),
        ("ACCESORIOS PARA MASCOTAS", _D),
    )),
    ("FINANZAS", G, (
        ("GASTOS FINANCIEROS", _N), ("INTERESES DE TARJETAS", _N), ("COMISIONES BANCARIAS", _N),
        ("ANUALIDADES", _N), ("INTERESES DE PRESTAMOS", _N), ("IMPUESTOS", _N), ("SEGURO DE VIDA", _E),
    )),
    ("REGALOS Y DONATIVOS", G, (
        ("REGALOS", _DA), ("DONATIVOS", _DA), ("CELEBRACIONES", _D), ("APOYO A FAMILIARES", _DA),
    )),
    ("EFECTIVO", G, (
        ("RETIROS DE EFECTIVO", _N),
    )),
    ("VARIOS", G, (
        ("OTROS GASTOS", None), ("IMPREVISTOS", None), ("MULTAS Y RECARGOS", None),
    )),
    ("SUELDO Y PRESTACIONES", I, (
        ("NOMINA", None), ("AGUINALDO", None), ("BONOS", None), ("PRIMA VACACIONAL", None),
        ("REPARTO DE UTILIDADES", None), ("HORAS EXTRA", None), ("VALES DE DESPENSA", None),
    )),
    ("INGRESOS INDEPENDIENTES", I, (
        ("FREELANCE", None), ("HONORARIOS", None), ("VENTAS", None), ("NEGOCIO PROPIO", None), ("PROPINAS", None),
    )),
    ("INVERSIONES Y RENTAS", I, (
        ("INTERESES Y RENDIMIENTOS", None), ("DIVIDENDOS", None), ("RENTAS COBRADAS", None),
    )),
    ("INGRESOS VARIOS", I, (
        ("OTROS INGRESOS", None), ("REGALOS RECIBIDOS", None), ("DEVOLUCION DE IMPUESTOS", None),
        ("BECAS Y APOYOS", None), ("PREMIOS", None), ("VENTA DE ARTICULOS USADOS", None),
        ("CASHBACK Y RECOMPENSAS", None),
    )),
)
PRINCIPAL = "NOMINA"
# Adonde va lo que no tiene categoría (subcategorías creadas por el usuario en versiones anteriores).
VARIOS = {ClaseCategoria.GASTO: "VARIOS", ClaseCategoria.INGRESO: "INGRESOS VARIOS"}


def cargar(libro: Libro) -> None:
    """Crea clasificaciones, categorías y subcategorías sugeridas. Solo actúa sobre un libro vacío."""
    if libro.grupos() or libro.rubros() or any(c.clase is not ClaseCategoria.SISTEMA for c in libro.categorias()):
        return
    for orden, nombre in enumerate(GRUPOS_INICIALES):
        libro.guardar_grupo(Grupo(libro.nuevo_id(), nombre, orden))
    _completar(libro, principal=True)


def necesita_actualizar(libro: Libro) -> bool:
    """True si los datos son de antes de las categorías con subcategorías (TALLY 0.3)."""
    return any(
        (c.rubro_id is None and c.clase is not ClaseCategoria.SISTEMA) or c.nombre != _estandar_o_igual(c.nombre)
        for c in libro.categorias()
    )


def actualizar(libro: Libro) -> None:
    """Pone al día datos de TALLY 0.3 sin perder nada.

    1. Nombres en MAYÚSCULAS y sin acentos («Nómina» → «NOMINA»). Si dos quedan iguales, la segunda se
       renombra «NOMBRE (2)»: nunca se juntan movimientos sin que el usuario lo decida.
    2. Cada subcategoría entra en su categoría del catálogo; las creadas por el usuario van a VARIOS (o a
       INGRESOS VARIOS). Sus movimientos, clasificación e ingreso principal no cambian.
    3. Se agregan las subcategorías del catálogo que falten.
    """
    usadas: set[str] = set()
    for categoria in libro.categorias():
        nombre = _estandar_o_igual(categoria.nombre)
        n = 2
        while clave(nombre) in usadas:
            nombre, n = f"{_estandar_o_igual(categoria.nombre)} ({n})", n + 1
        usadas.add(clave(nombre))
        if nombre != categoria.nombre:
            libro.guardar_categoria(replace(categoria, nombre=nombre))
    _completar(libro, principal=False)


# ---------------------------------------------------------------- internos


def _estandar_o_igual(nombre: str) -> str:
    try:
        return estandarizar(nombre)
    except Exception:  # noqa: BLE001 - un nombre vacío heredado se queda como está
        return nombre


def _completar(libro: Libro, *, principal: bool) -> None:
    """Crea las categorías del catálogo que falten, acomoda las subcategorías huérfanas y agrega las del
    catálogo que no existan (por nombre, sin importar mayúsculas ni acentos)."""
    grupos = {clave(g.nombre): g.id for g in libro.grupos()}
    rubros = {clave(r.nombre): r for r in libro.rubros()}
    existentes = {clave(c.nombre): c for c in libro.categorias()}
    orden_rubro = max((r.orden for r in libro.rubros()), default=-1) + 1
    orden_sub = max((c.orden for c in libro.categorias()), default=-1) + 1
    hogar_de: dict[str, tuple[str, ClaseCategoria]] = {}  # clave de subcategoría → su categoría del catálogo

    def rubro(nombre: str, clase: ClaseCategoria) -> Rubro:
        nonlocal orden_rubro
        actual = rubros.get(clave(nombre))
        if actual is None or actual.clase is not clase:
            actual = libro.guardar_rubro(Rubro(libro.nuevo_id(), nombre, clase, orden_rubro))
            rubros[clave(nombre)] = actual
            orden_rubro += 1
        return actual

    for nombre_rubro, clase, subcategorias in CATALOGO:
        destino = rubro(nombre_rubro, clase)
        for nombre, grupo in subcategorias:
            hogar_de[clave(nombre)] = (nombre_rubro, clase)
            if clave(nombre) in existentes:
                continue
            nueva = Categoria(
                libro.nuevo_id(), nombre, clase, grupo_id=grupos.get(clave(grupo)) if grupo else None,
                principal=principal and nombre == PRINCIPAL, orden=orden_sub, rubro_id=destino.id,
            )
            existentes[clave(nombre)] = libro.guardar_categoria(nueva)
            orden_sub += 1

    for categoria in libro.categorias():
        if categoria.rubro_id is None and categoria.clase is not ClaseCategoria.SISTEMA:
            nombre_rubro, clase = hogar_de.get(clave(categoria.nombre), (VARIOS[categoria.clase], categoria.clase))
            if clase is not categoria.clase:
                nombre_rubro = VARIOS[categoria.clase]
            libro.guardar_categoria(replace(categoria, rubro_id=rubro(nombre_rubro, categoria.clase).id))
