"""Copia de los respaldos en otra carpeta (NAS, disco externo, USB). Solo datos ficticios; el «NAS» es una carpeta
temporal."""

import errno
import json
import zipfile
from datetime import date, datetime, timedelta

import pytest

from conftest import AHORA
from motor import categorias, cifrado, copia_externa, cuentas, movimientos, perfil, respaldos, seguridad
from motor.errores import ErrorValidacion
from motor.sesion import Sesion

CONTRASENA = "Contraseña Ficticia 123"
LUNES = datetime(2026, 10, 19, 22, 0)


def reloj():
    return AHORA


@pytest.fixture
def raiz(tmp_path):
    return tmp_path / "PC"


@pytest.fixture
def nas(tmp_path):
    carpeta = tmp_path / "NAS Ficticio" / "Respaldos"
    carpeta.mkdir(parents=True)
    return carpeta


@pytest.fixture
def sesion(raiz):
    s = Sesion(raiz / "Datos" / "tally.db", reloj=reloj)
    with s.cambio() as libro:
        perfil.configurar(libro, "Usuario Ficticio")
        debito = cuentas.crear(libro, "Débito Ficticio", "debito", saldo_inicial=500, fecha_creacion=date(2026, 7, 1)).id
        movimientos.registrar_gasto(libro, date(2026, 7, 3), debito, categorias.buscar(libro, "ALIMENTOS").id, 120)
    return s


@pytest.fixture
def datos(sesion):
    return sesion.almacen.ruta


def _cambiar_algo(sesion) -> None:
    with sesion.cambio() as libro:
        perfil.ajustar(libro, nombre=f"Usuario Ficticio {libro.ahora():%H%M%S%f}")


def _copias(nas) -> list[str]:
    return sorted(p.name for p in nas.glob("TALLY_copia_*.zip"))


def test_sin_configurar_no_copia(datos):
    c = copia_externa.leer(datos)
    assert c == copia_externa.Copia() and not c.activa and not c.automatica
    assert (c.frecuencia, c.conservar) == ("diaria", 3)
    assert not copia_externa.toca(datos, LUNES)
    with pytest.raises(ErrorValidacion, match="Primero elige la carpeta"):
        copia_externa.copiar(datos, LUNES)


def test_configurar_prueba_la_carpeta_y_se_guarda_en_esta_pc(datos, nas):
    c = copia_externa.configurar(datos, f'  "{nas}"  ', "semanal", 5)
    assert (c.carpeta, c.frecuencia, c.conservar) == (str(nas), "semanal", 5)
    assert copia_externa.leer(datos) == c
    assert copia_externa.ruta_estado(datos) == datos.parent / "copia_externa.json"
    assert list(nas.iterdir()) == []                           # el archivito de prueba ya no está


@pytest.mark.parametrize("carpeta, frecuencia, conservar, motivo", [
    ("relativa/a/nada", "diaria", 3, "ruta completa"),
    ("{nas}/no-existe", "diaria", 3, "No encuentro la carpeta"),
    ("{nas}", "cada rato", 3, "cada cuánto"),
    ("{nas}", "diaria", 0, "entre 1 y 30"),
    ("{nas}", "diaria", 31, "entre 1 y 30"),
    ("{nas}", "diaria", True, "entre 1 y 30"),
])
def test_ajustes_no_validos(datos, nas, carpeta, frecuencia, conservar, motivo):
    with pytest.raises(ErrorValidacion, match=motivo):
        copia_externa.configurar(datos, carpeta.format(nas=nas), frecuencia, conservar)
    assert copia_externa.leer(datos) == copia_externa.Copia()


def test_no_vale_una_carpeta_de_tally_en_esta_pc(datos, raiz):
    (raiz / "Respaldos").mkdir(parents=True)
    for carpeta in (raiz / "Datos", raiz / "Respaldos"):
        with pytest.raises(ErrorValidacion, match="carpeta de TALLY en esta PC"):
            copia_externa.configurar(datos, str(carpeta), "diaria", 3)


def test_sin_carpeta_ya_no_copia(datos, nas):
    copia_externa.configurar(datos, str(nas), "diaria", 3)
    c = copia_externa.configurar(datos, "", "diaria", 3)
    assert not c.activa and not copia_externa.toca(datos, LUNES)


def test_copiar_ahora_deja_una_copia_completa_y_la_anota(sesion, datos, nas):
    copia_externa.configurar(datos, str(nas), "nunca", 3)
    ruta = copia_externa.copiar(datos, LUNES)
    assert ruta.parent == nas and ruta.name == "TALLY_copia_2026-10-19_220000.zip"
    info = respaldos.inspeccionar(ruta)                       # se puede restaurar como cualquier respaldo
    assert (info.perfil, info.movimientos) == ("Usuario Ficticio", 2)
    c = copia_externa.leer(datos)
    assert (c.ultima, c.archivo, c.error, c.fallando_desde) == (LUNES, ruta.name, "", None)
    assert c.revision == sesion.almacen.revision_en_disco()
    assert not list(nas.glob("*.tmp"))


