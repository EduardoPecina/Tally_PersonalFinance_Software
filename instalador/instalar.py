"""Instalador de TALLY. Lo llama INSTALAR.bat (que antes se asegura de que haya Python 3.13).

Se puede correr las veces que sea: la primera vez INSTALA y después ACTUALIZA (reemplaza solo el programa;
tus finanzas y tus respaldos no se tocan).

    1. Instala las librerías que faltan, en las versiones exactas de requirements-lock.txt.
    2. Si ya hay datos, crea un respaldo automático ANTES de actualizar (en Respaldos).
    3. Crea en el Escritorio del usuario (el de OneDrive, si Windows lo tiene ahí) la carpeta:
           TALLY\\
             LEEME.txt          instrucciones cortas
             Datos\\             tus finanzas (tally.db). Nunca se toca al actualizar
             Respaldos\\         respaldos manuales y automáticos
             _Programa\\         el programa (se reemplaza completo al actualizar)
             instalacion.log    todo lo que pasó en cada instalación
    4. Crea el acceso directo "TALLY" en el Escritorio y dentro de la carpeta (cuando exista el portal).

Uso manual (pruebas):  python instalador/instalar.py [--sin-librerias] [--sin-accesos]
La variable TALLY_ESCRITORIO permite instalar en otra carpeta (pruebas).
"""

import argparse
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ORIGEN = Path(__file__).resolve().parents[1]              # la carpeta del ZIP (o del repositorio)
NOMBRE_CARPETA = "TALLY"
NOMBRE_ACCESO = "TALLY"
PROGRAMA, DATOS, RESPALDOS = "_Programa", "Datos", "Respaldos"
ARCHIVO_DATOS = "tally.db"
PUERTO_PORTAL = 8765
PYTHON_PROBADO = (3, 13)                                  # el mismo que instala INSTALAR.bat

# Nunca se copian al programa: control de versiones, entornos, cachés y, sobre todo, datos personales.
NO_COPIAR = shutil.ignore_patterns(
    ".git", ".github", ".venv", "venv", "__pycache__", "*.pyc", ".pytest_cache", "*.tmp", "*.log",
    PROGRAMA, DATOS, RESPALDOS, "Exportaciones", "*.db", "*.db-wal", "*.db-shm", "*.zip",
)

BITACORA = "instalacion.log"                      # en la carpeta TALLY: todo lo que muestra la ventana negra
TAMANO_MAXIMO = 2_000_000                         # bytes; si crece más, se conservan las instalaciones más recientes
PIDE_BITACORA = (f"\n\nSi necesitas ayuda, comparte el archivo {BITACORA} (carpeta TALLY de tu Escritorio): "
                 "ahí quedó el detalle de lo que pasó. No contiene tus datos financieros.")

LEEME = f"""TALLY
=====
Mis finanzas, mis números, mi PC, mis datos.

ABRIR TALLY
  Doble clic en el acceso directo "{NOMBRE_ACCESO}" (en el Escritorio o en esta carpeta).
  Se abre en tu navegador, pero todo se queda en esta computadora: no usa Internet.

CARPETAS
  Datos       tus finanzas (tally.db). No la borres ni la edites a mano.
  Respaldos   respaldos manuales y automáticos (archivos .zip).
              Copia alguno a una memoria USB o a tu nube de vez en cuando.
  _Programa   el programa. No modifiques nada aquí.

ACTUALIZAR
  Cierra TALLY y vuelve a correr INSTALAR.bat de la versión nueva. Antes de actualizar se crea un
  respaldo automático en la carpeta Respaldos. Tus datos no se tocan.

PASAR TUS DATOS A OTRA PC
  Crea un respaldo desde TALLY, instala TALLY en la otra PC y restaura ese respaldo.

SI ALGO FALLA AL INSTALAR
  Revisa o comparte el archivo instalacion.log (está en esta carpeta).
"""


# ------------------------------------------------------------------ Bitácora
class _Doble:
    """Escribe en la ventana negra y en la bitácora a la vez (si una falla, la otra sigue)."""

    def __init__(self, *destinos):
        self.destinos = destinos

    def write(self, texto):
        for destino in self.destinos:
            try:
                destino.write(texto)
                destino.flush()
            except (OSError, ValueError, UnicodeError):
                pass
        return len(texto)

    def flush(self):
        pass


