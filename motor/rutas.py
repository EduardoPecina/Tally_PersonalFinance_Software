"""Dónde viven el programa y los datos del usuario.

Instalado en cualquier PC con Windows::

    Escritorio\\TALLY\\               (el Escritorio que diga Windows, esté o no en OneDrive)
      _Programa\\                     el programa (el instalador lo reemplaza al actualizar)
      TALLY.lnk, Mis datos de TALLY.lnk, LEEME.txt, instalacion.log

    C:\\Users\\<usuario>\\TALLY\\        tus datos, SIEMPRE en esta PC
      Datos\\tally.db                 tus finanzas (las actualizaciones nunca lo tocan)
      Respaldos\\                     respaldos manuales y automáticos

Los datos van en la carpeta del perfil del usuario porque:

- OneDrive no la sincroniza (solo mueve Escritorio, Documentos e Imágenes): tus finanzas no terminan en una
  nube, aunque sea la de tu empresa, y SQLite no pelea con la sincronización;
- no es ``AppData``: el Python de la Microsoft Store redirige en secreto lo que se escribe ahí a una carpeta
  privada que Windows borra al desinstalarlo;
- existe en cualquier Windows y el usuario siempre puede escribir en ella.

En desarrollo (desde el repositorio) todo vive dentro del repositorio (``Datos/`` y ``Respaldos/`` están en
``.gitignore``).

Variables de entorno: ``TALLY_RAIZ`` pone programa y datos en otra carpeta (pruebas); ``TALLY_DATOS`` cambia
solo la carpeta de los datos.
"""

from __future__ import annotations

import os
from pathlib import Path

from motor.persistencia import NOMBRE_ARCHIVO

CARPETA_PROGRAMA = "_Programa"
CARPETA_DATOS = "Datos"
CARPETA_RESPALDOS = "Respaldos"
NOMBRE_CARPETA_USUARIO = "TALLY"

_PROGRAMA = Path(__file__).resolve().parents[1]


def instalado(programa: Path | None = None) -> bool:
    """True si TALLY corre desde una instalación (carpeta ``_Programa``), no desde el repositorio."""
    return (programa or _PROGRAMA).name == CARPETA_PROGRAMA


def raiz() -> Path:
    """Carpeta de la instalación (la del Escritorio) o, en desarrollo, el repositorio."""
    if os.environ.get("TALLY_RAIZ"):
        return Path(os.environ["TALLY_RAIZ"])
    return _PROGRAMA.parent if instalado() else _PROGRAMA


def carpeta_local_del_usuario() -> Path:
    """``C:\\Users\\<usuario>\\TALLY``: donde viven los datos de una instalación."""
    if os.environ.get("TALLY_DATOS"):
        return Path(os.environ["TALLY_DATOS"])
    return Path.home() / NOMBRE_CARPETA_USUARIO


def carpeta_usuario() -> Path:
    """Carpeta que contiene ``Datos`` y ``Respaldos``.

    Si una versión anterior dejó los datos en ``Escritorio\\TALLY`` y el instalador todavía no pudo moverlos
    (OneDrive los tenía ocupados), se siguen usando ahí: nunca se empieza con un archivo vacío.
    """
    if os.environ.get("TALLY_RAIZ"):
        return Path(os.environ["TALLY_RAIZ"])
    if not instalado():
        return _PROGRAMA
    local = carpeta_local_del_usuario()
    if not _tiene_datos(local) and _tiene_datos(_PROGRAMA.parent):
        return _PROGRAMA.parent
    return local


def datos_sin_mover() -> bool:
    """True si los datos siguen en el Escritorio porque el instalador no pudo moverlos."""
    return instalado() and not os.environ.get("TALLY_RAIZ") and carpeta_usuario() != carpeta_local_del_usuario()


def _tiene_datos(carpeta: Path) -> bool:
    return (carpeta / CARPETA_DATOS / NOMBRE_ARCHIVO).exists()


def carpeta_datos() -> Path:
    return carpeta_usuario() / CARPETA_DATOS


def carpeta_respaldos() -> Path:
    return carpeta_usuario() / CARPETA_RESPALDOS


def archivo_datos() -> Path:
    return carpeta_datos() / NOMBRE_ARCHIVO
