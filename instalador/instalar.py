"""Instalador de TALLY. Lo llama INSTALAR.bat (que antes se asegura de que haya Python 3.13).

Se puede correr las veces que sea: la primera vez INSTALA y después ACTUALIZA (reemplaza solo el programa;
tus finanzas y tus respaldos no se tocan).

    1. Instala las librerías que faltan, en las versiones exactas de requirements-lock.txt.
    2. Si ya hay datos, crea un respaldo automático ANTES de actualizar (en Respaldos).
    3. Crea en el Escritorio del usuario (el que diga Windows, esté o no en OneDrive) la carpeta:
           TALLY\\
             TALLY.lnk                  abre TALLY
             Mis datos de TALLY.lnk     abre la carpeta de tus datos
             LEEME.txt                  instrucciones cortas
             _Programa\\                 el programa (se reemplaza completo al actualizar)
             instalacion.log            todo lo que pasó en cada instalación
       Si no se puede escribir en el Escritorio, instala en C:\\Users\\<usuario>\\TALLY.
    4. Tus datos viven SIEMPRE en esta PC, en C:\\Users\\<usuario>\\TALLY (Datos y Respaldos): fuera de
       OneDrive y de cualquier nube. Si una versión anterior los tenía en el Escritorio, se mueven ahí
       (copia verificada; el original se quita solo después de comprobar la copia).
    5. Crea el acceso directo "TALLY" en el Escritorio y dentro de la carpeta.

Uso manual (pruebas):  python instalador/instalar.py [--sin-librerias] [--sin-accesos]
Las variables TALLY_ESCRITORIO y TALLY_DATOS permiten usar otras carpetas (pruebas).
"""

import argparse
import os
import platform
import queue
import re
import shutil
import site
import socket
import stat
import subprocess
import sys
import sysconfig
import threading
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

NOMBRE_ACCESO_DATOS = "Mis datos de TALLY"