class Bitacora:
    """Copia a TALLY\\instalacion.log todo lo que el instalador muestra en la ventana negra (incluido lo que
    imprime pip), con un encabezado por instalación. Cada instalación se agrega al final (historial)."""

    def __init__(self, ruta):
        self.ruta = ruta

    def __enter__(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._recortar()
        self.archivo = open(self.ruta, "a", encoding="utf-8")
        self._salida, self._errores = sys.stdout, sys.stderr
        sys.stdout = _Doble(self._salida, self.archivo)
        sys.stderr = _Doble(self._errores, self.archivo)
        return self

    def __exit__(self, *_):
        sys.stdout, sys.stderr = self._salida, self._errores
        self.archivo.close()

    def solo_archivo(self, texto):
        self.archivo.write(texto if texto.endswith("\n") else texto + "\n")
        self.archivo.flush()

    def _recortar(self):
        """Si el archivo es muy grande, conserva solo las instalaciones más recientes."""
        try:
            if self.ruta.stat().st_size <= TAMANO_MAXIMO:
                return
            texto = self.ruta.read_text(encoding="utf-8", errors="replace")[-TAMANO_MAXIMO // 2:]
            inicio = texto.find("\n=====")
            self.ruta.write_text(texto[inicio + 1:] if inicio >= 0 else texto, encoding="utf-8")
        except OSError:
            pass


def version_del_programa():
    try:
        texto = (ORIGEN / "motor" / "config.py").read_text(encoding="utf-8")
        return re.search(r'VERSION = "([^"]+)"', texto).group(1)
    except (OSError, AttributeError):
        return "desconocida"


def encabezado(raiz):
    # Sin nombre de usuario: no se guarda información innecesaria sobre la persona.
    return "\n".join([
        "=" * 78,
        f"INSTALACIÓN {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Versión del programa: {version_del_programa()}  (desde {ORIGEN})",
        f"Python: {sys.version.split()[0]}  ({sys.executable})",
        f"Sistema: {platform.platform()}",
        f"Carpeta: {raiz}",
        "=" * 78,
    ])


def pasos_de_instalar_bat():
    """Lo que INSTALAR.bat anotó antes de llamar a este programa (búsqueda o instalación de Python)."""
    ruta = os.environ.get("TALLY_BITACORA_BAT")
    if not ruta or not Path(ruta).exists():
        return ""
    try:
        return Path(ruta).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def ejecutar(comando):
    """Corre un comando mostrando su salida en la ventana y en la bitácora. Devuelve el código de salida."""
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    with subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                          text=True, encoding="utf-8", errors="replace", env=entorno) as proceso:
        for linea in proceso.stdout:
            print(linea, end="")
        return proceso.wait()


# ------------------------------------------------------------------ Windows
def avisar(mensaje, titulo="Instalador de TALLY", error=False):
    if error:
        mensaje += PIDE_BITACORA
    print(("ERROR: " if error else "") + mensaje)
    if sys.platform == "win32" and not os.environ.get("TALLY_SIN_VENTANAS"):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensaje, titulo, 0x10 if error else 0x40)


