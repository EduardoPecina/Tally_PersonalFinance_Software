"""Almacenamiento local en SQLite.

Decisiones para que los datos sobrevivan a cierres inesperados, apagones y
errores de Streamlit:

- SQLite en modo WAL con ``synchronous=FULL``: cada guardado es una
  transacción completa o no ocurre.
- Solo se escriben las entidades que cambiaron (y su registro en la
  bitácora), dentro de la misma transacción.
- Cada entidad se guarda como un documento JSON (el mismo formato que los
  respaldos), lo que facilita agregar campos en versiones futuras.
- Un contador de revisión detecta si otra ventana modificó los datos.
- Al abrir se verifica la integridad del archivo y de los datos.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import closing
from datetime import datetime
from pathlib import Path

from motor import auditoria
from motor.config import VERSION
from motor.errores import ErrorDatos
from motor.libro import Libro
from motor.serializacion import Instantanea, instantanea, libro_desde_instantanea

VERSION_ESQUEMA = 1
NOMBRE_ARCHIVO = "tally.db"

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entidades (
    tipo  TEXT NOT NULL,
    id    TEXT NOT NULL,
    datos TEXT NOT NULL,
    PRIMARY KEY (tipo, id)
);
CREATE TABLE IF NOT EXISTS bitacora (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora TEXT NOT NULL,
    entidad    TEXT NOT NULL,
    entidad_id TEXT NOT NULL,
    accion     TEXT NOT NULL,
    antes      TEXT,
    despues    TEXT
);
CREATE INDEX IF NOT EXISTS bitacora_entidad ON bitacora (entidad, entidad_id);
"""


def _json(valor) -> str | None:
    return None if valor is None else json.dumps(valor, ensure_ascii=False, sort_keys=True)