LEEME = """TALLY
=====
Mis finanzas, mis números, mi PC, mis datos.

ABRIR TALLY
  Doble clic en el acceso directo "TALLY" (en el Escritorio o en esta carpeta).
  Se abre en tu navegador, pero todo se queda en esta computadora: no usa Internet.
  Para cerrarlo: botón "Cerrar TALLY" en el menú de la izquierda.
  Si el acceso directo no funciona: _Programa\\EJECUTAR PORTAL.bat

TUS DATOS
  Viven en esta PC, en la carpeta {datos}
  (acceso directo "Mis datos de TALLY" en esta carpeta). Nunca se suben a OneDrive ni a ninguna nube.
    Datos       tus finanzas (tally.db). No la borres ni la edites a mano.
    Respaldos   respaldos manuales y automáticos (archivos .zip).
                Copia alguno a una memoria USB o a donde quieras de vez en cuando.

ESTA CARPETA
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


AVISO_SILENCIO = 30                                   # segundos sin salida antes de decir «sigue trabajando»


def ejecutar(comando):
    """Corre un comando mostrando su salida en la ventana y en la bitácora. Devuelve el código de salida.

    Si el comando pasa un rato sin imprimir nada (pip instalando miles de archivos mientras el antivirus los
    revisa), se avisa que sigue trabajando: una ventana quieta parece congelada y la gente la cierra, lo que
    deja la instalación a medias."""
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    with subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                          text=True, encoding="utf-8", errors="replace", env=entorno) as proceso:
        lineas = queue.Queue()

        def leer():
            for linea in proceso.stdout:
                lineas.put(linea)
            lineas.put(None)

        threading.Thread(target=leer, daemon=True).start()
        inicio = time.monotonic()
        while True:
            try:
                linea = lineas.get(timeout=AVISO_SILENCIO)
            except queue.Empty:
                minutos, segundos = divmod(int(time.monotonic() - inicio), 60)
                print(f"   ...sigue trabajando ({minutos} min {segundos:02d} s). No cierres esta ventana.")
                continue
            if linea is None:
                break
            print(linea, end="")
        return proceso.wait()


def carpetas_de_librerias():
    """Carpetas donde pip instala para este Python (la del usuario y la general)."""
    carpetas = {Path(sysconfig.get_paths()["purelib"])}
    try:
        carpetas.add(Path(site.getusersitepackages()))
    except Exception:  # noqa: BLE001 - algunos Python empaquetados no la tienen
        pass
    return [c for c in carpetas if c.is_dir()]


def limpiar_restos_de_pip(carpetas=None):
    """Borra lo que deja una instalación interrumpida: pip renombra a «~nombre» mientras reemplaza un paquete y,
    si se cierra la ventana a la mitad, ahí se queda («Ignoring invalid distribution ~treamlit»). Solo toca
    entradas que empiezan con «~» dentro de las carpetas de librerías."""
    borrados = []
    for carpeta in carpetas if carpetas is not None else carpetas_de_librerias():
        for resto in carpeta.glob("~*"):
            if resto.is_dir():
                if borrar_carpeta(resto, intentos=3):
                    borrados.append(resto.name)
            else:
                try:
                    resto.unlink()
                    borrados.append(resto.name)
                except OSError:
                    pass
    if borrados:
        print(f"Se limpiaron restos de una instalación anterior interrumpida: {', '.join(borrados)}")
    return borrados


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
    limpiar_restos_de_pip()
    print("Revisando librerías en las versiones probadas...")
    print("La primera vez puede tardar hasta 10 minutos (el antivirus revisa miles de archivos). "
          "No cierres esta ventana aunque parezca quieta.")
    comando = [sys.executable, "-m", "pip", "install", "-r", str(ORIGEN / "requirements-lock.txt"),
               "--require-hashes", "--only-binary=:all:",
               "--disable-pip-version-check", "--progress-bar", "off", "--retries", "10", "--timeout", "60"]
    for intento in (1, 2):
        if ejecutar(comando) == 0:
            return True
        print(f"La instalación de librerías falló (intento {intento} de 2). Reintentando...")
    return False


def _motor(modulo):
    """Un módulo del motor de la versión NUEVA (la del ZIP), sin dejarlo en sys.path."""
    import importlib

    sys.path.insert(0, str(ORIGEN))
    try:
        return importlib.import_module(f"motor.{modulo}")
    finally:
        sys.path.remove(str(ORIGEN))


def carpeta_de_datos():
    """C:\\Users\\<usuario>\\TALLY: la misma regla que usa el programa instalado (motor/rutas.py)."""
    return _motor("rutas").carpeta_local_del_usuario()


def archivo_de_datos_actual(raiz, base):
    """Dónde están hoy los datos: en su lugar (base) o donde los dejó una versión anterior (Escritorio)."""
    for carpeta in (base, raiz):
        ruta = carpeta / DATOS / ARCHIVO_DATOS
        if ruta.exists():
            return ruta
    return None


def respaldar_datos(raiz, base):
    """Antes de actualizar, respalda los datos con el motor de la versión NUEVA (en solo lectura: el archivo
    original no se modifica). Devuelve la ruta del respaldo o None si aún no hay datos."""
    actual = archivo_de_datos_actual(raiz, base)
    if actual is None:
        return None
    return _motor("respaldos").respaldar_archivo_de_datos(actual, base / RESPALDOS, prefijo="antes_de_actualizar")


def migrar_datos(raiz, base):
    """Mueve los datos que una versión anterior dejó en el Escritorio (raiz) a su lugar (base).

    1. Copia tally.db y comprueba que la copia sea idéntica (motor.respaldos.copiar_archivo_de_datos).
    2. Solo entonces aparta el original («Datos_movido_<fecha>») y lo borra. Si Windows no deja apartarlo,
       se quita la copia nueva y se lanza el error: los datos se quedan donde estaban y el programa los sigue
       usando ahí (motor/rutas.py) hasta la próxima actualización. Nunca quedan dos versiones en uso.
    3. Mueve los respaldos .zip.

    Se llama DESPUÉS de instalar el programa nuevo: si se moviera antes y luego fallara la copia del programa,
    la versión anterior (que busca los datos en el Escritorio) abriría vacía.

    Si ya había datos en los dos lugares (no debería pasar), se usan los de su lugar y los del Escritorio se
    conservan sin tocar como «Datos_anterior_<fecha>». Devuelve un aviso para el usuario, o "".
    """
    if raiz.resolve() == base.resolve():
        return ""
    aviso = ""
    sello = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    viejos, nuevos = raiz / DATOS, base / DATOS
    if (viejos / ARCHIVO_DATOS).exists():
        if (nuevos / ARCHIVO_DATOS).exists():
            apartados = raiz / f"Datos_anterior_{sello}"
            try:
                renombrar(viejos, apartados)
            except OSError:
                apartados = viejos
            aviso = (f"Había datos en dos lugares. TALLY usa los de {nuevos}. Los del Escritorio se conservaron "
                     f"sin tocar en {apartados}.")
            print(aviso)
        else:
            print(f"Moviendo tus datos a {nuevos} (fuera de OneDrive y de cualquier nube)...")
            copia = _motor("respaldos").copiar_archivo_de_datos(viejos / ARCHIVO_DATOS, nuevos / ARCHIVO_DATOS)
            try:
                renombrar(viejos, raiz / f"Datos_movido_{sello}")
            except OSError:
                copia.unlink(missing_ok=True)          # el original sigue mandando: no dejar dos versiones
                raise
            if not borrar_carpeta(raiz / f"Datos_movido_{sello}", intentos=3):
                print("OneDrive todavía usa la copia anterior de tus datos: se borrará al abrir TALLY.")
            print("Datos movidos y verificados.")
    elif viejos.is_dir() and not any(viejos.iterdir()):
        try:
            viejos.rmdir()
        except OSError:
            pass
    return "\n\n".join(filter(None, [aviso, mover_respaldos(raiz / RESPALDOS, base / RESPALDOS)]))


def mover_respaldos(viejos, destino):
    """Mueve los respaldos .zip de la versión anterior. Si alguno no se puede mover, se queda donde estaba (no
    detiene la instalación). Devuelve un aviso, o ""."""
    if not viejos.is_dir() or viejos.resolve() == destino.resolve():
        return ""
    destino.mkdir(parents=True, exist_ok=True)
    pendientes = 0
    for archivo in sorted(viejos.iterdir()):
        final, n = destino / archivo.name, 2
        while final.exists():
            final, n = destino / f"{archivo.stem}_{n}{archivo.suffix}", n + 1
        try:
            shutil.move(str(archivo), str(final))
        except OSError as error:
            print(f"No se pudo mover el respaldo {archivo.name} ({error}).")
            pendientes += 1
    if pendientes:
        return f"{pendientes} respaldo(s) no se pudieron mover y siguen en {viejos}."
    borrar_carpeta(viejos, intentos=3)
    return ""


def puede_escribir(carpeta):
    """True si se puede crear y borrar un archivo en la carpeta (la crea si hace falta)."""
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / ".tally_prueba"
        prueba.write_text("ok")
        prueba.unlink()
        return True
    except OSError:
        return False


def carpeta_de_instalacion():
    """Escritorio\\TALLY; si Windows no deja escribir en el Escritorio, la carpeta del usuario."""
    raiz = escritorio() / NOMBRE_CARPETA
    if puede_escribir(raiz):
        return raiz
    respaldo = carpeta_de_datos()
    print(f"No se puede escribir en el Escritorio ({raiz}). Se instala en {respaldo}.")
    return respaldo


ESPERA_BLOQUEO = 1.0                              # segundos entre reintentos si Windows tiene archivos ocupados


def renombrar(origen, destino, intentos=15):
    """Renombra una carpeta reintentando unos segundos: justo después de copiar, el antivirus, el indexador de
    Windows u OneDrive suelen tener archivos abiertos un momento y Windows niega el cambio (PermissionError)."""
    for intento in range(intentos):
        try:
            origen.rename(destino)
            return
        except PermissionError:
            if intento == intentos - 1:
                raise
            if intento == 0:
                print(f"Windows tiene ocupada la carpeta {origen.name}; esperando a que la libere...")
            time.sleep(ESPERA_BLOQUEO)


def borrar_carpeta(ruta, intentos=10, espera=None):
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
            time.sleep(ESPERA_BLOQUEO if espera is None else espera)
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
        renombrar(destino, anterior)         # si TALLY o un archivo sigue abierto, al final: PermissionError
    try:
        shutil.copytree(ORIGEN, destino, ignore=NO_COPIAR)
    except BaseException:
        if destino.exists():
            borrar_carpeta(destino, intentos=3)
        if anterior.exists() and not destino.exists():
            renombrar(anterior, destino)     # algo falló: se deja la versión anterior como estaba
        raise
    if not borrar_carpeta(anterior):
        print(f"OneDrive todavía usa {anterior.name}: se borrará en la próxima actualización.")


def crear_estructura(raiz, base):
    for carpeta in (base / DATOS, base / RESPALDOS):
        carpeta.mkdir(parents=True, exist_ok=True)
    (raiz / "LEEME.txt").write_text(LEEME.format(datos=base), encoding="utf-8-sig")


def quitar_log_del_escritorio(raiz, base):
    """Hasta la 0.3.5 portal.log vivía en Escritorio\\TALLY y OneDrive lo resincronizaba mientras TALLY estaba
    abierto. Ahora vive junto a tus datos; el viejo se borra (si OneDrive no deja, no pasa nada)."""
    if raiz.resolve() == base.resolve():
        return
    try:
        (raiz / "portal.log").unlink(missing_ok=True)
    except OSError:
        pass


def portal_disponible(programa):
    return (programa / "portal" / "iniciar.py").exists()


def rutas_de_accesos(raiz):
    """Dónde va el acceso directo: en el Escritorio (si se puede escribir ahí) y dentro de la carpeta TALLY."""
    rutas = [raiz / f"{NOMBRE_ACCESO}.lnk"]
    escritorio_real = escritorio()
    if escritorio_real.resolve() != raiz.resolve() and puede_escribir(escritorio_real):
        rutas.insert(0, escritorio_real / f"{NOMBRE_ACCESO}.lnk")
    return rutas


def destino_del_acceso(programa):
    """Con pythonw (sin ventana negra) si existe; si no, el .bat."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if pythonw.exists():
        return pythonw, '"portal\\iniciar.py"'
    return programa / "EJECUTAR PORTAL.bat", ""


