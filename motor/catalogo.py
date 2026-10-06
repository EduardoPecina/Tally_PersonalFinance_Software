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

# Clasificaciones: para qué es cada gasto según tus metas (independiente de su categoría).
DESCRIPCIONES = {
    "Necesidad": "Lo indispensable para vivir: techo, comida, servicios, transporte, salud y ropa.",
    "Compromisos": "Lo que pagas por obligación y no te da nada a cambio: intereses, comisiones, impuestos, multas "
                   "y pagos de deudas.",
    "Estabilidad": "Lo que protege tu ingreso y tu tranquilidad: seguros, herramientas de trabajo e imprevistos.",
    "Crecimiento": "Lo que te hace crecer: estudios, cursos, libros, ejercicio y herramientas para aprender.",
    "Disfrute": "Gustos que eliges: salidas, viajes, entretenimiento, compras y caprichos.",
    "Antojos": "Los gastos hormiga: botanas, café, comida a domicilio. Pequeños, pero suman.",
    "Generosidad": "Lo que das a otros: regalos, celebraciones, donativos y apoyo a la familia.",
}
GRUPOS_INICIALES = tuple(DESCRIPCIONES)

_N, _C, _E, _CR, _D, _A, _G = GRUPOS_INICIALES
G, I = ClaseCategoria.GASTO, ClaseCategoria.INGRESO

