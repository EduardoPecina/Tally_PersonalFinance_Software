"""Sesión de trabajo: el libro en memoria más su archivo de datos.

Es la puerta de entrada que usará el portal::

    sesion = Sesion.abrir()
    with sesion.cambio() as libro:
        movimientos.registrar_gasto(libro, ...)

Al salir del bloque los cambios se guardan de inmediato. Si algo falla (una
validación, un error al guardar), el libro vuelve al último estado guardado:
nunca queda a medias.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from motor import categorias, rutas
from motor.libro import Libro
from motor.persistencia import Almacen


class Sesion:
    def __init__(self, ruta_datos: Path | str, *, reloj: Callable[[], datetime] | None = None) -> None:
        self._reloj = reloj
        self._candado = threading.RLock()  # el portal atiende cada pestaña en su propio hilo
        self.almacen = Almacen(ruta_datos)
        self.libro: Libro = self.almacen.cargar(reloj=reloj)
        if self.almacen.es_nuevo:
            with self.cambio() as libro:
                categorias.cargar_catalogo_inicial(libro)

    @classmethod
    def abrir(cls, ruta_datos: Path | str | None = None, *, reloj=None) -> Sesion:
        """Abre (o crea) el archivo de datos en su lugar habitual."""
        return cls(ruta_datos or rutas.archivo_datos(), reloj=reloj)

    @contextmanager
    def cambio(self) -> Iterator[Libro]:
        """Agrupa una o varias modificaciones que se guardan juntas (todo o nada)."""
        with self._candado:
            try:
                yield self.libro
                self.almacen.guardar(self.libro)
            except BaseException:
                self.libro = self.almacen.libro_guardado(reloj=self._reloj)
                raise

    def recargar(self) -> Libro:
        """Vuelve a leer el archivo (por ejemplo, si otra ventana lo modificó)."""
        with self._candado:
            self.libro = self.almacen.cargar(reloj=self._reloj)
            return self.libro

    @staticmethod
    def apartar_archivo_danado(ruta_datos: Path | str | None = None) -> Path | None:
        """Renombra un archivo de datos que no se puede abrir (no lo borra).

        Así se puede empezar de nuevo o restaurar un respaldo sin perder el
        archivo original. Devuelve la nueva ruta, o ``None`` si no existía.
        """
        ruta = Path(ruta_datos or rutas.archivo_datos())
        if not ruta.exists():
            return None
        destino = ruta.with_name(f"{ruta.stem}_danado_{datetime.now():%Y-%m-%d_%H%M%S}{ruta.suffix}")
        ruta.rename(destino)
        for extra in ("-wal", "-shm"):
            acompanante = ruta.with_name(ruta.name + extra)
            if acompanante.exists():
                acompanante.rename(destino.with_name(destino.name + extra))
        return destino
