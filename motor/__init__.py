"""Motor financiero de TALLY.

Toda la lógica vive aquí y es independiente de Streamlit. El portal solo
llama a estas funciones y muestra sus resultados.
"""

from motor.config import APP_NOMBRE, VERSION
from motor.libro import Libro

__all__ = ["APP_NOMBRE", "VERSION", "Libro"]