_CON_PYWIN32 = (
    "import sys, win32com.client\n"
    "shell = win32com.client.Dispatch('WScript.Shell')\n"
    "for ruta in sys.argv[6:]:\n"
    "    acceso = shell.CreateShortcut(ruta)\n"
    "    acceso.TargetPath, acceso.Arguments, acceso.WorkingDirectory = sys.argv[1], sys.argv[2], sys.argv[3]\n"
    "    if sys.argv[4]: acceso.IconLocation = sys.argv[4]\n"
    "    acceso.Description = sys.argv[5]\n"
    "    acceso.Save()\n"
)

_CON_POWERSHELL = (
    "foreach ($ruta in $env:TALLY_LNK.Split('|')) { "
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($ruta); "
    "$s.TargetPath = $env:TALLY_DESTINO; $s.Arguments = $env:TALLY_ARGUMENTOS; "
    "$s.WorkingDirectory = $env:TALLY_TRABAJO; $s.Description = $env:TALLY_DESCRIPCION; "
    "if ($env:TALLY_ICONO) { $s.IconLocation = $env:TALLY_ICONO }; $s.Save() }"
)


def crear_lnk(rutas, destino, argumentos, trabajo, icono, descripcion):
    """Crea accesos directos .lnk. Primero con pywin32, como el Portal de Honorarios (en otro proceso: pywin32
    se acaba de instalar y en este todavía no se puede importar); si falla, con PowerShell, que en algunas PC
    de trabajo está restringido. Al final comprueba que los archivos existan de verdad."""
    ejecutar([sys.executable, "-c", _CON_PYWIN32, str(destino), argumentos, str(trabajo), icono, descripcion,
              *map(str, rutas)])
    if all(ruta.exists() for ruta in rutas):
        return True
    print("Intentando crear el acceso directo con PowerShell...")
    entorno = {**os.environ, "TALLY_LNK": "|".join(map(str, rutas)), "TALLY_DESTINO": str(destino),
               "TALLY_ARGUMENTOS": argumentos, "TALLY_TRABAJO": str(trabajo), "TALLY_ICONO": icono,
               "TALLY_DESCRIPCION": descripcion}
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _CON_POWERSHELL],
                       env=entorno, stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"PowerShell no pudo ejecutarse: {error}")
    faltan = [ruta for ruta in rutas if not ruta.exists()]
    for ruta in faltan:
        print(f"No se pudo crear el acceso directo: {ruta}")
    return not faltan


