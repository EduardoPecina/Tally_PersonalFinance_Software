"""Crear y restaurar respaldos.

Un respaldo es un ``.zip`` con dos archivos:

- ``manifiesto.json``: formato, versión, fecha, resumen y huella SHA-256.
- ``datos.json``: todo el libro y la bitácora, en el mismo formato estable que
  usa la base de datos.

Con él se reconstruye el historial completo en cualquier PC. Restaurar nunca
sobrescribe en silencio: primero se valida el archivo, luego se crea un
respaldo de seguridad de lo actual y al final se reemplaza todo en una sola
transacción.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from motor import auditoria, catalogo, rutas
from motor.config import VERSION
from motor.errores import ErrorDatos
from motor.libro import Libro
from motor.persistencia import Almacen
from motor.serializacion import libro_desde_instantanea
from motor.sesion import Sesion

FORMATO = "tally-respaldo"
VERSION_FORMATO = 2  # 2: categorías con subcategorías (TALLY 0.4). Los de formato 1 se ponen al día al restaurar
MANIFIESTO = "manifiesto.json"
DATOS = "datos.json"
TAMANO_MAXIMO = 512 * 1024 * 1024  # bytes descomprimidos de datos.json


@dataclass(frozen=True, slots=True)
class InfoRespaldo:
    """Lo que se le muestra al usuario antes de restaurar."""

    ruta: Path
    creado_en: str
    version_app: str
    perfil: str | None
    cuentas: int
    movimientos: int
    primera_fecha: str | None
    ultima_fecha: str | None


@dataclass(frozen=True, slots=True)
class ResultadoRestauracion:
    restaurado: InfoRespaldo
    respaldo_de_seguridad: Path


# -------------------------------------------------------------------- crear


def crear(sesion: Sesion, destino: Path | str | None = None, *, prefijo: str = "respaldo") -> Path:
    """Crea un respaldo de lo guardado.

    ``destino`` puede ser una carpeta (se elige un nombre con fecha y hora) o
    la ruta completa del ``.zip``. Por omisión, la carpeta ``Respaldos``.
    """
    return _crear_desde(sesion.almacen, sesion.libro.ahora(), destino, prefijo)


def leer_perfil(ruta_datos: Path | str):
    """El perfil (y sus preferencias) de un archivo de datos, sin modificarlo; ``None`` si no hay. Lo usa el
    instalador para recrear el acceso directo con el ícono que eligió el usuario."""
    ruta_datos = Path(ruta_datos)
    if not ruta_datos.exists():
        return None
    with tempfile.TemporaryDirectory() as temporal:
        copia = Path(temporal) / "copia.db"
        _copia_de_lectura(ruta_datos, copia)
        return Almacen(copia).cargar().perfil


def respaldo_del_dia(sesion: Sesion, carpeta: Path | str | None = None) -> Path | None:
    """El respaldo automático diario (Configuración): uno por día, al abrir TALLY.

    No hace nada si el usuario lo desactivó, si aún no hay perfil o si ya existe el de hoy. Conserva los
    últimos ``respaldos_a_conservar``.
    """
    perfil = sesion.libro.perfil
    if perfil is None or not perfil.respaldo_diario:
        return None
    carpeta = Path(carpeta or rutas.carpeta_respaldos())
    if any(carpeta.glob(f"TALLY_automatico_{sesion.libro.hoy():%Y-%m-%d}_*.zip")):
        return None
    return respaldo_automatico(sesion, carpeta, conservar=perfil.respaldos_a_conservar)


def respaldo_automatico(
    sesion: Sesion, carpeta: Path | str | None = None, *, conservar: int = 10, prefijo: str = "automatico"
) -> Path:
    """Respaldo con rotación: conserva solo los ``conservar`` más recientes con ese prefijo."""
    carpeta = Path(carpeta or rutas.carpeta_respaldos())
    ruta = crear(sesion, carpeta, prefijo=prefijo)
    anteriores = sorted(carpeta.glob(f"TALLY_{prefijo}_*.zip"))
    for viejo in anteriores[:-conservar] if conservar > 0 else []:
        viejo.unlink(missing_ok=True)
    return ruta


def _copia_de_lectura(ruta_datos: Path, destino: Path) -> None:
    """Copia consistente de un archivo de datos abierto en solo lectura (incluye lo pendiente en el WAL)."""
    try:
        with closing(sqlite3.connect(f"{ruta_datos.resolve().as_uri()}?mode=ro", uri=True)) as origen:
            with closing(sqlite3.connect(destino)) as copia:
                origen.backup(copia)
    except sqlite3.DatabaseError as error:
        raise ErrorDatos(f"No se pudo leer el archivo de datos ({error}).") from error


def respaldar_archivo_de_datos(
    ruta_datos: Path | str, carpeta: Path | str, *, prefijo: str = "antes_de_actualizar"
) -> Path | None:
    """Respalda un archivo de datos sin modificarlo (lo usa el instalador).

    Se lee en modo de solo lectura y se trabaja sobre una copia temporal.
    Devuelve ``None`` si todavía no hay datos.
    """
    ruta_datos = Path(ruta_datos)
    if not ruta_datos.exists():
        return None
    with tempfile.TemporaryDirectory() as temporal:
        copia = Path(temporal) / "copia.db"
        _copia_de_lectura(ruta_datos, copia)
        almacen = Almacen(copia)
        almacen.cargar()
        return _crear_desde(almacen, datetime.now(), carpeta, prefijo)


def copiar_archivo_de_datos(origen: Path | str, destino: Path | str) -> Path:
    """Copia un archivo de datos a otra carpeta y comprueba que la copia sea idéntica.

    Lo usa el instalador para mover tus datos de lugar. El original no se modifica. La copia se escribe con
    otro nombre y solo al final, ya verificada, toma el nombre definitivo: si algo falla, no queda nada a
    medias. ``ErrorDatos`` si el destino ya existe, si el original está dañado o si la copia no coincide.
    """
    origen, destino = Path(origen), Path(destino)
    if destino.exists():
        raise ErrorDatos(f"Ya hay un archivo de datos en {destino}; no se sobrescribe.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".tmp")
    temporal.unlink(missing_ok=True)
    try:
        _copia_de_lectura(origen, temporal)
        with tempfile.TemporaryDirectory() as carpeta:
            referencia = Path(carpeta) / "referencia.db"
            _copia_de_lectura(origen, referencia)            # segunda lectura, independiente de la copia
            esperado, obtenido = Almacen(referencia), Almacen(temporal)
            esperado.cargar()
            obtenido.cargar()
            if (esperado.estado_guardado != obtenido.estado_guardado
                    or len(esperado.bitacora()) != len(obtenido.bitacora())):
                raise ErrorDatos("La copia de tus datos no coincide con el original; no se movió nada.")
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    return destino


def _crear_desde(almacen: Almacen, momento: datetime, destino: Path | str | None, prefijo: str) -> Path:
    destino = Path(destino or rutas.carpeta_respaldos())
    ruta = _ruta_libre(destino, prefijo, momento) if destino.suffix.lower() != ".zip" else destino
    ruta.parent.mkdir(parents=True, exist_ok=True)

    libro = almacen.libro_guardado()
    contenido = {
        "secuencia": libro.secuencia,
        "entidades": almacen.estado_guardado,
        "bitacora": [
            {k: v for k, v in asdict(r).items() if k != "id"}
            for r in almacen.bitacora(mas_recientes_primero=False)
        ],
    }
    datos = json.dumps(contenido, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")
    manifiesto = {
        "formato": FORMATO,
        "version_formato": VERSION_FORMATO,
        "version_app": VERSION,
        "creado_en": momento.isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(datos).hexdigest(),
        "resumen": _resumen(libro),
    }
    temporal = ruta.with_name(ruta.name + ".tmp")
    try:
        with open(temporal, "wb") as archivo:
            with zipfile.ZipFile(archivo, "w", compression=zipfile.ZIP_DEFLATED) as zz:
                zz.writestr(MANIFIESTO, json.dumps(manifiesto, ensure_ascii=False, indent=2))
                zz.writestr(DATOS, datos)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)
    return ruta


def _ruta_libre(carpeta: Path, prefijo: str, momento: datetime) -> Path:
    base = f"TALLY_{prefijo}_{momento:%Y-%m-%d_%H%M%S}"
    ruta, n = carpeta / f"{base}.zip", 2
    while ruta.exists():
        ruta, n = carpeta / f"{base}_{n}.zip", n + 1
    return ruta


def _resumen(libro: Libro) -> dict:
    operaciones = libro.operaciones()
    return {
        "perfil": libro.perfil.nombre if libro.perfil else None,
        "cuentas": len(libro.cuentas()),
        "movimientos": len(operaciones),
        "primera_fecha": operaciones[0].fecha.isoformat() if operaciones else None,
        "ultima_fecha": operaciones[-1].fecha.isoformat() if operaciones else None,
    }


# --------------------------------------------------------------- leer/validar


def inspeccionar(ruta: Path | str) -> InfoRespaldo:
    """Valida un respaldo y resume su contenido, sin tocar los datos actuales."""
    info, _, _ = _leer(Path(ruta))
    return info


def _leer(ruta: Path, reloj=None) -> tuple[InfoRespaldo, Libro, list[auditoria.Registro]]:
    if not ruta.is_file():
        raise ErrorDatos("No se encontró el archivo de respaldo.")
    with open(ruta, "rb") as archivo:
        if archivo.read(len(_FIRMA_SQLITE)) == _FIRMA_SQLITE:
            return _leer_archivo_de_datos(ruta, reloj)
    try:
        with zipfile.ZipFile(ruta) as zz:
            nombres = set(zz.namelist())
            if not {MANIFIESTO, DATOS} <= nombres:
                raise ErrorDatos("El archivo no es un respaldo de TALLY.")
            if zz.getinfo(DATOS).file_size > TAMANO_MAXIMO:
                raise ErrorDatos("El respaldo es demasiado grande para ser de TALLY.")
            manifiesto = json.loads(zz.read(MANIFIESTO))
            datos = zz.read(DATOS)
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, OSError) as error:
        raise ErrorDatos(f"El archivo de respaldo está dañado ({error}).") from error

    if manifiesto.get("formato") != FORMATO:
        raise ErrorDatos("El archivo no es un respaldo de TALLY.")
    if not isinstance(manifiesto.get("version_formato"), int) or manifiesto["version_formato"] > VERSION_FORMATO:
        raise ErrorDatos("El respaldo es de una versión más nueva de TALLY. Actualiza el programa.")
    if hashlib.sha256(datos).hexdigest() != manifiesto.get("sha256"):
        raise ErrorDatos("El respaldo está incompleto o fue modificado (la huella no coincide).")

    try:
        contenido = json.loads(datos)
        libro = libro_desde_instantanea(contenido["entidades"], contenido.get("secuencia", 0), reloj=reloj)
        bitacora = [
            auditoria.Registro(id=0, **{k: r[k] for k in ("fecha_hora", "entidad", "entidad_id", "accion")},
                               antes=r.get("antes"), despues=r.get("despues"))
            for r in contenido.get("bitacora", [])
        ]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ErrorDatos(f"El contenido del respaldo está dañado ({error}).") from error

    resumen = _resumen(libro)
    info = InfoRespaldo(
        ruta=ruta,
        creado_en=str(manifiesto.get("creado_en", "")),
        version_app=str(manifiesto.get("version_app", "")),
        perfil=resumen["perfil"],
        cuentas=resumen["cuentas"],
        movimientos=resumen["movimientos"],
        primera_fecha=resumen["primera_fecha"],
        ultima_fecha=resumen["ultima_fecha"],
    )
    return info, libro, bitacora


_FIRMA_SQLITE = b"SQLite format 3\x00"


def _leer_archivo_de_datos(ruta: Path, reloj=None) -> tuple[InfoRespaldo, Libro, list[auditoria.Registro]]:
    """Un ``tally.db`` también sirve para restaurar (por ejemplo, el de otra PC). Se lee en solo lectura, sobre
    una copia, y se valida igual que al abrirlo."""
    with tempfile.TemporaryDirectory() as temporal:
        copia = Path(temporal) / "copia.db"
        _copia_de_lectura(ruta, copia)
        almacen = Almacen(copia)
        libro = almacen.cargar(reloj=reloj)
        bitacora = almacen.bitacora(mas_recientes_primero=False)
    resumen = _resumen(libro)
    info = InfoRespaldo(
        ruta=ruta, creado_en=datetime.fromtimestamp(ruta.stat().st_mtime).isoformat(timespec="seconds"),
        version_app="(archivo de datos)", perfil=resumen["perfil"], cuentas=resumen["cuentas"],
        movimientos=resumen["movimientos"], primera_fecha=resumen["primera_fecha"],
        ultima_fecha=resumen["ultima_fecha"],
    )
    return info, libro, bitacora


# ------------------------------------------------------------------ restaurar


def restaurar(sesion: Sesion, ruta: Path | str, *, carpeta_seguridad: Path | str | None = None) -> ResultadoRestauracion:
    """Reemplaza los datos actuales por los del respaldo.

    1. Valida el respaldo por completo (si falla, nada cambia).
    2. Crea un respaldo de seguridad de los datos actuales.
    3. Reemplaza todo en una sola transacción y lo anota en la bitácora.
    """
    info, libro, bitacora = _leer(Path(ruta), reloj=sesion.libro.reloj)
    seguridad = crear(sesion, carpeta_seguridad, prefijo="antes_de_restaurar")
    nota = auditoria.Cambio(
        entidad="respaldo",
        entidad_id=info.ruta.name,
        accion=auditoria.RESTAURAR,
        antes=None,
        despues={
            "archivo": info.ruta.name,
            "creado_en": info.creado_en,
            "respaldo_de_seguridad": seguridad.name,
        },
    )
    sesion.almacen.reemplazar(libro, bitacora, nota)
    sesion.libro = libro
    sesion.poner_al_dia()                 # un respaldo de TALLY 0.3 no tiene categorías con subcategorías
    return ResultadoRestauracion(info, seguridad)


# ------------------------------------------------------------ empezar de cero


def empezar_de_cero(sesion: Sesion, *, carpeta_seguridad: Path | str | None = None) -> Path:
    """Borra todo (perfil, cuentas, movimientos, categorías y bitácora) y deja TALLY como recién instalado.

    Antes crea un respaldo completo de lo actual (si no se puede, no se borra nada); con él se recupera todo
    desde «Restaurar». Devuelve la ruta de ese respaldo.
    """
    seguridad = crear(sesion, carpeta_seguridad, prefijo="antes_de_empezar_de_cero")
    nuevo = Libro(reloj=sesion.libro.reloj)
    catalogo.cargar(nuevo)
    nota = auditoria.Cambio(
        entidad="respaldo", entidad_id=seguridad.name, accion=auditoria.EMPEZAR_DE_CERO, antes=None,
        despues={"archivo": seguridad.name, "respaldo_de_seguridad": seguridad.name},
    )
    sesion.almacen.reemplazar(nuevo, [], nota)
    sesion.libro = nuevo
    return seguridad

