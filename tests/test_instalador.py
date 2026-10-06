"""El instalador nunca debe tocar los datos del usuario."""

import hashlib
import importlib.util
import shutil
from datetime import date
from pathlib import Path

import pytest

from motor import cuentas, respaldos
from motor.serializacion import instantanea
from motor.sesion import Sesion

RAIZ_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def instalador(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("instalar", RAIZ_REPO / "instalador" / "instalar.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    monkeypatch.setenv("TALLY_ESCRITORIO", str(tmp_path / "Escritorio"))
    monkeypatch.setenv("TALLY_DATOS", str(tmp_path / "Usuario" / "TALLY"))   # C:\Users\<usuario>\TALLY
    monkeypatch.setenv("TALLY_SIN_VENTANAS", "1")
    monkeypatch.setattr(modulo, "portal_abierto", lambda: False)
    monkeypatch.setattr(modulo, "ESPERA_BLOQUEO", 0)
    return modulo


def carpeta(tmp_path):
    return tmp_path / "Escritorio" / "TALLY"


def datos(tmp_path):
    """Carpeta local del usuario: Datos y Respaldos (fuera del Escritorio y de OneDrive)."""
    return tmp_path / "Usuario" / "TALLY"


def huella(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_primera_instalacion(instalador, tmp_path):
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0
    raiz = carpeta(tmp_path)
    assert (datos(tmp_path) / "Datos").is_dir()
    assert (datos(tmp_path) / "Respaldos").is_dir()
    assert not (raiz / "Datos").exists() and not (raiz / "Respaldos").exists()   # nada personal en el Escritorio
    assert str(datos(tmp_path)) in (raiz / "LEEME.txt").read_text(encoding="utf-8-sig")
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
    raiz, base = carpeta(tmp_path), datos(tmp_path)
    sesion = Sesion(base / "Datos" / "tally.db")
    with sesion.cambio() as libro:
        cuentas.crear(libro, "Débito", "debito", saldo_inicial=1234, fecha_creacion=date(2026, 7, 1))
    datos_antes = huella(base / "Datos" / "tally.db")
    (raiz / "_Programa" / "archivo_viejo.py").write_text("viejo")
    (base / "Respaldos" / "mi_respaldo_manual.zip").write_bytes(b"lo que sea")

    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0

    assert huella(base / "Datos" / "tally.db") == datos_antes
    assert (base / "Respaldos" / "mi_respaldo_manual.zip").read_bytes() == b"lo que sea"
    (respaldo,) = base.joinpath("Respaldos").glob("TALLY_antes_de_actualizar_*.zip")
    assert respaldos.inspeccionar(respaldo).cuentas == 1
    assert not (raiz / "_Programa" / "archivo_viejo.py").exists()   # el programa se reemplaza completo
    assert not list(raiz.glob("_Programa_anterior*"))
    assert Sesion(base / "Datos" / "tally.db").libro.cuentas()[0].nombre == "Débito"


def _instalacion_anterior(raiz):
    """Como la dejaba la versión 0.3.x: Datos y Respaldos dentro de Escritorio\\TALLY (en OneDrive)."""
    sesion = Sesion(raiz / "Datos" / "tally.db")
    with sesion.cambio() as libro:
        cuentas.crear(libro, "Débito", "debito", saldo_inicial=4321, fecha_creacion=date(2026, 7, 1))
        cuentas.crear(libro, "TDC", "credito", dia_corte=3, dia_pago=23, deuda_inicial=500)
    (raiz / "Respaldos").mkdir(parents=True, exist_ok=True)
    (raiz / "Respaldos" / "TALLY_respaldo_viejo.zip").write_bytes(b"respaldo anterior")
    return instantanea(sesion.libro)


def test_actualizar_mueve_los_datos_fuera_del_escritorio(instalador, tmp_path):
    instalador.instalar(sin_librerias=True, sin_accesos=True)
    raiz, base = carpeta(tmp_path), datos(tmp_path)
    (base / "Datos").rmdir()
    antes = _instalacion_anterior(raiz)

    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0

    assert instantanea(Sesion(base / "Datos" / "tally.db").libro) == antes     # todo llegó igual
    assert not (raiz / "Datos").exists() and not list(raiz.glob("Datos_*"))    # y ya no está en el Escritorio
    assert (base / "Respaldos" / "TALLY_respaldo_viejo.zip").read_bytes() == b"respaldo anterior"
    assert not (raiz / "Respaldos").exists()
    (respaldo,) = base.joinpath("Respaldos").glob("TALLY_antes_de_actualizar_*.zip")   # respaldo previo
    assert respaldos.inspeccionar(respaldo).cuentas == 2
    log = (raiz / "instalacion.log").read_text(encoding="utf-8")
    assert "Datos movidos y verificados" in log


def _datos_que_usa_el_programa(programa, base):
    """Lo que resuelve motor/rutas.py del programa instalado (en otro proceso, como en la PC del usuario)."""
    import os
    import subprocess
    import sys

    salida = subprocess.run(
        [sys.executable, "-c", "from motor import rutas; print(rutas.archivo_datos())"],
        cwd=programa, capture_output=True, text=True, check=True, env={**os.environ, "TALLY_DATOS": str(base)},
    ).stdout.strip()
    return Path(salida)


def test_si_no_se_puede_apartar_el_original_no_queda_nada_a_medias(instalador, tmp_path, monkeypatch):
    raiz, base = carpeta(tmp_path), datos(tmp_path)
    raiz.mkdir(parents=True)
    antes = _instalacion_anterior(raiz)
    original = huella(raiz / "Datos" / "tally.db")

    def renombrar_ocupado(origen, destino, intentos=15):
        if origen.name == "Datos":
            raise PermissionError("OneDrive tiene abierto el archivo")
        origen.rename(destino)

    monkeypatch.setattr(instalador, "renombrar", renombrar_ocupado)
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0
    assert huella(raiz / "Datos" / "tally.db") == original       # el original sigue ahí, intacto
    assert not (base / "Datos" / "tally.db").exists()            # y no quedó una segunda versión
    # El programa nuevo quedó instalado y sigue usando los datos donde están: no abre vacío.
    usados = _datos_que_usa_el_programa(raiz / "_Programa", base)
    assert usados == raiz / "Datos" / "tally.db"
    assert instantanea(Sesion(usados).libro) == antes
    assert "No se pudieron mover tus datos" in (raiz / "instalacion.log").read_text(encoding="utf-8")

    monkeypatch.undo()                                            # la siguiente actualización sí los mueve
    monkeypatch.setenv("TALLY_ESCRITORIO", str(tmp_path / "Escritorio"))
    monkeypatch.setenv("TALLY_DATOS", str(base))
    monkeypatch.setenv("TALLY_SIN_VENTANAS", "1")
    monkeypatch.setattr(instalador, "portal_abierto", lambda: False)
    monkeypatch.setattr(instalador, "ESPERA_BLOQUEO", 0)
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0
    assert _datos_que_usa_el_programa(raiz / "_Programa", base) == base / "Datos" / "tally.db"
    assert instantanea(Sesion(base / "Datos" / "tally.db").libro) == antes
    assert not (raiz / "Datos").exists()


def test_un_respaldo_ocupado_no_detiene_la_mudanza(instalador, tmp_path, monkeypatch):
    raiz, base = carpeta(tmp_path), datos(tmp_path)
    raiz.mkdir(parents=True)
    antes = _instalacion_anterior(raiz)
    mover = instalador.shutil.move

    def mover_salvo_el_viejo(origen, destino):
        if origen.endswith("TALLY_respaldo_viejo.zip"):
            raise PermissionError("abierto en otra ventana")
        return mover(origen, destino)

    monkeypatch.setattr(instalador.shutil, "move", mover_salvo_el_viejo)
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0
    assert instantanea(Sesion(base / "Datos" / "tally.db").libro) == antes
    assert (raiz / "Respaldos" / "TALLY_respaldo_viejo.zip").exists()       # se queda donde estaba
    assert "no se pudieron mover" in (raiz / "instalacion.log").read_text(encoding="utf-8")


def test_si_hay_datos_en_los_dos_lugares_no_se_pierde_ninguno(instalador, tmp_path):
    instalador.instalar(sin_librerias=True, sin_accesos=True)
    raiz, base = carpeta(tmp_path), datos(tmp_path)
    actuales = Sesion(base / "Datos" / "tally.db")
    with actuales.cambio() as libro:
        cuentas.crear(libro, "Cuenta nueva", "debito")
    anterior = _instalacion_anterior(raiz)

    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0
    assert cuentas.buscar(Sesion(base / "Datos" / "tally.db").libro, "Cuenta nueva")
    (apartados,) = raiz.glob("Datos_anterior_*")
    assert instantanea(Sesion(apartados / "tally.db").libro) == anterior


def test_si_el_escritorio_no_deja_escribir_se_instala_en_la_carpeta_del_usuario(instalador, tmp_path, monkeypatch):
    escritorio_bloqueado = carpeta(tmp_path)
    original = instalador.puede_escribir
    monkeypatch.setattr(instalador, "puede_escribir", lambda c: c != escritorio_bloqueado and original(c))
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 0
    base = datos(tmp_path)
    assert (base / "_Programa" / "motor").is_dir()
    assert (base / "Datos").is_dir() and (base / "LEEME.txt").exists()
    assert not escritorio_bloqueado.exists()


def test_el_programa_instalado_busca_los_datos_en_la_carpeta_del_usuario(instalador, tmp_path):
    """La regla del instalador y la del programa instalado (motor/rutas.py) deben coincidir."""
    instalador.instalar(sin_librerias=True, sin_accesos=True)
    programa = carpeta(tmp_path) / "_Programa"
    assert _datos_que_usa_el_programa(programa, datos(tmp_path)) == datos(tmp_path) / "Datos" / "tally.db"


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
    raiz, base = carpeta(tmp_path), datos(tmp_path)
    (base / "Datos" / "tally.db").write_bytes(b"basura" * 100)
    (raiz / "_Programa" / "marca.txt").write_text("versión anterior")
    assert instalador.instalar(sin_librerias=True, sin_accesos=True) == 1
    assert (raiz / "_Programa" / "marca.txt").exists()       # no se tocó nada
    assert (base / "Datos" / "tally.db").read_bytes() == b"basura" * 100


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
    texto = (RAIZ_REPO / "requirements-lock.txt").read_text(encoding="utf-8").replace("\\\n", " ")
    paquetes = [linea for linea in texto.splitlines() if linea.strip() and not linea.lstrip().startswith("#")]
    assert any(p.startswith("streamlit==") for p in paquetes)
    for paquete in paquetes:
        assert "==" in paquete.split()[0] and "--hash=sha256:" in paquete, paquete


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


def test_crea_accesos_directos_cuando_hay_portal(instalador, tmp_path, monkeypatch):
    llamadas = []
    monkeypatch.setattr(instalador.sys, "platform", "win32")
    monkeypatch.setattr(instalador, "crear_accesos",
                        lambda raiz, programa, base: llamadas.append((raiz, programa, base)) or True)
    assert instalador.instalar(sin_librerias=True, sin_accesos=False) == 0
    raiz = carpeta(tmp_path)
    assert llamadas == [(raiz, raiz / "_Programa", datos(tmp_path))]
    assert instalador.portal_disponible(raiz / "_Programa")
    assert (raiz / "_Programa" / "portal" / "recursos" / "tally.ico").exists()


def _preparar_accesos(instalador, tmp_path):
    raiz = tmp_path / "Escritorio" / "TALLY"
    programa = raiz / "_Programa"
    (programa / "portal" / "recursos").mkdir(parents=True)
    (programa / "portal" / "recursos" / "tally.ico").write_bytes(b"ico")
    return raiz, programa


def test_acceso_directo_con_pywin32(instalador, tmp_path, monkeypatch):
    raiz, programa = _preparar_accesos(instalador, tmp_path)
    llamados = []

    def ejecutar(comando):
        llamados.append(comando)
        for ruta in comando[-2:]:
            Path(ruta).write_text("lnk")
        return 0

    monkeypatch.setattr(instalador, "ejecutar", ejecutar)
    monkeypatch.setattr(instalador.subprocess, "run", lambda *a, **k: pytest.fail("no debe usar PowerShell"))
    assert instalador.crear_accesos(raiz, programa)
    assert "win32com.client" in llamados[0][2]
    assert llamados[0][-2:] == [str(raiz.parent / "TALLY.lnk"), str(raiz / "TALLY.lnk")]
    assert llamados[0][6] == str(programa / "portal" / "recursos" / "tally.ico")


def test_acceso_directo_con_powershell_si_falla_pywin32(instalador, tmp_path, monkeypatch):
    raiz, programa = _preparar_accesos(instalador, tmp_path)
    monkeypatch.setattr(instalador, "ejecutar", lambda comando: 1)  # sin pywin32

    def powershell(comando, env, **_):
        assert comando[0] == "powershell"
        for ruta in env["TALLY_LNK"].split("|"):
            Path(ruta).write_text("lnk")

    monkeypatch.setattr(instalador.subprocess, "run", powershell)
    assert instalador.crear_accesos(raiz, programa)
    assert (raiz / "TALLY.lnk").exists() and (raiz.parent / "TALLY.lnk").exists()


def test_acceso_directo_que_no_se_pudo_crear(instalador, tmp_path, monkeypatch, capsys):
    raiz, programa = _preparar_accesos(instalador, tmp_path)
    monkeypatch.setattr(instalador, "ejecutar", lambda comando: 1)

    def powershell_bloqueado(*_, **__):
        raise OSError("PowerShell está restringido")

    monkeypatch.setattr(instalador.subprocess, "run", powershell_bloqueado)
    assert not instalador.crear_accesos(raiz, programa)
    assert "No se pudo crear el acceso directo" in capsys.readouterr().out


def test_avisa_que_sigue_trabajando_si_no_hay_salida(instalador, monkeypatch, capsys):
    """Una ventana quieta parece congelada: la gente la cierra y deja la instalación a medias."""
    import sys

    monkeypatch.setattr(instalador, "AVISO_SILENCIO", 0.3)
    codigo = instalador.ejecutar([sys.executable, "-c", "import time; time.sleep(1.2); print('listo')"])
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "sigue trabajando" in salida and "No cierres esta ventana" in salida
    assert salida.rstrip().endswith("listo")


def test_limpia_restos_de_una_instalacion_interrumpida(instalador, tmp_path):
    librerias = tmp_path / "site-packages"
    (librerias / "~treamlit").mkdir(parents=True)
    (librerias / "~treamlit" / "app.py").write_text("x")
    (librerias / "~umpy-2.5.3.dist-info").mkdir()
    (librerias / "~resto.pth").write_text("x")
    (librerias / "streamlit").mkdir()
    (librerias / "pandas-3.0.6.dist-info").mkdir()
    borrados = instalador.limpiar_restos_de_pip([librerias])
    assert sorted(borrados) == ["~resto.pth", "~treamlit", "~umpy-2.5.3.dist-info"]
    assert sorted(p.name for p in librerias.iterdir()) == ["pandas-3.0.6.dist-info", "streamlit"]


def test_instalar_librerias_limpia_y_avisa_antes(instalador, monkeypatch, capsys):
    pasos = []
    monkeypatch.setattr(instalador, "limpiar_restos_de_pip", lambda: pasos.append("limpiar"))
    monkeypatch.setattr(instalador, "ejecutar", lambda comando: pasos.append("pip") or 0)
    assert instalador.instalar_librerias()
    assert pasos == ["limpiar", "pip"]
    assert "hasta 10 minutos" in capsys.readouterr().out


def test_acceso_directo_a_mis_datos(instalador, tmp_path, monkeypatch):
    raiz, programa = _preparar_accesos(instalador, tmp_path)
    base = datos(tmp_path)
    llamados = []

    def ejecutar(comando):
        llamados.append(comando)
        for ruta in comando[8:]:
            Path(ruta).write_text("lnk")
        return 0

    monkeypatch.setattr(instalador, "ejecutar", ejecutar)
    assert instalador.crear_accesos(raiz, programa, base)
    (tally, mis_datos) = llamados
    assert tally[-2:] == [str(raiz.parent / "TALLY.lnk"), str(raiz / "TALLY.lnk")]
    assert mis_datos[3] == str(base) and mis_datos[-1] == str(raiz / "Mis datos de TALLY.lnk")
