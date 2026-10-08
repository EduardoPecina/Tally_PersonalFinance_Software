"""Comprobantes adjuntos (motor/comprobantes.py): guardado, cifrado, respaldos y deducibles.

Solo archivos ficticios: unos cuantos bytes con la «firma» de cada tipo, nada de tickets reales.
"""

import csv
import io
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import date

import pytest

from conftest import AHORA
from motor import categorias, cifrado, comprobantes, cuentas, impuestos, movimientos, perfil, respaldos, seguridad
from motor.errores import ErrorBloqueado, ErrorDatos, ErrorNoEncontrado, ErrorValidacion
from motor.serializacion import verificar_integridad
from motor.sesion import Sesion

CONTRASENA = "mi perro come tacos"
SECRETO = b"TICKET FICTICIO MUY SECRETO 4321"
FOTO = b"\xff\xd8\xff\xe0" + SECRETO * 4
PDF = b"%PDF-1.4\n" + b"Factura ficticia " * 8
XML = b'\xef\xbb\xbf<?xml version="1.0"?><cfdi:Comprobante Total="100.00"/>'
PNG = b"\x89PNG\r\n\x1a\n" + b"imagen ficticia" * 3


def reloj():
    return AHORA


@pytest.fixture(autouse=True)
def scrypt_rapido(monkeypatch):
    monkeypatch.setattr(cifrado, "SCRYPT", {"n": 2 ** 10, "r": 8, "p": 1})


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "Datos" / "tally.db"


@pytest.fixture
def sesion(ruta):
    s = Sesion(ruta, reloj=reloj)
    with s.cambio() as libro:
        perfil.configurar(libro, "Usuario Ficticio")
        banco = cuentas.crear(libro, "Banco Ficticio", "debito", saldo_inicial=10_000,
                              fecha_creacion=date(2026, 1, 1)).id
        medico = categorias.buscar(libro, "CONSULTAS MEDICAS") or categorias.buscar(libro, "DENTISTA")
        s.medico = medico.id
        s.gasto = movimientos.registrar_gasto(libro, date(2026, 7, 3), banco, medico.id, 800, "Consulta ficticia").id
        s.otro = movimientos.registrar_gasto(libro, date(2026, 7, 4), banco, categorias.buscar(libro, "ALIMENTOS").id,
                                             120, "Comida ficticia").id
    return s


def _adjuntar(sesion, nombre="ticket.jpg", datos=FOTO, operacion=None):
    with sesion.cambio() as libro:
        return comprobantes.adjuntar(libro, operacion or sesion.gasto, nombre, datos)


def _filas_archivos(ruta) -> list[tuple[str, bytes]]:
    with closing(sqlite3.connect(ruta)) as conexion:            # cerrada: en Windows no deja el archivo tomado
        return [(i, bytes(d)) for i, d in conexion.execute("SELECT id, datos FROM archivos")]


# ------------------------------------------------------------------ adjuntar


@pytest.mark.parametrize("nombre, datos, tipo", [
    ("ticket.JPG", FOTO, "image/jpeg"), ("factura.pdf", PDF, "application/pdf"),
    ("factura.xml", XML, "application/xml"), ("foto.png", PNG, "image/png"),
])
def test_tipos_aceptados(sesion, nombre, datos, tipo):
    c = _adjuntar(sesion, nombre, datos)
    assert (c.tipo, c.tamano, c.huella) == (tipo, len(datos), comprobantes.huella(datos))
    assert c.agregado == AHORA and sesion.libro.comprobantes(sesion.gasto) == [c]


@pytest.mark.parametrize("nombre, datos, error", [
    ("virus.exe", b"MZ" + b"0" * 20, "no se puede adjuntar"),
    ("ticket.jpg", PDF, "no parece ser un archivo JPG"),            # la extensión no corresponde al contenido
    ("factura.pdf", b"hola", "no parece ser un archivo PDF"),
    ("vacio.pdf", b"", "está vacío"),
])
def test_archivos_rechazados(sesion, nombre, datos, error):
    with pytest.raises(ErrorValidacion, match=error):
        _adjuntar(sesion, nombre, datos)
    assert sesion.libro.comprobantes() == [] and _filas_archivos(sesion.almacen.ruta) == []


def test_tamano_maximo_y_repetido(sesion, monkeypatch):
    monkeypatch.setattr(comprobantes, "MAXIMO_BYTES", 50)
    with pytest.raises(ErrorValidacion, match="el máximo es"):
        _adjuntar(sesion, "grande.jpg", FOTO)
    monkeypatch.undo()
    _adjuntar(sesion)
    with pytest.raises(ErrorValidacion, match="ya está adjunto"):
        _adjuntar(sesion, "otra_vez.jpg")
    c = _adjuntar(sesion, operacion=sesion.otro)                    # el mismo archivo en otro movimiento, sí
    assert comprobantes.en_otros_movimientos(sesion.libro, c) == [sesion.gasto]


