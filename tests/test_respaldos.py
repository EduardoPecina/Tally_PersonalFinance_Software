import json
import zipfile
from datetime import date

import pytest

from conftest import AHORA, D
from motor import auditoria, categorias, cuentas, movimientos, perfil, respaldos
from motor.errores import ErrorDatos
from motor.serializacion import instantanea
from motor.sesion import Sesion


def reloj():
    return AHORA


@pytest.fixture
def sesion(tmp_path):
    s = Sesion(tmp_path / "Datos" / "tally.db", reloj=reloj)
    with s.cambio() as libro:
        perfil.configurar(libro, "Usuario Ficticio")
        debito = cuentas.crear(libro, "Débito", "debito", saldo_inicial=500, fecha_creacion=date(2026, 7, 1)).id
        movimientos.registrar_gasto(libro, date(2026, 7, 3), debito, categorias.buscar(libro, "Alimentos").id, 120)
    return s


def test_crear_e_inspeccionar(sesion, tmp_path):
    ruta = respaldos.crear(sesion, tmp_path / "Respaldos")
    assert ruta.name == "TALLY_respaldo_2026-07-20_120000.zip"
    info = respaldos.inspeccionar(ruta)
    assert (info.perfil, info.cuentas, info.movimientos) == ("Usuario Ficticio", 1, 2)
    assert (info.primera_fecha, info.ultima_fecha) == ("2026-07-01", "2026-07-03")
    assert info.creado_en == "2026-07-20T12:00:00"
    # Mismo minuto: no se sobrescribe, se usa otro nombre.
    assert respaldos.crear(sesion, tmp_path / "Respaldos").name == "TALLY_respaldo_2026-07-20_120000_2.zip"


def test_crear_en_ruta_elegida(sesion, tmp_path):
    destino = tmp_path / "USB" / "mis_finanzas.zip"
    assert respaldos.crear(sesion, destino) == destino
    assert destino.exists()
    assert not list(destino.parent.glob("*.tmp"))


def test_restaurar_recupera_todo_y_crea_respaldo_de_seguridad(sesion, tmp_path):
    respaldo = respaldos.crear(sesion, tmp_path / "Respaldos")
    original = instantanea(sesion.libro)
    with sesion.cambio() as libro:
        movimientos.registrar_gasto(libro, date(2026, 7, 9), cuentas.buscar(libro, "Débito").id,
                                    categorias.buscar(libro, "Alimentos").id, 999)
        perfil.configurar(libro, "Otro")

    resultado = respaldos.restaurar(sesion, respaldo, carpeta_seguridad=tmp_path / "Respaldos")

    assert instantanea(sesion.libro) == original
    assert resultado.respaldo_de_seguridad.name.startswith("TALLY_antes_de_restaurar_")
    assert respaldos.inspeccionar(resultado.respaldo_de_seguridad).movimientos == 3
    # Persistido: al reabrir sigue restaurado y la bitácora lo anota.
    reabierta = Sesion(sesion.almacen.ruta, reloj=reloj)
    assert instantanea(reabierta.libro) == original
    ultimo = reabierta.almacen.bitacora(limite=1)[0]
    assert ultimo.accion == auditoria.RESTAURAR and ultimo.despues["archivo"] == respaldo.name
    # Y se puede seguir trabajando normalmente.
    with sesion.cambio() as libro:
        cuentas.crear(libro, "Nueva", "efectivo")


def test_restaurar_en_otra_pc(sesion, tmp_path):
    respaldo = respaldos.crear(sesion, tmp_path / "Respaldos")
    otra_pc = Sesion(tmp_path / "OtraPC" / "Datos" / "tally.db", reloj=reloj)
    respaldos.restaurar(otra_pc, respaldo, carpeta_seguridad=tmp_path / "OtraPC" / "Respaldos")
    assert instantanea(otra_pc.libro) == instantanea(sesion.libro)
    assert cuentas.saldo(otra_pc.libro, cuentas.buscar(otra_pc.libro, "Débito").id) == D(380)


def test_respaldo_daniado_no_cambia_nada(sesion, tmp_path):
    respaldo = respaldos.crear(sesion, tmp_path / "Respaldos")
    alterado = tmp_path / "alterado.zip"
    with zipfile.ZipFile(respaldo) as origen, zipfile.ZipFile(alterado, "w") as destino:
        destino.writestr(respaldos.MANIFIESTO, origen.read(respaldos.MANIFIESTO))
        destino.writestr(respaldos.DATOS, origen.read(respaldos.DATOS).replace(b"Usuario", b"Usuaria"))
    antes = instantanea(sesion.libro)
    seguridad = tmp_path / "Seguridad"
    with pytest.raises(ErrorDatos, match="huella"):
        respaldos.restaurar(sesion, alterado, carpeta_seguridad=seguridad)
    assert instantanea(sesion.libro) == antes
    assert not seguridad.exists()  # ni siquiera se creó el respaldo de seguridad


