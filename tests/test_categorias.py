from datetime import date

import pytest

from conftest import D, JULIO
from motor import categorias, movimientos, reportes
from motor.errores import ErrorValidacion
from motor.libro import Libro
from motor.modelo import CATEGORIA_AJUSTE, ClaseCategoria


def test_catalogo_inicial(libro):
    nombres = {g.nombre for g in libro.grupos()}
    assert nombres == set(categorias.GRUPOS_INICIALES)
    nomina = categorias.buscar(libro, "nómina")
    assert nomina.clase is ClaseCategoria.INGRESO and nomina.principal
    alimentos = categorias.buscar(libro, "Alimentos")
    assert libro.grupo(alimentos.grupo_id).nombre == "Necesidad"


def test_catalogo_inicial_no_se_duplica(libro):
    antes = len(libro.categorias())
    categorias.cargar_catalogo_inicial(libro)
    assert len(libro.categorias()) == antes


def test_libro_nuevo_solo_tiene_categorias_del_sistema():
    lib = Libro()
    assert {c.clase for c in lib.categorias()} == {ClaseCategoria.SISTEMA}


def test_nombres_se_normalizan_y_no_se_repiten(libro):
    cat = categorias.crear(libro, "  HARDWARE   & JUEGOS ", ClaseCategoria.GASTO)
    assert cat.nombre == "HARDWARE & JUEGOS"
    with pytest.raises(ErrorValidacion):
        categorias.crear(libro, "hardware & juegos", ClaseCategoria.GASTO)
    # El mismo nombre sí puede existir como ingreso.
    categorias.crear(libro, "Hardware & juegos", ClaseCategoria.INGRESO)
    with pytest.raises(ErrorValidacion):
        categorias.crear(libro, "   ", ClaseCategoria.GASTO)


def test_solo_ingresos_pueden_ser_principales(libro):
    with pytest.raises(ErrorValidacion):
        categorias.crear(libro, "Raro", ClaseCategoria.GASTO, principal=True)


def test_categorias_del_sistema_son_intocables(libro):
    with pytest.raises(ErrorValidacion):
        categorias.editar(libro, CATEGORIA_AJUSTE, nombre="Otra cosa")
    with pytest.raises(ErrorValidacion):
        categorias.eliminar(libro, CATEGORIA_AJUSTE)
    with pytest.raises(ErrorValidacion):
        categorias.crear(libro, "Sistema", ClaseCategoria.SISTEMA)


def test_editar_categoria_y_grupo(libro, cat):
    disfrute = next(g for g in libro.grupos() if g.nombre == "Disfrute")
    categorias.editar(libro, cat("Alimentos"), nombre="Comida", grupo_id=disfrute.id)
    comida = libro.categoria(cat("Comida"))
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


def test_eliminar_categoria_sin_uso(libro):
    nueva = categorias.crear(libro, "Temporal", ClaseCategoria.GASTO)
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
    assert total.nombre == "Alimentos" and total.total == D(165)


def test_fusion_une_partidas_de_un_gasto_repartido(libro, ctas, cat):
    op = movimientos.registrar_gasto(
        libro, date(2026, 7, 1), ctas.debito,
        reparto=[(cat("Alimentos"), 200), (cat("Snacks y antojos"), 50)],
    )
    categorias.eliminar(libro, cat("Snacks y antojos"), reasignar_a=cat("Alimentos"))
    actualizada = libro.operacion(op.id)
    assert len(actualizada.partidas) == 2
    assert movimientos.describir(actualizada).monto == D(250)


def test_archivar_categoria(libro, ctas, cat):
    categorias.archivar(libro, cat("Bonos"))
    with pytest.raises(ErrorValidacion, match="archivada"):
        movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("Bonos"), 100)
    categorias.reactivar(libro, cat("Bonos"))
    movimientos.registrar_ingreso(libro, date(2026, 7, 1), ctas.debito, cat("Bonos"), 100)
