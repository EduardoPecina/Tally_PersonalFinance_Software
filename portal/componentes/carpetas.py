"""Elegir una carpeta con la ventana normal de Windows (la misma de «Guardar como»).

Un navegador no puede: por seguridad, las páginas web no conocen las rutas de tus carpetas. TALLY sí, porque corre
en tu PC: abre la ventana con tkinter (viene con Python, no hay que instalar nada) en un proceso aparte, para que no
se cruce con el portal y para que, si algo falla, solo se pierda esa ventana. Si no se puede abrir, siempre queda
escribir o pegar la ruta.
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


def elegir_carpeta(titulo: str, inicial: str = "") -> str | None:
    """Abre la ventana y espera a que el usuario elija. La carpeta elegida, ``""`` si canceló, o ``None`` si la
    ventana no se pudo abrir (entonces hay que escribir la ruta)."""
    inicial = inicial if inicial and os.path.isdir(inicial) else ""
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