class Almacen:
    """Archivo de datos de TALLY. Una conexión por operación (seguro con hilos)."""

    def __init__(self, ruta: Path | str) -> None:
        self.ruta = Path(ruta)
        self._guardado: Instantanea = {}
        self._secuencia = 0
        self._revision = 0
        self.es_nuevo = False

    # --------------------------------------------------------------- conexión

    def _conectar(self) -> sqlite3.Connection:
        conexion = sqlite3.connect(self.ruta, isolation_level=None, timeout=10)
        try:
            conexion.execute("PRAGMA journal_mode=WAL")
            conexion.execute("PRAGMA synchronous=FULL")
        except BaseException:
            conexion.close()  # si no, en Windows el archivo queda bloqueado y no se puede apartar ni restaurar
            raise
        return conexion

    def _preparar(self) -> None:
        """Crea el archivo si no existe y comprueba que se pueda usar."""
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.es_nuevo = not self.ruta.exists() or self.ruta.stat().st_size == 0
        try:
            with closing(self._conectar()) as conexion:
                if not self.es_nuevo:
                    resultado = conexion.execute("PRAGMA quick_check").fetchone()[0]
                    if resultado != "ok":
                        raise ErrorDatos(f"El archivo de datos está dañado ({resultado}). Restaura un respaldo.")
                conexion.executescript(_ESQUEMA)
                version = self._meta(conexion, "version_esquema")
                if version is None:
                    conexion.execute("BEGIN IMMEDIATE")
                    self._poner_meta(conexion, "version_esquema", VERSION_ESQUEMA)
                    self._poner_meta(conexion, "revision", 0)
                    self._poner_meta(conexion, "secuencia", 0)
                    self._poner_meta(conexion, "creado_con", VERSION)
                    conexion.execute("COMMIT")
                elif int(version) > VERSION_ESQUEMA:
                    raise ErrorDatos("Estos datos son de una versión más nueva de TALLY. Actualiza el programa.")
        except sqlite3.DatabaseError as error:
            raise ErrorDatos(f"No se pudo abrir el archivo de datos ({error}). Restaura un respaldo.") from error

    @staticmethod
    def _meta(conexion: sqlite3.Connection, clave: str) -> str | None:
        fila = conexion.execute("SELECT valor FROM meta WHERE clave = ?", (clave,)).fetchone()
        return fila[0] if fila else None

    @staticmethod
    def _poner_meta(conexion: sqlite3.Connection, clave: str, valor) -> None:
        conexion.execute("INSERT OR REPLACE INTO meta (clave, valor) VALUES (?, ?)", (clave, str(valor)))

    # ------------------------------------------------------------------ carga

    def cargar(self, *, reloj: Callable[[], datetime] | None = None) -> Libro:
        """Lee el archivo completo y devuelve el libro."""
        self._preparar()
        try:
            with closing(self._conectar()) as conexion:
                datos: Instantanea = {}
                for tipo, entidad_id, texto in conexion.execute("SELECT tipo, id, datos FROM entidades"):
                    datos.setdefault(tipo, {})[entidad_id] = json.loads(texto)
                secuencia = int(self._meta(conexion, "secuencia") or 0)
                revision = int(self._meta(conexion, "revision") or 0)
        except (sqlite3.DatabaseError, json.JSONDecodeError) as error:
            raise ErrorDatos(f"No se pudieron leer los datos ({error}). Restaura un respaldo.") from error
        libro = libro_desde_instantanea(datos, secuencia, reloj=reloj)
        self._guardado = instantanea(libro)
        self._secuencia = libro.secuencia
        self._revision = revision
        return libro

    def libro_guardado(self, *, reloj: Callable[[], datetime] | None = None) -> Libro:
        """El último estado guardado, sin volver a leer el disco (para deshacer)."""
        return libro_desde_instantanea(self._guardado, self._secuencia, reloj=reloj)

    @property
    def estado_guardado(self) -> Instantanea:
        return self._guardado

    # --------------------------------------------------------------- guardado

    def guardar(self, libro: Libro) -> list[auditoria.Cambio]:
        """Guarda los cambios del libro en una sola transacción y los anota en la bitácora."""
        nuevo = instantanea(libro)
        cambios = auditoria.diferencias(self._guardado, nuevo)
        if not cambios and libro.secuencia == self._secuencia:
            return []
        self._escribir(libro, nuevo, cambios, reemplazar_todo=False)
        return cambios

    def reemplazar(self, libro: Libro, bitacora: Iterable[auditoria.Registro], nota: auditoria.Cambio) -> None:
        """Sustituye todo el contenido (restauración de un respaldo), en una sola transacción."""
        nuevo = instantanea(libro)
        self._escribir(libro, nuevo, [nota], reemplazar_todo=True, bitacora_previa=list(bitacora))

    def _escribir(
        self,
        libro: Libro,
        nuevo: Instantanea,
        cambios: list[auditoria.Cambio],
        *,
        reemplazar_todo: bool,
        bitacora_previa: list[auditoria.Registro] | None = None,
    ) -> None:
        momento = libro.ahora().isoformat(timespec="seconds")
        try:
            with closing(self._conectar()) as conexion:
                conexion.execute("BEGIN IMMEDIATE")
                try:
                    revision = int(self._meta(conexion, "revision") or 0)
                    if revision != self._revision and not reemplazar_todo:
                        raise ErrorDatos(
                            "Los datos cambiaron en otra ventana de TALLY. Recarga la página antes de seguir."
                        )
                    if reemplazar_todo:
                        conexion.execute("DELETE FROM entidades")
                        conexion.execute("DELETE FROM bitacora")
                        filas = [(t, i, _json(d)) for t, porid in nuevo.items() for i, d in porid.items()]
                        conexion.executemany("INSERT INTO entidades (tipo, id, datos) VALUES (?, ?, ?)", filas)
                        conexion.executemany(
                            "INSERT INTO bitacora (fecha_hora, entidad, entidad_id, accion, antes, despues)"
                            " VALUES (?, ?, ?, ?, ?, ?)",
                            [
                                (r.fecha_hora, r.entidad, r.entidad_id, r.accion, _json(r.antes), _json(r.despues))
                                for r in bitacora_previa or []
                            ],
                        )
                    else:
                        for c in cambios:
                            if c.despues is None:
                                conexion.execute(
                                    "DELETE FROM entidades WHERE tipo = ? AND id = ?", (c.entidad, c.entidad_id)
                                )
                            else:
                                conexion.execute(
                                    "INSERT OR REPLACE INTO entidades (tipo, id, datos) VALUES (?, ?, ?)",
                                    (c.entidad, c.entidad_id, _json(c.despues)),
                                )
                    conexion.executemany(
                        "INSERT INTO bitacora (fecha_hora, entidad, entidad_id, accion, antes, despues)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        [(momento, c.entidad, c.entidad_id, c.accion, _json(c.antes), _json(c.despues)) for c in cambios],
                    )
                    self._poner_meta(conexion, "secuencia", libro.secuencia)
                    self._poner_meta(conexion, "revision", revision + 1)
                    conexion.execute("COMMIT")
                except BaseException:
                    if conexion.in_transaction:
                        conexion.execute("ROLLBACK")
                    raise
        except sqlite3.DatabaseError as error:
            raise ErrorDatos(f"No se pudieron guardar los cambios ({error}).") from error
        self._guardado = nuevo
        self._secuencia = libro.secuencia
        self._revision = revision + 1

    # -------------------------------------------------------------- bitácora

    def bitacora(
        self,
        *,
        entidad: str | None = None,
        entidad_id: str | None = None,
        limite: int | None = None,
        mas_recientes_primero: bool = True,
    ) -> list[auditoria.Registro]:
        condiciones, parametros = [], []
        if entidad is not None:
            condiciones.append("entidad = ?")
            parametros.append(entidad)
        if entidad_id is not None:
            condiciones.append("entidad_id = ?")
            parametros.append(entidad_id)
        consulta = "SELECT id, fecha_hora, entidad, entidad_id, accion, antes, despues FROM bitacora"
        if condiciones:
            consulta += " WHERE " + " AND ".join(condiciones)
        consulta += " ORDER BY id " + ("DESC" if mas_recientes_primero else "ASC")
        if limite is not None:
            consulta += " LIMIT ?"
            parametros.append(limite)
        with closing(self._conectar()) as conexion:
            return [
                auditoria.Registro(
                    id=fila[0], fecha_hora=fila[1], entidad=fila[2], entidad_id=fila[3], accion=fila[4],
                    antes=json.loads(fila[5]) if fila[5] else None,
                    despues=json.loads(fila[6]) if fila[6] else None,
                )
                for fila in conexion.execute(consulta, parametros)
            ]
