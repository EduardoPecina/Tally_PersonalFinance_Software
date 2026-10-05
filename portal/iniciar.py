"""Abre TALLY: inicia el servidor local (si no está corriendo) y abre el navegador.

Lo usa el acceso directo del Escritorio (con ``pythonw``, sin ventana negra) y
``EJECUTAR PORTAL.bat``. El servidor escucha solo en ``localhost``: nadie más
en la red puede verlo.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

PROGRAMA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROGRAMA))

from motor import rutas  # noqa: E402
from motor.config import PUERTO_PORTAL  # noqa: E402

URL = f"http://localhost:{PUERTO_PORTAL}"
ESPERA_MAXIMA = 90  # segundos; la primera vez Streamlit tarda más en arrancar


def abierto() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PUERTO_PORTAL), timeout=1):
            return True
    except OSError:
        return False


def avisar_error(mensaje: str) -> None:
    print(mensaje, file=sys.stderr)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, mensaje, "TALLY", 0x10)


def iniciar_servidor() -> subprocess.Popen:
    bitacora = rutas.raiz() / "portal.log"
    bitacora.parent.mkdir(parents=True, exist_ok=True)
    comando = [
        sys.executable, "-m", "streamlit", "run", str(PROGRAMA / "portal" / "app.py"),
        "--server.port", str(PUERTO_PORTAL), "--server.address", "localhost", "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    opciones = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    # El servidor hereda su propia copia del archivo; este proceso cierra la suya al terminar el bloque.
    with open(bitacora, "a", encoding="utf-8") as salida:
        salida.write(f"\n===== {datetime.now():%d/%m/%Y %H:%M:%S} · iniciando TALLY =====\n")
        salida.flush()
        return subprocess.Popen(comando, cwd=PROGRAMA, stdout=salida, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env={**os.environ, "PYTHONUTF8": "1"}, **opciones)


def main() -> int:
    if not abierto():
        proceso = iniciar_servidor()
        inicio = time.monotonic()
        while not abierto():
            if proceso.poll() is not None or time.monotonic() - inicio > ESPERA_MAXIMA:
                avisar_error("TALLY no pudo iniciar.\n\nRevisa el archivo portal.log en la carpeta TALLY de tu "
                             "Escritorio; ahí quedó el detalle.")
                return 1
            time.sleep(0.5)
    webbrowser.open(URL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