def crear_accesos(raiz, programa, base=None):
    """Acceso directo «TALLY» en el Escritorio y en la carpeta TALLY, y «Mis datos de TALLY» en la carpeta."""
    destino, argumentos = destino_del_acceso(programa)
    icono = programa / "portal" / "recursos" / "tally.ico"
    icono = str(icono) if icono.exists() else ""
    print("Creando el acceso directo TALLY...")
    listo = crear_lnk(rutas_de_accesos(raiz), destino, argumentos, programa, icono, "Abre TALLY en el navegador")
    if base is not None and base.resolve() != raiz.resolve():
        crear_lnk([raiz / f"{NOMBRE_ACCESO_DATOS}.lnk"], base, "", base, "",
                  "Carpeta de tus datos y respaldos de TALLY (en esta PC)")
    return listo


def instalar(sin_librerias=False, sin_accesos=False):
    """Instala o actualiza, dejando todo registrado en TALLY\\instalacion.log."""
    raiz = carpeta_de_instalacion()
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
    base = carpeta_de_datos()
    print(f"Instalando en: {raiz}")
    print(f"Tus datos: {base}")

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
        respaldo = respaldar_datos(raiz, base)
    except Exception as error:                        # noqa: BLE001 - sin respaldo no se actualiza
        avisar(f"No se pudo respaldar tus datos antes de actualizar ({error}).\n\n"
               "No se cambió nada. Revisa que la carpeta Datos esté completa.", error=True)
        return 1
    if respaldo:
        print(f"Respaldo de tus datos antes de actualizar: {respaldo}")

    try:
        crear_estructura(raiz, base)
        copiar_programa(programa)
        quitar_log_del_escritorio(raiz, base)
    except PermissionError:
        avisar("Windows no dejó reemplazar la carpeta _Programa: algún archivo está abierto (TALLY, una "
               "ventana de esa carpeta u OneDrive sincronizando).\n\nCiérralos y vuelve a correr "
               "INSTALAR.bat. Tus datos no se modificaron.", error=True)
        return 1

    try:
        aviso_migracion = migrar_datos(raiz, base)
    except Exception as error:                        # noqa: BLE001 - el programa nuevo los sigue usando ahí
        aviso_migracion = (f"No se pudieron mover tus datos fuera del Escritorio ({error}). No se perdió nada: "
                           f"siguen en {raiz / DATOS} y TALLY los usa ahí. Para moverlos, cierra las ventanas de "
                           "esa carpeta, espera a que OneDrive termine de sincronizar y vuelve a correr "
                           "INSTALAR.bat.")
        print(aviso_migracion)

    hay_portal = portal_disponible(programa)
    accesos = sin_accesos or sys.platform != "win32" or not hay_portal or crear_accesos(raiz, programa, base)

    mensaje = (f"{'Actualización' if actualizacion else 'Instalación'} terminada.\n\nCarpeta: {raiz}"
               f"\nTus datos (solo en esta PC): {base}")
    if aviso_migracion:
        mensaje += f"\n\n{aviso_migracion}"
    if respaldo:
        mensaje += f"\n\nAntes de actualizar se respaldaron tus datos en:\n{respaldo.name}"
    if hay_portal:
        mensaje += f"\n\nPara abrir TALLY: doble clic en \"{NOMBRE_ACCESO}\" en tu Escritorio."
        if not accesos:
            mensaje += ("\n\nNo se pudo crear el acceso directo (el detalle está en instalacion.log). Mientras tanto, "
                        "abre TALLY con EJECUTAR PORTAL.bat dentro de _Programa.")
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