@pytest.mark.parametrize("contenido", [b"no es un zip", None])
def test_archivos_que_no_son_respaldos(tmp_path, contenido):
    ruta = tmp_path / "x.zip"
    if contenido is None:
        with zipfile.ZipFile(ruta, "w") as zz:
            zz.writestr("otra_cosa.txt", "hola")
    else:
        ruta.write_bytes(contenido)
    with pytest.raises(ErrorDatos):
        respaldos.inspeccionar(ruta)
    with pytest.raises(ErrorDatos):
        respaldos.inspeccionar(tmp_path / "no_existe.zip")


def test_respaldo_de_version_mas_nueva(sesion, tmp_path):
    respaldo = respaldos.crear(sesion, tmp_path / "Respaldos")
    nuevo = tmp_path / "nuevo.zip"
    with zipfile.ZipFile(respaldo) as origen, zipfile.ZipFile(nuevo, "w") as destino:
        manifiesto = json.loads(origen.read(respaldos.MANIFIESTO))
        manifiesto["version_formato"] = 99
        destino.writestr(respaldos.MANIFIESTO, json.dumps(manifiesto))
        destino.writestr(respaldos.DATOS, origen.read(respaldos.DATOS))
    with pytest.raises(ErrorDatos, match="más nueva"):
        respaldos.inspeccionar(nuevo)


def test_respaldo_automatico_rota(sesion, tmp_path):
    carpeta = tmp_path / "Respaldos"
    for _ in range(5):
        respaldos.respaldo_automatico(sesion, carpeta, conservar=3)
    respaldos.crear(sesion, carpeta)  # los manuales no se borran
    assert len(list(carpeta.glob("TALLY_automatico_*.zip"))) == 3
    assert len(list(carpeta.glob("TALLY_respaldo_*.zip"))) == 1


def test_los_de_seguridad_rotan_por_tipo(sesion, tmp_path):
    carpeta = tmp_path / "Respaldos"
    for _ in range(12):                                   # todos en el mismo segundo (reloj fijo)
        ultimo = respaldos.de_seguridad(sesion, "antes_de_cargar_datos", carpeta)
    respaldos.de_seguridad(sesion, "antes_de_restaurar", carpeta)
    for _ in range(7):
        respaldos.respaldar_archivo_de_datos(sesion.almacen.ruta, carpeta)
    respaldos.crear(sesion, carpeta)                      # los guardados a mano no se tocan
    assert len(list(carpeta.glob("TALLY_antes_de_cargar_datos_*.zip"))) == respaldos.DE_SEGURIDAD_A_CONSERVAR
    assert ultimo.exists()                                # nunca se borra el que se acaba de crear
    assert len(list(carpeta.glob("TALLY_antes_de_restaurar_*.zip"))) == 1
    assert len(list(carpeta.glob("TALLY_antes_de_actualizar_*.zip"))) == respaldos.DE_SEGURIDAD_A_CONSERVAR
    assert len(list(carpeta.glob("TALLY_respaldo_*.zip"))) == 1


def test_restaurar_y_empezar_de_cero_rotan_su_respaldo(sesion, tmp_path):
    carpeta = tmp_path / "Respaldos"
    respaldo = respaldos.crear(sesion, tmp_path / "otro")
    for _ in range(7):
        respaldos.restaurar(sesion, respaldo, carpeta_seguridad=carpeta)
        respaldos.empezar_de_cero(sesion, carpeta_seguridad=carpeta)
    assert len(list(carpeta.glob("TALLY_antes_de_restaurar_*.zip"))) == 5
    assert len(list(carpeta.glob("TALLY_antes_de_empezar_de_cero_*.zip"))) == 5


def test_respaldar_archivo_sin_modificarlo(sesion, tmp_path):
    ruta = sesion.almacen.ruta
    antes = ruta.read_bytes()
    respaldo = respaldos.respaldar_archivo_de_datos(ruta, tmp_path / "Respaldos")
    assert respaldo.name.startswith("TALLY_antes_de_actualizar_")
    assert respaldos.inspeccionar(respaldo).movimientos == 2
    assert ruta.read_bytes() == antes
    assert respaldos.respaldar_archivo_de_datos(tmp_path / "no_hay.db", tmp_path / "Respaldos") is None


def test_copiar_archivo_de_datos_identico(sesion, tmp_path):
    origen = sesion.almacen.ruta
    antes = origen.read_bytes()
    destino = respaldos.copiar_archivo_de_datos(origen, tmp_path / "Nueva" / "Datos" / "tally.db")
    copia = Sesion(destino, reloj=reloj)
    assert instantanea(copia.libro) == instantanea(sesion.libro)
    assert len(copia.almacen.bitacora()) == len(sesion.almacen.bitacora())
    assert origen.read_bytes() == antes                           # el original no se toca
    assert [p.name for p in destino.parent.iterdir()] == ["tally.db"]


def test_copiar_archivo_de_datos_no_sobrescribe(sesion, tmp_path):
    destino = tmp_path / "Nueva" / "tally.db"
    destino.parent.mkdir()
    destino.write_bytes(b"otros datos")
    with pytest.raises(ErrorDatos, match="no se sobrescribe"):
        respaldos.copiar_archivo_de_datos(sesion.almacen.ruta, destino)
    assert destino.read_bytes() == b"otros datos"


