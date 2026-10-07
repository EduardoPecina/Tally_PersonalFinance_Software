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
- Con contraseña (opcional, motor/cifrado.py), cada registro y la bitácora se guardan cifrados; lo único sin
  cifrar son las «cajas» que abren la llave (meta ``cifrado``) y los contadores. Sin la llave, ``cargar`` lanza
  ``ErrorBloqueado``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import closing
from datetime import datetime
from pathlib import Path

from motor import auditoria, cifrado
from motor.config import VERSION
from motor.errores import ErrorBloqueado, ErrorDatos
from motor.libro import Libro
from motor.serializacion import Instantanea, Memoria, instantanea, libro_desde_instantanea

VERSION_ESQUEMA = 6
# 1: TALLY 0.1–0.3. 2: categorías con subcategorías (entidad «rubro»). Las tablas no cambian; el contenido lo
#    pone al día ``Sesion`` (motor/catalogo.py) la primera vez que se abre. 3: títulos e inversiones a plazo
#    (entidades «valor» y «plazo», TALLY 0.7): una versión anterior ya no abre los datos, para no perderlos.
#    4: bienes (cuentas de tipo «bien» y entidad «bien», TALLY 0.10). 5: préstamos (TALLY 0.11). 6: contraseña
#    opcional (datos cifrados, motor/cifrado.py, TALLY 0.12): una versión anterior no sabría leerlos.
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
        self._memoria = Memoria()
        self._secuencia = 0
        self._revision = 0
        self.es_nuevo = False
        self._cifrador: cifrado.Cifrador | None = None

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
                elif int(version) < VERSION_ESQUEMA:
                    # Así una versión anterior de TALLY ya no los abre (no conoce las categorías nuevas).
                    conexion.execute("BEGIN IMMEDIATE")
                    self._poner_meta(conexion, "version_esquema", VERSION_ESQUEMA)
                    conexion.execute("COMMIT")
        except sqlite3.DatabaseError as error:
            raise ErrorDatos(f"No se pudo abrir el archivo de datos ({error}). Restaura un respaldo.") from error

    @staticmethod
    def _meta(conexion: sqlite3.Connection, clave: str) -> str | None:
        fila = conexion.execute("SELECT valor FROM meta WHERE clave = ?", (clave,)).fetchone()
        return fila[0] if fila else None

    @staticmethod
    def _poner_meta(conexion: sqlite3.Connection, clave: str, valor) -> None:
        conexion.execute("INSERT OR REPLACE INTO meta (clave, valor) VALUES (?, ?)", (clave, str(valor)))

    # ------------------------------------------------------------- contraseña

    def config_cifrado(self) -> cifrado.Config | None:
        """La configuración de la contraseña, o ``None`` si los datos no tienen contraseña."""
        self._preparar()
        try:
            with closing(self._conectar()) as conexion:
                texto = self._meta(conexion, "cifrado")
        except sqlite3.DatabaseError as error:
            raise ErrorDatos(f"No se pudo abrir el archivo de datos ({error}).") from error
        return cifrado.Config.de_json(texto) if texto else None

    @property
    def desbloqueado(self) -> bool:
        return self._cifrador is not None

    @property
    def llave(self) -> bytes | None:
        """La llave maestra en memoria (solo mientras TALLY está abierto con la contraseña)."""
        return self._cifrador.llave if self._cifrador else None

    def desbloquear(self, llave: bytes) -> None:
        """Le da a este almacén la llave maestra (ya comprobada con la contraseña o el Kit)."""
        config = self.config_cifrado()
        if config is None:
            raise ErrorDatos("Estos datos no tienen contraseña.")
        if cifrado.huella(llave) != config.llave_id:
            raise ErrorDatos("La llave no corresponde a estos datos.")
        self._cifrador = cifrado.Cifrador(llave)

    def guardar_config(self, config: cifrado.Config) -> None:
        """Guarda cambios de la contraseña (otra contraseña, el bloqueo, la última comprobación del Kit)."""
        actual = self.config_cifrado()
        if actual is None or actual.llave_id != config.llave_id:
            raise ErrorDatos("La configuración no corresponde a estos datos.")
        with closing(self._conectar()) as conexion:
            conexion.execute("BEGIN IMMEDIATE")
            try:
                self._poner_meta(conexion, "cifrado", config.a_json())
                conexion.execute("COMMIT")
            except BaseException:
                if conexion.in_transaction:
                    conexion.execute("ROLLBACK")
                raise

    def _guardar_valor(self, valor, contexto: str) -> str | None:
        if valor is None:
            return None
        return self._cifrador.cifrar(valor, contexto) if self._cifrador else _json(valor)

    def _leer_valor(self, texto: str | None, contexto: str):
        if texto is None or texto == "":
            return None
        if self._cifrador is not None:
            return self._cifrador.descifrar(texto, contexto)
        if cifrado.es_cifrado(texto):
            raise ErrorBloqueado("Tus datos tienen contraseña.")
        return json.loads(texto)

    def activar_cifrado(self, config: cifrado.Config, llave: bytes) -> None:
        """Cifra todos los registros y la bitácora en **una sola transacción** (todo o nada) y borra del disco
        los restos sin cifrar (``secure_delete``, checkpoint del WAL y ``VACUUM``)."""
        if self.config_cifrado() is not None:
            raise ErrorDatos("Tus datos ya tienen contraseña.")
        cifrador = cifrado.Cifrador(llave)
        self._transformar(lambda texto, contexto: cifrador.cifrar(json.loads(texto), contexto),
                          poner=config.a_json())
        self._cifrador = cifrador

    def desactivar_cifrado(self) -> None:
        """Descifra todo (una sola transacción) y quita la contraseña: los datos quedan como antes de ponerla."""
        if self._cifrador is None:
            raise ErrorBloqueado("Primero abre tus datos con tu contraseña.")
        cifrador = self._cifrador
        self._transformar(lambda texto, contexto: _json(cifrador.descifrar(texto, contexto)), poner=None)
        self._cifrador = None

    def _transformar(self, convertir, *, poner: str | None) -> None:
        try:
            with closing(self._conectar()) as conexion:
                conexion.execute("PRAGMA secure_delete=ON")
                conexion.execute("BEGIN IMMEDIATE")
                try:
                    filas = conexion.execute("SELECT tipo, id, datos FROM entidades").fetchall()
                    conexion.executemany(
                        "UPDATE entidades SET datos = ? WHERE tipo = ? AND id = ?",
                        [(convertir(datos, cifrado.contexto_entidad(tipo, i)), tipo, i) for tipo, i, datos in filas])
                    registros = conexion.execute(
                        "SELECT id, fecha_hora, entidad, entidad_id, accion, antes, despues FROM bitacora").fetchall()
                    cambios = []
                    for rid, fecha, entidad, entidad_id, accion, antes, despues in registros:
                        nuevos = [None if v is None else convertir(v, cifrado.contexto_bitacora(
                            campo, fecha, entidad, entidad_id, accion)) for campo, v in (("antes", antes),
                                                                                       ("despues", despues))]
                        cambios.append((*nuevos, rid))
                    conexion.executemany("UPDATE bitacora SET antes = ?, despues = ? WHERE id = ?", cambios)
                    if poner is None:
                        conexion.execute("DELETE FROM meta WHERE clave = 'cifrado'")
                    else:
                        self._poner_meta(conexion, "cifrado", poner)
                    revision = int(self._meta(conexion, "revision") or 0)
                    self._poner_meta(conexion, "revision", revision + 1)
                    conexion.execute("COMMIT")
                except BaseException:
                    if conexion.in_transaction:
                        conexion.execute("ROLLBACK")
                    raise
                self._revision = revision + 1
        except sqlite3.DatabaseError as error:
            raise ErrorDatos(f"No se pudieron convertir tus datos ({error}). No cambió nada.") from error
        self._limpiar_restos()

    def _limpiar_restos(self) -> None:
        """Borra del disco los restos de la versión anterior de los datos (páginas libres y el WAL)."""
        with closing(self._conectar()) as conexion:
            conexion.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conexion.execute("VACUUM")
            conexion.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def leer_crudo(self) -> dict:
        """Todo tal como está en el disco (cifrado o no), sin necesitar la llave: para respaldos y copias."""
        self._preparar()
        try:
            with closing(self._conectar()) as conexion:
                entidades: dict = {}
                for tipo, entidad_id, texto in conexion.execute("SELECT tipo, id, datos FROM entidades"):
                    entidades.setdefault(tipo, {})[entidad_id] = texto
                bitacora = [
                    {"fecha_hora": f, "entidad": e, "entidad_id": i, "accion": a, "antes": antes, "despues": despues}
                    for f, e, i, a, antes, despues in conexion.execute(
                        "SELECT fecha_hora, entidad, entidad_id, accion, antes, despues FROM bitacora ORDER BY id")
                ]
                return {"entidades": entidades, "bitacora": bitacora,
                        "secuencia": int(self._meta(conexion, "secuencia") or 0),
                        "cifrado": self._meta(conexion, "cifrado")}
        except sqlite3.DatabaseError as error:
            raise ErrorDatos(f"No se pudo leer el archivo de datos ({error}).") from error

    # ------------------------------------------------------------------ carga

    def cargar(self, *, reloj: Callable[[], datetime] | None = None) -> Libro:
        """Lee el archivo completo y devuelve el libro."""
        self._preparar()
        try:
            with closing(self._conectar()) as conexion:
                if self._meta(conexion, "cifrado") and self._cifrador is None:
                    raise ErrorBloqueado("Tus datos tienen contraseña: escríbela para entrar.")
                datos: Instantanea = {}
                for tipo, entidad_id, texto in conexion.execute("SELECT tipo, id, datos FROM entidades"):
                    datos.setdefault(tipo, {})[entidad_id] = self._leer_valor(
                        texto, cifrado.contexto_entidad(tipo, entidad_id))
                secuencia = int(self._meta(conexion, "secuencia") or 0)
                revision = int(self._meta(conexion, "revision") or 0)
        except (sqlite3.DatabaseError, json.JSONDecodeError) as error:
            raise ErrorDatos(f"No se pudieron leer los datos ({error}). Restaura un respaldo.") from error
        self._memoria = Memoria()        # recuerda cada movimiento con el diccionario que se leyó del archivo
        libro = libro_desde_instantanea(datos, secuencia, reloj=reloj, memoria=self._memoria)
        self._guardado = instantanea(libro, self._memoria)
        self._secuencia = libro.secuencia
        self._revision = revision
        return libro

    def libro_guardado(self, *, reloj: Callable[[], datetime] | None = None) -> Libro:
        """El último estado guardado, sin volver a leer el disco (para deshacer)."""
        return libro_desde_instantanea(self._guardado, self._secuencia, reloj=reloj, memoria=self._memoria)

    @property
    def estado_guardado(self) -> Instantanea:
        return self._guardado

    # --------------------------------------------------------------- guardado

    def guardar(self, libro: Libro) -> list[auditoria.Cambio]:
        """Guarda los cambios del libro en una sola transacción y los anota en la bitácora."""
        nuevo = instantanea(libro, self._memoria)
        cambios = auditoria.diferencias(self._guardado, nuevo)
        if not cambios and libro.secuencia == self._secuencia:
            return []
        self._escribir(libro, nuevo, cambios, reemplazar_todo=False)
        return cambios

    def reemplazar(self, libro: Libro, bitacora: Iterable[auditoria.Registro], nota: auditoria.Cambio, *,
                   adoptar: tuple[cifrado.Config, bytes] | None = None) -> None:
        """Sustituye todo el contenido (restauración de un respaldo), en una sola transacción.

        ``adoptar``: los datos quedan con esa contraseña (al restaurar en una PC sin contraseña un respaldo que sí
        la tiene: así sigues entrando con la misma contraseña y el mismo Kit)."""
        self._memoria = Memoria()
        nuevo = instantanea(libro, self._memoria)
        anterior = self._cifrador
        if adoptar is not None:
            if self.config_cifrado() is not None:
                raise ErrorDatos("Estos datos ya tienen contraseña.")
            self._cifrador = cifrado.Cifrador(adoptar[1])
        try:
            self._escribir(libro, nuevo, [nota], reemplazar_todo=True, bitacora_previa=list(bitacora),
                           poner_cifrado=adoptar[0].a_json() if adoptar else None)
        except BaseException:
            self._cifrador = anterior
            raise
        if adoptar is not None:
            self._limpiar_restos()

    def _escribir(
        self,
        libro: Libro,
        nuevo: Instantanea,
        cambios: list[auditoria.Cambio],
        *,
        reemplazar_todo: bool,
        bitacora_previa: list[auditoria.Registro] | None = None,
        poner_cifrado: str | None = None,
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
                        filas = [(t, i, self._guardar_valor(d, cifrado.contexto_entidad(t, i)))
                                 for t, porid in nuevo.items() for i, d in porid.items()]
                        conexion.executemany("INSERT INTO entidades (tipo, id, datos) VALUES (?, ?, ?)", filas)
                        conexion.executemany(
                            "INSERT INTO bitacora (fecha_hora, entidad, entidad_id, accion, antes, despues)"
                            " VALUES (?, ?, ?, ?, ?, ?)",
                            [self._fila_bitacora(r.fecha_hora, r.entidad, r.entidad_id, r.accion, r.antes, r.despues)
                             for r in bitacora_previa or []],
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
                                    (c.entidad, c.entidad_id,
                                     self._guardar_valor(c.despues, cifrado.contexto_entidad(c.entidad, c.entidad_id))),
                                )
                    conexion.executemany(
                        "INSERT INTO bitacora (fecha_hora, entidad, entidad_id, accion, antes, despues)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        [self._fila_bitacora(momento, c.entidad, c.entidad_id, c.accion, c.antes, c.despues)
                         for c in cambios],
                    )
                    if poner_cifrado is not None:
                        self._poner_meta(conexion, "cifrado", poner_cifrado)
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

    def _fila_bitacora(self, fecha_hora, entidad, entidad_id, accion, antes, despues) -> tuple:
        return (fecha_hora, entidad, entidad_id, accion,
                self._guardar_valor(antes, cifrado.contexto_bitacora("antes", fecha_hora, entidad, entidad_id, accion)),
                self._guardar_valor(despues, cifrado.contexto_bitacora("despues", fecha_hora, entidad, entidad_id,
                                                                       accion)))

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
            if self._meta(conexion, "cifrado") and self._cifrador is None:
                raise ErrorBloqueado("Tus datos tienen contraseña: escríbela para entrar.")
            return [
                auditoria.Registro(
                    id=fila[0], fecha_hora=fila[1], entidad=fila[2], entidad_id=fila[3], accion=fila[4],
                    antes=self._leer_valor(fila[5], cifrado.contexto_bitacora("antes", *fila[1:5])),
                    despues=self._leer_valor(fila[6], cifrado.contexto_bitacora("despues", *fila[1:5])),
                )
                for fila in conexion.execute(consulta, parametros)
            ]
