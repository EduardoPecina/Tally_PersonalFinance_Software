"""Crear y restaurar respaldos.

Un respaldo es un ``.zip`` con:

- ``manifiesto.json``: formato, versión, fecha, resumen y huellas SHA-256.
- ``datos.json``: todo el libro y la bitácora, en el mismo formato estable que
  usa la base de datos.
- ``archivos/<id>``: el archivo de cada comprobante (foto, PDF o XML), con su
  huella en el manifiesto.

Con él se reconstruye el historial completo en cualquier PC. Restaurar nunca
sobrescribe en silencio: primero se valida el archivo, luego se crea un
respaldo de seguridad de lo actual y al final se reemplaza todo en una sola
transacción.

Con contraseña (motor/cifrado.py), cada registro de ``datos.json`` y cada
comprobante van cifrados y el manifiesto lleva las «cajas» que abren la llave (con la contraseña de ese
día o con el Kit de emergencia), sin nombre ni montos. Se crea copiando lo
cifrado tal cual (no hace falta la llave) y se abre en cualquier PC.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from motor import auditoria, catalogo, cifrado, rutas
from motor.config import VERSION
from motor.errores import ErrorBloqueado, ErrorDatos
from motor.libro import Libro
from motor.persistencia import Almacen
from motor.serializacion import libro_desde_instantanea
from motor.sesion import Sesion

FORMATO = "tally-respaldo"
VERSION_FORMATO = 7  # 2: categorías con subcategorías (TALLY 0.4). 3: títulos e inversiones a plazo (TALLY 0.7).
# 4: bienes y su depreciación (TALLY 0.10). 5: préstamos (TALLY 0.11). 6: respaldos cifrados (TALLY 0.12).
# 7: reglas de categorías y comprobantes con sus archivos (TALLY 0.23).
#                      Los anteriores se ponen al día al restaurar
MANIFIESTO = "manifiesto.json"
DATOS = "datos.json"
ARCHIVOS = "archivos/"
TAMANO_MAXIMO = 512 * 1024 * 1024  # bytes descomprimidos de datos.json
TAMANO_MAXIMO_ARCHIVO = 32 * 1024 * 1024  # bytes de cada comprobante dentro del respaldo


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
    cifrado: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoRestauracion:
    restaurado: InfoRespaldo
    respaldo_de_seguridad: Path
    adopto_contrasena: bool = False      # tus datos quedaron con la contraseña de ese respaldo
    con_kit: bool = False                # se abrió con el Kit: conviene poner una contraseña nueva


# -------------------------------------------------------------------- crear


def crear(sesion: Sesion, destino: Path | str | None = None, *, prefijo: str = "respaldo",
          sin_contrasena: bool = False) -> Path:
    """Crea un respaldo de lo guardado.

    ``destino`` puede ser una carpeta (se elige un nombre con fecha y hora) o
    la ruta completa del ``.zip``. Por omisión, la carpeta ``Respaldos``.

    Si tus datos tienen contraseña, el respaldo sale cifrado; con ``sin_contrasena`` (y TALLY abierto con tu
    contraseña) sale sin cifrar, para guardarlo en un lugar seguro.
    """
    return _crear_desde(sesion.almacen, sesion.libro.ahora(), destino, prefijo, sin_contrasena=sin_contrasena)


DE_SEGURIDAD_A_CONSERVAR = 5


def de_seguridad(sesion: Sesion, prefijo: str, carpeta: Path | str | None = None) -> Path:
    """Respaldo automático antes de algo delicado (cargar datos, restaurar, empezar de cero). De cada tipo se
    conservan los últimos ``DE_SEGURIDAD_A_CONSERVAR``: los más viejos se borran solos."""
    ruta = crear(sesion, carpeta, prefijo=prefijo)
    rotar(ruta.parent, prefijo, DE_SEGURIDAD_A_CONSERVAR)
    return ruta


def rotar(carpeta: Path | str, prefijo: str, conservar: int) -> None:
    """Borra los respaldos ``TALLY_<prefijo>_*.zip`` más viejos y deja los ``conservar`` más recientes."""
    inicio = len(f"TALLY_{prefijo}_")

    def antiguedad(ruta: Path) -> tuple:              # fecha y hora del nombre; en el mismo segundo, el más nuevo
        return ruta.stem[inicio:].split("_")[:2], ruta.stat().st_mtime_ns

    anteriores = sorted(Path(carpeta).glob(f"TALLY_{prefijo}_*.zip"), key=antiguedad)
    for viejo in anteriores[:-conservar] if conservar > 0 else []:
        viejo.unlink(missing_ok=True)


def leer_perfil(ruta_datos: Path | str):
    """El perfil (y sus preferencias) de un archivo de datos, sin modificarlo; ``None`` si no hay. Lo usa el
    instalador para recrear el acceso directo con el ícono que eligió el usuario."""
    ruta_datos = Path(ruta_datos)
    if not ruta_datos.exists():
        return None
    with tempfile.TemporaryDirectory() as temporal:
        copia = Path(temporal) / "copia.db"
        _copia_de_lectura(ruta_datos, copia)
        almacen = Almacen(copia)
        if almacen.config_cifrado() is not None:
            return None                                    # con contraseña: el perfil está cifrado
        return almacen.cargar().perfil


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
    rotar(carpeta, prefijo, conservar)
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

    Se lee en modo de solo lectura y se trabaja sobre una copia temporal. Como los demás respaldos de seguridad,
    se conservan los últimos ``DE_SEGURIDAD_A_CONSERVAR``. Devuelve ``None`` si todavía no hay datos.
    """
    ruta_datos = Path(ruta_datos)
    if not ruta_datos.exists():
        return None
    with tempfile.TemporaryDirectory() as temporal:
        copia = Path(temporal) / "copia.db"
        _copia_de_lectura(ruta_datos, copia)
        almacen = Almacen(copia)
        if almacen.config_cifrado() is None:
            almacen.cargar()                               # valida los datos (con contraseña se copian tal cual)
        ruta = _crear_desde(almacen, datetime.now(), carpeta, prefijo)
    rotar(ruta.parent, prefijo, DE_SEGURIDAD_A_CONSERVAR)
    return ruta


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
            if esperado.leer_crudo() != obtenido.leer_crudo():          # igual con o sin contraseña
                raise ErrorDatos("La copia de tus datos no coincide con el original; no se movió nada.")
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)
    return destino


