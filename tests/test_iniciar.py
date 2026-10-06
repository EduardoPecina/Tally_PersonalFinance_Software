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
    monkeypatch.setattr(modulo, "CANDADO", tmp_path / "tally.lock")
    monkeypatch.setattr(modulo, "PAUSA_ENTRE_CLICS", 0)
    abiertas, avisos = [], []
    monkeypatch.setattr(modulo.webbrowser, "open", abiertas.append)
    monkeypatch.setattr(modulo, "avisar_error", avisos.append)
    modulo.abiertas, modulo.avisos = abiertas, avisos
    return modulo


def test_si_ya_esta_abierto_solo_abre_el_navegador(iniciar, monkeypatch):
    monkeypatch.setattr(iniciar, "abierto", lambda: True)
    monkeypatch.setattr(iniciar, "responde", lambda: True)
    monkeypatch.setattr(iniciar, "iniciar_servidor", lambda: pytest.fail("no debe iniciar otro servidor"))
    assert iniciar.main() == 0
    assert iniciar.abiertas == ["http://localhost:8765"]


def test_clic_de_mas_mientras_otro_lanzador_trabaja(iniciar, monkeypatch):
    candado = iniciar.tomar_turno()                  # otro lanzador tiene el turno
    try:
        monkeypatch.setattr(iniciar, "preparar_portal", lambda: pytest.fail("no debe hacer nada"))
        assert iniciar.main() == 0
        assert iniciar.abiertas == []
    finally:
        iniciar.soltar_turno(candado)
    assert iniciar.tomar_turno() is not None         # al terminar, el turno queda libre


def test_portal_trabado_se_reinicia(iniciar, monkeypatch):
    estado = {"abierto": True}
    monkeypatch.setattr(iniciar, "abierto", lambda: estado["abierto"])
    monkeypatch.setattr(iniciar, "responde", lambda: False)

    def detener():
        estado["abierto"] = False
        return True

    def arrancar():
        estado["abierto"] = True
        return None

    monkeypatch.setattr(iniciar, "detener_portal_trabado", detener)
    monkeypatch.setattr(iniciar, "arrancar_portal", arrancar)
    assert iniciar.main() == 0
    assert iniciar.abiertas == ["http://localhost:8765"]


def test_si_el_servidor_no_arranca_avisa_con_el_detalle(iniciar, monkeypatch, tmp_path):
    class Terminado:
        def poll(self):
            return 1

    def iniciar_servidor():
        (tmp_path / "portal.log").write_text("Traceback...\nModuleNotFoundError: No module named 'streamlit'\n")
        return Terminado()

    monkeypatch.setattr(iniciar, "abierto", lambda: False)
    monkeypatch.setattr(iniciar, "iniciar_servidor", iniciar_servidor)
    assert iniciar.main() == 1
    assert "No module named 'streamlit'" in iniciar.avisos[0]
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
    assert (tmp_path / "portal.log").read_text().startswith("=====")


def test_portal_log_vive_junto_a_los_datos_fuera_de_onedrive(monkeypatch, tmp_path):
    from motor import rutas

    from portal import iniciar

    monkeypatch.delenv("TALLY_RAIZ", raising=False)
    monkeypatch.setenv("TALLY_DATOS", str(tmp_path / "Usuario" / "TALLY"))
    monkeypatch.setattr(rutas, "_PROGRAMA", tmp_path / "OneDrive" / "Escritorio" / "TALLY" / "_Programa")
    assert iniciar.bitacora() == tmp_path / "Usuario" / "TALLY" / "portal.log"