def test_nombre_limpio(sesion):
    c = _adjuntar(sesion, 'C:\\Users\\Ficticio\\Mis "tickets"\\súper:julio?.jpg')
    assert c.nombre == "súper_julio_.jpg"
    assert comprobantes.limpiar_nombre("a:b.jpg") == "a_b.jpg"               # no es una unidad de Windows
    assert comprobantes.limpiar_nombre("a" * 200 + ".pdf").endswith(".pdf")
    assert len(comprobantes.limpiar_nombre("a" * 200 + ".pdf")) == 120


# ------------------------------------------------------------------ guardado


def test_se_guarda_con_el_movimiento_y_se_lee_al_volver_a_abrir(sesion, ruta):
    c = _adjuntar(sesion)
    assert sesion.libro.archivos_nuevos() == {}                       # ya se escribió
    otra = Sesion(ruta, reloj=reloj)
    assert otra.libro.comprobantes() == [c]
    assert comprobantes.contenido(otra, c.id) == FOTO
    assert verificar_integridad(otra.libro) == []
    registro = otra.almacen.bitacora(entidad="comprobante")[0]      # la bitácora guarda sus datos, no el archivo
    assert registro.despues["nombre"] == "ticket.jpg" and "datos" not in registro.despues


def test_si_algo_falla_no_queda_ni_el_archivo(sesion, ruta):
    with pytest.raises(ErrorValidacion):
        with sesion.cambio() as libro:
            comprobantes.adjuntar(libro, sesion.gasto, "ticket.jpg", FOTO)
            raise ErrorValidacion("falla a propósito")
    assert sesion.libro.comprobantes() == [] and sesion.libro.archivos_nuevos() == {}
    assert _filas_archivos(ruta) == []


def test_quitar_el_comprobante_o_el_movimiento_borra_el_archivo(sesion, ruta):
    a = _adjuntar(sesion)
    _adjuntar(sesion, "factura.pdf", PDF)
    with sesion.cambio() as libro:
        comprobantes.quitar(libro, a.id)
    assert len(_filas_archivos(ruta)) == 1
    with pytest.raises(ErrorNoEncontrado):
        comprobantes.contenido(sesion, a.id)
    with sesion.cambio() as libro:
        movimientos.eliminar(libro, sesion.gasto)
    assert sesion.libro.comprobantes() == [] and _filas_archivos(ruta) == []


def test_resumen_y_conteo(sesion):
    _adjuntar(sesion)
    _adjuntar(sesion, "factura.pdf", PDF)
    _adjuntar(sesion, "otro.png", PNG, operacion=sesion.otro)
    r = comprobantes.resumen(sesion.libro)
    assert (r.cuantos, r.bytes, r.movimientos) == (3, len(FOTO) + len(PDF) + len(PNG), 2)
    assert comprobantes.por_movimiento(sesion.libro) == {sesion.gasto: 2, sesion.otro: 1}


# ------------------------------------------------------------------ contraseña


def _activar(sesion, tmp_path):
    kit = cifrado.nuevo_kit()
    seguridad.activar(sesion, CONTRASENA, CONTRASENA, kit, kit, carpeta_respaldos=tmp_path / "Respaldos")
    return kit


def _en_disco(ruta) -> bytes:
    contenido = ruta.read_bytes()
    for extra in ("-wal",):
        otro = ruta.with_name(ruta.name + extra)
        if otro.exists():
            contenido += otro.read_bytes()
    return contenido


def test_con_contrasena_el_archivo_queda_cifrado(sesion, ruta, tmp_path):
    c = _adjuntar(sesion)                                             # adjunto antes de poner la contraseña
    _activar(sesion, tmp_path)
    assert SECRETO not in _en_disco(ruta)
    assert all(cifrado.es_archivo_cifrado(d) for _, d in _filas_archivos(ruta))
    d = _adjuntar(sesion, "factura.pdf", PDF)                         # y después
    assert b"Factura ficticia" not in _en_disco(ruta)
    llave = seguridad.entrar(ruta, CONTRASENA)
    abierta = Sesion(ruta, reloj=reloj, llave=llave)
    assert comprobantes.contenido(abierta, c.id) == FOTO and comprobantes.contenido(abierta, d.id) == PDF
    with pytest.raises(ErrorBloqueado):
        Sesion(ruta, reloj=reloj)
    # Quitar la contraseña los deja como antes.
    seguridad.desactivar(abierta, CONTRASENA, carpeta_respaldos=tmp_path / "Respaldos")
    assert SECRETO in _en_disco(ruta)
    assert comprobantes.contenido(Sesion(ruta, reloj=reloj), c.id) == FOTO


