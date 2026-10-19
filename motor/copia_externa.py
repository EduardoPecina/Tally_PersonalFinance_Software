"""Copia de tus respaldos en otra carpeta: tu NAS, un disco externo o una USB (Configuración › Respaldo automático).

Tus datos siguen en esta PC (``Datos``) y sus respaldos en ``Respaldos``; esto deja, además, una copia en la carpeta
que elijas, por si a la computadora le pasa algo. Nada sale a internet: Windows (o tu Mac) se encarga de entrar al
NAS (TALLY no guarda ninguna contraseña suya), y si tus datos tienen contraseña, la copia va cifrada como cualquier
respaldo.

- **Cuándo:** con la frecuencia que elijas (diariamente, cada semana o cada mes), al cerrar TALLY, o al abrirlo si
  quedó pendiente (el NAS estaba apagado o TALLY no se cerró bien), y solo si cambiaste algo desde la última copia.
  Con «Nunca», solo cuando le das «Copiar ahora».
- **Cuántas:** las últimas ``conservar`` (3 si no eliges otra cosa); las más viejas se borran solas.
- **Sin quedarte sin copia:** la nueva se escribe completa, se vuelve a leer para comprobarla y solo entonces se
  borran las viejas. Si algo falla a la mitad (se cae la red, se apaga el NAS), las anteriores siguen ahí.

Los ajustes y el resultado de la última copia viven en ``Datos\\copia_externa.json``: son de esta PC, no de tus
datos (no van en los respaldos) y se leen sin tu contraseña, para poder copiar al cerrar TALLY.
"""

from __future__ import annotations

import errno
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

from motor import respaldos
from motor.config import MAC
from motor.errores import ErrorTally, ErrorValidacion
from motor.persistencia import Almacen

ARCHIVO = "copia_externa.json"
PREFIJO = "copia"                       # TALLY_copia_2026-10-19_223200.zip
FRECUENCIAS = {"diaria": "Diariamente", "semanal": "Cada semana", "mensual": "Cada mes", "nunca": "Nunca"}
DIAS = {"diaria": 1, "semanal": 7, "mensual": 30}
CONSERVAR = 3
MAXIMO_CONSERVAR = 30
DIAS_PARA_AVISAR = 7                    # el Resumen avisa si lleva una semana sin poder copiar
ESPERA_AL_CERRAR = 120                  # segundos que TALLY espera la copia antes de apagarse


@dataclass(frozen=True, slots=True)
class Copia:
    """Tus ajustes (los eliges tú) y cómo salió la última copia (lo anota TALLY)."""

    carpeta: str = ""                   # vacía: no se copia a ningún lado
    frecuencia: str = "diaria"
    conservar: int = CONSERVAR
    ultima: datetime | None = None      # la última copia que salió bien
    archivo: str = ""                   # su nombre
    revision: int | None = None         # cómo estaban tus datos en esa copia (para no copiar si no cambiaron)
    error: str = ""                     # por qué falló el último intento («» si salió bien)
    intento: datetime | None = None     # el último intento, bien o mal
    fallando_desde: datetime | None = None

    @property
    def activa(self) -> bool:
        return bool(self.carpeta)

    @property
    def automatica(self) -> bool:
        return self.activa and self.frecuencia in DIAS


_FECHAS = ("ultima", "intento", "fallando_desde")
_CANDADO_ARCHIVO = threading.Lock()


def ruta_estado(ruta_datos: Path | str) -> Path:
    return Path(ruta_datos).parent / ARCHIVO


def leer(ruta_datos: Path | str) -> Copia:
    """Tus ajustes y el estado de la última copia (los de siempre si aún no hay o si el archivo se dañó)."""
    try:
        crudo = json.loads(ruta_estado(ruta_datos).read_text(encoding="utf-8"))
        datos = {k: v for k, v in crudo.items() if k in Copia.__dataclass_fields__}
        for clave in _FECHAS:
            datos[clave] = datetime.fromisoformat(datos[clave]) if datos.get(clave) else None
        copia = Copia(**datos)
    except (OSError, ValueError, TypeError, AttributeError):
        return Copia()
    if copia.frecuencia not in FRECUENCIAS:
        copia = replace(copia, frecuencia="diaria")
    if isinstance(copia.conservar, bool) or not isinstance(copia.conservar, int) or copia.conservar < 1:
        copia = replace(copia, conservar=CONSERVAR)
    if not isinstance(copia.carpeta, str):
        copia = Copia()
    return copia


def _escribir(ruta_datos: Path | str, copia: Copia) -> Copia:
    datos = asdict(copia)
    for clave in _FECHAS:
        datos[clave] = datos[clave].isoformat(timespec="seconds") if datos[clave] else None
    ruta = ruta_estado(ruta_datos)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporal, ruta)
    return copia


def _anotar(ruta_datos: Path | str, **cambios) -> Copia:
    """Cambia solo esos campos, sobre lo más reciente del archivo (los ajustes pudieron cambiar mientras copiaba)."""
    with _CANDADO_ARCHIVO:
        return _escribir(ruta_datos, replace(leer(ruta_datos), **cambios))