def _crear_desde(almacen: Almacen, momento: datetime, destino: Path | str | None, prefijo: str, *,
                 sin_contrasena: bool = False) -> Path:
    destino = Path(destino or rutas.carpeta_respaldos())
    ruta = _ruta_libre(destino, prefijo, momento) if destino.suffix.lower() != ".zip" else destino
    ruta.parent.mkdir(parents=True, exist_ok=True)

    config = almacen.config_cifrado()
    if config is not None and sin_contrasena and not almacen.desbloqueado:
        raise ErrorBloqueado("Para sacar una copia sin contraseña, primero entra con tu contraseña.")
    if config is not None and not sin_contrasena:
        crudo = almacen.leer_crudo()
        contenido = {"secuencia": crudo["secuencia"], "entidades": crudo["entidades"], "bitacora": crudo["bitacora"]}
        return _escribir_zip(ruta, contenido, momento, None, config, archivos=crudo["archivos"])
    libro = almacen.libro_guardado()
    contenido = {
        "secuencia": libro.secuencia,
        "entidades": almacen.estado_guardado,
        "bitacora": [                       # sin copias profundas: los datos de cada renglón se escriben tal cual
            {"fecha_hora": r.fecha_hora, "entidad": r.entidad, "entidad_id": r.entidad_id, "accion": r.accion,
             "antes": r.antes, "despues": r.despues}
            for r in almacen.bitacora(mas_recientes_primero=False)
        ],
    }
    return _escribir_zip(ruta, contenido, momento, _resumen(libro), None, archivos=almacen.archivos_descifrados())


