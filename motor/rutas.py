"""Dónde viven los datos del usuario.

Instalado, TALLY queda así en el Escritorio::

    TALLY\\
      _Programa\\     el programa (el instalador lo reemplaza al actualizar)
      Datos\\         tus finanzas (tally.db). Las actualizaciones no lo tocan
      Respaldos\\     respaldos manuales y automáticos

En desarrollo (desde el repositorio) se usan ``Datos/`` y ``Respaldos/`` dentro
del propio repositorio; ambas carpetas están en ``.gitignore``.

La variable de entorno ``TALLY_RAIZ`` permite usar otra carpeta (pruebas).
"""

from __future__ import annotations

import os
from pathlib import Path

from motor.persistencia import NOMBRE_ARCHIVO

CARPETA_PROGRAMA = "_Programa"
CARPETA_DATOS = "Datos"
CARPETA_RESPALDOS = "Respaldos"


def raiz() -> Path:
    if os.environ.get("TALLY_RAIZ"):
        return Path(os.environ["TALLY_RAIZ"])
    programa = Path(__file__).resolve().parents[1]
    return programa.parent if programa.name == CARPETA_PROGRAMA else programa


def carpeta_datos() -> Path:
    return raiz() / CARPETA_DATOS


def carpeta_respaldos() -> Path:
    return raiz() / CARPETA_RESPALDOS


def archivo_datos() -> Path:
    return carpeta_datos() / NOMBRE_ARCHIVO