def escritorio():
    """Escritorio del usuario tal como lo tiene Windows (si está en OneDrive, el de OneDrive)."""
    if os.environ.get("TALLY_ESCRITORIO"):                    # para pruebas
        return Path(os.environ["TALLY_ESCRITORIO"])
    if sys.platform == "win32":
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        guid = uuid.UUID("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}")          # FOLDERID_Desktop
        folderid = GUID(guid.fields[0], guid.fields[1], guid.fields[2],
                        (ctypes.c_ubyte * 8).from_buffer_copy(guid.bytes[8:]))
        ruta = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folderid), 0, None, ctypes.byref(ruta)) == 0:
            try:
                return Path(ruta.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(ruta)
    return Path.home() / "Desktop"


def portal_abierto():
    try:
        with socket.create_connection(("127.0.0.1", PUERTO_PORTAL), timeout=1):
            return True
    except OSError:
        return False


# ------------------------------------------------------------------ Pasos
def instalar_librerias():
    """pip install del árbol completo de requirements-lock.txt: versiones EXACTAS y verificadas con su huella
    (--require-hashes). Si ya están, solo lo confirma. Solo instaladores precompilados: nunca intenta compilar."""
    print("Revisando librerías en las versiones probadas...")
    comando = [sys.executable, "-m", "pip", "install", "-r", str(ORIGEN / "requirements-lock.txt"),
               "--require-hashes", "--only-binary=:all:",
               "--disable-pip-version-check", "--progress-bar", "off", "--retries", "10", "--timeout", "60"]
    for intento in (1, 2):
        if ejecutar(comando) == 0:
            return True
        print(f"La instalación de librerías falló (intento {intento} de 2). Reintentando...")
    return False


def respaldar_datos(raiz):
    """Antes de actualizar, respalda los datos con el motor de la versión NUEVA (en solo lectura: el archivo
    original no se modifica). Devuelve la ruta del respaldo o None si aún no hay datos."""
    sys.path.insert(0, str(ORIGEN))
    try:
        from motor.respaldos import respaldar_archivo_de_datos
    finally:
        sys.path.remove(str(ORIGEN))
    return respaldar_archivo_de_datos(raiz / DATOS / ARCHIVO_DATOS, raiz / RESPALDOS, prefijo="antes_de_actualizar")


def borrar_carpeta(ruta, intentos=10, espera=1.0):
    """Borra una carpeta aunque tenga archivos de solo lectura. Reintenta unos segundos: OneDrive (o el antivirus)
    a veces deja archivos abiertos un momento después de copiarlos. True si quedó borrada."""
    def quitar_solo_lectura(funcion, camino, _):
        try:
            os.chmod(camino, stat.S_IWRITE)
            funcion(camino)
        except OSError:
            pass
    opcion = {"onexc": quitar_solo_lectura} if sys.version_info >= (3, 12) else {"onerror": quitar_solo_lectura}
    for intento in range(intentos):
        if not ruta.exists():
            return True
        shutil.rmtree(ruta, **opcion)
        if ruta.exists() and intento < intentos - 1:
            time.sleep(espera)
    return not ruta.exists()


def anteriores(destino):
    """Copias que deja una actualización: _Programa_anterior, _Programa_anterior_2..."""
    return sorted(p for p in destino.parent.glob(destino.name + "_anterior*") if p.is_dir())


def copiar_programa(destino):
    """Copia el programa a TALLY\\_Programa. Al actualizar, la versión anterior se reemplaza completa
    (así no quedan archivos viejos). Si el origen ya es el destino (se corrió desde _Programa), no copia.
    Mientras copia, la versión anterior queda como _Programa_anterior; si algo falla se regresa (rollback)
    y al terminar se borra. Si OneDrive no deja borrarla en ese momento, se borra en la próxima actualización."""
    if destino.exists() and destino.resolve() == ORIGEN:
        print("El programa ya está en su lugar (se corrió desde _Programa).")
        return
    for viejo in anteriores(destino):                    # restos de actualizaciones anteriores
        borrar_carpeta(viejo, intentos=3)
    anterior, n = destino.with_name(destino.name + "_anterior"), 2
    while anterior.exists():                             # uno viejo sigue bloqueado: se usa otro nombre
        anterior, n = destino.with_name(f"{destino.name}_anterior_{n}"), n + 1
    if destino.exists():
        destino.rename(anterior)             # si el portal o un archivo está abierto, Windows no deja: PermissionError
    try:
        shutil.copytree(ORIGEN, destino, ignore=NO_COPIAR)
    except BaseException:
        if destino.exists():
            borrar_carpeta(destino, intentos=3)
        if anterior.exists() and not destino.exists():
            anterior.rename(destino)         # algo falló: se deja la versión anterior como estaba
        raise
    if not borrar_carpeta(anterior):
        print(f"OneDrive todavía usa {anterior.name}: se borrará en la próxima actualización.")


def crear_estructura(raiz):
    for carpeta in (raiz / DATOS, raiz / RESPALDOS):
        carpeta.mkdir(parents=True, exist_ok=True)
    (raiz / "LEEME.txt").write_text(LEEME, encoding="utf-8-sig")


def portal_disponible(programa):
    return (programa / "portal" / "iniciar.py").exists()


def crear_accesos(raiz, programa):
    """Acceso directo con pythonw (sin ventana negra), creado con PowerShell (no requiere librerías extra)."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if pythonw.exists():
        destino, argumentos = pythonw, '"portal\\iniciar.py"'
    else:                                                        # sin pythonw: el .bat
        destino, argumentos = programa / "EJECUTAR PORTAL.bat", ""
    icono = programa / "portal" / "recursos" / "tally.ico"
    resultado = 0
    for ruta in (raiz.parent / f"{NOMBRE_ACCESO}.lnk", raiz / f"{NOMBRE_ACCESO}.lnk"):
        script = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:TALLY_LNK); "
            "$s.TargetPath = $env:TALLY_DESTINO; $s.Arguments = $env:TALLY_ARGUMENTOS; "
            "$s.WorkingDirectory = $env:TALLY_TRABAJO; $s.Description = 'Abre TALLY en el navegador'; "
            "if ($env:TALLY_ICONO) { $s.IconLocation = $env:TALLY_ICONO }; $s.Save()"
        )
        entorno = {**os.environ, "TALLY_LNK": str(ruta), "TALLY_DESTINO": str(destino),
                   "TALLY_ARGUMENTOS": argumentos, "TALLY_TRABAJO": str(programa),
                   "TALLY_ICONO": str(icono) if icono.exists() else ""}
        resultado |= subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                                    env=entorno, stdin=subprocess.DEVNULL).returncode
    return resultado == 0


def instalar(sin_librerias=False, sin_accesos=False):
    """Instala o actualiza, dejando todo registrado en TALLY\\instalacion.log."""
    raiz = escritorio() / NOMBRE_CARPETA
    try:
        bitacora = Bitacora(raiz / BITACORA).__enter__()
    except OSError:                                   # sin bitácora se instala igual
        return _instalar(raiz, sin_librerias, sin_accesos)
    try:
        bitacora.solo_archivo("\n" + encabezado(raiz))
        bat = pasos_de_instalar_bat()
        if bat:
            bitacora.solo_archivo("-- INSTALAR.bat --\n" + bat + "\n-- Instalador --")
        try:
            resultado = _instalar(raiz, sin_librerias, sin_accesos)
        except Exception:                             # noqa: BLE001 - cualquier error inesperado queda registrado
            bitacora.solo_archivo(traceback.format_exc())
            avisar("La instalación se detuvo por un error inesperado. Tus datos no se modificaron.", error=True)
            resultado = 1
        bitacora.solo_archivo(f"RESULTADO: {'terminó bien' if resultado == 0 else 'NO se completó'} "
                              f"({datetime.now():%d/%m/%Y %H:%M:%S})")
        return resultado
    finally:
        bitacora.__exit__()


def _instalar(raiz, sin_librerias, sin_accesos):
    programa = raiz / PROGRAMA
    print(f"Instalando en: {raiz}")

    if raiz.resolve() == ORIGEN or raiz.resolve() in ORIGEN.parents and ORIGEN != programa.resolve():
        avisar("El instalador se está ejecutando desde dentro de la carpeta TALLY del Escritorio.\n\n"
               "Descomprime el ZIP en otra carpeta (por ejemplo, Descargas) y corre INSTALAR.bat desde ahí.",
               error=True)
        return 1
    if sys.version_info[:2] != PYTHON_PROBADO and not sin_librerias:
        version = ".".join(map(str, PYTHON_PROBADO))
        avisar(f"Este instalador debe correr con Python {version} (se está usando "
               f"{sys.version_info.major}.{sys.version_info.minor}).\n\nUsa INSTALAR.bat: busca Python {version} y, "
               "si no está, lo instala solo para tu usuario.", error=True)
        return 1
    if portal_abierto():
        avisar("TALLY está abierto.\n\nCiérralo y vuelve a correr INSTALAR.bat.", error=True)
        return 1
    if not sin_librerias and not instalar_librerias():
        avisar("No se pudieron instalar las librerías de Python (¿sin Internet o la red las bloquea?).\n\n"
               "Vuelve a intentarlo en unos minutos.", error=True)
        return 1

    actualizacion = programa.exists()
    try:
        respaldo = respaldar_datos(raiz)
    except Exception as error:                        # noqa: BLE001 - sin respaldo no se actualiza
        avisar(f"No se pudo respaldar tus datos antes de actualizar ({error}).\n\n"
               "No se cambió nada. Revisa que la carpeta Datos esté completa.", error=True)
        return 1
    if respaldo:
        print(f"Respaldo de tus datos antes de actualizar: {respaldo}")

    try:
        crear_estructura(raiz)
        copiar_programa(programa)
    except PermissionError:
        avisar("Windows no dejó reemplazar la carpeta _Programa: algún archivo está abierto (TALLY, una "
               "ventana de esa carpeta u OneDrive sincronizando).\n\nCiérralos y vuelve a correr "
               "INSTALAR.bat. Tus datos no se modificaron.", error=True)
        return 1

    hay_portal = portal_disponible(programa)
    accesos = sin_accesos or sys.platform != "win32" or not hay_portal or crear_accesos(raiz, programa)

    mensaje = f"{'Actualización' if actualizacion else 'Instalación'} terminada.\n\nCarpeta: {raiz}"
    if respaldo:
        mensaje += f"\n\nAntes de actualizar se respaldaron tus datos en:\n{respaldo.name}"
    if hay_portal:
        mensaje += f"\n\nPara abrir TALLY: doble clic en \"{NOMBRE_ACCESO}\" en tu Escritorio."
        if not accesos:
            mensaje += "\n\n(No se pudo crear el acceso directo: usa EJECUTAR PORTAL.bat dentro de _Programa.)"
    else:
        mensaje += ("\n\nEsta versión todavía no trae el portal (las pantallas). Para ver el motor en acción: "
                    "doble clic en EJECUTAR.bat dentro de _Programa.")
    avisar(mensaje)
    if sys.platform == "win32" and not os.environ.get("TALLY_SIN_VENTANAS"):
        os.startfile(raiz)                                        # abre la carpeta en el Explorador
    return 0


if __name__ == "__main__":
    opciones = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    opciones.add_argument("--sin-librerias", action="store_true", help="no correr pip (pruebas)")
    opciones.add_argument("--sin-accesos", action="store_true", help="no crear accesos directos (pruebas)")
    argumentos = opciones.parse_args()
    sys.exit(instalar(argumentos.sin_librerias, argumentos.sin_accesos))
