"""Errores del motor.

Los mensajes están pensados para mostrarse tal cual al usuario.
"""


class ErrorTally(Exception):
    """Base de todos los errores del motor."""


class ErrorValidacion(ErrorTally, ValueError):
    """Los datos recibidos no cumplen las reglas del motor."""


class ErrorNoEncontrado(ErrorTally, LookupError):
    """Se pidió una entidad que no existe."""


class ErrorDatos(ErrorTally):
    """El archivo de datos o un respaldo está dañado, es de otra versión o cambió por fuera."""


class ErrorBloqueado(ErrorTally):
    """Tus datos tienen contraseña y TALLY aún no la conoce: hay que escribirla (o usar el Kit de emergencia)."""


class ErrorContrasena(ErrorTally):
    """La contraseña o la llave del Kit de emergencia no abren estos datos."""
