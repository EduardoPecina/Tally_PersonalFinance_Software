"""El lanzador del portal (acceso directo del Escritorio)."""

import importlib.util
from pathlib import Path

import pytest

RAIZ_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def iniciar(monkeypatch, tmp_path):
    monkeypatch.setenv("TALLY_RAIZ", str(tmp_path))
    spec = importlib.util.spec_from_file_location("iniciar", RAIZ_REPO / "portal" / "iniciar.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    abiertas = []
    monkeypatch.setattr(modulo.webbrowser, "open", abiertas.append)
    modulo.abiertas = abiertas
    return modulo


def test_si_ya_esta_abierto_solo_abre_el_navegador(iniciar, monkeypatch):
    monkeypatch.setattr(iniciar, "abierto", lambda: True)
    monkeypatch.setattr(iniciar, "iniciar_servidor", lambda: pytest.fail("no debe iniciar otro servidor"))
    assert iniciar.main() == 0
    assert iniciar.abiertas == ["http://localhost:8765"]


def test_si_el_servidor_no_arranca_avisa(iniciar, monkeypatch):
    class Terminado:
        def poll(self):
            return 1

    avisos = []
    monkeypatch.setattr(iniciar, "abierto", lambda: False)
    monkeypatch.setattr(iniciar, "iniciar_servidor", lambda: Terminado())
    monkeypatch.setattr(iniciar, "avisar_error", avisos.append)
    assert iniciar.main() == 1
    assert "portal.log" in avisos[0]
    assert iniciar.abiertas == []


def test_inicia_streamlit_solo_en_localhost(iniciar, monkeypatch, tmp_path):
    lanzado = {}

    def popen(comando, **opciones):
        lanzado.update(comando=comando, **opciones)
        return object()

    monkeypatch.setattr(iniciar.subprocess, "Popen", popen)
    iniciar.iniciar_servidor()
    comando = lanzado["comando"]
    assert comando[1:4] == ["-m", "streamlit", "run"]
    assert comando[comando.index("--server.address") + 1] == "localhost"
    assert comando[comando.index("--server.port") + 1] == "8765"
    assert comando[comando.index("--browser.gatherUsageStats") + 1] == "false"
    assert lanzado["cwd"] == RAIZ_REPO  # ahí está .streamlit/config.toml
    assert (tmp_path / "portal.log").exists()
