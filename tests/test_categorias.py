from datetime import date

import pytest

from conftest import D, JULIO
from motor import catalogo, categorias, impuestos, movimientos, recurrentes, reportes
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import CATEGORIA_AJUSTE, ClaseCategoria


def rubro(libro, nombre):
    return categorias.buscar_rubro(libro, nombre).id


def test_catalogo_inicial(libro):
    nombres = {g.nombre for g in libro.grupos()}
    assert nombres == set(catalogo.GRUPOS_INICIALES)
    nomina = categorias.buscar(libro, "nómina")
    assert nomina.nombre == "NOMINA" and nomina.clase is ClaseCategoria.INGRESO and nomina.principal
    alimentos = categorias.buscar(libro, "Alimentos")
    assert libro.grupo(alimentos.grupo_id).nombre == "Necesidad"
    assert categorias.etiqueta(libro, alimentos.id) == "ALIMENTACION › ALIMENTOS"
    # Un universo amplio: todas las subcategorías viven en una categoría de su mismo tipo.
    assert len(libro.rubros()) >= 20 and len(libro.categorias()) >= 140
    for c in libro.categorias():
        if c.clase is not ClaseCategoria.SISTEMA:
            assert libro.rubro(c.rubro_id).clase is c.clase
    assert categorias.buscar(libro, "gimnasio").rubro_id == rubro(libro, "Deporte y bienestar")
    assert categorias.nombre_rubro(libro, categorias.buscar(libro, "Despensa").id) == "ALIMENTACION"


def test_catalogo_sin_repetidos_y_estandarizado():
    from motor.textos import clave, estandarizar

    rubros = [r for r, _, _ in catalogo.CATALOGO]
    subcategorias = [s for _, _, subs in catalogo.CATALOGO for s, _ in subs]
    for nombres in (rubros, subcategorias):
        assert len({clave(n) for n in nombres}) == len(nombres)
        assert all(n == estandarizar(n) for n in nombres)


def test_catalogo_inicial_no_se_duplica(libro):
    antes = len(libro.categorias())
    categorias.cargar_catalogo_inicial(libro)
    assert len(libro.categorias()) == antes


def test_libro_nuevo_solo_tiene_categorias_del_sistema():
    lib = Libro()
    assert {c.clase for c in lib.categorias()} == {ClaseCategoria.SISTEMA}


def test_nombres_en_mayusculas_sin_acentos_y_sin_repetir(libro):
    salud = rubro(libro, "Salud")
    cat = categorias.crear(libro, "  Ortodoncia   y  frenos ", salud)
    assert cat.nombre == "ORTODONCIA Y FRENOS" and cat.clase is ClaseCategoria.GASTO
    assert categorias.crear(libro, "Niñera de fin de semana", rubro(libro, "Hijos")).nombre == \
        "NIÑERA DE FIN DE SEMANA"
    assert categorias.crear(libro, "Clínica Médica", salud).nombre == "CLINICA MEDICA"
    # Mayúsculas, acentos, signos y espacios no hacen otra subcategoría…
    for repetida in ("ortodoncia y frenos", "Ortodóncia  Y  Frenos", "ORTODONCIA/Y-FRENOS"):
        with pytest.raises(ErrorValidacion, match="dos veces"):
            categorias.crear(libro, repetida, salud)
    # …ni aunque sea en otra categoría o de otro tipo: cada subcategoría existe una sola vez.
    with pytest.raises(ErrorValidacion, match="Ya existe la subcategoría «DENTISTA» \\(en SALUD\\)"):
        categorias.crear(libro, "dentísta", rubro(libro, "Varios"))
    with pytest.raises(ErrorValidacion):
        categorias.crear(libro, "Nomina", rubro(libro, "Ingresos varios"))
    with pytest.raises(ErrorValidacion):
        categorias.crear(libro, "   ", salud)
    with pytest.raises(ErrorValidacion, match="dos veces"):
        categorias.editar(libro, cat.id, nombre="gasolína")