def _escribir_zip(ruta: Path, contenido: dict, momento: datetime | str, resumen: dict | None,
                  config: cifrado.Config | None, *, archivos: dict[str, bytes] | None = None,
                  version_formato: int = VERSION_FORMATO, version_app: str = VERSION) -> Path:
    # Sin sangría: así Python usa su codificador en C (con sangría es diez veces más lento con años de datos).
    datos = json.dumps(contenido, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifiesto = {
        "formato": FORMATO,
        "version_formato": version_formato,
        "version_app": version_app,
        "creado_en": momento if isinstance(momento, str) else momento.isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(datos).hexdigest(),
    }
    if archivos:
        manifiesto["archivos"] = {i: hashlib.sha256(d).hexdigest() for i, d in sorted(archivos.items())}
    if config is None:
        manifiesto["resumen"] = resumen
    else:                       # sin nombre ni montos: solo lo necesario para abrirlo con la contraseña o el Kit
        manifiesto["cifrado"] = {k: v for k, v in json.loads(config.a_json()).items()
                                 if k not in ("bloqueo_minutos", "kit_comprobado")}
    temporal = ruta.with_name(ruta.name + ".tmp")
    try:
        with open(temporal, "wb") as archivo:
            with zipfile.ZipFile(archivo, "w", compression=zipfile.ZIP_DEFLATED) as zz:
                zz.writestr(MANIFIESTO, json.dumps(manifiesto, ensure_ascii=False, indent=2))
                zz.writestr(DATOS, datos)
                for i, d in sorted((archivos or {}).items()):
                    zz.writestr(ARCHIVOS + i, d)
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


@dataclass(frozen=True, slots=True)
class _Leido:
    info: InfoRespaldo
    libro: Libro
    bitacora: list[auditoria.Registro]
    config: cifrado.Config | None = None      # la contraseña del respaldo (si tiene)
    llave: bytes | None = None
    con_kit: bool = False


def inspeccionar(ruta: Path | str, *, llave: bytes | None = None, secreto: str | None = None) -> InfoRespaldo:
    """Valida un respaldo y resume su contenido, sin tocar los datos actuales.

    Si tiene contraseña hace falta ``llave`` (la de tu sesión) o ``secreto`` (la contraseña de ese día o la llave
    del Kit); si no, ``ErrorBloqueado``.
    """
    return _leer(Path(ruta), llave=llave, secreto=secreto).info


def contrasena_de(ruta: Path | str) -> cifrado.Config | None:
    """La contraseña de un respaldo (o de un ``tally.db``), sin abrirlo: ``None`` si no tiene."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ErrorDatos("No se encontró el archivo de respaldo.")
    with open(ruta, "rb") as archivo:
        if archivo.read(len(_FIRMA_SQLITE)) == _FIRMA_SQLITE:
            with tempfile.TemporaryDirectory() as temporal:
                copia = Path(temporal) / "copia.db"
                _copia_de_lectura(ruta, copia)
                return Almacen(copia).config_cifrado()
    manifiesto, _ = _abrir_zip(ruta)
    return _config_de(manifiesto)


def _config_de(manifiesto: dict) -> cifrado.Config | None:
    datos = manifiesto.get("cifrado")
    return cifrado.Config.de_json(json.dumps(datos)) if datos else None


def _llave_para(config: cifrado.Config, llave: bytes | None, secreto: str | None) -> tuple[bytes, bool]:
    """La llave maestra de un respaldo: la de tu sesión si es la misma, o la que abre tu contraseña o tu Kit."""
    if llave is not None and cifrado.huella(llave) == config.llave_id:
        return llave, False
    if not secreto:
        raise ErrorBloqueado(f"Este respaldo tiene contraseña. Escribe la contraseña que tenías ese día o la llave "
                             f"de tu Kit de emergencia del {cifrado._fecha(config.kit_creado)} (termina en "
                             f"…{config.kit_final}).")
    try:
        return cifrado.abrir_con_contrasena(config, secreto), False
    except Exception:                                         # no es la contraseña: ¿será el Kit?
        try:
            cifrado.normalizar_kit(secreto)
        except Exception:
            raise cifrado.ErrorContrasena("No coincide con la contraseña de ese respaldo ni con su Kit de "
                                          "emergencia.") from None
        return cifrado.abrir_con_kit(config, secreto), True


def _archivos_del_zip(ruta: Path, manifiesto: dict) -> dict[str, bytes]:
    """Los comprobantes del respaldo, tal como vienen (cifrados o no), comprobando su huella."""
    huellas = manifiesto.get("archivos") or {}
    if not isinstance(huellas, dict):
        raise ErrorDatos("El respaldo está dañado (la lista de comprobantes no es válida).")
    archivos = {}
    try:
        with zipfile.ZipFile(ruta) as zz:
            for i, huella in huellas.items():
                nombre = ARCHIVOS + str(i)
                if zz.getinfo(nombre).file_size > TAMANO_MAXIMO_ARCHIVO:
                    raise ErrorDatos("Un comprobante del respaldo es demasiado grande para ser de TALLY.")
                datos = zz.read(nombre)
                if hashlib.sha256(datos).hexdigest() != huella:
                    raise ErrorDatos("Un comprobante del respaldo está dañado o fue modificado (la huella no coincide).")
                archivos[str(i)] = datos
    except KeyError as error:
        raise ErrorDatos(f"Al respaldo le falta un comprobante ({error}).") from error
    except (zipfile.BadZipFile, OSError) as error:
        raise ErrorDatos(f"El archivo de respaldo está dañado ({error}).") from error
    return archivos


def _abrir_zip(ruta: Path) -> tuple[dict, bytes]:
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
    return manifiesto, datos


def _leer(ruta: Path, reloj=None, *, llave: bytes | None = None, secreto: str | None = None) -> _Leido:
    if not ruta.is_file():
        raise ErrorDatos("No se encontró el archivo de respaldo.")
    with open(ruta, "rb") as archivo:
        if archivo.read(len(_FIRMA_SQLITE)) == _FIRMA_SQLITE:
            return _leer_archivo_de_datos(ruta, reloj, llave=llave, secreto=secreto)
    manifiesto, datos = _abrir_zip(ruta)
    config = _config_de(manifiesto)
    llave_respaldo, con_kit = _llave_para(config, llave, secreto) if config else (None, False)
    try:
        contenido = json.loads(datos)
        entidades, bitacora_cruda = contenido["entidades"], contenido.get("bitacora", [])
        if config is not None:
            entidades, bitacora_cruda = _descifrar_contenido(entidades, bitacora_cruda,
                                                             cifrado.Cifrador(llave_respaldo))
        libro = libro_desde_instantanea(entidades, contenido.get("secuencia", 0), reloj=reloj)
        archivos = _archivos_del_zip(ruta, manifiesto)
        if config is not None:
            cifrador = cifrado.Cifrador(llave_respaldo)
            archivos = {i: cifrador.descifrar_bytes(d, cifrado.contexto_archivo(i)) for i, d in archivos.items()}
        _poner_archivos(libro, archivos)
        bitacora = [
            auditoria.Registro(id=0, **{k: r[k] for k in ("fecha_hora", "entidad", "entidad_id", "accion")},
                               antes=r.get("antes"), despues=r.get("despues"))
            for r in bitacora_cruda
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
        cifrado=config is not None,
    )
    return _Leido(info, libro, bitacora, config, llave_respaldo, con_kit)


def _poner_archivos(libro: Libro, archivos: dict[str, bytes]) -> None:
    """Le da al libro los archivos de sus comprobantes (se escriben al restaurar), comprobando que sean los mismos
    que se adjuntaron."""
    libro.poner_archivos(archivos)
    for c in libro.comprobantes():
        if hashlib.sha256(archivos[c.id]).hexdigest() != c.huella:
            raise ErrorDatos(f"El comprobante «{c.nombre}» del respaldo no es el que se adjuntó (la huella no "
                             "coincide).")


def _descifrar_contenido(entidades: dict, bitacora: list[dict], cifrador: cifrado.Cifrador) -> tuple[dict, list]:
    planas = {tipo: {i: cifrador.descifrar(v, cifrado.contexto_entidad(tipo, i)) for i, v in porid.items()}
              for tipo, porid in entidades.items()}
    registros = []
    for r in bitacora:
        clave = (r["fecha_hora"], r["entidad"], r["entidad_id"], r["accion"])
        registros.append({**r, **{campo: None if r.get(campo) is None else cifrador.descifrar(
            r[campo], cifrado.contexto_bitacora(campo, *clave)) for campo in ("antes", "despues")}})
    return planas, registros


def _cifrar_contenido(entidades: dict, bitacora: list[dict], cifrador: cifrado.Cifrador) -> tuple[dict, list]:
    cifradas = {tipo: {i: cifrador.cifrar(v, cifrado.contexto_entidad(tipo, i)) for i, v in porid.items()}
                for tipo, porid in entidades.items()}
    registros = []
    for r in bitacora:
        clave = (r["fecha_hora"], r["entidad"], r["entidad_id"], r["accion"])
        registros.append({**r, **{campo: None if r.get(campo) is None else cifrador.cifrar(
            r[campo], cifrado.contexto_bitacora(campo, *clave)) for campo in ("antes", "despues")}})
    return cifradas, registros


_FIRMA_SQLITE = b"SQLite format 3\x00"


def _leer_archivo_de_datos(ruta: Path, reloj=None, *, llave: bytes | None = None,
                           secreto: str | None = None) -> _Leido:
    """Un ``tally.db`` también sirve para restaurar (por ejemplo, el de otra PC). Se lee en solo lectura, sobre
    una copia, y se valida igual que al abrirlo."""
    with tempfile.TemporaryDirectory() as temporal:
        copia = Path(temporal) / "copia.db"
        _copia_de_lectura(ruta, copia)
        almacen = Almacen(copia)
        config = almacen.config_cifrado()
        llave_datos, con_kit = _llave_para(config, llave, secreto) if config else (None, False)
        if llave_datos is not None:
            almacen.desbloquear(llave_datos)
        libro = almacen.cargar(reloj=reloj)
        bitacora = almacen.bitacora(mas_recientes_primero=False)
        _poner_archivos(libro, almacen.archivos_descifrados())
    resumen = _resumen(libro)
    info = InfoRespaldo(
        ruta=ruta, creado_en=datetime.fromtimestamp(ruta.stat().st_mtime).isoformat(timespec="seconds"),
        version_app="(archivo de datos)", perfil=resumen["perfil"], cuentas=resumen["cuentas"],
        movimientos=resumen["movimientos"], primera_fecha=resumen["primera_fecha"],
        ultima_fecha=resumen["ultima_fecha"], cifrado=config is not None,
    )
    return _Leido(info, libro, bitacora, config, llave_datos, con_kit)


# ----------------------------------------------- cifrar los respaldos guardados


def cifrar_respaldo(ruta: Path | str, config: cifrado.Config, llave: bytes) -> bool:
    """Cifra un respaldo sin contraseña (en su lugar, sin cambiar su nombre ni su fecha). False si ya lo estaba."""
    ruta = Path(ruta)
    manifiesto, datos = _abrir_zip(ruta)
    if _config_de(manifiesto) is not None:
        return False
    contenido = json.loads(datos)
    cifrador = cifrado.Cifrador(llave)
    entidades, bitacora = _cifrar_contenido(contenido["entidades"], contenido.get("bitacora", []), cifrador)
    archivos = {i: cifrador.cifrar_bytes(d, cifrado.contexto_archivo(i))
                for i, d in _archivos_del_zip(ruta, manifiesto).items()}
    _reescribir(ruta, {**contenido, "entidades": entidades, "bitacora": bitacora}, manifiesto, config, archivos)
    return True


def descifrar_respaldo(ruta: Path | str, llave: bytes) -> bool:
    """Quita la contraseña de un respaldo cifrado con esta llave. False si no tenía o es de otra llave."""
    ruta = Path(ruta)
    manifiesto, datos = _abrir_zip(ruta)
    config = _config_de(manifiesto)
    if config is None or config.llave_id != cifrado.huella(llave):
        return False
    contenido = json.loads(datos)
    cifrador = cifrado.Cifrador(llave)
    entidades, bitacora = _descifrar_contenido(contenido["entidades"], contenido.get("bitacora", []), cifrador)
    archivos = {i: cifrador.descifrar_bytes(d, cifrado.contexto_archivo(i))
                for i, d in _archivos_del_zip(ruta, manifiesto).items()}
    plano = {**contenido, "entidades": entidades, "bitacora": bitacora}
    libro = libro_desde_instantanea(entidades, contenido.get("secuencia", 0))
    _reescribir(ruta, plano, {**manifiesto, "resumen": _resumen(libro)}, None, archivos)
    return True


def _reescribir(ruta: Path, contenido: dict, manifiesto: dict, config: cifrado.Config | None,
                archivos: dict[str, bytes]) -> None:
    fechas = ruta.stat()
    _escribir_zip(ruta, contenido, str(manifiesto.get("creado_en", "")), manifiesto.get("resumen"), config,
                  archivos=archivos,
                  version_formato=max(int(manifiesto.get("version_formato", 1)), VERSION_FORMATO if config else 1),
                  version_app=str(manifiesto.get("version_app", "")))
    os.utime(ruta, ns=(fechas.st_atime_ns, fechas.st_mtime_ns))       # conserva su orden en la carpeta


def convertir_carpeta(carpeta: Path | str, llave: bytes, config: cifrado.Config | None) -> tuple[int, list[str]]:
    """Cifra (``config``) o descifra (``None``) todos los respaldos de la carpeta. Devuelve cuántos cambió y los
    nombres de los que no se pudieron (por ejemplo, dañados): esos se dejan como estaban."""
    cambiados, fallidos = 0, []
    for ruta in sorted(Path(carpeta).glob("TALLY_*.zip")):
        try:
            hecho = cifrar_respaldo(ruta, config, llave) if config else descifrar_respaldo(ruta, llave)
            cambiados += int(hecho)
        except Exception:                               # noqa: BLE001 - uno dañado no detiene a los demás
            fallidos.append(ruta.name)
    return cambiados, fallidos


# ------------------------------------------------------------------ restaurar


def restaurar(sesion: Sesion, ruta: Path | str, *, carpeta_seguridad: Path | str | None = None,
              secreto: str | None = None) -> ResultadoRestauracion:
    """Reemplaza los datos actuales por los del respaldo.

    1. Valida el respaldo por completo (si falla, nada cambia). Si tiene contraseña, se abre con la de tu sesión
       (si es la misma llave) o con ``secreto``: la contraseña de ese día o la llave del Kit.
    2. Crea un respaldo de seguridad de los datos actuales.
    3. Reemplaza todo en una sola transacción y lo anota en la bitácora.

    Tus datos conservan tu contraseña actual. Si no tenías y el respaldo sí, quedan con la de ese respaldo (la
    misma contraseña y el mismo Kit).
    """
    leido = _leer(Path(ruta), reloj=sesion.libro.reloj, llave=sesion.almacen.llave, secreto=secreto)
    info = leido.info
    seguridad = de_seguridad(sesion, "antes_de_restaurar", carpeta_seguridad)
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
    adoptar = None
    if leido.config is not None and sesion.almacen.config_cifrado() is None:
        adoptar = (leido.config, leido.llave)
    sesion.almacen.reemplazar(leido.libro, leido.bitacora, nota, adoptar=adoptar)
    sesion.libro = leido.libro
    sesion.poner_al_dia()                 # un respaldo de TALLY 0.3 no tiene categorías con subcategorías
    return ResultadoRestauracion(info, seguridad, adoptar is not None, leido.con_kit and adoptar is not None)


# ------------------------------------------------------------ empezar de cero


def empezar_de_cero(sesion: Sesion, *, carpeta_seguridad: Path | str | None = None) -> Path:
    """Borra todo (perfil, cuentas, movimientos, categorías y bitácora) y deja TALLY como recién instalado.

    Antes crea un respaldo completo de lo actual (si no se puede, no se borra nada); con él se recupera todo
    desde «Restaurar». Devuelve la ruta de ese respaldo.
    """
    seguridad = de_seguridad(sesion, "antes_de_empezar_de_cero", carpeta_seguridad)
    nuevo = Libro(reloj=sesion.libro.reloj)
    catalogo.cargar(nuevo)
    nota = auditoria.Cambio(
        entidad="respaldo", entidad_id=seguridad.name, accion=auditoria.EMPEZAR_DE_CERO, antes=None,
        despues={"archivo": seguridad.name, "respaldo_de_seguridad": seguridad.name},
    )
    sesion.almacen.reemplazar(nuevo, [], nota)
    sesion.libro = nuevo
    return seguridad