def test_copiar_archivo_danado_no_deja_nada(tmp_path):
    origen = tmp_path / "danado.db"
    origen.write_bytes(b"esto no es una base de datos" * 50)
    destino = tmp_path / "Nueva" / "tally.db"
    with pytest.raises(ErrorDatos):
        respaldos.copiar_archivo_de_datos(origen, destino)
    assert list(destino.parent.iterdir()) == []


def test_copia_que_no_coincide_no_toma_el_nombre_final(sesion, tmp_path, monkeypatch):
    import sqlite3
    from contextlib import closing

    copiar = respaldos._copia_de_lectura
    llamadas = []

    def copiar_y_perder_un_registro(origen, destino):
        copiar(origen, destino)
        llamadas.append(destino)
        if len(llamadas) == 1:                               # la copia que se iba a quedar sale incompleta
            with closing(sqlite3.connect(destino)) as conexion, conexion:
                conexion.execute("DELETE FROM bitacora WHERE id = (SELECT MAX(id) FROM bitacora)")

    monkeypatch.setattr(respaldos, "_copia_de_lectura", copiar_y_perder_un_registro)
    destino = tmp_path / "Nueva" / "tally.db"
    with pytest.raises(ErrorDatos, match="no coincide"):
        respaldos.copiar_archivo_de_datos(sesion.almacen.ruta, destino)
    assert list(destino.parent.iterdir()) == []


def test_restaurar_desde_un_archivo_de_datos(sesion, tmp_path):
    """El tally.db de otra PC también sirve para restaurar."""
    from motor.respaldos import copiar_archivo_de_datos

    otra_pc = copiar_archivo_de_datos(sesion.almacen.ruta, tmp_path / "otra_pc" / "tally.db")
    info = respaldos.inspeccionar(otra_pc)
    assert (info.perfil, info.cuentas, info.movimientos) == ("Usuario Ficticio", 1, 2)

    nueva = Sesion(tmp_path / "nueva" / "tally.db", reloj=reloj)
    respaldos.restaurar(nueva, otra_pc, carpeta_seguridad=tmp_path / "seguridad")
    assert instantanea(nueva.libro) == instantanea(sesion.libro)
    assert len(nueva.almacen.bitacora()) == len(sesion.almacen.bitacora()) + 1      # + la restauración


def test_archivo_que_no_es_respaldo(tmp_path):
    falso = tmp_path / "foto.db"
    falso.write_bytes(b"SQLite format 3\x00" + b"basura" * 100)
    with pytest.raises(ErrorDatos):
        respaldos.inspeccionar(falso)


def test_respaldo_del_dia(sesion, tmp_path):
    carpeta = tmp_path / "Respaldos"
    primero = respaldos.respaldo_del_dia(sesion, carpeta)
    assert primero.name.startswith("TALLY_automatico_2026-07-20_")
    assert respaldos.respaldo_del_dia(sesion, carpeta) is None            # uno por día
    with sesion.cambio() as libro:
        perfil.ajustar(libro, respaldo_diario=False)
    primero.unlink()
    assert respaldos.respaldo_del_dia(sesion, carpeta) is None            # desactivado


def test_ajustes_del_perfil(sesion):
    from motor.errores import ErrorValidacion

    with sesion.cambio() as libro:
        perfil.ajustar(libro, nombre="  Apodo   Ficticio ", respaldos_a_conservar=30, periodo_inicial="quincena")
    ajustes = Sesion(sesion.almacen.ruta, reloj=reloj).libro.perfil
    assert (ajustes.nombre, ajustes.respaldos_a_conservar, ajustes.periodo_inicial, ajustes.respaldo_diario) == (
        "Apodo Ficticio", 30, "quincena", True)
    for malo in (dict(respaldos_a_conservar=0), dict(respaldos_a_conservar=500), dict(periodo_inicial="siglo"),
                 dict(nombre="  ")):
        with pytest.raises(ErrorValidacion):
            with sesion.cambio() as libro:
                perfil.ajustar(libro, **malo)


def test_tema_e_icono_y_leer_perfil_sin_tocar_el_archivo(sesion):
    from motor.errores import ErrorValidacion

    with sesion.cambio() as libro:
        perfil.ajustar(libro, tema="oscuro", icono="acento")
    antes = sesion.almacen.ruta.read_bytes()
    leido = respaldos.leer_perfil(sesion.almacen.ruta)
    assert (leido.tema, leido.icono) == ("oscuro", "acento")
    assert sesion.almacen.ruta.read_bytes() == antes
    assert respaldos.leer_perfil(sesion.almacen.ruta.with_name("no_existe.db")) is None
    for malo in (dict(tema="morado"), dict(icono="dorado")):
        with pytest.raises(ErrorValidacion):
            with sesion.cambio() as libro:
                perfil.ajustar(libro, **malo)