def test_categorias_que_agrupan(libro):
    tecnologia = categorias.crear_rubro(libro, "Electrónica y gadgets", ClaseCategoria.GASTO)
    assert tecnologia.nombre == "ELECTRONICA Y GADGETS"
    with pytest.raises(ErrorValidacion, match="dos veces"):
        categorias.crear_rubro(libro, "electronica y GADGETS", ClaseCategoria.INGRESO)
    with pytest.raises(ErrorValidacion):
        categorias.crear_rubro(libro, "Sistema", ClaseCategoria.SISTEMA)
    drones = categorias.crear(libro, "Drones", tecnologia.id)
    categorias.renombrar_rubro(libro, tecnologia.id, "Gadgets")
    assert categorias.etiqueta(libro, drones.id) == "GADGETS › DRONES"

    # Mover una subcategoría solo a otra categoría del mismo tipo.
    with pytest.raises(ErrorValidacion):
        categorias.editar(libro, drones.id, rubro_id=rubro(libro, "Ingresos varios"))
    categorias.editar(libro, drones.id, rubro_id=rubro(libro, "Tecnologia"))
    assert libro.categoria(drones.id).rubro_id == rubro(libro, "Tecnologia")

    # Borrar una categoría con subcategorías exige decir a dónde pasan (con todo y movimientos).
    with pytest.raises(ErrorValidacion):
        categorias.eliminar_rubro(libro, rubro(libro, "Mascotas"))
    veterinario = categorias.buscar(libro, "Veterinario").id
    categorias.eliminar_rubro(libro, rubro(libro, "Mascotas"), mover_a=rubro(libro, "Salud"))
    assert categorias.buscar_rubro(libro, "Mascotas") is None
    assert libro.categoria(veterinario).rubro_id == rubro(libro, "Salud")
    categorias.eliminar_rubro(libro, rubro(libro, "Gadgets"))          # vacía: se borra sin más


def test_solo_ingresos_pueden_ser_principales(libro):
    with pytest.raises(ErrorValidacion):
        categorias.crear(libro, "Raro", rubro(libro, "Varios"), principal=True)
    with pytest.raises(ErrorValidacion, match="Elige en qué categoría"):
        categorias.crear(libro, "Sin caja", None)


def test_categorias_del_sistema_son_intocables(libro):
    with pytest.raises(ErrorValidacion):
        categorias.editar(libro, CATEGORIA_AJUSTE, nombre="Otra cosa")
    with pytest.raises(ErrorValidacion):
        categorias.eliminar(libro, CATEGORIA_AJUSTE)
    with pytest.raises(ErrorValidacion):
        categorias.crear(libro, "Sistema", None)


def test_editar_categoria_y_grupo(libro, cat):
    disfrute = next(g for g in libro.grupos() if g.nombre == "Disfrute")
    categorias.editar(libro, cat("Alimentos"), nombre="Comida", grupo_id=disfrute.id)
    comida = libro.categoria(cat("Comida"))
    assert comida.nombre == "COMIDA"
    assert comida.grupo_id == disfrute.id
    categorias.editar(libro, comida.id, grupo_id=None)
    assert libro.categoria(comida.id).grupo_id is None


def test_grupos_editables(libro, cat):
    grupo = categorias.crear_grupo(libro, "Metas 2027")
    categorias.renombrar_grupo(libro, grupo.id, "Metas 2028")
    categorias.editar(libro, cat("Regalos"), grupo_id=grupo.id)
    categorias.eliminar_grupo(libro, grupo.id)
    assert libro.categoria(cat("Regalos")).grupo_id is None
    with pytest.raises(ErrorValidacion):
        categorias.crear_grupo(libro, "necesidad")
    with pytest.raises(ErrorValidacion):
        categorias.crear_grupo(libro, "ANTOJOS")        # sin importar mayúsculas


def test_eliminar_categoria_sin_uso(libro):
    nueva = categorias.crear(libro, "Temporal", rubro(libro, "Varios"))
    categorias.eliminar(libro, nueva.id)
    assert categorias.buscar(libro, "Temporal") is None


