"""Puesta al día de datos de TALLY 0.3 (sin subcategorías) y «empezar de cero». Datos ficticios."""

import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date

import pytest

from conftest import AHORA
from motor import auditoria, catalogo, categorias, cuentas, movimientos, perfil, reportes, respaldos
from motor.libro import Libro
from motor.modelo import Categoria, ClaseCategoria, Grupo
from motor.persistencia import VERSION_ESQUEMA, Almacen
from motor.serializacion import instantanea
from motor.sesion import Sesion


def reloj():
    return AHORA


# Así guardaba TALLY 0.3 el catálogo: nombres con acentos y minúsculas, sin categorías que agrupen.
CATALOGO_03 = (
    ("Nómina", ClaseCategoria.INGRESO, None, True), ("Intereses y rendimientos", ClaseCategoria.INGRESO, None, False),
    ("Alimentos", ClaseCategoria.GASTO, "Necesidad", False), ("Transporte", ClaseCategoria.GASTO, "Necesidad", False),
    ("Educación", ClaseCategoria.GASTO, "Inversión", False), ("Otros gastos", ClaseCategoria.GASTO, None, False),
    # Creadas por el usuario: una de gasto, una de ingreso y dos que chocan al quitar acentos.
    ("Clases de cerámica", ClaseCategoria.GASTO, "Disfrute", False), ("Venta de garage", ClaseCategoria.INGRESO, None, False),
    ("Café", ClaseCategoria.GASTO, "Disfrute", False), ("Cafe", ClaseCategoria.GASTO, None, False),
)


def libro_03() -> Libro:
    libro = Libro(reloj=reloj)
    for nombre, cat_id in (("Ajuste de saldo", "sistema-ajuste"), ("Saldo inicial", "sistema-saldo-inicial")):
        libro.guardar_categoria(Categoria(cat_id, nombre, ClaseCategoria.SISTEMA, orden=-1))
    grupos = {}
    for orden, nombre in enumerate(("Necesidad", "Disfrute", "Inversión")):
        grupos[nombre] = libro.guardar_grupo(Grupo(f"g{orden}", nombre, orden)).id
    for orden, (nombre, clase, grupo, principal) in enumerate(CATALOGO_03):
        libro.guardar_categoria(Categoria(f"c{orden}", nombre, clase, grupo_id=grupos.get(grupo),
                                          principal=principal, orden=orden))
    perfil.configurar(libro, "Usuario Ficticio")
    debito = cuentas.crear(libro, "Débito Ficticio", "debito", saldo_inicial=1000, fecha_creacion=date(2026, 7, 1)).id
    for categoria_id, monto in (("c2", 120), ("c6", 300), ("c8", 45), ("c9", 30), ("c3", 80)):
        movimientos.registrar_gasto(libro, date(2026, 7, 5), debito, categoria_id, monto)
    for categoria_id, monto in (("c0", 5000), ("c7", 250)):
        movimientos.registrar_ingreso(libro, date(2026, 7, 15), debito, categoria_id, monto)
    return libro


def archivo_03(ruta):
    """Un tally.db escrito como lo dejaba TALLY 0.3 (esquema 1)."""
    almacen = Almacen(ruta)
    almacen.cargar(reloj=reloj)
    almacen.guardar(libro_03())
    with closing(sqlite3.connect(ruta)) as conexion, conexion:
        conexion.execute("UPDATE meta SET valor = '1' WHERE clave = 'version_esquema'")
    return ruta


def gasto_por_subcategoria(libro):
    return {t.categoria_id: t.total for t in reportes.gastos_por_categoria(libro, date(2026, 7, 1), date(2026, 7, 31))}


def test_datos_de_la_03_se_ponen_al_dia_sin_perder_nada(tmp_path):
    ruta = archivo_03(tmp_path / "tally.db")
    antes = Almacen(ruta).cargar(reloj=reloj)
    gastos_antes = gasto_por_subcategoria(antes)
    saldo_antes = antes.saldo_centavos(cuentas.buscar(antes, "Débito Ficticio").id)

    libro = Sesion(ruta, reloj=reloj).libro

    nombres = {c.id: c.nombre for c in libro.categorias()}
    assert nombres["c0"] == "NOMINA" and libro.categoria("c0").principal
    assert nombres["c4"] == "EDUCACION" and libro.grupo(libro.categoria("c4").grupo_id).nombre == "Inversión"
    assert nombres["c6"] == "CLASES DE CERAMICA"
    assert (nombres["c8"], nombres["c9"]) == ("CAFE", "CAFE (2)")          # no se juntan solas
    assert nombres["sistema-ajuste"] == "AJUSTE DE SALDO"
    # Cada una en su caja: las del catálogo en la suya, las del usuario en VARIOS / INGRESOS VARIOS.
    assert categorias.nombre_rubro(libro, "c2") == "ALIMENTACION"
    assert categorias.nombre_rubro(libro, "c3") == "MOVILIDAD"
    assert categorias.nombre_rubro(libro, "c6") == "VARIOS"
    assert categorias.nombre_rubro(libro, "c7") == "INGRESOS VARIOS"
    assert libro.categoria("sistema-ajuste").rubro_id is None
    # Llega el universo de subcategorías y ninguna queda repetida.
    assert categorias.buscar(libro, "Gimnasio") and categorias.buscar(libro, "Despensa")
    claves = Counter(categorias.clave(c.nombre) for c in libro.categorias())
    assert max(claves.values()) == 1
    assert not catalogo.necesita_actualizar(libro)
    # Los movimientos y saldos quedan idénticos.
    assert gasto_por_subcategoria(libro) == gastos_antes
    assert libro.saldo_centavos(cuentas.buscar(libro, "Débito Ficticio").id) == saldo_antes
    assert len(libro.operaciones()) == len(antes.operaciones())