def test_un_archivo_cifrado_alterado_no_se_entrega(sesion, ruta, tmp_path):
    c = _adjuntar(sesion)
    _activar(sesion, tmp_path)
    (archivo_id, datos), = _filas_archivos(ruta)
    alterado = datos[:-1] + bytes([datos[-1] ^ 1])
    with closing(sqlite3.connect(ruta)) as conexion, conexion:
        conexion.execute("UPDATE archivos SET datos = ? WHERE id = ?", (alterado, archivo_id))
    abierta = Sesion(ruta, reloj=reloj, llave=seguridad.entrar(ruta, CONTRASENA))
    with pytest.raises(ErrorDatos, match="modificado"):
        comprobantes.contenido(abierta, c.id)


# ------------------------------------------------------------------ respaldos


def test_respaldo_y_restauracion_con_comprobantes(sesion, tmp_path):
    c = _adjuntar(sesion)
    zip_ = respaldos.crear(sesion, tmp_path / "respaldo.zip")
    with zipfile.ZipFile(zip_) as zz:
        manifiesto = json.loads(zz.read("manifiesto.json"))
        assert zz.read(f"archivos/{c.id}") == FOTO
    assert manifiesto["version_formato"] == respaldos.VERSION_FORMATO and c.id in manifiesto["archivos"]

    nueva = Sesion(tmp_path / "otra" / "tally.db", reloj=reloj)
    respaldos.restaurar(nueva, zip_, carpeta_seguridad=tmp_path / "seguridad")
    assert nueva.libro.comprobantes() == [c]
    assert comprobantes.contenido(nueva, c.id) == FOTO
    assert comprobantes.contenido(Sesion(tmp_path / "otra" / "tally.db", reloj=reloj), c.id) == FOTO

    respaldos.empezar_de_cero(nueva, carpeta_seguridad=tmp_path / "seguridad")
    assert _filas_archivos(tmp_path / "otra" / "tally.db") == []


def test_respaldo_cifrado_con_comprobantes(sesion, ruta, tmp_path):
    c = _adjuntar(sesion)
    _activar(sesion, tmp_path)
    zip_ = respaldos.crear(sesion, tmp_path / "cifrado.zip")
    with zipfile.ZipFile(zip_) as zz:
        assert all(SECRETO not in zz.read(n) for n in zz.namelist())
    # En otra PC sin contraseña: se restaura con la contraseña del respaldo y queda con ella.
    otra_ruta = tmp_path / "otra" / "tally.db"
    nueva = Sesion(otra_ruta, reloj=reloj)
    respaldos.restaurar(nueva, zip_, carpeta_seguridad=tmp_path / "seguridad", secreto=CONTRASENA)
    assert SECRETO not in _en_disco(otra_ruta)
    abierta = Sesion(otra_ruta, reloj=reloj, llave=seguridad.entrar(otra_ruta, CONTRASENA))
    assert comprobantes.contenido(abierta, c.id) == FOTO
    # Una copia sin contraseña lleva el archivo tal cual.
    plano = respaldos.crear(abierta, tmp_path / "plano.zip", sin_contrasena=True)
    with zipfile.ZipFile(plano) as zz:
        assert zz.read(f"archivos/{c.id}") == FOTO


def test_convertir_los_respaldos_guardados(sesion, tmp_path):
    c = _adjuntar(sesion)
    zip_ = respaldos.crear(sesion, tmp_path / "TALLY_respaldo_ficticio.zip")
    config, llave = cifrado.preparar(CONTRASENA, cifrado.nuevo_kit(), ahora=AHORA)
    assert respaldos.cifrar_respaldo(zip_, config, llave)
    with zipfile.ZipFile(zip_) as zz:
        assert SECRETO not in zz.read(f"archivos/{c.id}")
    assert respaldos.descifrar_respaldo(zip_, llave)
    with zipfile.ZipFile(zip_) as zz:
        assert zz.read(f"archivos/{c.id}") == FOTO


def _reempacar(origen, destino, cambiar):
    with zipfile.ZipFile(origen) as zz:
        contenido = {n: zz.read(n) for n in zz.namelist()}
    cambiar(contenido)
    with zipfile.ZipFile(destino, "w") as zz:
        for n, d in contenido.items():
            zz.writestr(n, d)
    return destino