def test_eliminar_categoria_en_uso_exige_reasignar(libro, ctas, cat):
    snacks, alimentos = cat("Snacks y antojos"), cat("Alimentos")
    movimientos.registrar_gasto(libro, date(2026, 7, 1), ctas.debito, snacks, 65)
    movimientos.registrar_gasto(libro, date(2026, 7, 2), ctas.debito, alimentos, 100)
    with pytest.raises(ErrorValidacion):
        categorias.eliminar(libro, snacks)
    with pytest.raises(ErrorValidacion):
        categorias.eliminar(libro, snacks, reasignar_a=cat("Nómina"))

    categorias.eliminar(libro, snacks, reasignar_a=alimentos)
    (total,) = reportes.gastos_por_categoria(libro, *JULIO)
    assert total.nombre == "ALIMENTOS" and total.total == D(165)


def test_fusion_une_partidas_de_un_gasto_repartido(libro, ctas, cat):
    op = movimientos.registrar_gasto(
        libro, date(2026, 7, 1), ctas.debito,
        reparto=[(cat("Alimentos"), 200), (cat("Snacks y antojos"), 50)],
    )
    categorias.eliminar(libro, cat("Snacks y antojos"), reasignar_a=cat("Alimentos"))
    actualizada = libro.operacion(op.id)
    assert len(actualizada.partidas) == 2
    assert movimientos.describir(actualizada).monto == D(250)


def test_borrar_o_juntar_una_subcategoria_actualiza_los_gastos_deducibles(libro, cat):
    lentes = categorias.crear(libro, "Lentes ficticios", rubro(libro, "Salud")).id
    otra = categorias.crear(libro, "Otra ficticia", rubro(libro, "Salud")).id
    impuestos.guardar_concepto(libro, "Médicos", [cat("Dentista"), lentes])
    impuestos.guardar_concepto(libro, "Solo lentes", [lentes, otra])
    categorias.eliminar(libro, lentes, reasignar_a=cat("Dentista"))           # juntarla: pasa a la otra, sin repetir
    medicos, solo = libro.fiscal.conceptos
    assert medicos.subcategorias == (cat("Dentista"),)
    assert solo.subcategorias == (cat("Dentista"), otra)
    categorias.eliminar(libro, otra)                                          # borrarla sin más: se quita
    assert libro.fiscal.conceptos[1].subcategorias == (cat("Dentista"),)
    with pytest.raises(ErrorValidacion, match="mismo tipo"):
        categorias.eliminar(libro, cat("Dentista"), reasignar_a=cat("Nómina"))


def test_borrar_la_subcategoria_de_un_pago_fijo_lo_deja_sin_elegir(libro, ctas):
    sueldo = categorias.crear(libro, "Sueldo ficticio", rubro(libro, "Sueldo y prestaciones")).id
    r = recurrentes.crear(libro, "Sueldo", "ingreso", 9_000, ctas.debito, "quincenal", date(2026, 1, 1),
                          categoria_id=sueldo)
    categorias.eliminar(libro, sueldo)
    r = libro.recurrente(r.id)
    assert (r.categoria_id, r.activa) == (None, False)


def test_archivar_categoria(libro, ctas, cat):
    categorias.archivar(libro, cat("Bonos"))
    with pytest.raises(ErrorValidacion, match="archivada"):
        movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("Bonos"), 100)
    categorias.reactivar(libro, cat("Bonos"))
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("Bonos"), 100)


def test_una_subcategoria_esta_en_una_sola_clasificacion(libro, cat):
    grupo = {g.nombre: g.id for g in libro.grupos()}
    snacks = cat("SNACKS Y ANTOJOS")
    with pytest.raises(ErrorValidacion, match="ya está en «Antojos»"):
        categorias.clasificar(libro, snacks, grupo["Disfrute"])
    categorias.clasificar(libro, snacks, None)                     # se quita de Antojos…
    categorias.clasificar(libro, snacks, grupo["Disfrute"])        # …y ya se puede poner en Disfrute
    assert libro.categoria(snacks).grupo_id == grupo["Disfrute"]
    categorias.clasificar(libro, snacks, grupo["Disfrute"])        # ponerla donde ya está no es error
