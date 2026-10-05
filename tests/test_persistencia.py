import sqlite3
from datetime import date

import pytest

from conftest import AHORA, D
from motor import auditoria, categorias, cuentas, movimientos, perfil, rutas
from motor.errores import ErrorDatos, ErrorNoEncontrado, ErrorValidacion
from motor.persistencia import Almacen
from motor.serializacion import instantanea, libro_desde_instantanea
from motor.sesion import Sesion
from motor.transferencias import registrar_transferencia


def reloj():
    return AHORA


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "Datos" / "tally.db"


def poblar(sesion):
    with sesion.cambio() as libro:
        perfil.configurar(libro, "Usuario Ficticio")
        debito = cuentas.crear(libro, "Débito", "debito", saldo_inicial=1000, fecha_creacion=date(2026, 7, 1)).id
        ahorro = cuentas.crear(libro, "Ahorro", "ahorro", fecha_creacion=date(2026, 7, 1)).id
        tdc = cuentas.crear(libro, "TDC", "credito", limite_credito=5000, dia_corte=3, fecha_creacion=date(2026, 7, 1)).id
        alimentos = categorias.buscar(libro, "Alimentos").id
        movimientos.registrar_gasto(libro, date(2026, 7, 2), tdc, alimentos, "123.45", "Pizza", "nota")
        movimientos.registrar_gasto(
            libro, date(2026, 7, 3), debito, reparto=[(alimentos, 10), (categorias.buscar(libro, "Regalos").id, 5)]
        )
        registrar_transferencia(libro, date(2026, 7, 4), debito, ahorro, 300)
        cuentas.archivar(libro, ahorro)
    return debito, ahorro, tdc


