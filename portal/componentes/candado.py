"""El candado del portal: la llave de tus datos mientras TALLY está abierto, el bloqueo automático y el freno a
quien intenta adivinar la contraseña.

La llave vive solo en la memoria de TALLY (nunca en el disco ni en el navegador). Al bloquear (con el botón o por
no usar TALLY un rato) se olvida, junto con tus datos en memoria, y hay que volver a escribir la contraseña.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import streamlit as st

from motor import cifrado, seguridad
from portal.componentes import sesion as sesion_portal


@dataclass
class _Estado:
    llave: bytes | None = field(default=None, repr=False)
    ultimo_uso: float = field(default_factory=time.monotonic)
    intentos: cifrado.Intentos = field(default_factory=cifrado.Intentos)
    config: cifrado.Config | None = None
    config_leida: bool = False


@st.cache_resource(show_spinner=False)
def _estado_de(ruta: str) -> _Estado:
    return _Estado()


def _estado() -> _Estado:
    """Un candado por archivo de datos (la llave de un archivo nunca se usa con otro)."""
    return _estado_de(sesion_portal.ruta_datos())


def config() -> cifrado.Config | None:
    """La contraseña de tus datos (``None`` si no tienen). Se lee una vez y se refresca tras cada cambio."""
    estado = _estado()
    if not estado.config_leida:
        estado.config = seguridad.config(sesion_portal.ruta_datos())
        estado.config_leida = True
    return estado.config


def refrescar() -> None:
    """Vuelve a leer la configuración (después de poner, cambiar o quitar la contraseña, o de restaurar)."""
    estado = _estado()
    estado.config_leida = False
    llave = sesion_portal.llave_actual()
    if llave is not None:
        estado.llave = llave


def llave() -> bytes | None:
    return _estado().llave


def abierto() -> bool:
    """True si no hay contraseña, o si ya se escribió y no ha vencido el bloqueo automático."""
    actual = config()
    if actual is None:
        return True
    estado = _estado()
    if estado.llave is None:
        return False
    minutos = actual.bloqueo_minutos
    if minutos and time.monotonic() - estado.ultimo_uso > minutos * 60:
        bloquear()
        return False
    return True


def tocar() -> None:
    """Cada vez que usas TALLY se reinicia la cuenta del bloqueo automático."""
    _estado().ultimo_uso = time.monotonic()


def entrar(llave_maestra: bytes) -> None:
    estado = _estado()
    estado.llave = llave_maestra
    estado.ultimo_uso = time.monotonic()
    estado.intentos.acierto()
    sesion_portal.olvidar_sesion()


def bloquear() -> None:
    """Olvida la llave y los datos en memoria: hay que volver a escribir la contraseña."""
    _estado().llave = None
    sesion_portal.olvidar_sesion()


def intentos() -> cifrado.Intentos:
    return _estado().intentos