# --------------------------------------------------------------------------- ajustes


def normalizar(carpeta: str) -> str:
    """La ruta como la escribió o pegó el usuario, sin comillas ni espacios de más (``"\\\\NAS\\Respaldos" `` →
    ``\\\\NAS\\Respaldos``)."""
    texto = (carpeta or "").strip().strip('"').strip("'").strip()
    return os.path.normpath(texto) if texto else ""


def configurar(ruta_datos: Path | str, carpeta: str, frecuencia: str, conservar: int) -> Copia:
    """Guarda tus ajustes. Con una carpeta, primero comprueba que TALLY pueda guardar ahí; sin carpeta, ya no se
    copia a ningún lado. Si cambias de carpeta, la siguiente oportunidad hace una copia nueva ahí."""
    carpeta = normalizar(carpeta)
    if frecuencia not in FRECUENCIAS:
        raise ErrorValidacion("Elige cada cuánto copiar: diariamente, cada semana, cada mes o nunca.")
    if isinstance(conservar, bool) or not 1 <= int(conservar) <= MAXIMO_CONSERVAR:
        raise ErrorValidacion(f"Conserva entre 1 y {MAXIMO_CONSERVAR} copias.")
    if carpeta:
        _no_es_de_esta_pc(ruta_datos, carpeta)
        probar(carpeta)
    with _CANDADO_ARCHIVO:
        actual = leer(ruta_datos)
        nueva = replace(actual, carpeta=carpeta, frecuencia=frecuencia, conservar=int(conservar))
        if carpeta != actual.carpeta:                      # otra carpeta: empieza de nuevo
            nueva = replace(nueva, ultima=None, archivo="", revision=None, error="", intento=None,
                            fallando_desde=None)
        return _escribir(ruta_datos, nueva)


def _no_es_de_esta_pc(ruta_datos: Path | str, carpeta: str) -> None:
    datos = Path(ruta_datos).parent
    propias = {datos.resolve(), (datos.parent / "Respaldos").resolve()}
    try:
        elegida = Path(carpeta).resolve()
    except OSError:
        return
    if elegida in propias:
        raise ErrorValidacion("Esa es una carpeta de TALLY en esta computadora. Elige la de tu NAS o tu disco "
                              "externo: la idea es tener la copia en otro lado.")


def probar(carpeta: str) -> None:
    """Comprueba que TALLY pueda guardar en la carpeta: escribe un archivito, lo lee y lo borra. Si no puede,
    ``ErrorValidacion`` con lo que pasa, en palabras sencillas."""
    carpeta = normalizar(carpeta)
    if not carpeta:
        raise ErrorValidacion("Primero escribe o elige la carpeta de tu NAS o disco externo.")
    if not Path(carpeta).is_absolute():
        ejemplo = "/Volumes/MiNAS/Respaldos" if MAC else "\\\\MiNAS\\Respaldos o E:\\Respaldos TALLY"
        raise ErrorValidacion(f"Escribe la ruta completa de la carpeta, por ejemplo {ejemplo}.")
    ruta = Path(carpeta)
    try:
        if not ruta.is_dir():
            raise FileNotFoundError(errno.ENOENT, "no existe", carpeta)
        prueba = ruta / f".tally_prueba_{secrets.token_hex(4)}.tmp"
        try:
            prueba.write_bytes(b"TALLY")
            if prueba.read_bytes() != b"TALLY":
                raise OSError(errno.EIO, "lo que se escribió no se pudo leer igual")
        finally:
            prueba.unlink(missing_ok=True)
    except OSError as error:
        raise ErrorValidacion(explicar(error, carpeta)) from error


def explicar(error: Exception, carpeta: str) -> str:
    """Un error al copiar, en palabras sencillas."""
    if isinstance(error, ErrorTally):
        return str(error)
    if isinstance(error, FileNotFoundError):
        return (f"No encuentro la carpeta «{carpeta}». Revisa que tu NAS esté encendido (o tu disco conectado) y que "
                "la ruta esté bien escrita.")
    if isinstance(error, PermissionError):
        sistema = "Tu Mac" if MAC else "Windows"
        return f"{sistema} no deja guardar en «{carpeta}». Revisa que tu usuario tenga permiso de escribir ahí."
    if isinstance(error, OSError) and error.errno == errno.ENOSPC:
        return f"Ya no cabe nada en «{carpeta}»: está lleno. Libera espacio o conserva menos copias."
    detalle = error.strerror if isinstance(error, OSError) and error.strerror else str(error)
    return f"No se pudo guardar en «{carpeta}» ({detalle})."


# --------------------------------------------------------------------------- copiar


def toca(ruta_datos: Path | str, ahora: datetime | None = None) -> bool:
    """Si ya toca la copia automática: con carpeta y frecuencia, pasó el plazo desde la última que salió bien y
    cambiaste algo desde entonces."""
    copia = leer(ruta_datos)
    if not copia.automatica or not Path(ruta_datos).exists():
        return False
    ahora = ahora or datetime.now()
    if copia.ultima is not None and (ahora.date() - copia.ultima.date()).days < DIAS[copia.frecuencia]:
        return False
    return copia.revision is None or Almacen(ruta_datos).revision_en_disco() != copia.revision