def test_sesion_nueva_crea_archivo_y_catalogo(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    assert ruta.exists()
    assert categorias.buscar(sesion.libro, "Nómina") is not None
    assert perfil.necesita_bienvenida(sesion.libro)


def test_todo_sobrevive_a_cerrar_y_abrir(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    poblar(sesion)
    antes = instantanea(sesion.libro)

    reabierta = Sesion(ruta, reloj=reloj)
    assert instantanea(reabierta.libro) == antes
    assert reabierta.libro.secuencia == sesion.libro.secuencia
    assert reabierta.libro.perfil.nombre == "Usuario Ficticio"
    assert not perfil.necesita_bienvenida(reabierta.libro)
    # El catálogo no se vuelve a cargar al reabrir.
    assert len(reabierta.libro.categorias()) == len(sesion.libro.categorias())


def test_el_orden_de_captura_se_conserva_tras_reabrir(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    debito, _, _ = poblar(sesion)
    reabierta = Sesion(ruta, reloj=reloj)
    with reabierta.cambio() as libro:
        nueva = movimientos.registrar_gasto(libro, date(2026, 7, 2), debito, categorias.buscar(libro, "Alimentos").id, 1)
    assert nueva.secuencia > max(op.secuencia for op in sesion.libro.operaciones())


def test_cambio_fallido_no_deja_nada_a_medias(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    debito, _, _ = poblar(sesion)
    antes = instantanea(sesion.libro)
    with pytest.raises(ErrorNoEncontrado):
        with sesion.cambio() as libro:
            movimientos.registrar_gasto(libro, date(2026, 7, 5), debito, categorias.buscar(libro, "Alimentos").id, 50)
            movimientos.registrar_gasto(libro, date(2026, 7, 5), debito, "no-existe", 50)
    assert instantanea(sesion.libro) == antes
    assert instantanea(Sesion(ruta, reloj=reloj).libro) == antes


def test_validacion_fallida_en_sesion(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    with pytest.raises(ErrorValidacion):
        with sesion.cambio() as libro:
            cuentas.crear(libro, "", "debito")
    assert cuentas.listar(sesion.libro) == []


def test_bitacora_registra_antes_y_despues(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    debito, _, _ = poblar(sesion)
    with sesion.cambio() as libro:
        op = movimientos.registrar_gasto(libro, date(2026, 7, 9), debito, categorias.buscar(libro, "Alimentos").id, 80)
    with sesion.cambio() as libro:
        movimientos.editar(libro, op.id, monto=95, descripcion="Corregido")
    with sesion.cambio() as libro:
        movimientos.eliminar(libro, op.id)

    historial = sesion.almacen.bitacora(entidad="operacion", entidad_id=op.id, mas_recientes_primero=False)
    assert [r.accion for r in historial] == [auditoria.CREAR, auditoria.EDITAR, auditoria.BORRAR]
    assert all(r.fecha_hora == AHORA.isoformat(timespec="seconds") for r in historial)
    edicion = auditoria.campos_modificados(historial[1])
    assert edicion["descripcion"] == ("", "Corregido")
    assert historial[2].antes["descripcion"] == "Corregido"  # copia completa de lo borrado
    assert historial[2].despues is None
    assert len(sesion.almacen.bitacora(limite=2)) == 2


def test_sin_cambios_no_se_escribe_nada(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    total = len(sesion.almacen.bitacora())
    with sesion.cambio():
        pass
    assert len(sesion.almacen.bitacora()) == total


def test_otra_ventana_modifico_los_datos(ruta):
    ventana_a = Sesion(ruta, reloj=reloj)
    ventana_b = Sesion(ruta, reloj=reloj)
    with ventana_a.cambio() as libro:
        cuentas.crear(libro, "Débito", "debito")
    with pytest.raises(ErrorDatos, match="otra ventana"):
        with ventana_b.cambio() as libro:
            cuentas.crear(libro, "Efectivo", "efectivo")
    ventana_b.recargar()
    with ventana_b.cambio() as libro:
        cuentas.crear(libro, "Efectivo", "efectivo")
    assert {c.nombre for c in Sesion(ruta).libro.cuentas()} == {"Débito", "Efectivo"}


def test_archivo_que_no_es_base_de_datos(ruta):
    ruta.parent.mkdir(parents=True)
    ruta.write_bytes(b"esto no es sqlite" * 100)
    with pytest.raises(ErrorDatos):
        Sesion(ruta)


def test_datos_que_no_cuadran_se_detectan(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    poblar(sesion)
    with sqlite3.connect(ruta) as conexion:
        conexion.execute(
            "UPDATE entidades SET datos = replace(datos, '\"importe\": 12345', '\"importe\": 99999') "
            "WHERE tipo = 'operacion'"
        )
    with pytest.raises(ErrorDatos, match="no cuadran"):
        Sesion(ruta)


def test_version_de_esquema_mas_nueva(ruta):
    Sesion(ruta)
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("UPDATE meta SET valor = '999' WHERE clave = 'version_esquema'")
    with pytest.raises(ErrorDatos, match="más nueva"):
        Sesion(ruta)


def test_instantanea_ida_y_vuelta(ruta):
    sesion = Sesion(ruta, reloj=reloj)
    poblar(sesion)
    copia = libro_desde_instantanea(instantanea(sesion.libro), sesion.libro.secuencia)
    assert instantanea(copia) == instantanea(sesion.libro)
    assert cuentas.saldo(copia, cuentas.buscar(copia, "Débito").id) == D(1000 - 15 - 300)


def test_almacen_libro_guardado_es_independiente(ruta):
    almacen = Almacen(ruta)
    libro = almacen.cargar()
    cuentas.crear(libro, "Sin guardar", "debito")
    assert cuentas.listar(almacen.libro_guardado()) == []


def test_rutas_por_defecto(monkeypatch, tmp_path):
    monkeypatch.setenv("TALLY_RAIZ", str(tmp_path))
    assert rutas.archivo_datos() == tmp_path / "Datos" / "tally.db"
    assert rutas.carpeta_respaldos() == tmp_path / "Respaldos"
    sesion = Sesion.abrir()
    assert sesion.almacen.ruta == tmp_path / "Datos" / "tally.db"


def test_rutas_instalado(monkeypatch):
    monkeypatch.delenv("TALLY_RAIZ", raising=False)
    raiz = rutas.raiz()
    assert (raiz / "motor").is_dir()  # en desarrollo, la raíz es el repositorio