def test_un_respaldo_con_un_comprobante_alterado_o_faltante_no_se_restaura(sesion, tmp_path):
    c = _adjuntar(sesion)
    zip_ = respaldos.crear(sesion, tmp_path / "respaldo.zip")
    alterado = _reempacar(zip_, tmp_path / "alterado.zip",
                          lambda z: z.__setitem__(f"archivos/{c.id}", FOTO + b"!"))
    faltante = _reempacar(zip_, tmp_path / "faltante.zip", lambda z: z.pop(f"archivos/{c.id}"))
    for malo, error in ((alterado, "huella no coincide"), (faltante, "falta un comprobante")):
        with pytest.raises(ErrorDatos, match=error):
            respaldos.inspeccionar(malo)


def test_respaldos_viejos_sin_comprobantes_se_siguen_restaurando(sesion, tmp_path):
    zip_ = respaldos.crear(sesion, tmp_path / "respaldo.zip")
    viejo = _reempacar(zip_, tmp_path / "viejo.zip", lambda z: z.__setitem__("manifiesto.json", json.dumps(
        {**{k: v for k, v in json.loads(z["manifiesto.json"]).items() if k != "archivos"}, "version_formato": 6})))
    nueva = Sesion(tmp_path / "otra" / "tally.db", reloj=reloj)
    respaldos.restaurar(nueva, viejo, carpeta_seguridad=tmp_path / "seguridad")
    assert nueva.libro.comprobantes() == []


def test_mover_el_archivo_de_datos_lleva_los_comprobantes(sesion, ruta, tmp_path):
    c = _adjuntar(sesion)
    destino = respaldos.copiar_archivo_de_datos(ruta, tmp_path / "nuevo" / "tally.db")
    assert comprobantes.contenido(Sesion(destino, reloj=reloj), c.id) == FOTO


# ------------------------------------------------------------------ deducibles


def test_deducibles_con_y_sin_comprobante_y_su_zip(sesion):
    with sesion.cambio() as libro:
        impuestos.guardar_concepto(libro, "Gastos médicos", [sesion.medico])
        segundo = movimientos.registrar_gasto(libro, date(2026, 7, 10), libro.cuentas()[0].id, sesion.medico, 300,
                                              "Medicinas ficticias").id
    _adjuntar(sesion, "factura.pdf", PDF)
    _adjuntar(sesion, "factura.xml", XML)
    lista = comprobantes.deducibles(sesion.libro, 2026)
    assert [(d.pago.descripcion, len(d.comprobantes)) for d in lista] == [("Consulta ficticia", 2),
                                                                         ("Medicinas ficticias", 0)]
    assert [d.pago.operacion_id for d in comprobantes.sin_comprobante(sesion.libro, 2026)] == [segundo]

    with zipfile.ZipFile(io.BytesIO(comprobantes.zip_de_deducibles(sesion, 2026))) as zz:
        nombres = set(zz.namelist())
        assert {"indice.csv", "Gastos médicos/2026-07-03_factura.pdf", "Gastos médicos/2026-07-03_factura.xml"} \
            == nombres
        assert zz.read("Gastos médicos/2026-07-03_factura.pdf") == PDF
        indice = list(csv.reader(io.StringIO(zz.read("indice.csv").decode("utf-8-sig"))))
    assert indice[0][0] == "Concepto" and indice[-1][-1] == "SIN COMPROBANTE"

    # Dos archivos con el mismo nombre el mismo día: el segundo lleva «_2», con «/» en cualquier sistema.
    with sesion.cambio() as libro:
        otra = movimientos.registrar_gasto(libro, date(2026, 7, 3), libro.cuentas()[0].id, sesion.medico, 50,
                                           "Otra consulta ficticia").id
    _adjuntar(sesion, "factura.pdf", PDF + b"otra", operacion=otra)
    with zipfile.ZipFile(io.BytesIO(comprobantes.zip_de_deducibles(sesion, 2026))) as zz:
        assert "Gastos médicos/2026-07-03_factura_2.pdf" in zz.namelist()
        assert not any("\\" in n for n in zz.namelist())
    assert comprobantes.anios_con_deducibles(sesion.libro) == [2026]


def test_si_al_poner_la_contrasena_un_comprobante_no_cuadra_se_deshace(sesion, ruta, tmp_path, monkeypatch):
    _adjuntar(sesion)
    original = cifrado.Cifrador.cifrar_bytes

    def defectuoso(self, datos, contexto):                 # simula un error al cifrar un archivo
        return original(self, datos + b"!", contexto)

    monkeypatch.setattr(cifrado.Cifrador, "cifrar_bytes", defectuoso)
    with pytest.raises(ErrorDatos, match="comprobantes no coincidió"):
        _activar(sesion, tmp_path)
    monkeypatch.undo()
    assert seguridad.config(ruta) is None                  # tus datos siguen sin contraseña
