#!/bin/bash
# Instalador de TALLY para Mac (con chip de Apple: M1 o más nuevo).
# Busca Python 3.13 (o lo instala desde python.org, con la contraseña de tu Mac), prepara el Python de TALLY en
# ~/TALLY/_Python (no toca el de tu Mac) y llama a instalador/instalar.py.
# Se puede correr las veces que sea: la primera vez instala y después actualiza sin tocar tus datos.
#
# La primera vez, macOS dice que no puede verificar al desarrollador: clic derecho en este archivo → Abrir
# (o Ajustes del Sistema → Privacidad y seguridad → «Abrir de todos modos»). Solo una vez.

cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
BITACORA="${TMPDIR:-/tmp}/tally_instalar_command.log"
export TALLY_BITACORA_BAT="$BITACORA"                    # el instalador la agrega a instalacion.log
echo "INSTALAR.command $(date '+%d/%m/%Y %H:%M:%S') · macOS $(sw_vers -productVersion 2>/dev/null)" > "$BITACORA"
DATOS="${TALLY_DATOS:-$HOME/TALLY}"
ENTORNO="$DATOS/_Python"
PYTHON_ORG="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
PY=""

terminar() {
    echo
    echo "$1"
    echo "$1" >> "$BITACORA"
    echo
    if [ -z "$TALLY_SIN_VENTANAS" ]; then
        read -r -p "Presiona Enter para cerrar esta ventana..." _
    fi
    exit "${2:-1}"
}

es_313() {
    [ -n "$1" ] && [ -x "$1" ] && "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)' \
        >/dev/null 2>&1
}

buscar_python() {
    for candidato in "$PYTHON_ORG" "$(command -v python3.13 2>/dev/null)" /opt/homebrew/bin/python3.13 \
            /usr/local/bin/python3.13; do
        if es_313 "$candidato"; then
            PY="$candidato"
            return 0
        fi
    done
    return 1
}

descargar_python() {
    # El instalador oficial más reciente de Python 3.13 para Mac, de python.org. Deja su ruta en PKG.
    PKG="${TMPDIR:-/tmp}/python-3.13-para-tally.pkg"
    rm -f "$PKG"
    versiones=$(curl -fsSL --max-time 60 https://www.python.org/ftp/python/ 2>>"$BITACORA" |
        grep -oE 'href="3\.13\.[0-9]+/"' | grep -oE '3\.13\.[0-9]+' | sort -t. -k3 -n -r | uniq)
    for version in $versiones; do
        url="https://www.python.org/ftp/python/$version/python-$version-macos11.pkg"
        if curl -fsIL --max-time 60 "$url" >/dev/null 2>&1; then
            echo "Descargando Python $version de python.org (unos 70 MB)..."
            echo "Descarga: $url" >> "$BITACORA"
            if curl -fL --progress-bar --max-time 1800 -o "$PKG" "$url"; then
                break
            fi
            rm -f "$PKG"
        fi
    done
    [ -s "$PKG" ] || return 1
    # Solo se instala si lo firmó la Python Software Foundation (y Apple lo reconoce).
    if ! pkgutil --check-signature "$PKG" 2>&1 | tee -a "$BITACORA" | grep -q "Python Software Foundation"; then
        echo "La descarga no está firmada por la Python Software Foundation: no se instala." | tee -a "$BITACORA"
        rm -f "$PKG"
        return 1
    fi
    return 0
}

instalar_python() {
    echo "No se encontró Python 3.13. Se instala el oficial, de python.org."
    echo "Python 3.13 no encontrado; se descarga de python.org" >> "$BITACORA"
    descargar_python || return 1
    echo "Tu Mac te pedirá tu contraseña para instalar Python (es la de tu usuario de la Mac)..."
    osascript -e "do shell script \"/usr/sbin/installer -pkg '$PKG' -target /\" with administrator privileges" \
        >>"$BITACORA" 2>&1
    resultado=$?
    if [ $resultado -ne 0 ]; then
        # Sin permiso de administrador (o se canceló): se abre el instalador normal de Python.
        echo "Se abrirá el instalador de Python: síguelo y luego vuelve a abrir INSTALAR.command."
        open "$PKG"
        return 1
    fi
    rm -f "$PKG"
    return 0
}

# Prueba de la descarga (la usan las pruebas automáticas en una Mac de GitHub): descarga y verifica, sin instalar.
if [ "$1" = "--probar-descarga" ]; then
    descargar_python && echo "Descarga verificada: $PKG" && rm -f "$PKG" && exit 0
    exit 1
fi

if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" != "1" ]; then
    terminar "Esta Mac tiene procesador Intel. Por ahora TALLY funciona en Mac con chip de Apple (M1 o más nuevo):
una de sus librerías de seguridad ya no se publica para Intel. No se cambió nada."
fi

echo "Buscando Python 3.13..."
if ! buscar_python; then
    instalar_python
    buscar_python || terminar "No se pudo instalar Python 3.13. Cuando termine de instalarse, vuelve a abrir
INSTALAR.command. (Detalle en $BITACORA)"
fi
echo "Python encontrado: $PY"
echo "Python: $PY" >> "$BITACORA"

# El Python de TALLY: un entorno propio, para no tocar el Python de tu Mac (ni el de Homebrew).
mkdir -p "$DATOS" || terminar "No se pudo crear la carpeta $DATOS."
if ! es_313 "$ENTORNO/bin/python"; then
    echo "Preparando el Python de TALLY (solo la primera vez)..."
    rm -rf "$ENTORNO"
    arch -arm64 "$PY" -m venv "$ENTORNO" >>"$BITACORA" 2>&1 ||
        terminar "No se pudo preparar el Python de TALLY. (Detalle en $BITACORA)"
fi
echo "Entorno: $ENTORNO" >> "$BITACORA"

arch -arm64 "$ENTORNO/bin/python" instalador/instalar.py "$@" ||
    terminar "La instalación no se completó. Revisa el archivo instalacion.log de la carpeta $DATOS."
exit 0
