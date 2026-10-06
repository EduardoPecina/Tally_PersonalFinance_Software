"""Cambiar el color del ícono de los accesos directos de TALLY (Configuración → Apariencia).

Los accesos están en el Escritorio y dentro de la carpeta TALLY (los crea el instalador). Se actualizan con
pywin32, como al instalarlos; en otra plataforma no hay nada que hacer.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from motor import rutas

RECURSOS = Path(__file__).resolve().parent / "recursos"


def archivo_icono(variante: str) -> Path:
    """El .ico de la variante (la clara es tally.ico, la de siempre)."""
    ruta = RECURSOS / ("tally.ico" if variante == "claro" else f"tally_{variante}.ico")
    return ruta if ruta.exists() else RECURSOS / "tally.ico"


def imagen_pestana(variante: str) -> Path:
    ruta = RECURSOS / f"pestana_{variante}.png"
    return ruta if ruta.exists() else RECURSOS / "marca.png"


def _escritorio() -> Path:
    """El Escritorio que diga Windows, aunque esté en OneDrive (igual que instalador/instalar.py)."""
    if os.environ.get("TALLY_ESCRITORIO"):                    # para pruebas
        return Path(os.environ["TALLY_ESCRITORIO"])
    if sys.platform == "win32":
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        guid = uuid.UUID("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}")          # FOLDERID_Desktop
        folderid = GUID(guid.fields[0], guid.fields[1], guid.fields[2],
                        (ctypes.c_ubyte * 8).from_buffer_copy(guid.bytes[8:]))
        ruta = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folderid), 0, None, ctypes.byref(ruta)) == 0:
            try:
                return Path(ruta.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(ruta)
    return Path.home() / "Desktop"


def accesos_directos() -> list[Path]:
    posibles = [rutas.raiz() / "TALLY.lnk", _escritorio() / "TALLY.lnk"]
    return [r for r in dict.fromkeys(posibles) if r.exists()]


def cambiar_icono(variante: str) -> tuple[int, str]:
    """Pone el ícono de la variante en los accesos directos. Devuelve (cuántos se cambiaron, mensaje)."""
    if sys.platform != "win32":
        return 0, "Los accesos directos solo existen en Windows."
    accesos = accesos_directos()
    if not accesos:
        return 0, "No se encontraron los accesos directos de TALLY; se usará este ícono al reinstalar."
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return 0, "Falta pywin32; vuelve a correr INSTALAR.bat."
    pythoncom.CoInitialize()           # el portal atiende cada pestaña en su propio hilo
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        for ruta in accesos:
            acceso = shell.CreateShortcut(str(ruta))
            acceso.IconLocation = str(archivo_icono(variante))
            acceso.Save()
    except Exception as error:  # noqa: BLE001 - se informa, sin romper la página
        return 0, f"Windows no dejó cambiar el ícono ({error})."
    finally:
        pythoncom.CoUninitialize()
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # que el Explorador refresque íconos
    except Exception:  # noqa: BLE001
        pass
    return len(accesos), f"Ícono cambiado en {len(accesos)} acceso(s) directo(s)."