def test_conserva_solo_las_ultimas(sesion, datos, nas):
    copia_externa.configurar(datos, str(nas), "diaria", 3)
    (nas / "Mis fotos.zip").write_bytes(b"no es de TALLY")          # lo demás de la carpeta no se toca
    for dia in range(5):
        copia_externa.copiar(datos, LUNES + timedelta(days=dia))
    assert _copias(nas) == [f"TALLY_copia_2026-10-{d}_220000.zip" for d in (21, 22, 23)]
    assert (nas / "Mis fotos.zip").exists()
    copia_externa.configurar(datos, str(nas), "diaria", 1)          # tu idea: solo la última
    copia_externa.copiar(datos, LUNES + timedelta(days=5))
    assert _copias(nas) == ["TALLY_copia_2026-10-24_220000.zip"]


def test_si_falla_las_anteriores_siguen_ahi(sesion, datos, nas, monkeypatch):
    copia_externa.configurar(datos, str(nas), "diaria", 1)
    buena = copia_externa.copiar(datos, LUNES)

    def se_cae_la_red(*args, **kwargs):
        raise OSError(errno.EHOSTDOWN, "Se perdió la conexión de red")
    monkeypatch.setattr(respaldos, "_escribir_zip", se_cae_la_red)
    with pytest.raises(ErrorValidacion, match="Se perdió la conexión de red"):
        copia_externa.copiar(datos, LUNES + timedelta(days=1))
    assert _copias(nas) == [buena.name]
    c = copia_externa.leer(datos)
    assert (c.ultima, c.archivo) == (LUNES, buena.name)               # la última buena no cambia
    assert "Se perdió la conexión" in c.error and c.fallando_desde == LUNES + timedelta(days=1)


def test_una_copia_danada_no_borra_las_anteriores(sesion, datos, nas, monkeypatch):
    copia_externa.configurar(datos, str(nas), "diaria", 1)
    buena = copia_externa.copiar(datos, LUNES)
    real = respaldos._escribir_zip

    def dana(ruta, *args, **kwargs):                                  # el NAS guardó otra cosa
        hecha = real(ruta, *args, **kwargs)
        hecha.write_bytes(hecha.read_bytes()[:200])
        return hecha
    monkeypatch.setattr(respaldos, "_escribir_zip", dana)
    with pytest.raises(ErrorValidacion, match="quedó dañada"):
        copia_externa.copiar(datos, LUNES + timedelta(days=1))
    assert _copias(nas) == [buena.name]


def test_mensajes_sencillos_de_lo_que_pasa(datos, nas):
    assert "No encuentro la carpeta" in copia_externa.explicar(FileNotFoundError(), "Z:\\X")
    assert "Windows no deja guardar" in copia_externa.explicar(PermissionError(), "Z:\\X")
    assert "está lleno" in copia_externa.explicar(OSError(errno.ENOSPC, "No space left"), "Z:\\X")
    copia_externa.configurar(datos, str(nas), "diaria", 3)
    nas.rmdir()                                                       # se apagó el NAS
    with pytest.raises(ErrorValidacion, match="Revisa que tu NAS esté encendido"):
        copia_externa.copiar(datos, LUNES)


@pytest.mark.parametrize("frecuencia, dias", [("diaria", 1), ("semanal", 7), ("mensual", 30)])
def test_cuando_toca_la_copia_automatica(sesion, datos, nas, frecuencia, dias):
    copia_externa.configurar(datos, str(nas), frecuencia, 3)
    assert copia_externa.toca(datos, LUNES)                           # la primera, en cuanto se pueda
    copia_externa.copiar(datos, LUNES)
    _cambiar_algo(sesion)
    antes = LUNES.replace(hour=0) + timedelta(days=dias - 1)
    assert not copia_externa.toca(datos, antes)                        # aún no pasa el plazo
    assert copia_externa.toca(datos, LUNES + timedelta(days=dias))


def test_sin_cambios_no_vuelve_a_copiar(sesion, datos, nas):
    copia_externa.configurar(datos, str(nas), "diaria", 3)
    copia_externa.copiar(datos, LUNES)
    assert not copia_externa.toca(datos, LUNES + timedelta(days=30))  # nada cambió: la copia sigue al día
    _cambiar_algo(sesion)
    assert copia_externa.toca(datos, LUNES + timedelta(days=1))


