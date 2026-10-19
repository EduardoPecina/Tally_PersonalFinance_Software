"""Elegir una carpeta con la ventana normal del sistema (la misma de «Guardar como»).

Un navegador no puede: por seguridad, las páginas web no conocen las rutas de tus carpetas. TALLY sí, porque corre
en tu computadora. En Windows abre la ventana con tkinter (viene con Python, no hay que instalar nada); en Mac, con
la de la propia Mac («choose folder» de AppleScript). Siempre en un proceso aparte, para que no se cruce con el
portal y para que, si algo falla, solo se pierda esa ventana. Si no se puede abrir, siempre queda escribir o pegar la
ruta.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ESPERA = 10 * 60                        # segundos: si nadie elige nada, la ventana se da por cancelada

_VENTANA = r"""
import sys
import tkinter
from tkinter import filedialog

salida, titulo, inicial = sys.argv[1:4]
raiz = tkinter.Tk()
raiz.withdraw()
raiz.attributes("-topmost", True)       # al frente del navegador
raiz.update()
elegida = filedialog.askdirectory(parent=raiz, title=titulo, initialdir=inicial or None, mustexist=True)
raiz.destroy()
with open(salida, "w", encoding="utf-8") as archivo:
    archivo.write(elegida or "")
"""


_VENTANA_MAC = """on run argv
set aviso to item 1 of argv
if (count of argv) > 1 then
    set elegida to choose folder with prompt aviso default location (POSIX file (item 2 of argv))
else
    set elegida to choose folder with prompt aviso
end if
return POSIX path of elegida
end run"""


def elegir_carpeta(titulo: str, inicial: str = "") -> str | None:
    """Abre la ventana y espera a que el usuario elija. La carpeta elegida, ``""`` si canceló, o ``None`` si la
    ventana no se pudo abrir (entonces hay que escribir la ruta)."""
    inicial = inicial if inicial and os.path.isdir(inicial) else ""
    if sys.platform == "darwin":
        return _elegir_en_mac(titulo, inicial)
    opciones = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    with tempfile.TemporaryDirectory() as temporal:
        salida = Path(temporal) / "carpeta.txt"
        try:
            resultado = subprocess.run([sys.executable, "-c", _VENTANA, str(salida), titulo, inicial],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=ESPERA, check=False, **opciones)
            if resultado.returncode != 0 or not salida.exists():
                return None
            elegida = salida.read_text(encoding="utf-8").strip()
        except (OSError, subprocess.SubprocessError):
            return None
    return os.path.normpath(elegida) if elegida else ""


def _elegir_en_mac(titulo: str, inicial: str) -> str | None:
    try:
        resultado = subprocess.run(["osascript", "-e", _VENTANA_MAC, titulo, *([inicial] if inicial else [])],
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=ESPERA,
                                   check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if resultado.returncode == 0 and resultado.stdout.strip():
        return os.path.normpath(resultado.stdout.strip())
    if "-128" in resultado.stderr:                       # «User canceled»: le dio Cancelar
        return ""
    return None
