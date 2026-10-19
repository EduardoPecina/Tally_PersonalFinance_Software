"""Arranca el servidor del portal (Streamlit) y deja listo de antemano lo más pesado de la primera vista.

Lo lanza ``portal/iniciar.py`` con los mismos argumentos que ``streamlit run`` (``servidor.py run portal/app.py
--server.port …``). Mientras tu navegador abre (uno o dos segundos), un hilo aparte carga las librerías (pandas,
Altair…) y las páginas del Resumen y, si tus datos no tienen contraseña, los lee. Así la primera vista sale casi un
segundo antes. Si algo falla aquí no pasa nada: la primera vista lo hace como siempre.

Para no estorbarse: la precarga empieza cuando Streamlit ya está escuchando, y la primera vista la espera
(:func:`esperar_precarga`) antes de cargar lo mismo.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

PROGRAMA = Path(__file__).resolve().parents[1]
HILO = "tally-precarga"
ESPERA_SERVIDOR = 60                # segundos: si Streamlit no abre el puerto en este tiempo, no se precarga nada
ESPERA_PRECARGA = 60                # segundos que la primera vista espera, a lo más, a que termine


def esperar_servidor(puerto: int, segundos: float = ESPERA_SERVIDOR) -> bool:
    """True cuando el servidor ya escucha en ``puerto`` (False si no abre a tiempo)."""
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def precargar(puerto: int | None = None) -> None:
    """Carga lo de la primera vista (en el hilo :data:`HILO`). Con ``puerto``, primero espera a que Streamlit abra."""
    if puerto is not None and not esperar_servidor(puerto):
        return
    try:
        if str(PROGRAMA) not in sys.path:
            sys.path.insert(0, str(PROGRAMA))
        from portal.componentes import sesion
        from portal.paginas import inicio, salud  # noqa: F401 - pandas, Altair y lo que usa el Resumen

        sesion.precargar()
    except Exception:  # noqa: BLE001 - la precarga es solo para ganar tiempo; la primera vista lo hará si falla
        pass


def iniciar_precarga(puerto: int | None) -> threading.Thread:
    hilo = threading.Thread(target=precargar, args=(puerto,), name=HILO, daemon=True)
    hilo.start()
    return hilo


def esperar_precarga(segundos: float = ESPERA_PRECARGA) -> None:
    """La primera vista espera a que termine la precarga (si la hay): así no se carga lo mismo en dos hilos a la vez."""
    for hilo in threading.enumerate():
        if hilo.name == HILO and hilo is not threading.current_thread():
            hilo.join(segundos)


def puerto_de(argumentos: list[str]) -> int:
    """El puerto que se le pide a Streamlit (o el de TALLY, si no se dice)."""
    try:
        return int(argumentos[argumentos.index("--server.port") + 1])
    except (ValueError, IndexError):
        sys.path.insert(0, str(PROGRAMA))
        from motor.config import PUERTO_PORTAL

        return PUERTO_PORTAL


def main(argumentos: list[str]) -> int:
    from streamlit.web import cli

    iniciar_precarga(puerto_de(argumentos))
    sys.argv = ["streamlit", *argumentos]
    return cli.main(prog_name="streamlit")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
