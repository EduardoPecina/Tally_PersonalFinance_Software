"""Precarga del portal (portal/servidor.py): lo pesado de la primera vista se deja listo mientras abre el navegador.

Solo con datos ficticios.
"""

from __future__ import annotations

import socket
import threading

import pytest

from motor import perfil
from motor.sesion import Sesion
from portal import servidor
from portal.componentes import sesion as sesion_portal


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("TALLY_RAIZ", str(tmp_path))
    sesion_portal._PRECARGADAS.clear()
    sesion_portal._abrir.clear()
    yield tmp_path
    sesion_portal._PRECARGADAS.clear()
    sesion_portal._abrir.clear()


def _con_datos(raiz) -> str:
    ruta = raiz / "Datos" / "tally.db"
    s = Sesion(ruta)
    with s.cambio() as lib:
        perfil.configurar(lib, "Usuario Ficticio")
    return str(ruta)


@pytest.fixture
def puerto_abierto():
    """Un puerto escuchando, como el de Streamlit ya arrancado."""
    with socket.socket() as escucha:
        escucha.bind(("127.0.0.1", 0))
        escucha.listen()
        yield escucha.getsockname()[1]


def test_puerto_de_los_argumentos():
    assert servidor.puerto_de(["run", "portal/app.py", "--server.port", "8799"]) == 8799
    from motor.config import PUERTO_PORTAL

    assert servidor.puerto_de(["run", "portal/app.py"]) == PUERTO_PORTAL


def test_precarga_tus_datos_cuando_el_servidor_ya_escucha(raiz, puerto_abierto):
    ruta = _con_datos(raiz)
    servidor.precargar(puerto_abierto)
    precargada = sesion_portal._PRECARGADAS[ruta]
    assert precargada.libro.perfil.nombre == "Usuario Ficticio"
    assert sesion_portal._abrir(ruta) is precargada                      # la primera vista la usa tal cual
    assert ruta not in sesion_portal._PRECARGADAS                         # y solo una vez


def test_si_tus_datos_cambiaron_despues_se_vuelven_a_leer(raiz):
    ruta = _con_datos(raiz)
    sesion_portal.precargar()
    precargada = sesion_portal._PRECARGADAS[ruta]
    with Sesion(ruta).cambio() as lib:                                    # otro cambio, después de precargar
        perfil.ajustar(lib, ingreso_esperado=1)
    abierta = sesion_portal._abrir(ruta)
    assert abierta is not precargada and abierta.libro.perfil.ingreso_esperado


def test_sin_datos_o_con_contrasena_no_se_precarga(raiz, monkeypatch):
    sesion_portal.precargar()                                             # aún no hay datos: no los crea
    assert not sesion_portal._PRECARGADAS and not (raiz / "Datos" / "tally.db").exists()
    _con_datos(raiz)
    from motor import seguridad

    monkeypatch.setattr(seguridad, "config", lambda ruta: object())       # con contraseña: hay que escribirla
    sesion_portal.precargar()
    assert not sesion_portal._PRECARGADAS


def test_si_el_servidor_no_abre_no_precarga_nada(raiz, monkeypatch):
    _con_datos(raiz)
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]                                   # nadie escucha aquí
    assert servidor.esperar_servidor(puerto, 0.2) is False
    monkeypatch.setattr(servidor, "esperar_servidor", lambda puerto: False)
    servidor.precargar(puerto)
    assert not sesion_portal._PRECARGADAS


def test_un_error_en_la_precarga_no_detiene_nada(raiz, monkeypatch):
    def falla():
        raise RuntimeError("falla ficticia")

    monkeypatch.setattr(sesion_portal, "precargar", falla)
    servidor.precargar(None)                                              # no truena: la primera vista lo hará


def test_la_primera_vista_espera_a_la_precarga(monkeypatch):
    soltar, termino = threading.Event(), threading.Event()

    def lenta(puerto):
        soltar.wait(5)
        termino.set()

    monkeypatch.setattr(servidor, "precargar", lenta)
    hilo = servidor.iniciar_precarga(None)
    assert hilo.name == servidor.HILO
    threading.Timer(0.2, soltar.set).start()
    servidor.esperar_precarga()
    assert termino.is_set() and not hilo.is_alive()