# (categoría, clase, ((subcategoría, clasificación), ...)). La nómina es el ingreso principal (quincenas).
CATALOGO: tuple[tuple[str, ClaseCategoria, tuple[tuple[str, str | None], ...]], ...] = (
    ("ALIMENTACION", G, (
        ("DESPENSA", _N), ("ALIMENTOS", _N), ("RESTAURANTES", _D), ("COMIDA A DOMICILIO", _A),
        ("SNACKS Y ANTOJOS", _A), ("CAFETERIAS", _A), ("COMIDA EN EL TRABAJO O ESCUELA", _N),
        ("AGUA PURIFICADA", _N),
    )),
    ("HOGAR", G, (
        ("RENTA", _N), ("HIPOTECA", _N), ("VIVIENDA", _N), ("CUOTA DE MANTENIMIENTO", _N), ("PREDIAL", _C),
        ("HOGAR Y MANTENIMIENTO", _N), ("MEJORAS DEL HOGAR", _D), ("MUEBLES Y DECORACION", _D),
        ("ARTICULOS DE LIMPIEZA", _N), ("SERVICIO DOMESTICO", _N), ("SEGURO DE CASA", _E),
    )),
    ("SERVICIOS", G, (
        ("LUZ", _N), ("AGUA", _N), ("GAS", _N), ("INTERNET", _N), ("RECARGAS Y TELEFONIA", _N), ("TV DE PAGA", _D),
    )),
    ("MOVILIDAD", G, (
        ("TRANSPORTE", _N), ("GASOLINA", _N), ("TRANSPORTE PUBLICO", _N), ("TAXI Y APPS DE VIAJE", _N),
        ("ESTACIONAMIENTO", _N), ("CASETAS", _N), ("MANTENIMIENTO DEL AUTO", _N), ("SEGURO DEL AUTO", _E),
        ("TENENCIA Y VERIFICACION", _C), ("PAGO DEL AUTO", _C), ("LAVADO DEL AUTO", _D),
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
        ("GIMNASIO", _CR), ("CLASES Y DEPORTES", _CR), ("EQUIPO DEPORTIVO", _CR), ("SUPLEMENTOS", _D),
    )),
    ("ROPA Y CALZADO", G, (
        ("ROPA", _N), ("CALZADO", _N), ("ACCESORIOS", _D), ("LAVANDERIA Y TINTORERIA", _N),
    )),
    ("TECNOLOGIA", G, (
        ("HARDWARE Y ENTRETENIMIENTO", _D), ("CELULARES Y TABLETS", _D), ("COMPUTADORAS Y ACCESORIOS", _CR),
        ("VIDEOJUEGOS", _D), ("SERVICIOS DE SOFTWARE", _CR), ("REPARACION DE EQUIPOS", _N),
    )),
    ("SUSCRIPCIONES", G, (
        ("SUSCRIPCIONES Y STREAMING", _D), ("STREAMING DE VIDEO", _D), ("MUSICA", _D),
        ("ALMACENAMIENTO EN LA NUBE", _N), ("MEMBRESIAS", _D),
    )),
    ("ENTRETENIMIENTO", G, (
        ("CINE", _D), ("CONCIERTOS Y EVENTOS", _D), ("BARES Y FIESTAS", _D), ("SALIDAS Y PASEOS", _D),
        ("LIBROS Y REVISTAS", _CR), ("PASATIEMPOS", _D), ("LOTERIA Y APUESTAS", _A),
    )),
    ("COMPRAS", G, (
        ("COMPRAS EN LINEA", _D), ("TIENDAS DEPARTAMENTALES", _D), ("PAPELERIA", _N),
    )),
    ("VIAJES", G, (
        ("VUELOS", _D), ("HOSPEDAJE", _D), ("TRANSPORTE EN VIAJES", _D), ("COMIDA EN VIAJES", _D),
        ("TOURS Y ACTIVIDADES", _D),
    )),
    ("ESTUDIOS", G, (
        ("EDUCACION", _CR), ("COLEGIATURAS", _CR), ("CURSOS Y CERTIFICACIONES", _CR), ("IDIOMAS", _CR),
        ("LIBROS Y MATERIAL ESCOLAR", _CR),
    )),
    ("TRABAJO", G, (
        ("INSUMOS DE TRABAJO", _E), ("CUOTAS PROFESIONALES", _E), ("COMIDAS DE TRABAJO", _N),
    )),
    ("HIJOS", G, (
        ("GUARDERIA", _N), ("ROPA INFANTIL", _N), ("JUGUETES", _D), ("PAÑALES Y ARTICULOS DE BEBE", _N),
        ("NIÑERA", _N), ("MESADAS", _G), ("ACTIVIDADES EXTRAESCOLARES", _CR),
    )),
    ("MASCOTAS", G, (
        ("ALIMENTO PARA MASCOTAS", _N), ("VETERINARIO", _N), ("ESTETICA DE MASCOTAS", _D),
        ("ACCESORIOS PARA MASCOTAS", _D),
    )),
    ("FINANZAS", G, (
        ("GASTOS FINANCIEROS", _C), ("INTERESES DE TARJETAS", _C), ("COMISIONES BANCARIAS", _C),
        ("ANUALIDADES", _C), ("INTERESES DE PRESTAMOS", _C), ("IMPUESTOS", _C), ("SEGURO DE VIDA", _E),
    )),
    ("REGALOS Y DONATIVOS", G, (
        ("REGALOS", _G), ("DONATIVOS", _G), ("CELEBRACIONES", _G), ("APOYO A FAMILIARES", _G),
    )),
    ("EFECTIVO", G, (
        ("RETIROS DE EFECTIVO", _N),
    )),
    ("VARIOS", G, (
        ("OTROS GASTOS", None), ("IMPREVISTOS", _E), ("MULTAS Y RECARGOS", _C),
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

# TALLY 0.6 reacomodó las clasificaciones (antes eran Necesidad, Disfrute, Estabilidad, Inversión y Dádivas).
RENOMBRES_0_6 = {"Inversión": "Crecimiento", "Dádivas": "Generosidad"}
NUEVAS_0_6 = ("Compromisos", "Antojos")
# Subcategoría del catálogo → (clasificación anterior, nueva). Solo se cambian las que el usuario no movió.
RECLASIFICACION_0_6 = {
    "COMIDA A DOMICILIO": ("Disfrute", "Antojos"),
    "SNACKS Y ANTOJOS": ("Disfrute", "Antojos"),
    "CAFETERIAS": ("Disfrute", "Antojos"),
    "PREDIAL": ("Necesidad", "Compromisos"),
    "TENENCIA Y VERIFICACION": ("Necesidad", "Compromisos"),
    "PAGO DEL AUTO": ("Necesidad", "Compromisos"),
    "EQUIPO DEPORTIVO": ("Disfrute", "Crecimiento"),
    "SERVICIOS DE SOFTWARE": ("Necesidad", "Crecimiento"),
    "LIBROS Y REVISTAS": ("Disfrute", "Crecimiento"),
    "LOTERIA Y APUESTAS": ("Disfrute", "Antojos"),
    "GASTOS FINANCIEROS": ("Necesidad", "Compromisos"),
    "INTERESES DE TARJETAS": ("Necesidad", "Compromisos"),
    "COMISIONES BANCARIAS": ("Necesidad", "Compromisos"),
    "ANUALIDADES": ("Necesidad", "Compromisos"),
    "INTERESES DE PRESTAMOS": ("Necesidad", "Compromisos"),
    "IMPUESTOS": ("Necesidad", "Compromisos"),
    "CELEBRACIONES": ("Disfrute", "Generosidad"),
    "IMPREVISTOS": (None, "Estabilidad"),
    "MULTAS Y RECARGOS": (None, "Compromisos"),
}
VERSION_CLASIFICACIONES = 2
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


def necesita_reclasificar(libro: Libro) -> bool:
    """True si los datos tienen las clasificaciones de antes de TALLY 0.6 (se revisa una sola vez)."""
    return libro.perfil is not None and libro.perfil.clasificaciones < VERSION_CLASIFICACIONES


def reclasificar(libro: Libro) -> None:
    """Pone al día las clasificaciones sin pisar lo que el usuario decidió.

    1. «Inversión» → «Crecimiento» y «Dádivas» → «Generosidad» (si siguen con ese nombre).
    2. Crea «Compromisos» y «Antojos» si no existen.
    3. Mueve las subcategorías del catálogo de :data:`RECLASIFICACION_0_6` **solo** si siguen en su clasificación
       original: las que el usuario ya había movido se quedan donde las puso.
    Se hace una sola vez: después el usuario puede acomodarlas como quiera.
    """
    grupos = {g.nombre: g for g in libro.grupos()}
    for viejo, nuevo in RENOMBRES_0_6.items():
        if viejo in grupos and not any(clave(n) == clave(nuevo) for n in grupos):
            grupos[nuevo] = libro.guardar_grupo(replace(grupos.pop(viejo), nombre=nuevo))
    orden = max((g.orden for g in grupos.values()), default=-1) + 1
    for nombre in NUEVAS_0_6:
        if not any(clave(n) == clave(nombre) for n in grupos):
            grupos[nombre] = libro.guardar_grupo(Grupo(libro.nuevo_id(), nombre, orden))
            orden += 1
    for posicion, nombre in enumerate(GRUPOS_INICIALES):                 # el orden sugerido
        if nombre in grupos and grupos[nombre].orden != posicion:
            grupos[nombre] = libro.guardar_grupo(replace(grupos[nombre], orden=posicion))
    nombre_de = {g.id: g.nombre for g in grupos.values()}
    for categoria in libro.categorias():
        cambio = RECLASIFICACION_0_6.get(categoria.nombre)
        if cambio is None:
            continue
        antes, despues = cambio
        actual = nombre_de.get(categoria.grupo_id)
        if actual == RENOMBRES_0_6.get(antes, antes) and despues in grupos:
            libro.guardar_categoria(replace(categoria, grupo_id=grupos[despues].id))
    libro.perfil = replace(libro.perfil, clasificaciones=VERSION_CLASIFICACIONES)


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