def copiar(ruta_datos: Path | str, ahora: datetime | None = None) -> Path:
    """Hace la copia ya (toque o no): la escribe completa, la comprueba y solo entonces borra las más viejas. Anota
    cómo salió; si falla, ``ErrorValidacion`` con lo que pasó y las copias anteriores quedan como estaban."""
    ahora = ahora or datetime.now()
    copia = leer(ruta_datos)
    if not copia.activa:
        raise ErrorValidacion("Primero elige la carpeta de tu NAS o disco externo y dale «Guardar».")
    carpeta = Path(copia.carpeta)
    nueva: Path | None = None
    try:
        if not carpeta.is_dir():
            raise FileNotFoundError(errno.ENOENT, "no existe", copia.carpeta)
        revision = Almacen(ruta_datos).revision_en_disco()
        nueva = respaldos.crear_desde_archivo(ruta_datos, carpeta, prefijo=PREFIJO, momento=ahora)
        try:
            respaldos.verificar(nueva)
        except ErrorTally as error:
            raise ErrorValidacion(f"La copia en «{copia.carpeta}» quedó dañada al escribirla; las anteriores siguen "
                                  "ahí. Vuelve a intentarlo.") from error
        try:
            respaldos.rotar(carpeta, PREFIJO, copia.conservar)
        except OSError:
            pass                                           # la copia nueva ya quedó; las viejas, en la siguiente
    except (OSError, ErrorTally) as error:
        if nueva is not None and isinstance(error, ErrorValidacion):
            nueva.unlink(missing_ok=True)
        mensaje = explicar(error, copia.carpeta)
        _anotar(ruta_datos, error=mensaje, intento=ahora, fallando_desde=copia.fallando_desde or ahora)
        raise ErrorValidacion(mensaje) from error
    _anotar(ruta_datos, ultima=ahora, archivo=nueva.name, revision=revision, error="", intento=ahora,
            fallando_desde=None)
    return nueva


def aviso(ruta_datos: Path | str, ahora: datetime | None = None) -> str | None:
    """Para el Resumen: si lleva ``DIAS_PARA_AVISAR`` días o más sin poder copiar."""
    copia = leer(ruta_datos)
    if not copia.automatica or not copia.error or copia.fallando_desde is None:
        return None
    dias = ((ahora or datetime.now()).date() - copia.fallando_desde.date()).days
    if dias < DIAS_PARA_AVISAR:
        return None
    return f"Hace {dias} días que no se puede copiar tu respaldo a «{copia.carpeta}». {copia.error}"


# --------------------------------------------------------------------------- en segundo plano


class CopiaEnCurso:
    """Una copia que se hace en segundo plano (al abrir TALLY, si quedó pendiente): no te hace esperar aunque el NAS
    tarde en responder."""

    def __init__(self, ruta_datos: Path, ahora: datetime) -> None:
        self.ruta: Path | None = None
        self.error: Exception | None = None
        self._hilo = threading.Thread(target=self._hacer, args=(ruta_datos, ahora), name="TALLY-copia-externa",
                                      daemon=True)

    def _hacer(self, ruta_datos: Path, ahora: datetime) -> None:
        try:
            self.ruta = copiar(ruta_datos, ahora)
        except Exception as error:  # noqa: BLE001 - se anota y se le avisa a quien la pidió
            self.error = error

    @property
    def terminado(self) -> bool:
        return not self._hilo.is_alive()

    def esperar(self, segundos: float | None = None) -> Path | None:
        self._hilo.join(segundos)
        return self.ruta


_EN_CURSO: CopiaEnCurso | None = None
_CANDADO = threading.Lock()


def iniciar(ruta_datos: Path | str, ahora: datetime | None = None) -> CopiaEnCurso | None:
    """Si toca, empieza la copia en segundo plano; si ya se está haciendo una, regresa esa misma."""
    global _EN_CURSO
    with _CANDADO:
        if _EN_CURSO is not None and not _EN_CURSO.terminado:
            return _EN_CURSO
        if not toca(ruta_datos, ahora):
            return None
        _EN_CURSO = CopiaEnCurso(Path(ruta_datos), ahora or datetime.now())
        _EN_CURSO._hilo.start()
        return _EN_CURSO


def al_cerrar(ruta_datos: Path | str, ahora: datetime | None = None, segundos: float = ESPERA_AL_CERRAR) -> None:
    """Antes de apagar TALLY: termina la copia que se esté haciendo o hace la que toque (a lo más ``segundos``).
    Nunca impide que TALLY se cierre: si falla, queda anotado y se vuelve a intentar al abrirlo."""
    try:
        en_curso = iniciar(ruta_datos, ahora)
        if en_curso is not None:
            en_curso.esperar(segundos)
    except Exception:  # noqa: BLE001 - cerrar TALLY siempre gana
        pass
