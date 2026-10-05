"""El instalador nunca debe tocar los datos del usuario."""

import hashlib
import importlib.util
import shutil
from datetime import date
from pathlib import Path

import pytest

from motor import cuentas, respaldos
from motor.sesion import Sesion

RAIZ_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def instalador(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("instalar", RAIZ_REPO / "instalador" / "instalar.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    monkeypatch.setenv("TALLY_ESCRITORIO", str(tmp_path / "Escritorio"))
    monkeypatch.setenv("TALLY_SIN_VENTANAS", "1")
    monkeypatch.setattr(modulo, "portal_abierto", lambda: False)
    monkeypatch.setattr(modulo, "ESPERA_BLOQUEO", 0)
    return modulo


def carpeta(tmp_path):
    return tmp_path / "Escritorio" / "TALLY"


def huella(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_primera_instalacion(instalador, tmp_path):
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0
    raiz = carpeta(tmp_path)
    assert (raiz / "Datos").is_dir()
    assert (raiz / "Respaldos").is_dir()
    assert (raiz / "LEEME.txt").exists()
    assert (raiz / "_Programa" / "motor" / "libro.py").exists()
    assert (raiz / "_Programa" / "INSTALAR.bat").exists()
    log = (raiz / "instalacion.log").read_text(encoding="utf-8")
    assert "RESULTADO: terminó bien" in log
    # Nada personal ni de desarrollo se copia al programa.
    programa = raiz / "_Programa"
    for prohibido in (".git", ".venv", "Datos", "Respaldos", "_Programa", ".pytest_cache"):
        assert not (programa / prohibido).exists(), prohibido
    assert not list(programa.rglob("__pycache__"))


def test_actualizar_respalda_y_no_toca_los_datos(instalador, tmp_path):
    instalador.instalar(sin_librerias=True, sin_accesos=True)
    raiz = carpeta(tmp_path)
    sesion = Sesion(raiz / "Datos" / "tally.db")
    with sesion.cambio() as libro:
        cuentas.crear(libro, "Débito", "debito", saldo_inicial=1234, fecha_creacion=date(2026, 7, 1))
    datos_antes = huella(raiz / "Datos" / "tally.db")
    (raiz / "_Programa" / "archivo_viejo.py").write_text("viejo")
    (raiz / "Respaldos" / "mi_respaldo_manual.zip").write_bytes(b"lo que sea")

    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0

    assert huella(raiz / "Datos" / "tally.db") == datos_antes
    assert (raiz / "Respaldos" / "mi_respaldo_manual.zip").read_bytes() == b"lo que sea"
    (respaldo,) = raiz.joinpath("Respaldos").glob("TALLY_antes_de_actualizar_*.zip")
    assert respaldos.inspeccionar(respaldo).cuentas == 1
    assert not (raiz / "_Programa" / "archivo_viejo.py").exists()   # el programa se reemplaza completo
    assert not list(raiz.glob("_Programa_anterior*"))
    assert Sesion(raiz / "Datos" / "tally.db").libro.cuentas()[0].nombre == "Débito"


def test_si_la_copia_falla_se_regresa_la_version_anterior(instalador, tmp_path, monkeypatch):
    instalador.instalar(sin_librerias=True, sin_accesos=True)
    raiz = carpeta(tmp_path)
    (raiz / "_Programa" / "marca.txt").write_text("versión anterior")

    def copia_que_falla(origen, destino, **_):
        Path(destino).mkdir()
        (Path(destino) / "a_medias.py").write_text("")
        raise OSError("disco lleno")

    monkeypatch.setattr(instalador.shutil, "copytree", copia_que_falla)
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 1
    assert (raiz / "_Programa" / "marca.txt").read_text() == "versión anterior"
    assert not (raiz / "_Programa" / "a_medias.py").exists()
    assert "NO se completó" in (raiz / "instalacion.log").read_text(encoding="utf-8")


def test_datos_daniados_detienen_la_actualizacion(instalador, tmp_path):
    instalador.instalar(sin_librerias=True, sin_accesos=True)
    raiz = carpeta(tmp_path)
    (raiz / "Datos" / "tally.db").write_bytes(b"basura" * 100)
    (raiz / "_Programa" / "marca.txt").write_text("versión anterior")
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 1
    assert (raiz / "_Programa" / "marca.txt").exists()       # no se tocó nada
    assert (raiz / "Datos" / "tally.db").read_bytes() == b"basura" * 100


def test_no_instala_con_tally_abierto(instalador, tmp_path, monkeypatch):
    monkeypatch.setattr(instalador, "portal_abierto", lambda: True)
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 1
    assert not (carpeta(tmp_path) / "_Programa").exists()


def test_no_se_instala_desde_dentro_de_la_carpeta_destino(instalador, tmp_path, monkeypatch):
    raiz = carpeta(tmp_path)
    falso_origen = raiz / "copia_del_zip"
    shutil.copytree(RAIZ_REPO / "motor", falso_origen / "motor")
    monkeypatch.setattr(instalador, "ORIGEN", falso_origen.resolve())
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 1
    assert not (raiz / "_Programa").exists()


def test_version_del_programa(instalador):
    from motor.config import VERSION

    assert instalador.version_del_programa() == VERSION


def test_librerias_se_instalan_desde_el_lock_verificado(instalador, monkeypatch):
    """Con hashes en el lock, pip exige instalar el lock mismo (no usarlo como restricción -c)."""
    comandos = []
    monkeypatch.setattr(instalador, "ejecutar", lambda comando: comandos.append(comando) or 0)
    assert instalador.instalar_librerias()
    (comando,) = comandos
    assert comando[comando.index("-r") + 1].endswith("requirements-lock.txt")
    assert "--require-hashes" in comando and "-c" not in comando
    for linea in (RAIZ_REPO / "requirements-lock.txt").read_text().splitlines():
        if linea and not linea.startswith("#"):
            assert "==" in linea and "--hash=sha256:" in linea, linea


def test_reintenta_si_windows_tiene_ocupada_la_carpeta(instalador, tmp_path, monkeypatch):
    """Justo después de copiar, el antivirus u OneDrive bloquean la carpeta unos segundos."""
    instalador.instalar(sin_librerias=True, sin_accesos=True)
    raiz = carpeta(tmp_path)
    original = Path.rename
    fallos = {"pendientes": 3}

    def rename_ocupado(self, destino):
        if self.name == "_Programa" and fallos["pendientes"]:
            fallos["pendientes"] -= 1
            raise PermissionError("El proceso no tiene acceso al archivo")
        return original(self, destino)

    monkeypatch.setattr(Path, "rename", rename_ocupado)
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0
    assert fallos["pendientes"] == 0
    assert (raiz / "_Programa" / "motor").is_dir()
    assert not list(raiz.glob("_Programa_anterior*"))


def test_si_sigue_ocupada_avisa_sin_tocar_nada(instalador, tmp_path, monkeypatch):
    instalador.instalar(sin_librerias=True, sin_accesos=True)
    raiz = carpeta(tmp_path)
    (raiz / "_Programa" / "marca.txt").write_text("versión anterior")

    def siempre_ocupado(self, destino):
        raise PermissionError("ocupado")

    monkeypatch.setattr(Path, "rename", siempre_ocupado)
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 1
    assert (raiz / "_Programa" / "marca.txt").exists()
