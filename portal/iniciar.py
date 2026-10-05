"""Abre TALLY sin ventana negra: arranca el servidor local (si no está corriendo) y abre el navegador.

Lo usan el acceso directo del Escritorio (con ``pythonw``) y ``EJECUTAR PORTAL.bat``. El servidor escucha solo
en ``localhost``: nadie más en la red puede verlo. Si algo falla, muestra una ventana de Windows con el motivo;
el detalle queda en ``portal.log`` (carpeta TALLY).

Clics de más (doble clic varias veces): solo un lanzador a la vez trabaja. Los que llegan mientras otro arranca
el portal (o acaba de abrir la pestaña) se retiran sin hacer nada, así que nunca se arranca más de un servidor ni
se abren varias pestañas. El turno lo suelta el sistema operativo cuando el lanzador termina, aunque se caiga, y
un lanzador nunca vive más de ``VIDA_MAXIMA``.

Portal trabado (el puerto está abierto pero no contesta): se detienen sus procesos y se arranca uno nuevo.

Basado en el lanzador del Portal de Honorarios.
"""

from __future__ import annotations

import http.client
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

PROGRAMA = Path(__file__).resolve().parents[1]
if str(PROGRAMA) not in sys.path:
    sys.path.insert(0, str(PROGRAMA))

from motor import rutas  # noqa: E402
from motor.config import PUERTO_PORTAL  # noqa: E402

URL = f"http://localhost:{PUERTO_PORTAL}"
ESPERA_MAXIMA = 120                      # segundos; la primera vez el antivirus puede hacerlo lento
VIDA_MAXIMA = ESPERA_MAXIMA + 90         # pase lo que pase, el lanzador no vive más que esto (suelta el turno)
PAUSA_ENTRE_CLICS = 5                    # tras abrir la pestaña, los clics de más en estos segundos no abren otra
CANDADO = Path(tempfile.gettempdir()) / f"tally-{PUERTO_PORTAL}.lock"   # en TEMP, no en OneDrive


def bitacora() -> Path:
    return rutas.raiz() / "portal.log"


def abierto() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PUERTO_PORTAL), timeout=1):
            return True
    except OSError:
        return False


def responde(intentos: int = 4, tiempo_espera: float = 5) -> bool:
    """True si el portal contesta (aunque sea «todavía arrancando»). Directo a 127.0.0.1, sin proxy.
    Se le dan varias oportunidades para no confundir un portal ocupado con uno trabado."""
    for intento in range(intentos):
        conexion = http.client.HTTPConnection("127.0.0.1", PUERTO_PORTAL, timeout=tiempo_espera)
        try:
            conexion.request("GET", "/_stcore/health")
            conexion.getresponse()
            return True
        except (OSError, http.client.HTTPException):
            if intento < intentos - 1:
                time.sleep(1)
        finally:
            conexion.close()
    return False


def avisar_error(mensaje: str) -> None:
    """Ventana de Windows (no hay consola); en otros sistemas, texto."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, mensaje, "TALLY", 0x10)
    else:
        print(mensaje, file=sys.stderr)


# ------------------------------------------------------------------ Un solo lanzador a la vez
def tomar_turno():
    """Candado para que solo un lanzador a la vez arranque el portal. Devuelve el candado (se suelta con
    :func:`soltar_turno`), ``None`` si otro lanzador ya tiene el turno, o ``"sin candado"`` si no se pudo crear
    el archivo (se sigue sin protección en lugar de dejar el acceso directo sin funcionar)."""
    try:
        candado = os.open(CANDADO, os.O_RDWR | os.O_CREAT)
    except OSError:
        return "sin candado"
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(candado, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(candado, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return candado
    except OSError:
        os.close(candado)
        return None


def soltar_turno(candado) -> None:
    if isinstance(candado, int):
        os.close(candado)                      # cerrar el archivo suelta el candado


# ------------------------------------------------------------------ Arranque
def detener_portal_trabado() -> bool:
    """Detiene los procesos de este portal (nunca otro Python) y espera a que se libere el puerto. No toca a este
    lanzador ni a quien lo lanzó (si se detiene a ``pyw.exe``, Windows cierra también este lanzador)."""
    from portal.apagado import detener, procesos_del_portal

    try:
        import psutil

        yo = {os.getpid()} | {padre.pid for padre in psutil.Process().parents()}
    except Exception:
        yo = {os.getpid()}
    detener([proceso for proceso in procesos_del_portal() if proceso.pid not in yo])
    limite = time.monotonic() + 15
    while abierto() and time.monotonic() < limite:
        time.sleep(0.5)
    return not abierto()


def iniciar_servidor() -> subprocess.Popen:
    comando = [
        sys.executable, "-m", "streamlit", "run", str(PROGRAMA / "portal" / "app.py"),
        "--server.port", str(PUERTO_PORTAL), "--server.address", "localhost", "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    opciones = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    ruta = bitacora()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # El servidor hereda su propia copia del archivo; este proceso cierra la suya al terminar el bloque.
    with open(ruta, "w", encoding="utf-8") as salida:
        salida.write(f"===== {datetime.now():%d/%m/%Y %H:%M:%S} · iniciando TALLY =====\n")
        salida.flush()
        return subprocess.Popen(comando, cwd=PROGRAMA, stdout=salida, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env={**os.environ, "PYTHONUTF8": "1"}, **opciones)


def _ultimas_lineas(cuantas: int = 8) -> str:
    try:
        lineas = bitacora().read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError:
        return ""
    return "".join(lineas[-cuantas:])


def arrancar_portal() -> str | None:
    """Arranca el servidor y espera a que abra el puerto. ``None`` si quedó listo, o el mensaje de error."""
    proceso = iniciar_servidor()
    limite = time.monotonic() + ESPERA_MAXIMA
    while time.monotonic() < limite:
        if abierto():
            return None
        if proceso.poll() is not None:         # terminó antes de estar listo…
            if abierto():                      # …porque otro servidor ganó el puerto: ese sirve
                return None
            break
        time.sleep(0.5)
    else:
        proceso.terminate()
    return ("TALLY no pudo iniciar.\n\n"
            f"Detalle (últimas líneas de portal.log):\n{_ultimas_lineas() or '(vacío)'}\n"
            "El archivo portal.log está en la carpeta TALLY de tu Escritorio.")


def preparar_portal() -> str | None:
    """Deja el portal listo para abrir la pestaña. ``None`` si quedó listo, o el mensaje de error."""
    if abierto():
        if responde():
            return None                        # doble clic con TALLY ya abierto: solo otra pestaña
        if not detener_portal_trabado():
            return ("TALLY no responde y no se pudo cerrar solo.\n\n"
                    "Reinicia la computadora y vuelve a abrirlo. Tus datos están a salvo.")
    return arrancar_portal()


def main() -> int:
    candado = tomar_turno()
    if candado is None:                        # otro clic ya se está encargando: ese abre la pestaña
        return 0
    vigia = threading.Timer(VIDA_MAXIMA, os._exit, args=(1,))
    vigia.daemon = True
    vigia.start()
    try:
        error = preparar_portal()
        if error is None:
            webbrowser.open(URL)               # navegador predeterminado: pestaña nueva, o lo abre si estaba cerrado
            time.sleep(PAUSA_ENTRE_CLICS)      # se conserva el turno: los clics de más no abren otra pestaña
    finally:
        soltar_turno(candado)
        vigia.cancel()
    if error:
        avisar_error(error)                    # ya sin el turno: con la ventana abierta, otro clic puede reintentar
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
