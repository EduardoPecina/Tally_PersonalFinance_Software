#!/bin/bash
# Abre TALLY en tu navegador (servidor local en localhost:8765), por si la app TALLY no abre.
# Usa el Python de TALLY (~/TALLY/_Python, lo prepara INSTALAR.command); en desarrollo, .venv o python3.13.
cd "$(dirname "$0")" || exit 1
for py in "${TALLY_DATOS:-$HOME/TALLY}/_Python/bin/python" ".venv/bin/python" "$(command -v python3.13 2>/dev/null)"; do
    if [ -n "$py" ] && [ -x "$py" ]; then
        exec "$py" portal/iniciar.py
    fi
done
echo "No se encontró el Python de TALLY. Corre INSTALAR.command."
read -r -p "Presiona Enter para cerrar esta ventana..." _
exit 1