def test_nunca_solo_con_copiar_ahora(sesion, datos, nas):
    copia_externa.configurar(datos, str(nas), "nunca", 3)
    assert not copia_externa.toca(datos, LUNES)
    copia_externa.al_cerrar(datos, LUNES)
    assert _copias(nas) == []
    copia_externa.copiar(datos, LUNES)
    assert len(_copias(nas)) == 1


def test_al_cerrar_hace_la_que_toca_y_nunca_falla(sesion, datos, nas):
    copia_externa.configurar(datos, str(nas), "diaria", 3)
    copia_externa.al_cerrar(datos, LUNES)
    assert _copias(nas) == ["TALLY_copia_2026-10-19_220000.zip"]
    copia_externa.al_cerrar(datos, LUNES + timedelta(hours=1))        # ya se hizo la de hoy
    assert len(_copias(nas)) == 1
    _cambiar_algo(sesion)
    nas.rename(nas.with_name("apagado"))                              # el NAS se apagó: TALLY igual se cierra
    copia_externa.al_cerrar(datos, LUNES + timedelta(days=1))
    assert "No encuentro la carpeta" in copia_externa.leer(datos).error


def test_en_segundo_plano(sesion, datos, nas):
    copia_externa.configurar(datos, str(nas), "diaria", 3)
    en_curso = copia_externa.iniciar(datos, LUNES)
    assert en_curso is not None
    assert en_curso.esperar(30).name == "TALLY_copia_2026-10-19_220000.zip" and en_curso.terminado
    assert en_curso.error is None and copia_externa.iniciar(datos, LUNES) is None


def test_aviso_si_lleva_una_semana_sin_poder_copiar(sesion, datos, nas):
    copia_externa.configurar(datos, str(nas), "diaria", 3)
    nas.rmdir()
    with pytest.raises(ErrorValidacion):
        copia_externa.copiar(datos, LUNES)
    assert copia_externa.aviso(datos, LUNES + timedelta(days=6)) is None
    texto = copia_externa.aviso(datos, LUNES + timedelta(days=7))
    assert texto.startswith("Hace 7 días que no se puede copiar tu respaldo") and "No encuentro" in texto
    nas.mkdir()
    copia_externa.copiar(datos, LUNES + timedelta(days=8))
    assert copia_externa.aviso(datos, LUNES + timedelta(days=20)) is None


def test_con_contrasena_la_copia_va_cifrada(sesion, datos, nas, raiz):
    kit = cifrado.nuevo_kit()
    seguridad.activar(sesion, CONTRASENA, CONTRASENA, kit, kit, carpeta_respaldos=raiz / "Respaldos")
    copia_externa.configurar(datos, str(nas), "diaria", 3)
    ruta = copia_externa.copiar(datos, LUNES)                         # sin necesitar la contraseña
    with zipfile.ZipFile(ruta) as zz:
        contenido = b"".join(zz.read(n) for n in zz.namelist())
    assert b"Usuario Ficticio" not in contenido and b"D\xc3\xa9bito Ficticio" not in contenido
    assert respaldos.inspeccionar(ruta, secreto=CONTRASENA).perfil == "Usuario Ficticio"


def test_un_archivo_de_ajustes_danado_no_rompe_nada(datos):
    copia_externa.ruta_estado(datos).write_text("{no es json", encoding="utf-8")
    assert copia_externa.leer(datos) == copia_externa.Copia()
    copia_externa.ruta_estado(datos).write_text(json.dumps({"carpeta": "X", "frecuencia": "rara", "conservar": -2}),
                                                encoding="utf-8")
    c = copia_externa.leer(datos)
    assert (c.carpeta, c.frecuencia, c.conservar) == ("X", "diaria", 3)


def test_la_ventana_para_elegir_carpeta(monkeypatch, tmp_path):
    import subprocess

    from portal.componentes import carpetas

    def ventana(eligio):
        def correr(argumentos, **kwargs):
            salida, titulo = argumentos[3], argumentos[4]
            assert titulo == "Elige dónde guardar las copias de TALLY"
            compile(argumentos[2], "<ventana>", "exec")                # el programita de la ventana es válido
            open(salida, "w", encoding="utf-8").write(eligio)
            return subprocess.CompletedProcess(argumentos, 0)
        return correr
    monkeypatch.setattr(subprocess, "run", ventana(str(tmp_path)))
    assert carpetas.elegir_carpeta("Elige dónde guardar las copias de TALLY") == str(tmp_path)
    monkeypatch.setattr(subprocess, "run", ventana(""))                 # canceló
    assert carpetas.elegir_carpeta("Elige dónde guardar las copias de TALLY") == ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1))   # sin tkinter
    assert carpetas.elegir_carpeta("x") is None
