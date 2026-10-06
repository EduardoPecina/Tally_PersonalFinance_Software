"""Limpieza al abrir el portal: borra las copias que deja una actualización (``_Programa_anterior``) si el
instalador no pudo borrarlas en su momento (OneDrive sincronizando, antivirus). Así no quedan carpetas raras.

Solo se borra una carpeta si es seguro que es una copia vieja del programa: está junto a ``_Programa``, se llama
``_Programa_anterior...`` y todo lo que contiene son nombres que también tiene el programa actual. Nunca toca
``Datos`` ni ``Respaldos``.

Basado en la limpieza del Portal de Honorarios.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import threading
import time
from pathlib import Path

PROGRAMA = Path(__file__).resolve().parents[1]


def es_copia_del_programa(carpeta: Path, programa: Path = PROGRAMA) -> bool:
    """True si todo lo que hay en la carpeta también existe en el programa actual (aunque esté a medio borrar)."""
    actuales = {p.name.lower() for p in programa.iterdir()}
    try:
        return all(p.name.lower() in actuales for p in carpeta.iterdir())
    except OSError:
        return False


def copias_viejas(programa: Path = PROGRAMA) -> list[Path]:
    if programa.name != "_Programa":                     # en una carpeta de desarrollo no se toca nada
        return []
    return [p for p in sorted(programa.parent.glob("_Programa_anterior*"))
            if p.is_dir() and es_copia_del_programa(p, programa)]


def restos_de_migracion(programa: Path = PROGRAMA) -> list[Path]:
    """Carpetas «Datos_movido_*» que dejó el instalador al mover tus datos fuera del Escritorio.

    Solo se crean DESPUÉS de comprobar que la copia nueva es idéntica, así que borrarlas es seguro; quedan
    cuando OneDrive no dejó borrarlas en ese momento. (Las «Datos_anterior_*» nunca se borran solas.)"""
    if programa.name != "_Programa":
        return []
    return [p for p in sorted(programa.parent.glob("Datos_movido_*")) if p.is_dir()]


def borrar(carpeta: Path, intentos: int = 5, espera: float = 2.0) -> bool:
    def quitar_solo_lectura(funcion, camino, _):
        try:
            os.chmod(camino, stat.S_IWRITE)
            funcion(camino)
        except OSError:
            pass

    opcion = {"onexc": quitar_solo_lectura} if sys.version_info >= (3, 12) else {"onerror": quitar_solo_lectura}
    for _ in range(intentos):
        shutil.rmtree(carpeta, **opcion)
        if not carpeta.exists():
            return True
        time.sleep(espera)
    return False


def limpiar_copias(programa: Path = PROGRAMA, en_segundo_plano: bool = True) -> None:
    """Borra las copias viejas. En segundo plano para no retrasar la apertura del portal."""
    viejas = copias_viejas(programa) + restos_de_migracion(programa)
    if not viejas:
        return

    def trabajo():
        for carpeta in viejas:
            borrar(carpeta)

    if en_segundo_plano:
        threading.Thread(target=trabajo, name="limpieza-copias", daemon=True).start()
    else:
        trabajo()
