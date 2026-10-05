"""Apagado del portal: solo procesos de esta instalación, y por inactividad."""

import subprocess
import sys
import time

import pytest

from portal import apagado

APP = str(apagado.PORTAL / "app.py")
INICIAR = str(apagado.PORTAL / "iniciar.py")


@pytest.mark.parametrize(
    ("linea", "carpeta", "esperado"),
    [
        (["C:/Python313/pythonw.exe", "-m", "streamlit", "run", APP, "--server.port", "8765"], "/", True),
        (["pythonw.exe", "portal/iniciar.py"], str(apagado.PORTAL.parent), True),
        (["python3.13", INICIAR], "/", True),
        (["python.exe", "otro_proyecto/app.py"], "/tmp", False),          # otro Python (p. ej. VS Code)
        (["Code.exe", APP], "/", False),                                  # no es Python
        ([], "/", False),
    ],
)
def test_es_del_portal(linea, carpeta, esperado):
    assert apagado.es_del_portal(linea, carpeta) is esperado


def test_tiempo_sin_pestanas():
    assert apagado.tiempo_sin_pestanas(0, 0, revision=30) == 30
    assert apagado.tiempo_sin_pestanas(870, 0, revision=30) == 900
    assert apagado.tiempo_sin_pestanas(870, 1, revision=30) == 0     # alguien volvió a abrir una pestaña
    assert apagado.tiempo_sin_pestanas(870, None, revision=30) is None


def test_pestanas_abiertas_fuera_de_streamlit():
    assert apagado.pestanas_abiertas() is None


def test_detener_termina_procesos_y_no_toca_otros():
    psutil = pytest.importorskip("psutil")
    hijo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert hijo.pid not in [p.pid for p in apagado.procesos_del_portal()]  # no es del portal
        apagado.detener([psutil.Process(hijo.pid)], espera=5)
        inicio = time.monotonic()
        while hijo.poll() is None and time.monotonic() - inicio < 5:
            time.sleep(0.1)
        assert hijo.poll() is not None
    finally:
        hijo.kill()