def test_la_puesta_al_dia_queda_en_la_bitacora_y_solo_ocurre_una_vez(tmp_path):
    ruta = archivo_03(tmp_path / "tally.db")
    sesion = Sesion(ruta, reloj=reloj)
    registros = sesion.almacen.bitacora()
    assert any(r.entidad == "categoria" and r.accion == auditoria.EDITAR and r.antes["nombre"] == "Nómina"
               for r in registros)
    assert any(r.entidad == "rubro" and r.accion == auditoria.CREAR for r in registros)
    estado = instantanea(sesion.libro)

    otra = Sesion(ruta, reloj=reloj)                       # al volver a abrir no cambia nada
    assert instantanea(otra.libro) == estado
    assert len(otra.almacen.bitacora()) == len(registros)
    with closing(sqlite3.connect(ruta)) as conexion:
        assert conexion.execute("SELECT valor FROM meta WHERE clave='version_esquema'").fetchone() == \
            (str(VERSION_ESQUEMA),)


def test_lo_que_el_usuario_borro_no_regresa(tmp_path):
    sesion = Sesion(tmp_path / "tally.db", reloj=reloj)
    with sesion.cambio() as libro:
        categorias.eliminar(libro, categorias.buscar(libro, "Lotería y apuestas").id)
    assert categorias.buscar(Sesion(tmp_path / "tally.db", reloj=reloj).libro, "Loteria y apuestas") is None


def test_restaurar_un_respaldo_de_la_03_lo_pone_al_dia(tmp_path):
    # Un respaldo con el contenido de la 0.3 (sin rubros), escrito directo desde el almacén.
    datos_03 = Almacen(tmp_path / "otra.db")
    datos_03.cargar(reloj=reloj)
    datos_03.guardar(libro_03())
    respaldo = respaldos._crear_desde(datos_03, AHORA, tmp_path / "TALLY_respaldo_03.zip", "x")

    actual = Sesion(tmp_path / "actual.db", reloj=reloj)
    respaldos.restaurar(actual, respaldo, carpeta_seguridad=tmp_path / "seguridad")
    assert actual.libro.categoria("c0").nombre == "NOMINA"
    assert categorias.nombre_rubro(actual.libro, "c6") == "VARIOS"
    assert not catalogo.necesita_actualizar(Sesion(tmp_path / "actual.db", reloj=reloj).libro)


def test_empezar_de_cero(tmp_path):
    sesion = Sesion(tmp_path / "Datos" / "tally.db", reloj=reloj)
    with sesion.cambio() as libro:
        perfil.configurar(libro, "Usuario Ficticio")
        debito = cuentas.crear(libro, "Débito Ficticio", "debito", saldo_inicial=700).id
        movimientos.registrar_gasto(libro, date(2026, 7, 5), debito, categorias.buscar(libro, "Despensa").id, 90)
        categorias.crear_rubro(libro, "Mi caja", ClaseCategoria.GASTO)
    antes = instantanea(sesion.libro)

    seguridad = respaldos.empezar_de_cero(sesion, carpeta_seguridad=tmp_path / "Respaldos")

    for libro in (sesion.libro, Sesion(tmp_path / "Datos" / "tally.db", reloj=reloj).libro):
        assert perfil.necesita_bienvenida(libro)                      # vuelve el «¡Hola!»
        assert libro.cuentas() == [] and libro.operaciones() == []
        assert categorias.buscar_rubro(libro, "Mi caja") is None
        assert categorias.buscar(libro, "Despensa") is not None      # catálogo de fábrica
    (registro,) = sesion.almacen.bitacora()
    assert "Empezó de cero" in auditoria.resumen(registro) and seguridad.name in auditoria.resumen(registro)
    # Todo lo anterior se recupera con el respaldo.
    assert seguridad.name.startswith("TALLY_antes_de_empezar_de_cero_")
    respaldos.restaurar(sesion, seguridad, carpeta_seguridad=tmp_path / "Respaldos")
    assert instantanea(sesion.libro) == antes


def test_sin_respaldo_no_se_borra_nada(tmp_path, monkeypatch):
    sesion = Sesion(tmp_path / "tally.db", reloj=reloj)
    with sesion.cambio() as libro:
        perfil.configurar(libro, "Usuario Ficticio")
    monkeypatch.setattr(respaldos, "crear", lambda *a, **k: (_ for _ in ()).throw(OSError("disco lleno")))
    with pytest.raises(OSError):
        respaldos.empezar_de_cero(sesion)
    assert Sesion(tmp_path / "tally.db", reloj=reloj).libro.perfil.nombre == "Usuario Ficticio"
